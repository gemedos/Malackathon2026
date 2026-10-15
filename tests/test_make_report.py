"""scripts/make_report.py: un criterio de negocio no se aprueba si falta o falla algún check que lo respalda."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "make_report.py"
spec = importlib.util.spec_from_file_location("make_report", SCRIPT)
make_report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(make_report)


def _check(scenario, name, status="pass", game="Juego Y"):
    return {"scenario": scenario, "market": "es", "provider": "Proveedor X", "game": game, "check": name,
            "status": status, "detail": "d", "evidence": None, "expected": "", "observed": ""}


def _all_checks(scenario):
    names = [n for _, ns in make_report.SCENARIOS[scenario]["assertions"] for n in ns]
    return [_check(scenario, n) for n in names]


def test_missing_check_is_not_run_never_pass():
    checks = [c for c in _all_checks("spin_completado") if c["check"] != "Saldo Betsson reconcilia"]
    rows = make_report.evaluate(checks, make_report.SCENARIOS["spin_completado"]["assertions"])
    assert rows[-1]["status"] == "not_run" and "Sin ejecutar" in rows[-1]["detail"]
    assert all(r["status"] == "pass" for r in rows[:-1])


def test_worst_status_wins():
    checks = _all_checks("saldo_insuficiente")
    checks[0]["status"] = "fail"
    rows = make_report.evaluate(checks, make_report.SCENARIOS["saldo_insuficiente"]["assertions"])
    assert rows[0]["status"] == "fail"


def test_report_uses_provider_and_game_from_results(tmp_path):
    results = tmp_path / "results.json"
    results.write_text(json.dumps(_all_checks("spin_completado") + _all_checks("saldo_insuficiente")), encoding="utf-8")
    out = tmp_path / "r.html"
    assert make_report.main([str(results), str(out)]) == 0
    html = out.read_text(encoding="utf-8")
    assert "Proveedor X / Juego Y" in html and "Pragmatic" not in html
    assert html.count("APROBADO") >= 2
