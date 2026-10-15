"""Clic único en Spin (scenarios._click_spin): espera a un frame previo limpio sin reintentar el giro."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from validator.game.scenarios import SPIN_EXTRA_FRAMES, _click_spin
from vision_engine import SpinNotFoundError


class FakeRecorder:
    """Spin visible solo a partir del frame `visible_from` (los anteriores los tapa una animación)."""

    def __init__(self, visible_from: int) -> None:
        self.frames, self.visible_from, self.clicked = 1, visible_from, False

    def observe_before(self, frame, timestamp) -> None:
        assert not self.clicked
        self.frames += 1

    def register_click(self, timestamp):
        if self.frames < self.visible_from:
            raise SpinNotFoundError("Spin no identificado en el último frame previo; no clicar (INCONCLUSIVE)")
        self.clicked = True
        return SimpleNamespace(point=(596.0, 387.0))


class FakeDriver:
    def __init__(self) -> None:
        self.clicks: list = []

    def wait(self, ms) -> None:
        pass

    def capture(self) -> np.ndarray:
        return np.zeros((433, 770, 3), np.uint8)

    def click(self, point, frame_size):
        self.clicks.append(point)
        return point


def test_clic_directo_si_el_spin_se_ve() -> None:
    driver, notes = FakeDriver(), []
    assert _click_spin(FakeRecorder(visible_from=1), driver, (770, 433), notes)
    assert driver.clicks == [(596.0, 387.0)] and not notes


def test_espera_un_frame_limpio_y_clica_una_sola_vez() -> None:
    driver, recorder = FakeDriver(), FakeRecorder(visible_from=3)   # dos frames con destello
    assert _click_spin(recorder, driver, (770, 433), [])
    assert len(driver.clicks) == 1 and recorder.frames == 3


def test_sin_spin_visible_no_clica() -> None:
    driver, notes = FakeDriver(), []
    assert not _click_spin(FakeRecorder(visible_from=99), driver, (770, 433), notes)
    assert driver.clicks == [] and len(notes) == 1
    assert SPIN_EXTRA_FRAMES >= 3
