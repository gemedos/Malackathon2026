"""Página del juego: espera al iframe y a que el canvas cargue; devuelve una GameSession.

Punto de extensión para la fase de visión: `GameSession` es la entrada del driver del juego.
"""

from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image
from playwright.sync_api import BrowserContext, FrameLocator, Locator, Page

from validator.config import MarketConfig, SelectorsConfig
from validator.errors import EvidenceError
from validator.evidence import Evidence
from validator.pages.base_page import BasePage, build_locator

log = logging.getLogger(__name__)


class GameLoadError(EvidenceError):
    """El iframe o el canvas del juego no llegó a cargarse."""


class DemoModeError(EvidenceError):
    """El juego se abrió en modo demo."""


class SessionLimitsRequiredError(EvidenceError):
    """La web exige configurar límites de sesión y no hay pasos definidos en el YAML."""


@dataclass
class GameSession:
    page: Page
    iframe_locator: Locator
    bounding_box: dict[str, float]
    provider: str
    game: str

    @property
    def frame(self) -> FrameLocator:
        """FrameLocator del juego (para la futura capa de visión/OCR)."""
        return self.iframe_locator.content_frame


class GamePage(BasePage):
    def __init__(self, page: Page, market: MarketConfig, selectors: SelectorsConfig, evidence: Evidence) -> None:
        super().__init__(page, market, selectors)
        self.evidence = evidence

    # ------------------------------------------------------------------ público

    @classmethod
    def after_launch(
        cls, context: BrowserContext, origin: Page, market: MarketConfig, selectors: SelectorsConfig,
        evidence: Evidence, pages_before: int,
    ) -> "GamePage":
        """Si el lanzamiento abrió una pestaña nueva, el juego vive en ella."""
        page = origin
        if len(context.pages) > pages_before:
            page = context.pages[-1]
            page.wait_for_load_state("domcontentloaded")
            log.info("El juego se abrió en una pestaña nueva")
        return cls(page, market, selectors, evidence)

    def wait_loaded(self, provider: str, game: str) -> GameSession:
        self._handle_session_limits()
        iframe = self._wait_iframe()
        box = self._wait_stable_box(iframe)
        self._assert_not_demo(iframe)
        self._wait_canvas(iframe)
        shot = self.evidence.screenshot(self.page, "game_loaded.png")
        log.info("Juego cargado (%s): caja %s; evidencia %s", game, box, self.evidence.relative(shot))
        return GameSession(self.page, iframe, box, provider, game)

    # ------------------------------------------------------------------ pasos

    def _handle_session_limits(self) -> None:
        launch = self.selectors.game_launch
        if self.find_first(launch.session_limits_indicator, 3000, what="límites-sesión") is None:
            return
        if not launch.session_limits_steps:
            shot = self.evidence.screenshot(self.page, "session_limits.png")
            raise SessionLimitsRequiredError(
                "La web pide configurar límites de sesión antes de jugar y no hay pasos definidos en "
                "game_launch.session_limits_steps", self.evidence.relative(shot)
            )
        for step in launch.session_limits_steps:
            target = self.find_first([step], self.nav.default_timeout_ms, what="paso-límites")
            if target is None:
                raise SessionLimitsRequiredError(f"Paso de límites de sesión no encontrado: {step.describe()}")
            target.click()
        log.info("Límites de sesión confirmados con los pasos del YAML")

    def _wait_iframe(self) -> Locator:
        """Iframe visible más grande que el tamaño mínimo configurado."""
        nav = self.nav
        deadline = time.monotonic() + nav.iframe_timeout_ms / 1000
        while time.monotonic() < deadline:
            best, best_area = None, 0.0
            for candidate in self.selectors.game.iframe:
                locator = build_locator(self.page, candidate)
                for index in range(min(locator.count(), 15)):
                    item = locator.nth(index)
                    box = self._box(item)
                    if box and box["width"] >= nav.iframe_min_width and box["height"] >= nav.iframe_min_height:
                        area = box["width"] * box["height"]
                        if area > best_area:
                            best, best_area = item, area
            if best is not None:
                return best
            self.page.wait_for_timeout(500)
        shot = self.evidence.screenshot(self.page, "game_iframe_missing.png")
        raise GameLoadError("No apareció el iframe del juego", self.evidence.relative(shot))

    def _wait_stable_box(self, iframe: Locator) -> dict[str, float]:
        """El bounding box debe mantenerse (±1 px) durante `iframe_stable_ms`."""
        nav = self.nav
        deadline = time.monotonic() + nav.iframe_timeout_ms / 1000
        reference = self._box(iframe)
        stable_since = time.monotonic()
        while time.monotonic() < deadline:
            self.page.wait_for_timeout(250)
            box = self._box(iframe)
            if box is None or reference is None or not _same_box(box, reference):
                reference, stable_since = box, time.monotonic()
                continue
            if (time.monotonic() - stable_since) * 1000 >= nav.iframe_stable_ms:
                return reference
        raise GameLoadError("El iframe del juego no se estabilizó (tamaño o posición cambiando)")

    def _assert_not_demo(self, iframe: Locator) -> None:
        src = (iframe.get_attribute("src") or "").lower()
        url = self.page.url.lower()
        real = [m for m in self.market.real_play_url_markers if m.lower() in src or m.lower() in url]
        log.info("Marcadores de Real Play en la URL: %s", real or "ninguno")
        for marker in self.market.demo_url_markers:
            if marker.lower() in src or marker.lower() in url:
                shot = self.evidence.screenshot(self.page, "game_demo_mode.png")
                raise DemoModeError(
                    f"El juego se abrió en modo demo (marcador {marker!r})", self.evidence.relative(shot)
                )

    def _wait_canvas(self, iframe: Locator) -> None:
        """Capturas cada `canvas_poll_ms`; cargado cuando dos seguidas difieren menos del umbral."""
        nav = self.nav
        deadline = time.monotonic() + nav.canvas_timeout_ms / 1000
        previous: np.ndarray | None = None
        last_diff: float | None = None
        while time.monotonic() < deadline:
            frame = _to_gray(iframe.screenshot(animations="allow"))
            if previous is not None and previous.shape == frame.shape:
                last_diff = float(np.mean(np.abs(frame - previous) > nav.canvas_pixel_delta))
                if last_diff < nav.canvas_diff_threshold and float(frame.std()) >= nav.canvas_min_stddev:
                    log.info("Canvas estable (diferencia %.4f < %.4f)", last_diff, nav.canvas_diff_threshold)
                    return
            previous = frame
            self.page.wait_for_timeout(nav.canvas_poll_ms)
        shot = self.evidence.screenshot(self.page, "game_canvas_timeout.png")
        raise GameLoadError(
            f"El canvas no se estabilizó en {nav.canvas_timeout_ms} ms (última diferencia {last_diff})",
            self.evidence.relative(shot),
        )

    @staticmethod
    def _box(locator: Locator) -> dict[str, Any] | None:
        try:
            if not locator.is_visible():
                return None
            return locator.bounding_box()
        except Exception:
            return None


def _same_box(a: dict[str, float], b: dict[str, float], tolerance: float = 1.0) -> bool:
    return all(abs(a[k] - b[k]) <= tolerance for k in ("x", "y", "width", "height"))


def _to_gray(png: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(png)).convert("L"), dtype=np.int16)
