"""Bajada a la apuesta mínima (scenarios._lower_to_min_bet) con un juego simulado: sin navegador ni OCR real."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from validator.game import scenarios
from validator.game.calibration import MinBet
from validator.game.scenarios import _lower_to_min_bet
from vision_engine import Verdict

FRAME = (770, 433)
CFG = MinBet(point=(0.695, 0.902), max_clicks=10, settle_ms=100)


class FakeGame:
    """Juego con niveles de apuesta; «−» baja un nivel. `ocr` permite simular lecturas fallidas."""

    def __init__(self, levels: list[str], start: int, *, ocr=None, step: int = -1) -> None:
        self.levels, self.index, self.step, self.clicks = levels, start, step, 0
        self.ocr = ocr or (lambda value, n: value)

    # GameDriver
    def capture(self) -> np.ndarray:
        return np.zeros((FRAME[1], FRAME[0], 3), np.uint8)

    def wait(self, ms: float) -> None:
        pass

    def click(self, point, frame_size):
        self.clicks += 1
        self.index = min(max(self.index + self.step, 0), len(self.levels) - 1)
        return point

    # VisionEngine
    def read_field(self, frame, field, sample):
        assert field == "wager"
        return SimpleNamespace(value=self.ocr(self.levels[self.index], self.clicks))


LEVELS = ["0.20", "0.40", "0.60", "0.80", "1.00", "1.20", "1.40", "1.60", "1.80", "2.00"]


def _run(game: FakeGame, cfg: MinBet = CFG):
    return _lower_to_min_bet(game, game, cfg, FRAME)


def test_baja_desde_2_euros_hasta_la_minima() -> None:
    game = FakeGame(LEVELS, start=9)
    result = _run(game, MinBet(point=CFG.point, max_clicks=20, settle_ms=100))
    assert result.verdict is Verdict.PASS
    assert "0.20" in result.detail and "9 bajadas" in result.detail
    assert game.clicks == 11          # 9 bajadas + 2 confirmaciones sin cambio


def test_ya_en_la_minima() -> None:
    result = _run(FakeGame(LEVELS, start=0))
    assert result.verdict is Verdict.PASS and "0 bajadas" in result.detail


def test_ocr_fallido_no_es_un_valor() -> None:
    game = FakeGame(LEVELS, start=3, ocr=lambda value, n: None if n == 2 else value)
    assert _run(game).verdict is Verdict.INCONCLUSIVE


def test_punto_equivocado_que_sube_la_apuesta() -> None:
    result = _run(FakeGame(LEVELS, start=3, step=+1))
    assert result.verdict is Verdict.INCONCLUSIVE and "subió" in result.detail


def test_cierra_el_panel_de_apuesta_si_tapa_el_spin(monkeypatch) -> None:
    """En la mínima, «−» abre el panel de apuesta (tapa el Spin): se cierra con «×» y se verifica viendo el Spin."""
    game = FakeGame(LEVELS, start=2)
    panel = {"open": True}
    clicks_before_close: list[int] = []

    def fake_click(point, frame_size):
        if point[1] < FRAME[1] * 0.5:      # «×» del panel (arriba); «−» está abajo
            clicks_before_close.append(game.clicks)
            panel["open"] = False
            return point
        return FakeGame.click(game, point, frame_size)

    monkeypatch.setattr(game, "click", fake_click)
    monkeypatch.setattr(scenarios, "_spin_visible", lambda driver, engine, template: not panel["open"])
    cfg = MinBet(point=CFG.point, close_point=(0.874, 0.157), max_clicks=10, settle_ms=100)
    result = _lower_to_min_bet(game, game, cfg, FRAME, spin_template=object())
    assert result.verdict is Verdict.PASS and not panel["open"]
    assert len(clicks_before_close) == 1


def test_panel_que_no_se_cierra_no_es_pass(monkeypatch) -> None:
    monkeypatch.setattr(scenarios, "_spin_visible", lambda driver, engine, template: False)
    cfg = MinBet(point=CFG.point, close_point=(0.874, 0.157), max_clicks=10, settle_ms=100)
    result = _lower_to_min_bet(FakeGame(LEVELS, start=0), FakeGame(LEVELS, start=0), cfg, FRAME, spin_template=object())
    assert result.verdict is Verdict.INCONCLUSIVE and "panel" in result.detail


def test_sin_llegar_a_la_minima_en_el_limite_de_clics() -> None:
    result = _run(FakeGame(LEVELS, start=9), MinBet(point=CFG.point, max_clicks=3, settle_ms=100))
    assert result.verdict is Verdict.INCONCLUSIVE and "seguía bajando" in result.detail
