"""Diagnóstico de un juego SIN apostar: entra con la cuenta FUNDED, abre el juego y durante ~30 s
resuelve las pantallas previas; después imprime qué diálogos y botones hay visibles y guarda una captura.

    python run.py inspect "Pragmatic Play" "Bubble Up"        # (equivale a python scripts/inspect_game.py ...)

Sirve para entender por qué no se detecta algo (un aviso nuevo, un diálogo que tapa el juego...) y para
escribir la regla en config/selectors/es.yaml (game_launch.pregame)."""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "vision-module")]

from playwright.sync_api import sync_playwright  # noqa: E402

from validator.browser import launch_browser  # noqa: E402
from validator.config import current_market, load_market, load_selectors  # noqa: E402
from validator.evidence import Evidence  # noqa: E402
from validator.navigation import login, open_game, work_context  # noqa: E402
from validator.pages.game_page import OVERLAY_SELECTOR  # noqa: E402
from validator.results import Checklist, Results  # noqa: E402
from validator.secrets import load_env_file  # noqa: E402

WATCH_S = 30


def main(provider: str, game: str) -> int:
    load_env_file()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    market = load_market(current_market())
    selectors = load_selectors(current_market())
    evidence = Evidence(current_market())
    results = Results(evidence.path("inspect_results.json"))
    checklist = Checklist(results, "inspect", current_market(), provider, game, ())
    with sync_playwright() as pw:
        browser = launch_browser(pw, headless=False)
        try:
            state = login(browser, market, selectors, evidence, provider=provider, account="FUNDED",
                          check=checklist.check)
            with work_context(browser, market, evidence, state) as ctx, open_game(ctx, market, selectors, evidence, provider=provider, game=game,
                                           check=checklist.check) as session:
                print(f"\nVigilando {WATCH_S}s las pantallas previas (se resuelven solas)...")
                end = time.monotonic() + WATCH_S
                while time.monotonic() < end:
                    if not (session.pregame and session.pregame()):
                        session.page.wait_for_timeout(500)
                shot = evidence.screenshot(session.page, "inspect.png")
                print(f"\nCaptura: {evidence.relative(shot)}")
                overlays = session.page.locator(OVERLAY_SELECTOR)
                print(f"Diálogos/paneles en la página: {overlays.count()}")
                for i in range(min(overlays.count(), 8)):
                    item = overlays.nth(i)
                    if not item.is_visible():
                        continue
                    text = " ".join(item.inner_text(timeout=1000).split())[:200]
                    buttons = [" ".join(b.inner_text(timeout=300).split())
                               for b in (item.get_by_role("button").nth(j) for j in range(min(item.get_by_role('button').count(), 10)))]
                    print(f"  - {text!r}\n    botones: {buttons}")
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    sys.exit(main(args[0] if args else "Pragmatic Play", args[1] if len(args) > 1 else "Bubble Up"))
