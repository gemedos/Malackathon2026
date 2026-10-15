"""El botón «Jugar» elegido es el de la tarjeta del juego, no el primero del DOM (p. ej. con el buscador abierto)."""

from __future__ import annotations

import pytest

from validator.config import load_market, load_selectors
from validator.pages.provider_page import ProviderPage

pytestmark = pytest.mark.browser

HTML = """
<div style="position:absolute;left:0;top:0"><button id="a" onclick="window.clicked='a'">Jugar</button></div>
<div id="card" style="position:absolute;left:600px;top:400px;width:120px;height:120px">
  <button id="b" style="position:absolute;left:10px;top:50px" onclick="window.clicked='b'">Jugar</button></div>
"""


def test_nearest_button_to_card() -> None:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Chromium no disponible: {type(exc).__name__}")
        page = browser.new_page()
        page.set_content(HTML)
        market, selectors = load_market("es"), load_selectors("es")
        provider_page = ProviderPage(page, market, selectors)
        button = provider_page._find_label_button(selectors.game_launch.real_play, market.real_play_labels, 2000,
                                                  near=page.locator("#card"))
        assert button is not None
        button.click()
        assert page.evaluate("window.clicked") == "b"
        browser.close()
