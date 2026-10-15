"""Piezas de la integración que no necesitan navegador: calibración normalizada, checks e informe."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from validator.checks import check_name
from validator.config import load_market
from validator.game.calibration import GameCalibration, build_profile, skeleton, to_pixels
from validator.report import load_groups, render_html, render_summary, render_text
from vision_engine.errors import CalibrationError

REGIONS = {name: [0.1, 0.1, 0.2, 0.2] for name in
           ("spin_search", "reels", "balance", "wager", "payout", "currency", "message")}


def calibration(**changes) -> GameCalibration:
    data = {"provider": "Pragmatic Play", "game": "Sweet Bonanza", "reference_size": [800, 450],
            "spin_template": "spin.png", "regions": REGIONS, **changes}
    return GameCalibration.model_validate(data)


def test_regions_scale_with_iframe_size():
    assert to_pixels((0.1, 0.2, 0.5, 0.5), (800, 450)) == [80, 90, 400, 225]
    assert to_pixels((0.1, 0.2, 0.5, 0.5), (1600, 900)) == [160, 180, 800, 450]
    assert to_pixels((0.9, 0.9, 0.2, 0.2), (100, 100)) == [90, 90, 10, 10]   # recortada al borde


def test_profile_uses_market_config_and_scales_templates():
    market = load_market("es")
    profile = build_profile(calibration(template_scales=[1.0]), market, (1600, 900))
    assert (profile.market, profile.expected_currency, profile.decimal_separator) == ("es", "EUR", ",")
    assert profile.language == "es" and profile.template_scales == (2.0,)
    assert profile.calibrated is False


def test_different_aspect_ratio_is_rejected():
    with pytest.raises(CalibrationError):
        build_profile(calibration(), load_market("es"), (800, 800))


def test_invalid_calibration():
    with pytest.raises(ValidationError):
        calibration(regions={**REGIONS, "reels": [0.8, 0.1, 0.5, 0.2]})   # se sale del iframe
    with pytest.raises(ValidationError):
        calibration(regions={k: v for k, v in REGIONS.items() if k != "payout"})


def test_skeleton_is_valid_but_not_calibrated():
    import yaml
    data = yaml.safe_load(skeleton("Pragmatic Play", "Sweet Bonanza", (800, 450)))
    assert GameCalibration.model_validate(data).calibrated is False


def test_check_names_follow_market():
    market = load_market("es")
    assert check_name("currency", market)[0] == "Moneda = EUR"
    assert check_name("message_language", market)[0] == "Idioma = español"


def test_report_final_results(tmp_path):
    items = [
        {"scenario": "spin_completado", "market": "es", "provider": "P", "game": "G", "check": "Spin iniciado",
         "status": "pass", "detail": "ok", "evidence": None, "expected": "", "observed": ""},
        {"scenario": "spin_completado", "market": "es", "provider": "P", "game": "G", "check": "Saldo Betsson reconcilia",
         "status": "inconclusive", "detail": "no visible", "evidence": None, "expected": "", "observed": ""},
        {"scenario": "saldo_insuficiente", "market": "es", "provider": "P", "game": "G", "check": "Spin rechazado",
         "status": "fail", "detail": "cargo", "evidence": "artifacts/es/x.png", "expected": "", "observed": ""},
    ]
    path = tmp_path / "results.json"
    path.write_text(json.dumps(items), encoding="utf-8")
    groups = load_groups(path)
    assert [g.final for g in groups] == ["INCONCLUSIVE", "FAIL"]
    market = load_market("es")
    text = render_text(groups, market)
    assert "Market: www.betsson.es" in text and "FINAL RESULT: FAIL" in text
    assert "**FAIL**" in render_summary(groups, market)
    assert "<img" in render_html(groups, market, tmp_path)
