"""Creación de navegador y contextos con las opciones del mercado."""

from __future__ import annotations

import logging
from pathlib import Path

from playwright.sync_api import Browser, BrowserContext, Playwright

from validator.config import MarketConfig

log = logging.getLogger(__name__)

VIEWPORT = {"width": 1280, "height": 720}  # fijo: las coordenadas de visión dependen de ello


def launch_browser(pw: Playwright, headless: bool = True) -> Browser:
    log.info("Lanzando Chromium (headless=%s)", headless)
    return pw.chromium.launch(headless=headless)


def new_context(
    browser: Browser,
    market: MarketConfig,
    *,
    storage_state: Path | None = None,
    video_dir: Path | None = None,
) -> BrowserContext:
    """Contexto con viewport, locale y zona horaria del mercado.

    - Contexto de login: sin `storage_state` ni `video_dir` (nunca se graba el formulario).
    - Contexto de trabajo: con `storage_state` del login y vídeo desde el inicio.
    """
    kwargs: dict = {
        "viewport": VIEWPORT,
        "device_scale_factor": 1,
        "locale": market.locale,
        "timezone_id": market.timezone,
        "extra_http_headers": {"Accept-Language": f"{market.locale},{market.language};q=0.9"},
    }
    if storage_state is not None:
        kwargs["storage_state"] = str(storage_state)
    if video_dir is not None:
        video_dir.mkdir(parents=True, exist_ok=True)
        kwargs["record_video_dir"] = str(video_dir)
        kwargs["record_video_size"] = VIEWPORT
    context = browser.new_context(**kwargs)
    context.set_default_timeout(market.navigation.default_timeout_ms)
    context.set_default_navigation_timeout(market.navigation.navigation_timeout_ms)
    log.info(
        "Contexto creado (locale=%s, tz=%s, sesión=%s, vídeo=%s)",
        market.locale, market.timezone, storage_state is not None, video_dir is not None,
    )
    return context
