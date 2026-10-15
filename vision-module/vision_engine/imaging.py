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


def strip_trailing_symbol(binary: np.ndarray, min_gap_ratio: float = 0.3) -> np.ndarray | None:
    """Quita el último glifo (p. ej. «€») si va separado del importe por un espacio; None si no lo hay.

    Tesseract a veces lee el símbolo de moneda como un dígito («112,25 €» → «112,256»). Se localizan los
    glifos por columnas oscuras; el último se descarta solo si el hueco que lo separa del resto es claramente
    mayor que el de un dígito (≥ `min_gap_ratio` × altura del texto) y se parece a un símbolo (ancho ≈ alto)."""
    gray = to_gray(binary)
    dark = gray < 128
    rows = np.where(dark.any(axis=1))[0]
    cols = dark.any(axis=0)
    if rows.size == 0 or not cols.any():
        return None
    height = int(rows[-1] - rows[0] + 1)
    runs, start = [], None
    for x, on in enumerate(cols):
        if on and start is None:
            start = x
        elif not on and start is not None:
            runs.append((start, x - 1))
            start = None
    if start is not None:
        runs.append((start, len(cols) - 1))
    if len(runs) < 2:
        return None
    (last_start, last_end), previous_end = runs[-1], runs[-2][1]
    gap, width = last_start - previous_end - 1, last_end - last_start + 1
    if gap < min_gap_ratio * height or not 0.4 * height <= width <= 1.4 * height:
        return None
    cleaned = gray.copy()
    cleaned[:, last_start:] = 255
    return cleaned
