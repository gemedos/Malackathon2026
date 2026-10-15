"""Calibración por proveedor (config/games/<proveedor>/_default.yaml) y modo de giro 'ready'."""

from __future__ import annotations

import pytest

from validator.config import load_market
from validator.game.calibration import CalibrationMissingError, build_profile, load_calibration


def test_game_without_own_yaml_uses_provider_default():
    loaded = load_calibration("Pragmatic Play", "Juego Que No Existe")
    assert loaded.path.name == "_default.yaml"
    assert loaded.calibration.settle == "ready"
    assert loaded.splash_template() is not None


def test_provider_without_default_is_not_calibrated():
    with pytest.raises(CalibrationMissingError):
        load_calibration("Proveedor Inventado", "Cualquiera")


def test_profile_carries_ready_settle_and_idle_patterns():
    loaded = load_calibration("Pragmatic Play", "Bubble Up")
    profile = build_profile(loaded.calibration, load_market("es"), (1280, 720))
    assert profile.settle == "ready"
    assert any(p.search("haga su apuesta") for p in profile.idle_patterns)
