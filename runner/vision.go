package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"os/exec"
)

// vision_client habla con el proceso Python (vision/vision_server.py): una línea JSON por petición y respuesta.
type vision_client struct {
	cmd    *exec.Cmd
	stdin  io.WriteCloser
	stdout *bufio.Scanner
}

func start_vision(python_path, script_path string) (*vision_client, error) {
	cmd := exec.Command(python_path, script_path)
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return nil, err
	}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return nil, err
	}
	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("no se pudo arrancar la visión: %w", err)
	}
	scanner := bufio.NewScanner(stdout)
	scanner.Buffer(make([]byte, 1024*1024), 16*1024*1024)
	client := &vision_client{cmd: cmd, stdin: stdin, stdout: scanner}
	var pong map[string]any
	if err := client.call(map[string]any{"cmd": "ping"}, &pong); err != nil {
		return nil, err
	}
	return client, nil
}

// call envía una petición y decodifica la respuesta. Un {"ok": false} de Python se devuelve como error.
func (v *vision_client) call(request any, response any) error {
	line, err := json.Marshal(request)
	if err != nil {
		return err
	}
	if _, err := v.stdin.Write(append(line, '\n')); err != nil {
		return fmt.Errorf("visión no disponible: %w", err)
	}
	if !v.stdout.Scan() {
		return fmt.Errorf("la visión terminó sin responder")
	}
	raw := v.stdout.Bytes()
	var status struct {
		Ok    bool   `json:"ok"`
		Error string `json:"error"`
	}
	if err := json.Unmarshal(raw, &status); err != nil {
		return fmt.Errorf("respuesta de visión no válida: %w", err)
	}
	if !status.Ok {
		return fmt.Errorf("visión: %s", status.Error)
	}
	return json.Unmarshal(raw, response)
}

func (v *vision_client) close() {
	v.stdin.Close()
	v.cmd.Wait()
}

type region_reading struct {
	Text       string  `json:"text"`
	Cents      *int64  `json:"cents"` // nil = ilegible (nunca se interpreta como cero)
	HasEuro    bool    `json:"has_euro"`
	Confidence float64 `json:"confidence"`
	Error      *string `json:"error"`
}

// read lee importes en las regiones; con text_hsv solo se lee el texto de ese color (y se exige unanimidad).
func (v *vision_client) read(image_path string, regions map[string][4]float64, text_hsv *[2][3]int) (map[string]region_reading, error) {
	var response struct {
		Readings map[string]region_reading `json:"readings"`
	}
	request := map[string]any{"cmd": "read", "image": image_path, "regions": regions}
	if text_hsv != nil {
		request["text_hsv"] = text_hsv
	}
	err := v.call(request, &response)
	return response.Readings, err
}

func (v *vision_client) motion(image_a, image_b string, region [4]float64) (float64, error) {
	var response struct {
		ChangedFraction float64 `json:"changed_fraction"`
	}
	err := v.call(map[string]any{"cmd": "motion", "image_a": image_a, "image_b": image_b, "region": region}, &response)
	return response.ChangedFraction, err
}

// find_text busca los patrones en toda la captura o, si se indica, solo en una región.
func (v *vision_client) find_text(image_path string, patterns []string, region *[4]float64) (bool, string, error) {
	var response struct {
		Found bool    `json:"found"`
		Match *string `json:"match"`
	}
	request := map[string]any{"cmd": "find_text", "image": image_path, "patterns": patterns}
	if region != nil {
		request["region"] = region
	}
	err := v.call(request, &response)
	match := ""
	if response.Match != nil {
		match = *response.Match
	}
	return response.Found, match, err
}

type location struct {
	Found bool     `json:"found"`
	Score float64  `json:"score"`
	X     *float64 `json:"x"`
	Y     *float64 `json:"y"`
}

func (v *vision_client) locate(image_path, template_path string, reference_width int, threshold float64) (location, error) {
	var response location
	err := v.call(map[string]any{"cmd": "locate", "image": image_path, "template": template_path,
		"reference_width": reference_width, "threshold": threshold}, &response)
	return response, err
}
