"""Localización de plantillas (botón Spin) por correlación normalizada multi-escala."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import cv2
import numpy as np

from .errors import ImageError
from .geometry import ROI, Point
from .imaging import to_gray

# Una plantilla casi uniforme no tiene textura que correlacionar.
MIN_TEMPLATE_STD = 1.0


@dataclass(frozen=True)
class TemplateMatch:
    point: Point          # centro del acierto, píxeles LOCALES de la captura
    confidence: float     # TM_CCOEFF_NORMED en [-1, 1]
    scale: float
    box: ROI

    def to_dict(self) -> dict:
        return {'point': list(self.point), 'confidence': self.confidence,
                'scale': self.scale, 'box': self.box.as_list()}


def load_template(path: str | Path) -> np.ndarray:
    """Carga una plantilla recortada de una captura REAL. No se inventan plantillas."""
    template = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if template is None:
        raise ImageError(f'No se puede leer la plantilla {path}; recortarla de una captura real')
    if to_gray(template).std() < MIN_TEMPLATE_STD:
        raise ImageError(f'Plantilla {path} uniforme; no sirve para localizar el botón')
    return template


def best_match(frame: np.ndarray, template: np.ndarray, search: ROI,
               scales: Sequence[float]) -> Optional[TemplateMatch]:
    """Mejor coincidencia dentro de `search`, sin aplicar umbral. None si ninguna escala cabe."""
    region = to_gray(search.crop(frame))
    best: Optional[TemplateMatch] = None
    for scale in scales:
        scaled = template if scale == 1 else cv2.resize(
            template, None, fx=scale, fy=scale,
            interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
        gray = to_gray(scaled)
        height, width = gray.shape
        if height > region.shape[0] or width > region.shape[1] or gray.std() < MIN_TEMPLATE_STD:
            continue
        scores = cv2.matchTemplate(region, gray, cv2.TM_CCOEFF_NORMED)
        scores = np.nan_to_num(scores, nan=-1.0, posinf=-1.0, neginf=-1.0)
        _, confidence, _, (px, py) = cv2.minMaxLoc(scores)
        if best is None or confidence > best.confidence:
            box = ROI(search.x + px, search.y + py, width, height)
            best = TemplateMatch(point=(box.x + width / 2, box.y + height / 2),
                                 confidence=float(min(confidence, 1.0)), scale=float(scale), box=box)
    return best
