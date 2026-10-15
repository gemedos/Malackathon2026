"""Página del juego: espera al iframe y a que el canvas cargue; devuelve una GameSession.

Punto de extensión para la fase de visión: `GameSession` es la entrada del driver del juego.
"""

from __future__ import annotations

import io
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
from PIL import Image
from playwright.sync_api import BrowserContext, FrameLocator, Locator, Page

from validator.config import MarketConfig, SelectorsConfig
from validator.evidence import Evidence
from validator.pages.base_page import BasePage, build_locator

log = logging.getLogger(__name__)

PREGAME_CHECK_S = 1.5     # separación mínima entre comprobaciones de pantallas previas


class GameLoadError(RuntimeError):
    """El iframe o el canvas del juego no llegó a cargarse."""


class DemoModeError(RuntimeError):
    """El juego se abrió en modo demo."""


class SessionLimitsRequiredError(RuntimeError):
    """La web exige configurar límites de sesión y no hay pasos definidos en el YAML."""


class PregameError(RuntimeError):
    """Una pantalla previa (límites, aviso...) se detectó pero no se pudo resolver con sus pasos."""


OVERLAY_CHECK_S = 3.0
OVERLAY_SELECTOR = '[role="dialog"], [aria-modal="true"], fds-dialog, site-drawer'
_SAFE_BUTTON = re.compile(r"\b(cerrar|aceptar|continuar|entendido|ok|de acuerdo|m[aá]s tarde|ahora no|omitir|close)\b|^\s*[x×✕]\s*$", re.I)
_UNSAFE_BUTTON = re.compile(r"depos|compr|pagar|retir|jugar|apost|registr|inici(?:a|ar) sesi", re.I)


@dataclass
class GameSession:
    page: Page
    iframe_locator: Locator
    bounding_box: dict[str, float]
    provider: str
    game: str
    pregame: Callable[[], bool] | None = None   # resuelve pantallas previas que aparezcan más tarde (True si actuó)

    @property
    def frame(self) -> FrameLocator:
        """FrameLocator del juego (para la futura capa de visión/OCR)."""
        return self.iframe_locator.content_frame


class GamePage(BasePage):
    def __init__(self, page: Page, market: MarketConfig, selectors: SelectorsConfig, evidence: Evidence) -> None:
        super().__init__(page, market, selectors)
        self.evidence = evidence
        self._pregame_checked = 0.0
        self._overlay_checked = 0.0
        self._overlay_reported: set[str] = set()
        self._game_box: dict[str, float] | None = None

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
        if not self.selectors.game_launch.pregame:
            self._handle_session_limits()      # configuración antigua (session_limits_*)
        iframe = self._wait_iframe()
        box = self._wait_stable_box(iframe)
        self._game_box = box
        self._assert_not_demo(iframe)
        self._wait_canvas(iframe)
        shot = self.evidence.screenshot(self.page, "game_loaded.png")
        log.info("Juego cargado (%s): caja %s; evidencia %s", game, box, self.evidence.relative(shot))
        return GameSession(self.page, iframe, box, provider, game, pregame=self.handle_pregame)

    # ------------------------------------------------------------------ pasos

    def handle_pregame(self) -> bool:
        """Resuelve UNA pantalla previa visible (config game_launch.pregame). True si actuó.

        Puede llamarse en bucle mientras se espera al juego: las pantallas regulatorias (aviso de sesión de
        juego, límites, avisos que tapan el juego) llegan en distinto orden según el juego y el proveedor."""
        # Sondear tres pantallas en cada vuelta hace que la página parpadee mientras carga el juego:
        # como mucho una comprobación cada PREGAME_CHECK_S segundos.
        now = time.monotonic()
        if now - self._pregame_checked < PREGAME_CHECK_S:
            return False
        self._pregame_checked = now
        for screen in self.selectors.game_launch.pregame:
            if self.find_first(screen.detect, 0, what=f"pregame:{screen.name}") is None:
                continue
            log.info("Pantalla previa: %s", screen.name)
            for step in screen.steps:
                alternatives = step if isinstance(step, list) else [step]
                target = self.find_first(alternatives, 1500 if all(a.optional for a in alternatives) else 3000,
                                         what=f"pregame:{screen.name}")
                if target is None and all(a.optional for a in alternatives):
                    log.info("Pantalla previa %r: paso opcional ausente, se omite (%s)", screen.name,
                             alternatives[0].describe())
                    continue
                if target is None:
                    shot = self.evidence.screenshot(self.page, "pregame_step_missing.png")
                    raise PregameError(f"Pantalla previa {screen.name!r}: no encuentro el paso {alternatives[0].describe()} "
                                       f"(evidencia: {self.evidence.relative(shot)})")
                try:
                    target.click(timeout=2500)
                except Exception as exc:     # p. ej. otro diálogo intercepta el clic: se reintenta en la siguiente pasada
                    log.warning("Pantalla previa %r: clic no aplicado (%s)", screen.name, type(exc).__name__)
                    return True
                self.page.wait_for_timeout(300)
            self.page.wait_for_timeout(700)
            return True
        return self._dismiss_unknown_overlay()

    def _dismiss_unknown_overlay(self) -> bool:
        """Red de seguridad genérica: un diálogo/panel que tape el juego y no esté en las reglas del YAML.

        Solo pulsa botones inequívocamente inocuos («Entendido», «Cerrar», «Más tarde»...) y nunca los que
        mueven dinero o lanzan acciones (Depositar, Jugar...). Si no hay ninguno, lo deja registrado una vez
        con su texto y una captura, para poder añadir la regla al YAML."""
        now = time.monotonic()
        if now - self._overlay_checked < OVERLAY_CHECK_S:
            return False
        self._overlay_checked = now
        try:
            overlays = self.page.locator(OVERLAY_SELECTOR)
            for index in range(min(overlays.count(), 5)):
                overlay = overlays.nth(index)
                box = self._box(overlay)
                if box is None or not self._covers_game(box):
                    continue
                text = " ".join((overlay.inner_text(timeout=500) or "").split())[:200]
                button = self._safe_button(overlay)
                if button is None:
                    if text not in self._overlay_reported:
                        self._overlay_reported.add(text)
                        shot = self.evidence.screenshot(self.page, "overlay_unknown.png")
                        log.warning("Diálogo desconocido sobre el juego, sin botón seguro que pulsar: %r "
                                    "(evidencia: %s). Añade una regla en game_launch.pregame.", text,
                                    self.evidence.relative(shot))
                    continue
                log.info("Diálogo genérico sobre el juego (%r): se cierra con un botón seguro", text)
                button.click(timeout=2500)
                self.page.wait_for_timeout(500)
                return True
        except Exception as exc:    # la red de seguridad nunca debe romper el flujo
            log.debug("Detección genérica de diálogos falló: %s", type(exc).__name__)
        return False

    def _covers_game(self, box: dict[str, float]) -> bool:
        game = self._game_box
        if game is None:
            return box["width"] > 200 and box["height"] > 100
        overlap_w = min(box["x"] + box["width"], game["x"] + game["width"]) - max(box["x"], game["x"])
        overlap_h = min(box["y"] + box["height"], game["y"] + game["height"]) - max(box["y"], game["y"])
        return overlap_w > 0 and overlap_h > 0 and overlap_w * overlap_h > 0.1 * game["width"] * game["height"]

    @staticmethod
    def _safe_button(overlay: Locator) -> Locator | None:
        buttons = overlay.get_by_role("button")
        for index in range(min(buttons.count(), 12)):
            button = buttons.nth(index)
            try:
                if not button.is_visible():
                    continue
                label = " ".join(filter(None, [button.inner_text(timeout=300), button.get_attribute("aria-label")]))
            except Exception:
                continue
            if _UNSAFE_BUTTON.search(label):
                continue
            if _SAFE_BUTTON.search(label):
                return button
        return None

    def _handle_session_limits(self) -> None:
        launch = self.selectors.game_launch
        if self.find_first(launch.session_limits_indicator, 3000, what="límites-sesión") is None:
            return
        if not launch.session_limits_steps:
            shot = self.evidence.screenshot(self.page, "session_limits.png")
            raise SessionLimitsRequiredError(
                "La web pide configurar límites de sesión antes de jugar y no hay pasos definidos en "
                f"game_launch.session_limits_steps (evidencia: {self.evidence.relative(shot)})"
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
            if self.handle_pregame():
                continue
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
        raise GameLoadError(f"No apareció el iframe del juego (evidencia: {self.evidence.relative(shot)})")

    def _wait_stable_box(self, iframe: Locator) -> dict[str, float]:
        """El bounding box debe mantenerse (±1 px) durante `iframe_stable_ms`."""
        nav = self.nav
        deadline = time.monotonic() + nav.iframe_timeout_ms / 1000
        reference = self._box(iframe)
        stable_since = time.monotonic()
        while time.monotonic() < deadline:
            if self.handle_pregame():          # los avisos/límites pueden salir mientras el iframe se asienta
                reference, stable_since = self._box(iframe), time.monotonic()
                continue
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
                    f"El juego se abrió en modo demo (marcador {marker!r}; evidencia: {self.evidence.relative(shot)})"
                )

    def _wait_canvas(self, iframe: Locator) -> None:
        """Capturas cada `canvas_poll_ms`; cargado cuando dos seguidas difieren menos del umbral."""
        nav = self.nav
        deadline = time.monotonic() + nav.canvas_timeout_ms / 1000
        previous: np.ndarray | None = None
        last_diff: float | None = None
        while time.monotonic() < deadline:
            if self.handle_pregame():
                previous = None
                continue
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
            f"El canvas no se estabilizó en {nav.canvas_timeout_ms} ms (última diferencia {last_diff}; "
            f"evidencia: {self.evidence.relative(shot)})"
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
