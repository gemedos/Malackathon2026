"""Evidencias anotadas: regiones con los valores leídos y tira de fotogramas del spin."""
from __future__ import annotations

import unicodedata
from typing import Mapping, Optional, Sequence

import cv2
import numpy as np

from .geometry import ROI

COLORS = {'spin_search': (0, 200, 255), 'reels': (255, 160, 0), 'message': (255, 0, 200)}
DEFAULT_COLOR = (0, 230, 0)
FONT = cv2.FONT_HERSHEY_SIMPLEX


def _ascii(text: str) -> str:
    """cv2.putText solo dibuja ASCII: '€' -> 'EUR', tildes fuera."""
    text = text.replace('€', 'EUR').replace('\n', ' ')
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')[:60]


def annotate(frame: np.ndarray, regions: Mapping[str, ROI], labels: Optional[Mapping[str, str]] = None) -> np.ndarray:
    """Copia del frame con cada región enmarcada y su etiqueta (nombre: valor leído)."""
    out = frame.copy()
    labels = labels or {}
    for name, roi in regions.items():
        color = COLORS.get(name, DEFAULT_COLOR)
        cv2.rectangle(out, (roi.x, roi.y), (roi.x + roi.w - 1, roi.y + roi.h - 1), color, 2)
        text = _ascii(f'{name}: {labels[name]}' if name in labels else name)
        (tw, th), _ = cv2.getTextSize(text, FONT, 0.45, 1)
        y = max(th + 4, roi.y - 4)
        cv2.rectangle(out, (roi.x, y - th - 4), (roi.x + tw + 4, y + 2), (0, 0, 0), -1)
        cv2.putText(out, text, (roi.x + 2, y - 2), FONT, 0.45, color, 1, cv2.LINE_AA)
    return out


def strip(frames: Sequence[np.ndarray], captions: Sequence[str], thumb_width: int = 320, per_row: int = 4) -> np.ndarray:
    """Tira de miniaturas (filas de `per_row`) con un pie de texto en cada una."""
    if not frames:
        raise ValueError('La tira necesita al menos un frame')
    thumbs = []
    for frame, caption in zip(frames, captions):
        scale = thumb_width / frame.shape[1]
        thumb = cv2.resize(frame, (thumb_width, max(1, int(frame.shape[0] * scale))), interpolation=cv2.INTER_AREA)
        thumb = cv2.copyMakeBorder(thumb, 0, 22, 0, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        cv2.putText(thumb, _ascii(caption), (4, thumb.shape[0] - 6), FONT, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
        thumbs.append(thumb)
    height = max(t.shape[0] for t in thumbs)
    thumbs = [cv2.copyMakeBorder(t, 0, height - t.shape[0], 0, 2, cv2.BORDER_CONSTANT, value=(40, 40, 40))
              for t in thumbs]
    blank = np.full_like(thumbs[0], 40)
    rows = []
    for start in range(0, len(thumbs), per_row):
        row = thumbs[start:start + per_row]
        row += [blank] * (per_row - len(row))
        rows.append(np.hstack(row))
    return np.vstack(rows)
