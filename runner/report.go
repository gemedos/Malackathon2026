package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

const (
	PASS         = "PASS"
	FAIL         = "FAIL"
	INCONCLUSIVE = "INCONCLUSIVE"
	ERROR        = "ERROR"
)

type check struct {
	Name     string   `json:"name"`
	Status   string   `json:"status"`
	Detail   string   `json:"detail"`
	Evidence []string `json:"evidence"`
}

type case_result struct {
	ID       string  `json:"id"`
	Market   string  `json:"market"`
	Scenario string  `json:"scenario"`
	Game     string  `json:"game"`
	Status   string  `json:"status"`
	Checks   []check `json:"checks"`
}

// verdict: sin evidencia suficiente el resultado es INCONCLUSIVE, nunca PASS.
func verdict(name string, passed bool, evidence_complete bool, detail string, evidence []string) check {
	switch {
	case !evidence_complete:
		return check{name, INCONCLUSIVE, detail, evidence}
	case passed:
		return check{name, PASS, detail, evidence}
	default:
		return check{name, FAIL, detail, evidence}
	}
}

func error_check(name string, err error) check {
	return check{name, ERROR, err.Error(), nil}
}

// overall: PASS solo si todas las comprobaciones pasan; un FAIL pesa más que la falta de evidencia.
func overall(checks []check) string {
	result := PASS
	for _, c := range checks {
		switch c.Status {
		case FAIL:
			return FAIL
		case ERROR:
			result = ERROR
		case INCONCLUSIVE:
			if result == PASS {
				result = INCONCLUSIVE
			}
		}
	}
	if len(checks) == 0 {
		return ERROR
	}
	return result
}

func write_report(dir string, results []case_result) error {
	raw, err := json.MarshalIndent(results, "", "  ")
	if err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(dir, "report.json"), raw, 0o644); err != nil {
		return err
	}
	var md strings.Builder
	md.WriteString("# Informe de validación\n\n| Caso | Mercado | Escenario | Juego | Resultado |\n|---|---|---|---|---|\n")
	for _, r := range results {
		fmt.Fprintf(&md, "| %s | %s | %s | %s | **%s** |\n", r.ID, r.Market, r.Scenario, r.Game, r.Status)
	}
	for _, r := range results {
		fmt.Fprintf(&md, "\n## %s — %s (%s)\n\n| Comprobación | Resultado | Detalle | Evidencia |\n|---|---|---|---|\n", r.ID, r.Scenario, r.Status)
		for _, c := range r.Checks {
			links := []string{}
			for _, path := range c.Evidence {
				relative, _ := filepath.Rel(dir, path)
				links = append(links, fmt.Sprintf("[%s](%s)", filepath.Base(path), relative))
			}
			fmt.Fprintf(&md, "| %s | %s | %s | %s |\n", c.Name, c.Status, strings.ReplaceAll(c.Detail, "|", "/"), strings.Join(links, " "))
		}
	}
	return os.WriteFile(filepath.Join(dir, "report.md"), []byte(md.String()), 0o644)
}
