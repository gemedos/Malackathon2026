"""Perfil de calibración de UN juego, en UNA resolución y UN mercado.

Todas las coordenadas son píxeles LOCALES de la captura del rectángulo del
juego. Los datos de cada mercado (idioma, moneda, frases de rechazo) viven en
config/markets.json, separados de la lógica. Los perfiles de ejemplo son
ilustrativos: `calibrated` debe ponerse a true solo tras calibrar con capturas reales.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Tuple

from .errors import ProfileError
from .geometry import ROI
from .messages import compile_patterns

REQUIRED_REGIONS = ('spin_search', 'reels', 'balance', 'wager', 'payout', 'currency', 'message')
DEFAULT_MARKETS_PATH = Path(__file__).resolve().parent.parent / 'config' / 'markets.json'
SUPPORTED_LANGUAGES = ('en', 'es')


@dataclass(frozen=True)
class Market:
    """Configuración de un mercado (config/markets.json)."""

    name: str
    language: str              # 'en' | 'es'
    language_name: str         # 'English' | 'Spanish' (para el informe)
    currency: str              # código ISO esperado
    ocr_language: str          # idiomas de Tesseract
    insufficient_patterns: Tuple[str, ...]


def load_markets(path: str | Path = DEFAULT_MARKETS_PATH) -> Dict[str, Market]:
    try:
        raw = json.loads(Path(path).read_text(encoding='utf-8'))
        markets = {name: Market(name=name, language=d['language'], language_name=d['language_name'],
                                currency=d['currency'], ocr_language=d['ocr_language'],
                                insufficient_patterns=tuple(d['insufficient_patterns']))
                   for name, d in raw.items()}
    except (OSError, json.JSONDecodeError, KeyError, TypeError, AttributeError) as exc:
        raise ProfileError(f'Configuración de mercados inválida en {path}: {exc}') from exc
    for market in markets.values():
        if market.language not in SUPPORTED_LANGUAGES:
            raise ProfileError(f'{market.name}: idioma {market.language!r} no soportado')
    return markets


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
class BetssonPage:
    """Región del saldo Betsson en una captura de la PÁGINA (fuera del iframe del juego)."""

    image_size: Tuple[int, int]
    balance: ROI


@dataclass(frozen=True)
class GameProfile:
    game: str
    calibrated: bool
    image_size: Tuple[int, int]
    market: str
    language: str
    language_name: str
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
    betsson_page: Optional[BetssonPage]
    # Juegos que ocultan el premio al perder: región de premio SIN texto en un frame liquidado = 0.
    # Es una observación positiva (región vacía), no un fallo de OCR. Activar solo tras calibrar.
    payout_empty_is_zero: bool = False
    empty_region_max_std: float = 4.0
    # 'motion': giro terminado = rodillos quietos. 'ready': juegos con animación constante (p. ej. Bubble Up),
    # giro terminado = el control Spin vuelve a estar listo tras verse ocupado.
    settle: str = 'motion'
    idle_patterns: Tuple[re.Pattern, ...] = ()      # línea de premio sin ganancia, p. ej. «haga su apuesta»
    # HUD con importes en texto blanco: (saturación máx., brillo mín.) en HSV para aislar SOLO ese texto antes del
    # OCR (sin fondo, brillos ni etiquetas de color). None = preprocesado por defecto (Otsu en gris).
    light_text: Optional[Tuple[int, int]] = None

    @classmethod
    def load(cls, path: str | Path, markets: Optional[Mapping[str, Market]] = None) -> 'GameProfile':
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8'))
        except json.JSONDecodeError as exc:
            raise ProfileError(f'Perfil {path} no es JSON válido: {exc}') from exc
        return cls.from_dict(data, markets)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any],
                  markets: Optional[Mapping[str, Market]] = None) -> 'GameProfile':
        try:
            return cls._parse(data, markets if markets is not None else load_markets())
        except KeyError as exc:
            raise ProfileError(f'Falta el campo obligatorio {exc.args[0]!r} en el perfil') from None
        except TypeError as exc:
            raise ProfileError(f'Perfil con campos inválidos: {exc}') from None

    @classmethod
    def _parse(cls, data: Mapping[str, Any], markets: Mapping[str, Market]) -> 'GameProfile':
        width, height = size = _image_size(data['image_size'], 'image_size')

        if data['market'] not in markets:
            raise ProfileError(f'Mercado {data["market"]!r} no soportado; usar uno de {sorted(markets)}')
        market = markets[data['market']]
        expected_currency = data['expected_currency']
        if expected_currency != market.currency:
            raise ProfileError(f'{market.name} exige moneda {market.currency}, no {expected_currency!r}')

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
            raise ProfileError(f'Regiones fuera de image_size {list(size)}: {outside}')

        # Las frases del mercado son un punto de partida; el perfil puede ajustarlas al texto real.
        patterns = compile_patterns(data.get('insufficient_patterns') or market.insufficient_patterns)
        if not patterns:
            raise ProfileError('insufficient_patterns no puede estar vacío')

        calibrated = data.get('calibrated', False)
        if not isinstance(calibrated, bool):
            raise ProfileError('calibrated debe ser true o false')

        return cls(
            game=str(data.get('game', 'sin-nombre')),
            calibrated=calibrated,
            image_size=(width, height),
            market=market.name,
            language=market.language,
            language_name=market.language_name,
            expected_currency=expected_currency,
            ocr_language=data.get('ocr_language', market.ocr_language),
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
            betsson_page=_betsson_page(data.get('betsson_page')),
            payout_empty_is_zero=_flag(data.get('payout_empty_is_zero', False), 'payout_empty_is_zero'),
            empty_region_max_std=_number(data.get('empty_region_max_std', 4.0), 'empty_region_max_std'),
            settle=_settle(data.get('settle', 'motion')),
            idle_patterns=_idle_patterns(data.get('idle_patterns', [])),
            light_text=_light_text(data.get('light_text')),
        )


def _light_text(value: Any) -> Optional[Tuple[int, int]]:
    if value is None:
        return None
    if not (isinstance(value, Mapping) and set(value) == {'max_saturation', 'min_value'}
            and all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 255 for v in value.values())):
        raise ProfileError('light_text debe ser {max_saturation: 0-255, min_value: 0-255}')
    return value['max_saturation'], value['min_value']


def _settle(value: Any) -> str:
    if value not in ('motion', 'ready'):
        raise ProfileError("settle debe ser 'motion' o 'ready'")
    return value


def _idle_patterns(values: Any) -> Tuple[re.Pattern, ...]:
    """Frases (minúsculas, sin tildes) que muestra la línea de premio cuando NO hay ganancia."""
    if not isinstance(values, list):
        raise ProfileError('idle_patterns debe ser una lista de expresiones')
    compiled = []
    for pattern in values:
        try:
            compiled.append(re.compile(pattern))
        except (re.error, TypeError) as exc:
            raise ProfileError(f'idle_patterns inválido {pattern!r}: {exc}') from exc
    return tuple(compiled)


def _flag(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ProfileError(f'{name} debe ser true o false')
    return value


def _image_size(value: Any, name: str) -> Tuple[int, int]:
    if not (isinstance(value, list) and len(value) == 2
            and all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in value)):
        raise ProfileError(f'{name} debe ser [ancho, alto] con enteros positivos')
    return value[0], value[1]


def _betsson_page(data: Optional[Mapping[str, Any]]) -> Optional[BetssonPage]:
    if data is None:
        return None
    size = _image_size(data['image_size'], 'betsson_page.image_size')
    balance = ROI.from_list(data['balance'], 'betsson_page.balance')
    if not balance.fits(*size):
        raise ProfileError('betsson_page.balance fuera de betsson_page.image_size')
    return BetssonPage(size, balance)
