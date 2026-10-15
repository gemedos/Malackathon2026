"""Fachada del motor: solo píxeles BGR. No accede al DOM, red, canvas API ni estado interno."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Union

import numpy as np

from .errors import CalibrationError, ProfileError
from .evidence import EvidenceStore
from .geometry import ROI
from .matching import TemplateMatch, best_match
from .messages import matches_any
from .ocr import (BETSSON_BALANCE_FIELD, HUD_FIELDS, MESSAGE_FIELD, FieldReader, OcrBackend, OcrReading,
                  tesseract_backend)
from .profile import GameProfile


class VisionEngine:
    def __init__(self, profile: GameProfile, evidence: Union[EvidenceStore, str, Path],
                 ocr_backend: OcrBackend = tesseract_backend):
        self.profile = profile
        self.evidence = evidence if isinstance(evidence, EvidenceStore) else EvidenceStore(evidence)
        self._reader = FieldReader(profile, self.evidence, ocr_backend)

    def roi(self, name: str) -> ROI:
        try:
            return self.profile.regions[name]
        except KeyError:
            raise ProfileError(f'Región {name!r} no definida en el perfil') from None

    def check_size(self, frame: np.ndarray) -> None:
        size = (frame.shape[1], frame.shape[0])
        if size != self.profile.image_size:
            raise CalibrationError(f'Resolución {size} distinta al perfil {self.profile.image_size}; recalibrar')

    def locate_spin(self, frame: np.ndarray, template: np.ndarray) -> Optional[TemplateMatch]:
        """Botón Spin con confianza >= template_threshold, o None si falta evidencia."""
        self.check_size(frame)
        match = best_match(frame, template, self.roi('spin_search'), self.profile.template_scales)
        if match is None or match.confidence < self.profile.template_threshold:
            return None
        return match

    def read_field(self, frame: np.ndarray, field: str, sample_id: str,
                   timestamp: Optional[float] = None) -> OcrReading:
        self.check_size(frame)
        return self._reader.read(frame, field, sample_id, timestamp)

    def read_hud(self, frame: np.ndarray, sample_id: str,
                 timestamp: Optional[float] = None) -> Dict[str, OcrReading]:
        """Balance, apuesta, premio y moneda, cada uno en su propia región."""
        return {field: self.read_field(frame, field, sample_id, timestamp) for field in HUD_FIELDS}

    def read_wide_message(self, frame: np.ndarray, sample_id: str,
                          timestamp: Optional[float] = None) -> OcrReading:
        return self._reader.read_wide_message(frame, sample_id, timestamp)

    def read_message(self, frame: np.ndarray, sample_id: str,
                     timestamp: Optional[float] = None) -> OcrReading:
        return self.read_field(frame, MESSAGE_FIELD, sample_id, timestamp)

    def read_betsson_balance(self, page: np.ndarray, sample_id: str,
                             timestamp: Optional[float] = None) -> OcrReading:
        """Saldo de la cuenta Betsson en una captura de la PÁGINA (no del juego)."""
        layout = self.profile.betsson_page
        if layout is None:
            raise ProfileError('El perfil no define betsson_page; no se puede leer el saldo Betsson')
        size = (page.shape[1], page.shape[0])
        if size != layout.image_size:
            raise CalibrationError(f'Captura de página {size} distinta a betsson_page {layout.image_size}')
        return self._reader.read(page, BETSSON_BALANCE_FIELD, sample_id, timestamp, roi=layout.balance)

    def read_image(self, image: np.ndarray, field: str, sample_id: str,
                   timestamp: Optional[float] = None) -> OcrReading:
        """OCR de una imagen completa (p. ej. captura de un elemento de la web de Betsson)."""
        height, width = image.shape[:2]
        return self._reader.read(image, field, sample_id, timestamp, roi=ROI(0, 0, width, height))

    def is_insufficient_message(self, text: str) -> bool:
        """Frase específica calibrada por mercado; una palabra genérica no basta."""
        return matches_any(text, self.profile.insufficient_patterns)
