"""Almacén de evidencias: crops originales/preprocesados, frames y JSON.

Solo se guardan imágenes del rectángulo del juego. Nunca secretos.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .errors import ImageError, VisionError

_SAFE_NAME = re.compile(r'[A-Za-z0-9_-]+')


class EvidenceStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, *parts: str, suffix: str) -> Path:
        for part in parts:
            if not _SAFE_NAME.fullmatch(part):
                raise VisionError(f'Nombre de evidencia inválido: {part!r}')
        return self.root / ('-'.join(parts) + suffix)

    def save_image(self, sample_id: str, name: str, image: np.ndarray) -> str:
        path = self._path(sample_id, name, suffix='.png')
        if not cv2.imwrite(str(path), image):
            raise ImageError(f'No se pudo guardar la evidencia {path}')
        return str(path)

    def save_json(self, name: str, data: Any) -> str:
        path = self._path(name, suffix='.json')
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
        return str(path)
