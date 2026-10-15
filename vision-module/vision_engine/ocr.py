"""OCR por campo: recorte → preprocesado → Tesseract → interpretación estricta.

Cada campo tiene su propia región; nunca se infieren campos por el orden de
números en una barra completa. Se conservan texto, crop original y preprocesado.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable, Optional, Tuple

import numpy as np

from .currency import detect_currency
from .errors import OcrUnavailableError, ProfileError
from .evidence import EvidenceStore
from .imaging import preprocess_for_ocr
from .money import parse_money
from .profile import GameProfile

MONEY_FIELDS = ('balance', 'wager', 'payout')
CURRENCY_FIELD = 'currency'
MESSAGE_FIELD = 'message'
HUD_FIELDS = MONEY_FIELDS + (CURRENCY_FIELD,)
OCR_FIELDS = HUD_FIELDS + (MESSAGE_FIELD,)

# (imagen preprocesada, idioma, config de Tesseract) -> texto. Inyectable en pruebas.
OcrBackend = Callable[[np.ndarray, str, str], str]


def tesseract_backend(image: np.ndarray, language: str, config: str) -> str:
    import pytesseract
    try:
        return pytesseract.image_to_string(image, lang=language, config=config)
    except pytesseract.TesseractNotFoundError as exc:
        raise OcrUnavailableError('Tesseract no está instalado; usar el contenedor Docker') from exc
    except pytesseract.TesseractError as exc:
        raise OcrUnavailableError(f'Tesseract falló (¿idioma {language!r} instalado?): {exc}') from exc


@dataclass(frozen=True)
class OcrReading:
    field: str
    sample_id: str
    timestamp: Optional[float]
    raw_text: str
    value: Optional[str]   # Decimal como texto, o código de moneda; None si no se pudo interpretar
    error: Optional[str]
    crop_path: str
    processed_path: str

    def to_dict(self) -> dict:
        return asdict(self)


class FieldReader:
    def __init__(self, profile: GameProfile, evidence: EvidenceStore, backend: OcrBackend = tesseract_backend):
        self.profile = profile
        self.evidence = evidence
        self.backend = backend

    def read(self, frame: np.ndarray, field: str, sample_id: str,
             timestamp: Optional[float] = None) -> OcrReading:
        if field not in OCR_FIELDS:
            raise ProfileError(f'Campo OCR desconocido {field!r}')
        crop = self.profile.regions[field].crop(frame)
        processed = preprocess_for_ocr(crop)
        crop_path = self.evidence.save_image(sample_id, field, crop)
        processed_path = self.evidence.save_image(sample_id, f'{field}-ocr', processed)
        config = '--psm 6' if field == MESSAGE_FIELD else '--psm 7'
        raw = self.backend(processed, self.profile.ocr_language, config).strip()
        value, error = self._interpret(field, raw)
        return OcrReading(field, sample_id, timestamp, raw, value, error, crop_path, processed_path)

    def _interpret(self, field: str, raw: str) -> Tuple[Optional[str], Optional[str]]:
        try:
            if field in MONEY_FIELDS:
                return str(parse_money(raw, self.profile.decimal_separator)), None
            if field == CURRENCY_FIELD:
                return detect_currency(raw), None
        except ValueError as exc:
            return None, str(exc)
        return None, None  # el mensaje se conserva solo como texto
