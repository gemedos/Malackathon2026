"""Creación de navegador y contextos con las opciones del mercado."""

from __future__ import annotations

import logging
import json
from pathlib import Path

from playwright.sync_api import Browser, BrowserContext, Page, Playwright

from validator.config import MarketConfig

log = logging.getLogger(__name__)

VIEWPORT = {"width": 1280, "height": 720}  # fijo: las coordenadas de visión dependen de ello


def launch_browser(pw: Playwright, headless: bool = True) -> Browser:
    log.info("Lanzando Chromium (headless=%s)", headless)
    # Sin la marca de automatización: el sitio (WAF / antibot) trata el navegador como el de un jugador.
    return pw.chromium.launch(headless=headless, args=["--disable-blink-features=AutomationControlled"],
                              ignore_default_args=["--enable-automation"])


def session_file(state_path: Path) -> Path:
    return state_path.with_suffix(".session.json")


def save_session_storage(page: Page, state_path: Path) -> list[str]:
    """Guarda el sessionStorage del login junto al storage_state (en `.auth/`, fuera de artifacts).

    `storage_state` solo guarda cookies y localStorage; betsson.es mantiene la sesión en sessionStorage, que
    se perdía al pasar al contexto de trabajo («la sesión del login no se conservó»). Devuelve solo los
    NOMBRES de las claves (nunca valores) para el log."""
    data = page.evaluate("() => Object.fromEntries(Object.entries(window.sessionStorage))")
    session_file(state_path).write_text(json.dumps({"origin": page.url.split("/", 3)[:3], "items": data}),
                                        encoding="utf-8")
    return sorted(data)


def _restore_script(state_path: Path) -> str | None:
    path = session_file(state_path)
    if not path.is_file():
        return None
    saved = json.loads(path.read_text(encoding="utf-8"))
    origin = "/".join(saved["origin"])
    return (
        "(() => { try { if (location.origin !== %s) return; const items = %s;"
        " for (const [k, v] of Object.entries(items)) if (sessionStorage.getItem(k) === null) sessionStorage.setItem(k, v);"
        " } catch (e) {} })();" % (json.dumps(origin), json.dumps(saved["items"]))
    )


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
    if storage_state is not None:
        script = _restore_script(storage_state)
        if script:
            context.add_init_script(script)    # sessionStorage de la sesión, en cada página y marco del contexto
    context.set_default_timeout(market.navigation.default_timeout_ms)
    context.set_default_navigation_timeout(market.navigation.navigation_timeout_ms)
    log.info(
        "Contexto creado (locale=%s, tz=%s, sesión=%s, vídeo=%s)",
        market.locale, market.timezone, storage_state is not None, video_dir is not None,
    )
    return context
