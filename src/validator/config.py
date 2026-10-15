"""Carga y validación (pydantic) de la configuración de mercado y de selectores."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from validator import PROJECT_ROOT

log = logging.getLogger(__name__)

CONFIG_DIR = PROJECT_ROOT / "config"
STRATEGIES = ("role", "label", "placeholder", "text", "alt_text", "title", "css")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------- mercado


class NumberFormat(_Strict):
    decimal: str
    thousands: str


class NavigationSettings(_Strict):
    default_timeout_ms: int = 15_000
    navigation_timeout_ms: int = 45_000
    settle_timeout_ms: int = 3_000
    cookie_banner_timeout_ms: int = 6_000
    login_confirm_timeout_ms: int = 30_000
    card_search_timeout_ms: int = 8_000
    max_scrolls: int = 12
    launch_button_timeout_ms: int = 6_000
    iframe_timeout_ms: int = 45_000
    iframe_min_width: int = 400
    iframe_min_height: int = 300
    iframe_stable_ms: int = 2_000
    canvas_poll_ms: int = 500
    canvas_timeout_ms: int = 60_000
    canvas_diff_threshold: float = 0.02
    canvas_pixel_delta: int = 12
    canvas_min_stddev: float = 6.0


class CatalogSettings(_Strict):
    providers_page_path: str
    games_api_path: str
    studios_api_path: str
    game_types: list[str] = Field(min_length=1)
    min_providers: int = 10
    min_games: int = 200


class VisionMarketSettings(_Strict):
    """Datos del mercado que necesita la lectura visual del juego."""

    language_name: str
    ocr_language: str = "spa"
    insufficient_patterns: list[str] = Field(min_length=1)
    balance_poll_interval_s: float = Field(default=2.0, gt=0)
    balance_poll_timeout_s: float = Field(default=30.0, gt=0)
    balance_min_wait_s: float = Field(default=6.0, ge=0)


class MarketConfig(_Strict):
    market: str
    base_url: str
    provider_path_template: str
    lobby_path: str
    language: str
    locale: str
    timezone: str
    currency: str
    currency_symbols: list[str]
    number_format: NumberFormat
    provider_slugs: dict[str, str] = Field(default_factory=dict)
    real_play_labels: list[str] = Field(min_length=1)
    demo_labels: list[str] = Field(default_factory=list)
    demo_url_markers: list[str] = Field(default_factory=list)
    real_play_url_markers: list[str] = Field(default_factory=list)
    navigation: NavigationSettings = Field(default_factory=NavigationSettings)
    catalog: CatalogSettings
    vision: VisionMarketSettings

    @model_validator(mode="after")
    def _check(self) -> "MarketConfig":
        if not self.base_url.startswith("https://"):
            raise ValueError("base_url debe ser https://")
        if "{provider_slug}" not in self.provider_path_template:
            raise ValueError("provider_path_template debe contener {provider_slug}")
        return self


# ------------------------------------------------------------------------ selectores


class SelectorCandidate(_Strict):
    """Una alternativa de localización. Exactamente una estrategia por candidato."""

    role: str | None = None
    name: str | None = None
    label: str | None = None
    placeholder: str | None = None
    text: str | None = None
    alt_text: str | None = None
    title: str | None = None
    css: str | None = None
    exact: bool = False
    fuzzy: bool = False
    last: bool = False     # si hay varias coincidencias visibles, la última (la que está encima en el DOM)

    @model_validator(mode="after")
    def _one_strategy(self) -> "SelectorCandidate":
        used = [s for s in STRATEGIES if getattr(self, s) is not None]
        if len(used) != 1:
            raise ValueError(f"cada candidato necesita exactamente una estrategia, tiene {used}")
        if self.name is not None and self.role is None:
            raise ValueError("'name' solo se usa junto a 'role'")
        if self.exact and self.fuzzy:
            raise ValueError("'exact' y 'fuzzy' son incompatibles")
        return self

    @property
    def strategy(self) -> str:
        return next(s for s in STRATEGIES if getattr(self, s) is not None)

    def describe(self) -> str:
        """Descripción legible para el log (sin datos sensibles: son textos de la UI)."""
        value = getattr(self, self.strategy)
        extra = f", name={self.name!r}" if self.name is not None else ""
        flags = "".join([" exact" if self.exact else "", " fuzzy" if self.fuzzy else ""])
        return f"{self.strategy}={value!r}{extra}{flags}"

    def render(self, **params: str) -> "SelectorCandidate":
        """Sustituye plantillas ({game}, {label}) en los valores de texto."""
        if not params:
            return self
        updates: dict[str, Any] = {}
        for field in (*STRATEGIES, "name"):
            value = getattr(self, field)
            if isinstance(value, str) and "{" in value:
                updates[field] = value.format(**params)
        return self.model_copy(update=updates) if updates else self


Candidates = list[SelectorCandidate]


class CookieSelectors(_Strict):
    reject: Candidates = Field(default_factory=list)
    settings: Candidates = Field(default_factory=list)
    accept: Candidates = Field(default_factory=list)


class LoginSelectors(_Strict):
    open_button: Candidates
    username: Candidates
    password: Candidates
    submit: Candidates
    logged_in: Candidates
    error: Candidates = Field(default_factory=list)
    verification: Candidates = Field(default_factory=list)


class LobbySelectors(_Strict):
    not_found: Candidates = Field(default_factory=list)
    search_open: Candidates = Field(default_factory=list)
    search_input: Candidates = Field(default_factory=list)
    load_more: Candidates = Field(default_factory=list)
    game_card: Candidates


class PregameScreen(_Strict):
    """Pantalla previa al juego (aviso regulatorio, límites, panel de torneos...).

    Se detecta por texto visible y se resuelve pulsando `steps` en orden. En cada pasada se resuelve UNA
    pantalla; el orden de la lista decide cuál tiene prioridad si varias coinciden."""

    name: str
    detect: Candidates = Field(min_length=1)
    # Cada paso es una alternativa o una lista de alternativas (se pulsa la primera visible).
    steps: list[SelectorCandidate | list[SelectorCandidate]] = Field(min_length=1)


class GameLaunchSelectors(_Strict):
    real_play: Candidates
    login_required: Candidates = Field(default_factory=list)
    demo: Candidates = Field(default_factory=list)
    session_limits_indicator: Candidates = Field(default_factory=list)
    session_limits_steps: Candidates = Field(default_factory=list)
    pregame: list[PregameScreen] = Field(default_factory=list)


class GameSelectors(_Strict):
    iframe: Candidates


class AccountSelectors(_Strict):
    balance: Candidates = Field(default_factory=list)


class SelectorsConfig(_Strict):
    cookies: CookieSelectors
    login: LoginSelectors
    lobby: LobbySelectors
    game_launch: GameLaunchSelectors
    game: GameSelectors
    account: AccountSelectors = Field(default_factory=AccountSelectors)


# ------------------------------------------------------------------------- carga


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"No existe el archivo de configuración: {path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} debe contener un mapa YAML")
    return data


def current_market() -> str:
    """Clave de mercado activa (variable MARKET; por defecto 'es')."""
    return os.environ.get("MARKET", "es").strip().lower() or "es"


@lru_cache(maxsize=None)
def load_market(market: str) -> MarketConfig:
    cfg = MarketConfig.model_validate(_read_yaml(CONFIG_DIR / "markets" / f"{market}.yaml"))
    if cfg.market != market:
        raise ValueError(f"config/markets/{market}.yaml declara market={cfg.market!r}")
    log.info("Mercado cargado: %s (%s)", cfg.market, cfg.base_url)
    return cfg


@lru_cache(maxsize=None)
def load_selectors(market: str) -> SelectorsConfig:
    return SelectorsConfig.model_validate(_read_yaml(CONFIG_DIR / "selectors" / f"{market}.yaml"))
