package main

import (
	"os/exec"
	"path/filepath"
	"testing"
)

// Prueba sintética del contrato Go↔Python: imágenes generadas, no capturas reales del juego.
const MAKE_IMAGES = `
import sys, cv2, numpy
out = sys.argv[1]
def canvas(): return numpy.zeros((300, 600, 3), numpy.uint8)
a = canvas(); cv2.putText(a, "12,34", (40, 80), cv2.FONT_HERSHEY_DUPLEX, 2, (255,255,255), 4)
cv2.putText(a, "SALDO INSUFICIENTE", (40, 220), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255,255,255), 3)
cv2.imwrite(out + "/a.png", a)
b = a.copy(); cv2.rectangle(b, (300, 100), (600, 300), (0, 200, 0), -1)
cv2.imwrite(out + "/b.png", b)
`

func TestVisionContract(t *testing.T) {
	dir := t.TempDir()
	python := "../vision/.venv/bin/python"
	if out, err := exec.Command(python, "-c", MAKE_IMAGES, dir).CombinedOutput(); err != nil {
		t.Fatalf("no se generaron las imágenes: %v %s", err, out)
	}
	vision, err := start_vision(python, "../vision/vision_server.py")
	if err != nil {
		t.Fatal(err)
	}
	defer vision.close()
	a, b := filepath.Join(dir, "a.png"), filepath.Join(dir, "b.png")

	readings, err := vision.read(a, map[string][4]float64{"amount": {0, 0, 0.5, 0.4}, "nothing": {0.6, 0, 0.4, 0.3}}, nil)
	if err != nil {
		t.Fatal(err)
	}
	if readings["amount"].Cents == nil || *readings["amount"].Cents != 1234 {
		t.Errorf("importe esperado 1234 céntimos, leído %+v", readings["amount"])
	}
	if readings["nothing"].Cents != nil {
		t.Errorf("una región vacía debe ser desconocida, no %d", *readings["nothing"].Cents)
	}
	if changed, _ := vision.motion(a, a, [4]float64{0, 0, 1, 1}, "pixel", [2]int{}); changed != 0 {
		t.Errorf("misma imagen debe dar 0 de cambio, dio %f", changed)
	}
	if changed, _ := vision.motion(a, b, [4]float64{0, 0, 1, 1}, "pixel", [2]int{}); changed < MOTION_THRESHOLDS["pixel"].started {
		t.Errorf("imágenes distintas deben superar el umbral, dio %f", changed)
	}
	if found, match, _ := vision.find_text(a, []string{"saldo insuficiente"}, nil); !found {
		t.Errorf("no encontró el mensaje (match %q)", match)
	}
	if _, err := vision.read(filepath.Join(dir, "missing.png"), map[string][4]float64{"x": {0, 0, 1, 1}}, nil); err == nil {
		t.Error("una imagen inexistente debe dar error")
	}
}

func TestOverallNeverPassWithoutEvidence(t *testing.T) {
	if got := overall([]check{{Status: PASS}, {Status: INCONCLUSIVE}}); got != INCONCLUSIVE {
		t.Errorf("esperado INCONCLUSIVE, obtenido %s", got)
	}
	if got := overall(nil); got != ERROR {
		t.Errorf("sin comprobaciones debe ser ERROR, obtenido %s", got)
	}
	if got := verdict("x", true, false, "", nil).Status; got != INCONCLUSIVE {
		t.Errorf("sin evidencia completa no puede ser PASS, obtenido %s", got)
	}
}

func TestParseBetssonBalance(t *testing.T) {
	cases := map[string]int64{"53,00 €": 5300, "1.234,56 €": 123456, "€0,20": 20}
	for text, want := range cases {
		match := EURO_AMOUNT.FindStringSubmatch(text)
		if match == nil {
			t.Errorf("%q no reconocido", text)
			continue
		}
		if got, _ := parse_spanish_euros(match); got != want {
			t.Errorf("%q: esperado %d, obtenido %d", text, want, got)
		}
	}
}
