"""Pantallas previas (aviso de sesión, límites, panel de torneos) sobre una página falsa con shadow DOM.

Reproduce el caso real: el aviso modal tapa el panel de torneos, así que el aviso debe resolverse primero."""

from __future__ import annotations

import pytest

from validator.config import load_market, load_selectors
from validator.pages.game_page import GamePage

pytestmark = pytest.mark.browser

HTML = """
<body style="margin:0">
<div id="tour" style="position:fixed;top:0;right:0;width:300px;height:100px"><span>Cerrar y no volver a mostrar</span></div>
<fds-dialog id="dlg" style="position:fixed;inset:0;background:rgba(0,0,0,.5)"></fds-dialog>
<script>
const dlg = document.getElementById('dlg');
const root = dlg.attachShadow({mode: 'open'});
root.innerHTML = '<div style="position:absolute;top:200px;left:300px;background:#fff;padding:20px">' +
  '<p>Hace menos de 60 mins. que finalizaste tu sesión de juego.</p>' +
  '<button id="b">Iniciar sesión</button></div>';
root.getElementById('b').onclick = () => { dlg.remove(); window.noticeDone = true; };
document.querySelector('#tour span').onclick = () => { document.getElementById('tour').remove(); window.tourDone = true; };
</script></body>
"""


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


def test_notice_is_closed_before_tournament_panel(browser) -> None:
    page = browser.new_page()
    page.set_content(HTML)
    game_page = GamePage(page, load_market("es"), load_selectors("es"), object())  # type: ignore[arg-type]  (solo se usa al fallar)
    steps = 0
    for _ in range(8):
        if game_page.handle_pregame():
            steps += 1
        elif page.evaluate("window.noticeDone && window.tourDone"):
            break
        else:
            page.wait_for_timeout(1600)   # el sondeo está espaciado (PREGAME_CHECK_S)
    assert page.evaluate("window.noticeDone") is True
    assert page.evaluate("window.tourDone") is True
    assert steps == 2


def test_optional_step_is_skipped(browser) -> None:
    """Sin saldo el formulario de límites no ofrece el gasto: el paso opcional se omite y el envío se pulsa."""
    page = browser.new_page()
    page.set_content('<div data-test-id="session-settings"><button data-test-id="session-settings_time-limit-option-3600">1h</button>'
                     '<button data-test-id="session-settings_submit-button-btn-1" onclick="window.sent=true">Iniciar sesión</button></div>')
    game_page = GamePage(page, load_market("es"), load_selectors("es"), object())  # type: ignore[arg-type]
    assert game_page.handle_pregame() is True
    assert page.evaluate("window.sent") is True
