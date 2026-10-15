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
from .geometry import ROI
from .imaging import preprocess_for_ocr, preprocess_light_text, to_gray
from .messages import normalize_text
from .money import parse_money
from .profile import GameProfile

MONEY_FIELDS = ('balance', 'wager', 'payout')
CURRENCY_FIELD = 'currency'
MESSAGE_FIELD = 'message'
BETSSON_BALANCE_FIELD = 'betsson_balance'   # saldo de la cuenta, en la página fuera del iframe
HUD_FIELDS = MONEY_FIELDS + (CURRENCY_FIELD,)
OCR_FIELDS = HUD_FIELDS + (MESSAGE_FIELD, BETSSON_BALANCE_FIELD)
MONEY_UPSCALE = 4              # importes: más ampliación para distinguir coma de punto
MONEY_CHARS = '0123456789.,€'

# (imagen preprocesada, idioma, config de Tesseract) -> texto. Inyectable en pruebas.
OcrBackend = Callable[[np.ndarray, str, str], str]


def _digits(text: str) -> str:
    return ''.join(c for c in text if c.isdigit())


def _locate_tesseract(pytesseract) -> None:
    """Ruta del ejecutable: TESSERACT_CMD, el PATH o, en Windows, las carpetas de instalación habituales."""
    import os
    import shutil
    cmd = os.environ.get('TESSERACT_CMD')
    if not cmd and not shutil.which('tesseract'):
        for candidate in (r'C:\Program Files\Tesseract-OCR\tesseract.exe',
                          r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
                          os.path.expandvars(r'%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe')):
            if os.path.isfile(candidate):
                cmd = candidate
                break
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd


def tesseract_backend(image: np.ndarray, language: str, config: str) -> str:
    import pytesseract
    _locate_tesseract(pytesseract)
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
             timestamp: Optional[float] = None, roi: Optional[ROI] = None) -> OcrReading:
        """Lee `field` en su región del perfil (o en `roi` si se indica)."""
        if field not in OCR_FIELDS:
            raise ProfileError(f'Campo OCR desconocido {field!r}')
        crop = (roi or self.profile.regions[field]).crop(frame)
        money = field in MONEY_FIELDS
        light = self.profile.light_text if money else None
        # Saldo y apuesta solo contienen importes; el premio se lee sin lista porque puede mostrar «haga su apuesta».
        # Con light_text solo queda el texto blanco (sin etiquetas de color): el importe se lee con lista y el
        # mensaje de reposo con una lectura aparte sin ella.
        whitelist = money and (field != 'payout' or light is not None)
        if light is not None:
            processed = preprocess_light_text(crop, *light)
        else:
            processed = preprocess_for_ocr(crop, MONEY_UPSCALE) if money else preprocess_for_ocr(crop)
        crop_path = self.evidence.save_image(sample_id, field, crop)
        processed_path = self.evidence.save_image(sample_id, f'{field}-ocr', processed)
        if field == 'payout' and self._is_empty(crop):
            return OcrReading(field, sample_id, timestamp, '', '0.00', None, crop_path, processed_path)
        config = '--psm 6' if field == MESSAGE_FIELD else '--psm 7'
        if whitelist:
            config += f' -c tessedit_char_whitelist={MONEY_CHARS}'
        raw = self.backend(processed, self.profile.ocr_language, config).strip()
        value, error = self._interpret(field, raw)
        if whitelist and value is None:
            # Otros modos de segmentación (palabra / línea cruda) corrigen lecturas fallidas distintas por
            # versión de Tesseract. Solo se aceptan si conservan las MISMAS cifras que la lectura principal
            # (p. ej. «4814» -> «48,14»): un modo que pierde una cifra («4,14») daría un valor erróneo.
            primary_digits = _digits(raw)
            for psm in (8, 13):
                retry = self.backend(processed, self.profile.ocr_language,
                                     f'--psm {psm} -c tessedit_char_whitelist={MONEY_CHARS}').strip()
                alt_value, alt_error = self._interpret(field, retry)
                if alt_value is not None and primary_digits and _digits(retry) != primary_digits:
                    error = f'Lecturas con cifras distintas ({raw!r} / {retry!r}): no se acepta ninguna'
                    continue
                if alt_value is not None:
                    raw, value, error = retry, alt_value, alt_error
                    break
        if field == 'payout' and value is None:
            idle_raw = raw
            if light is not None:   # el texto de reposo tiene letras: lectura sin lista de caracteres
                idle_raw = self.backend(processed, self.profile.ocr_language, '--psm 7').strip()
            if self._shows_idle_prompt(idle_raw):
                raw, value, error = idle_raw, '0.00', None   # mensaje de reposo, sin importe
        return OcrReading(field, sample_id, timestamp, raw, value, error, crop_path, processed_path)

    def _shows_idle_prompt(self, raw: str) -> bool:
        text = normalize_text(raw)
        return not any(c.isdigit() for c in text) and any(p.search(text) for p in self.profile.idle_patterns)

    def _is_empty(self, crop: np.ndarray) -> bool:
        """Región sin texto (casi uniforme), solo si el perfil declara que el juego oculta el premio."""
        return self.profile.payout_empty_is_zero and float(to_gray(crop).std()) <= self.profile.empty_region_max_std

    def _interpret(self, field: str, raw: str) -> Tuple[Optional[str], Optional[str]]:
        try:
            if field in MONEY_FIELDS or field == BETSSON_BALANCE_FIELD:
                return str(parse_money(raw, self.profile.decimal_separator)), None
            if field == CURRENCY_FIELD:
                return detect_currency(raw), None
        except ValueError as exc:
            return None, str(exc)
        return None, None  # el mensaje se conserva solo como texto
