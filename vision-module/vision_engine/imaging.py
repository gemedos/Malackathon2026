"""Utilidades de imagen: decodificación y preprocesado para OCR."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .errors import ImageError

OCR_UPSCALE = 3


def decode_png(data: bytes) -> np.ndarray:
    """Decodifica bytes de imagen (p. ej. `page.screenshot()`) a un frame BGR."""
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ImageError('Imagen no válida')
    return frame


def load_image(path: str | Path) -> np.ndarray:
    return decode_png(Path(path).read_bytes())


def to_gray(image: np.ndarray) -> np.ndarray:
    return image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def preprocess_for_ocr(crop: np.ndarray, upscale: int = OCR_UPSCALE) -> np.ndarray:
    """Gris → ampliación → binarización Otsu, con texto oscuro sobre fondo claro."""
    gray = cv2.resize(to_gray(crop), None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Tesseract rinde mejor con texto oscuro; los HUD de slots suelen ser texto claro.
    if binary.mean() < 127:
        binary = cv2.bitwise_not(binary)
    return binary


LIGHT_TEXT_UPSCALE = 6
LIGHT_TEXT_BORDER = 12


def preprocess_light_text(crop: np.ndarray, max_saturation: int, min_value: int,
                          upscale: int = LIGHT_TEXT_UPSCALE) -> np.ndarray:
    """Solo el texto blanco (saturación baja y brillo alto en HSV), negro sobre blanco y con margen.

    En HUD con fondo degradado, brillos y etiquetas de color, Otsu en gris mezcla el fondo con las cifras
    (p. ej. «48,14» se leía «4,14»); aislar el color del texto deja únicamente los glifos."""
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = ((hsv[..., 1] <= max_saturation) & (hsv[..., 2] >= min_value)).astype(np.uint8) * 255
    mask = cv2.resize(mask, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)
    _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    return cv2.copyMakeBorder(cv2.bitwise_not(mask), LIGHT_TEXT_BORDER, LIGHT_TEXT_BORDER, LIGHT_TEXT_BORDER,
                              LIGHT_TEXT_BORDER, cv2.BORDER_CONSTANT, value=255)
