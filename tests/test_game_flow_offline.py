"""Flujo completo Playwright -> visión -> veredicto sobre una tragaperras FALSA en Chromium local.

No abre betsson.es ni usa credenciales: verifica que la integración (capturas del iframe, clic en el
Spin, OCR, saldo de cabecera por DOM+OCR y reglas de evaluación) funciona de extremo a extremo.
Necesita Chromium de Playwright y Tesseract (spa).
"""

from __future__ import annotations

import shutil

import cv2
import pytest
import yaml

from fake_slot import BASE, REGIONS, SIZE, SPIN_BOX, handle_route
from validator.browser import VIEWPORT
from validator.config import load_market, load_selectors
from validator.game.calibration import calibration_path
from validator.game.driver import GameDriver
from validator.game.scenarios import INSUFFICIENT, SPIN, run_scenario
from validator.pages.game_page import GameSession
from vision_engine import Verdict

pytestmark = pytest.mark.browser
PROVIDER, GAME = "Fake Studio", "Fake Slot"


@pytest.fixture(scope="module")
def fake_browser():
    if shutil.which("tesseract") is None:
        pytest.skip("Tesseract no instalado")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Chromium de Playwright no disponible: {type(exc).__name__}")
        yield browser
        browser.close()


@pytest.fixture(scope="module")
def market():
    real = load_market("es")   # mercado real (frases, idioma, moneda) con esperas más cortas
    vision = real.vision.model_copy(update={"balance_poll_interval_s": 0.5, "balance_min_wait_s": 1.5,
                                            "balance_poll_timeout_s": 10})
    return real.model_copy(update={"vision": vision})


def _open(fake_browser, balance: str):
    context = fake_browser.new_context(viewport=VIEWPORT, device_scale_factor=1, locale="es-ES")
    context.route("**/*", handle_route)   # todo lo que no sea el juego falso se aborta
    page = context.new_page()
    page.goto(f"{BASE}/?balance={balance}")
    iframe = page.locator("#game")
    iframe.wait_for(state="visible")
    page.wait_for_timeout(800)
    return context, GameSession(page, iframe, iframe.bounding_box(), PROVIDER, GAME)


def _calibrate(session: GameSession, games_dir) -> None:
    """Calibración como la haría una persona: plantilla recortada de una captura real del juego."""
    frame = GameDriver(session).capture()
    path = calibration_path(PROVIDER, GAME, games_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    x, y, w, h = SPIN_BOX
    cv2.imwrite(str(path.parent / "spin.png"), frame[y:y + h, x:x + w])
    width, height = SIZE
    path.write_text(yaml.safe_dump({
        "provider": PROVIDER, "game": GAME, "calibrated": True, "reference_size": list(SIZE),
        "spin_template": "spin.png", "template_scales": [1.0],
        "regions": {k: [r[0] / width, r[1] / height, r[2] / width, r[3] / height] for k, r in REGIONS.items()},
        "insufficient_window_seconds": 3.0,
        "motion": {"quiet_seconds": 0.8, "timeout_seconds": 15.0},
    }), encoding="utf-8")


@pytest.mark.parametrize("kind, balance", [(SPIN, "10.00"), (INSUFFICIENT, "0.50")])
def test_full_flow_on_fake_slot(kind, balance, fake_browser, market, tmp_path):
    context, session = _open(fake_browser, balance)
    try:
        _calibrate(session, tmp_path / "games")
        outcome = run_scenario(kind, session, context, market, load_selectors("es"), tmp_path / "evidence",
                               games_dir=tmp_path / "games")
    finally:
        context.close()
    report = outcome.report
    details = "\n".join(f"{a.verdict.value:12} {a.name}: {a.detail}" for a in report.assertions)
    assert report.verdict is Verdict.PASS, details
    assert {"before", "after", "strip"} <= set(outcome.images)
    if kind == SPIN:
        assert report.observed == {"initial_balance": "10.00", "wager": "1.00", "payout": "5.00",
                                   "final_balance": "14.00", "betsson_before": "10.00", "betsson_after": "14.00"}
    else:
        assert report.observed["betsson_before"] == report.observed["betsson_after"] == "0.50"
