"""Driver del juego: SOLO píxeles. Captura el iframe visible y hace clics por coordenadas."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np

from validator.game.calibration import SetupClick
from validator.pages.game_page import GameSession
from vision_engine import decode_png, page_point
from vision_engine.errors import CalibrationError

log = logging.getLogger(__name__)

BOX_TOLERANCE_PX = 1.0
CLICK_CHANGE_THRESHOLD = 2.0     # media de |diferencia| (0-255) alrededor del clic
CLICK_AREA = 0.15                # lado de la zona comprobada, fracción del iframe


@dataclass(frozen=True)
class ClickCheck:
    name: str
    changed: bool
    delta: float


class GameDriver:
    def __init__(self, session: GameSession) -> None:
        self.session = session
        self.page = session.page

    def capture(self) -> np.ndarray:
        """Captura BGR del rectángulo visible del iframe (escala CSS, device_scale_factor=1)."""
        return decode_png(self.session.iframe_locator.screenshot(animations="allow"))

    def wait(self, ms: float) -> None:
        self.page.wait_for_timeout(ms)

    def click(self, point: tuple[float, float], frame_size: tuple[int, int]) -> tuple[float, float]:
        """Clic en un punto LOCAL de la captura. Falla si el iframe se movió desde que se cargó."""
        box = self._current_box()
        x, y = page_point(point, frame_size, box)
        self.page.mouse.click(x, y)
        log.info("Clic en (%.0f, %.0f) de la página", x, y)
        return x, y

    def verified_click(self, name: str, point: tuple[float, float], frame_size: tuple[int, int],
                       settle_ms: float = 700) -> ClickCheck:
        """Clic que solo cuenta si la zona alrededor cambia en la captura posterior (CLAUDE.md §4)."""
        before = self.capture()
        self.click(point, frame_size)
        self.wait(settle_ms)
        after = self.capture()
        delta = _local_delta(before, after, point)
        return ClickCheck(name, delta > CLICK_CHANGE_THRESHOLD, delta)

    def run_setup(self, clicks: list[SetupClick], frame_size: tuple[int, int]) -> list[ClickCheck]:
        checks = []
        width, height = frame_size
        for click in clicks:
            point = (click.point[0] * (width - 1), click.point[1] * (height - 1))
            for _ in range(click.repeat):
                checks.append(self.verified_click(click.name, point, frame_size))
        return checks

    def _current_box(self) -> dict[str, float]:
        box = self.session.iframe_locator.bounding_box()
        if box is None:
            raise CalibrationError("El iframe del juego dejó de estar visible")
        reference = self.session.bounding_box
        if any(abs(box[k] - reference[k]) > BOX_TOLERANCE_PX for k in ("x", "y", "width", "height")):
            raise CalibrationError(f"El iframe se movió o cambió de tamaño ({reference} -> {box}); no se clica")
        return box


def _local_delta(before: np.ndarray, after: np.ndarray, point: tuple[float, float]) -> float:
    if before.shape != after.shape:
        return float("inf")
    height, width = before.shape[:2]
    half_w, half_h = int(width * CLICK_AREA / 2), int(height * CLICK_AREA / 2)
    x, y = int(point[0]), int(point[1])
    x0, x1 = max(0, x - half_w), min(width, x + half_w)
    y0, y1 = max(0, y - half_h), min(height, y + half_h)
    a = cv2.cvtColor(before[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    b = cv2.cvtColor(after[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    return float(np.mean(cv2.absdiff(a, b)))
