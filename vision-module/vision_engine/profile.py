"""Perfil de calibración de UN juego, en UNA resolución y UN mercado.

Todas las coordenadas son píxeles LOCALES de la captura del rectángulo del
juego. El perfil de ejemplo es ilustrativo: `calibrated` debe ponerse a true
solo tras calibrarlo con capturas reales.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Tuple

from .errors import ProfileError
from .geometry import ROI
from .messages import compile_patterns

REQUIRED_REGIONS = ('spin_search', 'reels', 'balance', 'wager', 'payout', 'currency', 'message')

# Moneda esperada e idioma OCR por defecto de cada mercado soportado.
MARKETS = {
    'betsson.com': {'currency': 'EUR', 'ocr_language': 'eng'},
    'betsson.pe': {'currency': 'PEN', 'ocr_language': 'spa+eng'},
}


def _number(value: Any, name: str, *, allow_zero: bool = False) -> float:
    ok = (isinstance(value, (int, float)) and not isinstance(value, bool)
          and math.isfinite(value) and (value > 0 or (allow_zero and value == 0)))
    if not ok:
        raise ProfileError(f'{name} debe ser un número finito {">= 0" if allow_zero else "> 0"}')
    return float(value)


@dataclass(frozen=True)
class MotionSettings:
    """Umbrales de movimiento (media de |diferencia| en gris, 0-255) y tiempos en segundos."""

    start_threshold: float = 8.0
    quiet_threshold: float = 2.0
    quiet_seconds: float = 1.0
    timeout_seconds: float = 20.0

    def __post_init__(self):
        for name in ('start_threshold', 'quiet_threshold', 'quiet_seconds', 'timeout_seconds'):
            _number(getattr(self, name), f'motion.{name}')
        if self.quiet_threshold >= self.start_threshold:
            raise ProfileError('motion.quiet_threshold debe ser menor que motion.start_threshold')


@dataclass(frozen=True)
class ConsensusSettings:
    """Lecturas OCR mínimas en frames distintos y separación temporal entre ellas."""

    min_readings: int = 3
    min_separation_seconds: float = 0.3

    def __post_init__(self):
        if not isinstance(self.min_readings, int) or isinstance(self.min_readings, bool) or self.min_readings < 3:
            raise ProfileError('consensus.min_readings debe ser un entero >= 3')
        _number(self.min_separation_seconds, 'consensus.min_separation_seconds')


@dataclass(frozen=True)
class ReadySettings:
    """Control listo: confianza mínima de la plantilla y margen sobre la plantilla 'ocupado'."""

    threshold: float = 0.85
    busy_margin: float = 0.05

    def __post_init__(self):
        if not 0 < _number(self.threshold, 'ready.threshold') <= 1:
            raise ProfileError('ready.threshold debe estar en (0, 1]')
        _number(self.busy_margin, 'ready.busy_margin', allow_zero=True)


@dataclass(frozen=True)
class GameProfile:
    game: str
    calibrated: bool
    image_size: Tuple[int, int]
    market: str
    expected_currency: str
    ocr_language: str
    decimal_separator: str
    template_threshold: float
    template_scales: Tuple[float, ...]
    insufficient_patterns: Tuple[re.Pattern, ...]
    insufficient_window_seconds: float
    regions: Mapping[str, ROI]
    motion: MotionSettings
    consensus: ConsensusSettings
    ready: ReadySettings

    @classmethod
    def load(cls, path: str | Path) -> 'GameProfile':
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8'))
        except json.JSONDecodeError as exc:
            raise ProfileError(f'Perfil {path} no es JSON válido: {exc}') from exc
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> 'GameProfile':
        try:
            return cls._parse(data)
        except KeyError as exc:
            raise ProfileError(f'Falta el campo obligatorio {exc.args[0]!r} en el perfil') from None
        except TypeError as exc:
            raise ProfileError(f'Perfil con campos inválidos: {exc}') from None

    @classmethod
    def _parse(cls, data: Mapping[str, Any]) -> 'GameProfile':
        size = data['image_size']
        if not (isinstance(size, list) and len(size) == 2
                and all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in size)):
            raise ProfileError('image_size debe ser [ancho, alto] con enteros positivos')
        width, height = size

        market = data['market']
        if market not in MARKETS:
            raise ProfileError(f'Mercado {market!r} no soportado; usar uno de {sorted(MARKETS)}')
        expected_currency = data['expected_currency']
        if expected_currency != MARKETS[market]['currency']:
            raise ProfileError(f'{market} exige moneda {MARKETS[market]["currency"]}, no {expected_currency!r}')

        separator = data['decimal_separator']
        if separator not in ('.', ','):
            raise ProfileError("decimal_separator debe ser '.' o ','")

        threshold = _number(data.get('template_threshold', 0.85), 'template_threshold')
        if threshold > 1:
            raise ProfileError('template_threshold debe estar en (0, 1]')
        scales = tuple(_number(s, 'template_scales') for s in data.get('template_scales', [1.0]))
        if not scales:
            raise ProfileError('template_scales no puede estar vacío')

        raw_regions = data['regions']
        missing = [name for name in REQUIRED_REGIONS if name not in raw_regions]
        if missing:
            raise ProfileError(f'Faltan regiones obligatorias: {missing}')
        regions = {name: ROI.from_list(values, name) for name, values in raw_regions.items()}
        outside = [name for name, roi in regions.items() if not roi.fits(width, height)]
        if outside:
            raise ProfileError(f'Regiones fuera de image_size {size}: {outside}')

        patterns = compile_patterns(data['insufficient_patterns'])
        if not patterns:
            raise ProfileError('insufficient_patterns no puede estar vacío')

        calibrated = data.get('calibrated', False)
        if not isinstance(calibrated, bool):
            raise ProfileError('calibrated debe ser true o false')

        return cls(
            game=str(data.get('game', 'sin-nombre')),
            calibrated=calibrated,
            image_size=(width, height),
            market=market,
            expected_currency=expected_currency,
            ocr_language=data.get('ocr_language', MARKETS[market]['ocr_language']),
            decimal_separator=separator,
            template_threshold=threshold,
            template_scales=scales,
            insufficient_patterns=patterns,
            insufficient_window_seconds=_number(data.get('insufficient_window_seconds', 5.0),
                                                'insufficient_window_seconds'),
            regions=MappingProxyType(regions),
            motion=MotionSettings(**data.get('motion', {})),
            consensus=ConsensusSettings(**data.get('consensus', {})),
            ready=ReadySettings(**data.get('ready', {})),
        )
