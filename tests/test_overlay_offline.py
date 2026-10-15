"""Red de seguridad genérica: un diálogo desconocido que tapa el juego se cierra solo si hay un botón inocuo."""

from __future__ import annotations

import pytest

from validator.config import load_market, load_selectors
from validator.pages.game_page import GamePage

pytestmark = pytest.mark.browser

SAFE = """<div role="dialog" style="position:fixed;inset:0;background:#fff"><p>Novedades</p>
<button onclick="window.deposit=true">Depositar</button>
<button onclick="this.parentNode.remove();window.dismissed=true">Entendido</button></div>"""
UNSAFE_ONLY = """<div role="dialog" style="position:fixed;inset:0;background:#fff"><p>Promo</p>
<button onclick="window.deposit=true">Depositar ahora</button></div>"""


class _Evidence:
    def screenshot(self, page, name):
        return name

    def relative(self, path):
        return path


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        try:
            b = pw.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Chromium no disponible: {type(exc).__name__}")
        yield b
        b.close()


def _game_page(page):
    return GamePage(page, load_market("es"), load_selectors("es"), _Evidence())  # type: ignore[arg-type]


def test_unknown_dialog_is_dismissed_with_safe_button(browser) -> None:
    page = browser.new_page()
    page.set_content(SAFE)
    assert _game_page(page).handle_pregame() is True
    assert page.evaluate("window.dismissed") is True
    assert page.evaluate("window.deposit") is None


def test_dialog_with_only_unsafe_buttons_is_left_alone(browser) -> None:
    page = browser.new_page()
    page.set_content(UNSAFE_ONLY)
    assert _game_page(page).handle_pregame() is False
    assert page.evaluate("window.deposit") is None
