"""Flujo reutilizable: login una vez por sesión y, para cada juego, betsson.es -> juego en Real Play.

    state = login(...)                                   # contexto de login (sin vídeo ni traza)
    with work_context(browser, market, state) as ctx:    # contexto de trabajo (vídeo + traza)
        for game in games:
            with open_game(ctx, ..., game=game, check=checklist.check) as session:
                ...                                      # aquí irán los escenarios de visión
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, ContextManager, Iterator

from playwright.sync_api import Browser, BrowserContext

from validator.browser import new_context, save_session_storage
from validator.config import MarketConfig, SelectorsConfig
from validator.evidence import Evidence
from validator.pages.cookie_banner import CookieBanner
from validator.pages.game_page import GamePage, GameSession
from validator.pages.login_page import LoginPage
from validator.pages.provider_page import ProviderPage
from validator.results import CheckOutcome
from validator.secrets import get_credentials
from validator.urls import provider_url

log = logging.getLogger(__name__)

CHECK_LOGIN = "Login correcto"
CHECK_PROVIDER_URL = "URL de proveedor accesible"
CHECK_GAME_FOUND = "Juego encontrado"
CHECK_REAL_PLAY = "Real Play lanzado"
CHECK_IFRAME = "Iframe cargado"
GAME_CHECKS = (CHECK_PROVIDER_URL, CHECK_GAME_FOUND, CHECK_REAL_PLAY, CHECK_IFRAME)

Checker = Callable[[str], ContextManager[CheckOutcome]]


def login(
    browser: Browser, market: MarketConfig, selectors: SelectorsConfig, evidence: Evidence,
    *, provider: str, account: str, check: Checker,
) -> Path:
    """Inicia sesión en un contexto sin vídeo ni traza y guarda `storage_state` en `.auth/`."""
    state_path = evidence.storage_state_path(account)
    context = new_context(browser, market)
    try:
        page = context.new_page()
        with check(CHECK_LOGIN) as out:
            page.goto(provider_url(market, provider), wait_until="domcontentloaded")
            CookieBanner(page, market, selectors).handle()
            credentials = get_credentials(account, market.market)
            out.detail = f"cuenta {account}: " + LoginPage(page, market, selectors).login(credentials, evidence)
            context.storage_state(path=str(state_path))
            keys = save_session_storage(page, state_path)
            log.info("sessionStorage de la sesión guardado (%d claves: %s)", len(keys), ", ".join(keys))
            log.info("storage_state guardado en .auth/ (fuera de artifacts)")
    finally:
        context.close()
    return state_path


@contextmanager
def work_context(browser: Browser, market: MarketConfig, evidence: Evidence, state_path: Path) -> Iterator[BrowserContext]:
    """Contexto de trabajo con la sesión del login; vídeo y traza activos desde el inicio."""
    context = new_context(browser, market, storage_state=state_path, video_dir=evidence.video_dir)
    context.tracing.start(screenshots=False, snapshots=False, sources=False)
    log.info("Contexto de trabajo creado (traza y vídeo posteriores al login)")
    try:
        yield context
    finally:
        try:
            context.tracing.stop()
        except Exception as exc:
            log.warning("No se pudo cerrar la traza: %s", type(exc).__name__)
        context.close()
        evidence.cleanup()


@contextmanager
def open_game(
    context: BrowserContext, market: MarketConfig, selectors: SelectorsConfig, evidence: Evidence,
    *, provider: str, game: str, check: Checker,
) -> Iterator[GameSession]:
    """Abre el juego en Real Play en una pestaña nueva y entrega la GameSession.

    Al salir cierra las pestañas del juego y guarda su traza y su vídeo en la carpeta del juego.
    """
    context.tracing.start_chunk(title=f"{provider} / {game}")
    pages_before = set(context.pages)
    page = context.new_page()
    try:
        provider_page = ProviderPage(page, market, selectors)
        with check(CHECK_PROVIDER_URL) as out:
            opened = provider_page.open(provider)
            CookieBanner(page, market, selectors).handle(timeout=2000)
            out.detail = f"{opened.url} -> HTTP {opened.status}"
            if opened.plan_b:
                out.passed = False
                out.detail += f"; plan B usado ({opened.reason})"
            out.evidence = evidence.relative(evidence.screenshot(page, "provider_page.png"))
        if not LoginPage(page, market, selectors).is_logged_in(3000):
            log.warning("No se ve el indicador de sesión en el contexto de trabajo")

        with check(CHECK_GAME_FOUND) as out:
            card = provider_page.find_game_card(game)
            out.detail = f"tarjeta {card.name!r}"
            if card.others:
                out.detail += f"; otras coincidencias: {', '.join(card.others)}"
            out.evidence = evidence.relative(evidence.screenshot(page, "game_card.png"))
        with check(CHECK_REAL_PLAY) as out:
            pages_launch = len(context.pages)
            out.detail = provider_page.launch_real_play(card)
        with check(CHECK_IFRAME) as out:
            game_page = GamePage.after_launch(context, page, market, selectors, evidence, pages_launch)
            session = game_page.wait_loaded(provider, game)
            box = session.bounding_box
            out.detail = f"iframe {box['width']:.0f}x{box['height']:.0f} en ({box['x']:.0f},{box['y']:.0f})"
            out.evidence = evidence.relative(evidence.path("game_loaded.png"))
        yield session
    finally:
        game_pages = [p for p in context.pages if p not in pages_before]
        try:
            context.tracing.stop_chunk(path=str(evidence.trace_path))
            log.info("Traza guardada: %s", evidence.relative(evidence.trace_path))
        except Exception as exc:
            log.warning("No se pudo guardar la traza: %s", type(exc).__name__)
        for p in game_pages:
            try:
                p.close()
            except Exception:
                pass
        evidence.save_videos(game_pages)
