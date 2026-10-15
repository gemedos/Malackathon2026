"""Calibración de un juego y conversión al perfil de vision_engine.

Archivo: config/games/<proveedor-slug>/<juego-slug>.yaml. Las regiones son [x, y, ancho, alto]
normalizadas (0–1) respecto al iframe, así sirven aunque el iframe cambie de tamaño. Las plantillas
(recortes reales del botón Spin) van junto al YAML.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from validator import PROJECT_ROOT
from validator.config import CONFIG_DIR, MarketConfig
from validator.urls import slugify
from vision_engine import GameProfile, Market, load_template
from vision_engine.errors import CalibrationError
from vision_engine.profile import REQUIRED_REGIONS

log = logging.getLogger(__name__)

GAMES_DIR = CONFIG_DIR / "games"
ASPECT_TOLERANCE = 0.03

Region = tuple[float, float, float, float]


class CalibrationMissingError(RuntimeError):
    """El juego no tiene archivo de calibración: no se puede leer la pantalla con garantías."""


class SetupClick(BaseModel):
    """Clic previo al escenario (p. ej. bajar a la apuesta mínima o desactivar turbo)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    point: tuple[float, float]
    repeat: int = Field(default=1, ge=1, le=20)

    @field_validator("point")
    @classmethod
    def _normalized(cls, value: tuple[float, float]) -> tuple[float, float]:
        if not all(0 <= v <= 1 for v in value):
            raise ValueError("point debe estar normalizado (0–1)")
        return value


class GameCalibration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str
    game: str
    calibrated: bool = False
    reference_size: tuple[int, int]            # tamaño del iframe en el que se recortaron las plantillas
    spin_template: str                         # relativo al YAML
    busy_template: str | None = None
    template_threshold: float = Field(default=0.85, gt=0, le=1)
    template_scales: list[float] = Field(default_factory=lambda: [0.9, 1.0, 1.1], min_length=1)
    regions: dict[str, Region]
    payout_empty_is_zero: bool = False
    setup_clicks: list[SetupClick] = Field(default_factory=list)
    insufficient_window_seconds: float = Field(default=5.0, gt=0)
    motion: dict[str, float] = Field(default_factory=dict)
    consensus: dict[str, float] = Field(default_factory=dict)
    ready: dict[str, float] = Field(default_factory=dict)

    @field_validator("regions")
    @classmethod
    def _regions(cls, regions: dict[str, Region]) -> dict[str, Region]:
        missing = [name for name in REQUIRED_REGIONS if name not in regions]
        if missing:
            raise ValueError(f"faltan regiones: {missing}")
        for name, (x, y, w, h) in regions.items():
            if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 and 0 < h <= 1 and x + w <= 1.0001 and y + h <= 1.0001):
                raise ValueError(f"región {name!r} fuera de 0–1: {[x, y, w, h]}")
        return regions


@dataclass(frozen=True)
class LoadedCalibration:
    calibration: GameCalibration
    path: Path

    def template_path(self, name: str) -> Path:
        return self.path.parent / name

    def templates(self) -> tuple[np.ndarray, np.ndarray | None]:
        cal = self.calibration
        spin = load_template(self.template_path(cal.spin_template))
        busy = load_template(self.template_path(cal.busy_template)) if cal.busy_template else None
        return spin, busy


def calibration_path(provider: str, game: str, games_dir: Path = GAMES_DIR) -> Path:
    return games_dir / slugify(provider) / f"{slugify(game)}.yaml"


def load_calibration(provider: str, game: str, games_dir: Path = GAMES_DIR) -> LoadedCalibration:
    path = calibration_path(provider, game, games_dir)
    if not path.is_file():
        shown = path.relative_to(PROJECT_ROOT) if PROJECT_ROOT in path.parents else path
        raise CalibrationMissingError(
            f"Juego sin calibrar: falta {shown}. "
            f"Ejecuta: python scripts/calibrate.py capture --provider \"{provider}\" --game \"{game}\""
        )
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    calibration = GameCalibration.model_validate(data)
    log.info("Calibración cargada: %s (calibrated=%s)", path.name, calibration.calibrated)
    return LoadedCalibration(calibration, path)


def vision_market(market: MarketConfig) -> Market:
    """El mercado de vision_engine a partir de config/markets/<mercado>.yaml (única fuente)."""
    return Market(name=market.market, language=market.language, language_name=market.vision.language_name,
                  currency=market.currency, ocr_language=market.vision.ocr_language,
                  insufficient_patterns=tuple(market.vision.insufficient_patterns))


def to_pixels(region: Region, size: tuple[int, int]) -> list[int]:
    """Región normalizada -> [x, y, ancho, alto] en píxeles, recortada a la imagen."""
    width, height = size
    x, y = round(region[0] * width), round(region[1] * height)
    w, h = max(1, round(region[2] * width)), max(1, round(region[3] * height))
    x, y = min(x, width - 1), min(y, height - 1)
    return [x, y, min(w, width - x), min(h, height - y)]


def build_profile(calibration: GameCalibration, market: MarketConfig, frame_size: tuple[int, int]) -> GameProfile:
    """Perfil de visión en píxeles para el tamaño real de la captura del iframe."""
    width, height = frame_size
    ref_w, ref_h = calibration.reference_size
    if abs(width / height - ref_w / ref_h) > ASPECT_TOLERANCE * (ref_w / ref_h):
        raise CalibrationError(
            f"El iframe mide {width}x{height} y la calibración se hizo a {ref_w}x{ref_h}: proporción distinta, recalibrar"
        )
    factor = width / ref_w   # las plantillas se recortaron a reference_size
    data = {
        "game": f"{calibration.provider} / {calibration.game}",
        "calibrated": calibration.calibrated,
        "image_size": [width, height],
        "market": market.market,
        "expected_currency": market.currency,
        "decimal_separator": market.number_format.decimal,
        "ocr_language": market.vision.ocr_language,
        "template_threshold": calibration.template_threshold,
        "template_scales": [s * factor for s in calibration.template_scales],
        "insufficient_window_seconds": calibration.insufficient_window_seconds,
        "payout_empty_is_zero": calibration.payout_empty_is_zero,
        "regions": {name: to_pixels(region, frame_size) for name, region in calibration.regions.items()},
        "motion": calibration.motion,
        "consensus": {k: int(v) if k == "min_readings" else v for k, v in calibration.consensus.items()},
        "ready": calibration.ready,
    }
    return GameProfile.from_dict(data, {market.market: vision_market(market)})


def skeleton(provider: str, game: str, reference_size: tuple[int, int]) -> str:
    """YAML inicial para calibrar a mano sobre una captura real (calibrated: false)."""
    w, h = reference_size
    return f"""# Calibración de {provider} / {game}. Regiones [x, y, ancho, alto] normalizadas (0–1) respecto al iframe.
# 1) Recorta el botón Spin de una captura real ({w}x{h}) y guárdalo como spin.png junto a este archivo.
# 2) Ajusta cada región y compruébala con: python scripts/calibrate.py check --provider "{provider}" --game "{game}" --image <captura>
# 3) Solo cuando todas las lecturas sean correctas, pon calibrated: true.
provider: "{provider}"
game: "{game}"
calibrated: false
reference_size: [{w}, {h}]
spin_template: spin.png
busy_template: null          # opcional: recorte del botón en estado ocupado/deshabilitado
template_threshold: 0.85
template_scales: [0.9, 1.0, 1.1]
regions:                     # VALORES DE EJEMPLO: ajustar sobre la captura
  spin_search: [0.75, 0.60, 0.25, 0.40]
  reels:       [0.20, 0.10, 0.60, 0.65]
  balance:     [0.02, 0.90, 0.25, 0.08]
  wager:       [0.30, 0.90, 0.20, 0.08]
  payout:      [0.52, 0.90, 0.20, 0.08]
  currency:    [0.02, 0.90, 0.25, 0.08]
  message:     [0.20, 0.25, 0.60, 0.45]
payout_empty_is_zero: false  # true solo si el juego oculta el premio al perder (verificado en capturas)
setup_clicks: []             # p. ej. apuesta mínima: [{{name: "bajar apuesta", point: [0.30, 0.94], repeat: 10}}]
insufficient_window_seconds: 5.0
motion: {{start_threshold: 8.0, quiet_threshold: 2.0, quiet_seconds: 1.0, timeout_seconds: 25.0}}
consensus: {{min_readings: 3, min_separation_seconds: 0.3}}
ready: {{threshold: 0.85, busy_margin: 0.05}}
"""
