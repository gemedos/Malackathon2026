"""Regiones de interés y conversión de coordenadas de imagen a CSS."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence, Tuple

import numpy as np

from .errors import CalibrationError, ProfileError

Point = Tuple[float, float]


@dataclass(frozen=True)
class ROI:
    """Rectángulo en píxeles LOCALES de la captura (origen arriba-izquierda)."""

    x: int
    y: int
    w: int
    h: int

    @classmethod
    def from_list(cls, values: Sequence[int], name: str = 'region') -> 'ROI':
        valid = (isinstance(values, (list, tuple)) and len(values) == 4
                 and all(isinstance(v, int) and not isinstance(v, bool) for v in values))
        if not valid:
            raise ProfileError(f'La región {name!r} debe ser [x, y, ancho, alto] con enteros')
        return cls(*values)

    def fits(self, width: int, height: int) -> bool:
        return (self.x >= 0 and self.y >= 0 and self.w > 0 and self.h > 0
                and self.x + self.w <= width and self.y + self.h <= height)

    def crop(self, frame: np.ndarray) -> np.ndarray:
        height, width = frame.shape[:2]
        if not self.fits(width, height):
            raise CalibrationError('ROI fuera de la imagen; recalibrar perfil')
        return frame[self.y:self.y + self.h, self.x:self.x + self.w]

    def as_list(self) -> list:
        return [self.x, self.y, self.w, self.h]


def page_point(point: Point, image_size: Tuple[int, int], game_box: Mapping[str, float],
               aspect_tolerance: float = 0.02) -> Point:
    """Convierte un punto de la captura a coordenadas CSS del viewport.

    `game_box` es la caja CSS ({x, y, width, height}) del MISMO rectángulo que se
    capturó; la aporta el equipo Playwright. Se aplica offset + escala por eje.
    Si las proporciones de imagen y caja difieren, no representan el mismo
    rectángulo y se rechaza en lugar de hacer clic en un punto dudoso.
    """
    x, y = point
    image_width, image_height = image_size
    if image_width <= 0 or image_height <= 0 or not (0 <= x < image_width and 0 <= y < image_height):
        raise CalibrationError('Coordenadas de imagen inválidas')
    box = [game_box['x'], game_box['y'], game_box['width'], game_box['height']]
    if not all(math.isfinite(v) for v in box) or box[2] <= 0 or box[3] <= 0:
        raise CalibrationError('Caja CSS inválida')
    scale_x = box[2] / image_width
    scale_y = box[3] / image_height
    if abs(scale_x - scale_y) > aspect_tolerance * max(scale_x, scale_y):
        raise CalibrationError('Captura y caja CSS con proporciones distintas; no son el mismo rectángulo')
    return (box[0] + x * scale_x, box[1] + y * scale_y)
