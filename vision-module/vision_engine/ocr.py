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
from .imaging import preprocess_for_ocr, strip_trailing_symbol, to_gray
from .messages import normalize_text
from .money import parse_money_lenient
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
        # Saldo y apuesta solo contienen importes; el premio se lee sin lista porque puede mostrar «haga su apuesta».
        whitelist = money and field != 'payout'
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
            # versión de Tesseract. La interpretación sigue siendo estricta: no se adivina nada.
            for psm in (8, 13):
                retry = self.backend(processed, self.profile.ocr_language,
                                     f'--psm {psm} -c tessedit_char_whitelist={MONEY_CHARS}').strip()
                alt_value, alt_error = self._interpret(field, retry)
                if alt_value is not None:
                    raw, value, error = retry, alt_value, alt_error
                    break
        if whitelist and value is None:
            # El símbolo de moneda («€») se lee a veces como un dígito pegado al importe: se vuelve a leer sin él.
            stripped = strip_trailing_symbol(processed)
            if stripped is not None:
                retry = self.backend(stripped, self.profile.ocr_language,
                                     f'--psm 7 -c tessedit_char_whitelist={MONEY_CHARS}').strip()
                alt_value, alt_error = self._interpret(field, retry, symbol_seen=True)
                if alt_value is not None:
                    raw, value, error = retry, alt_value, alt_error
        if field == 'payout' and value is None and self._shows_idle_prompt(raw):
            value, error = '0.00', None       # la línea de premio muestra el mensaje de reposo, sin importe
        return OcrReading(field, sample_id, timestamp, raw, value, error, crop_path, processed_path)

    def read_wide_message(self, frame: np.ndarray, sample_id: str, timestamp: Optional[float] = None) -> OcrReading:
        """Texto de TODA la zona central del juego, para cuando el mensaje no está donde la calibración espera
        (otro juego, otro diálogo). Más lento que la región calibrada: se usa solo como respaldo."""
        height = frame.shape[0]
        band = frame[int(0.12 * height):int(0.88 * height)]
        gray = to_gray(band)
        texts = []
        for image in (gray, 255 - gray):
            processed = preprocess_for_ocr(image, 2)
            texts.append(self.backend(processed, self.profile.ocr_language, '--psm 11').strip())
        raw = '\n'.join(t for t in texts if t)
        crop_path = self.evidence.save_image(sample_id, 'message-wide', band)
        return OcrReading(MESSAGE_FIELD, sample_id, timestamp, raw, None, None, crop_path, crop_path)

    def _shows_idle_prompt(self, raw: str) -> bool:
        text = normalize_text(raw)
        return not any(c.isdigit() for c in text) and any(p.search(text) for p in self.profile.idle_patterns)

    def _is_empty(self, crop: np.ndarray) -> bool:
        """Región sin texto (casi uniforme), solo si el perfil declara que el juego oculta el premio."""
        return self.profile.payout_empty_is_zero and float(to_gray(crop).std()) <= self.profile.empty_region_max_std

    def _interpret(self, field: str, raw: str, symbol_seen: bool = False) -> Tuple[Optional[str], Optional[str]]:
        try:
            if field in MONEY_FIELDS or field == BETSSON_BALANCE_FIELD:
                # Solo la apuesta puede ser un entero («2 €»); un saldo o un premio sin decimales sería una lectura recortada.
                integer_ok = field == 'wager' and (symbol_seen or '€' in raw or 'EUR' in raw.upper())
                return str(parse_money_lenient(raw, self.profile.decimal_separator, integer_ok)), None
            if field == CURRENCY_FIELD:
                return detect_currency(raw), None
        except ValueError as exc:
            return None, str(exc)
        return None, None  # el mensaje se conserva solo como texto
