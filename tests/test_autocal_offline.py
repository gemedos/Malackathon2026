"""Calibración automática sobre una captura real (HUD con la etiqueta encima del importe y apuesta sin decimales)."""

from __future__ import annotations

from pathlib import Path

import cv2

from validator.config import load_market
from validator.game import autocal
from validator.game.calibration import build_profile, load_calibration

FRAME = Path(__file__).parent / "data" / "hud_bottom_amounts_above.png"


class FakeDriver:
    def __init__(self, frame):
        self.frame = frame
        self.clicks = []

    def capture(self):
        return self.frame

    def wait(self, ms):
        pass

    def click(self, point, size):
        self.clicks.append(point)


class FakeSession:
    provider, game, pregame = "Proveedor X", "Juego Y", None


def test_auto_calibration_writes_a_loadable_yaml(tmp_path, monkeypatch):
    monkeypatch.setattr(autocal, "OCR_LANGS", "eng")          # el sandbox de pruebas solo tiene inglés
    driver = FakeDriver(cv2.imread(str(FRAME)))
    loaded = autocal.auto_calibrate(FakeSession(), driver, tmp_path)
    cal = loaded.calibration
    assert cal.calibrated is True and loaded.path.parent == tmp_path / "proveedor-x"
    assert (loaded.path.parent / cal.spin_template).is_file()
    profile = build_profile(cal, load_market("es"), (760, 428))
    # El saldo y la apuesta de la captura están a la derecha y a la izquierda del botón central, abajo.
    balance, wager = profile.regions["balance"], profile.regions["wager"]
    assert balance.x > 600 and wager.x < 200 and balance.y > 360 and wager.y > 360
    assert load_calibration("Proveedor X", "Juego Y", tmp_path).path == loaded.path
