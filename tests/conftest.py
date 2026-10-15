"""Opciones de línea de comandos, parametrización por juego y fixtures compartidas.

Prioridad: CLI (--provider/--game/--account/--market) > entorno > valor por defecto.
Juegos a probar (fixture `game`), en este orden:
  1. GAMES_JSON  — lista JSON de nombres (la usa el workflow para cada lote).
  2. --game/GAME — un juego ("Sweet Bonanza" o "Pragmatic Play / Sweet Bonanza").
  3. vacío       — todos los juegos del proveedor según config/catalog/<mercado>.json.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Iterator

import pytest
from playwright.sync_api import Browser, BrowserContext, sync_playwright

from validator.browser import launch_browser
from validator.catalog import ALL_GAMES_OPTION, load_catalog, select_games, split_game_option
from validator.config import MarketConfig, SelectorsConfig, current_market, load_market, load_selectors
from validator.evidence import Evidence
from validator.navigation import CHECK_LOGIN, login, work_context
from validator.results import Checklist, Results
from validator.secrets import ACCOUNTS, load_env_file
from validator.urls import slugify


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("validator")
    group.addoption("--provider", default=None, help="Proveedor (o variable PROVIDER)")
    group.addoption("--game", default=None, help="Juego (o GAME); vacío = todos los del proveedor")
    group.addoption("--account", default=None, help="FUNDED | EMPTY (o variable ACCOUNT; por defecto FUNDED)")
    group.addoption("--market", default=None, help="Mercado (o variable MARKET; por defecto es)")
    group.addoption("--headed", action="store_true", default=False, help="Ver el navegador (o HEADED=1)")


@dataclass(frozen=True)
class RunConfig:
    market: str
    provider: str
    account: str
    headless: bool


def _pick(config: pytest.Config, option: str, env: str) -> str | None:
    value = config.getoption(option)
    if value is None or not str(value).strip():
        value = os.environ.get(env)
    return value.strip() if value and value.strip() else None


def _provider_and_games(config: pytest.Config) -> tuple[str, list[str]]:
    load_env_file()
    market = (_pick(config, "market", "MARKET") or current_market()).lower()
    provider = _pick(config, "provider", "PROVIDER")
    game = _pick(config, "game", "GAME")
    games_json = os.environ.get("GAMES_JSON", "").strip()
    if games_json:
        games = json.loads(games_json)
        if not provider or not isinstance(games, list) or not games:
            raise pytest.UsageError("GAMES_JSON necesita PROVIDER y una lista no vacía de juegos")
        return provider, [str(g) for g in games]
    if game and game != ALL_GAMES_OPTION:
        game_provider, name = split_game_option(game)
        if not (game_provider or provider):
            raise pytest.UsageError("Falta --provider / PROVIDER")
        return game_provider or provider, [name]  # type: ignore[list-item]
    if not provider:
        raise pytest.UsageError("Falta --provider / PROVIDER")
    return select_games(load_catalog(market), provider, None)


def pytest_configure(config: pytest.Config) -> None:
    config._validator_selection = None  # type: ignore[attr-defined]


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Un caso de test por juego para cualquier test que pida la fixture `game`."""
    if "game" not in metafunc.fixturenames:
        return
    config = metafunc.config
    if config._validator_selection is None:  # type: ignore[attr-defined]
        config._validator_selection = _provider_and_games(config)  # type: ignore[attr-defined]
    _, games = config._validator_selection  # type: ignore[attr-defined]
    metafunc.parametrize("game", games, ids=[slugify(g) for g in games])


@pytest.fixture(scope="session")
def run_config(pytestconfig: pytest.Config) -> RunConfig:
    selection = pytestconfig._validator_selection or _provider_and_games(pytestconfig)  # type: ignore[attr-defined]
    account = (_pick(pytestconfig, "account", "ACCOUNT") or "FUNDED").upper()
    if account not in ACCOUNTS:
        pytest.fail(f"ACCOUNT debe ser uno de {ACCOUNTS}", pytrace=False)
    market = (_pick(pytestconfig, "market", "MARKET") or current_market()).lower()
    headed = pytestconfig.getoption("headed") or os.environ.get("HEADED", "") in ("1", "true")
    return RunConfig(market, selection[0], account, headless=not headed)


@pytest.fixture(scope="session")
def market_config(run_config: RunConfig) -> MarketConfig:
    return load_market(run_config.market)


@pytest.fixture(scope="session")
def selectors(run_config: RunConfig) -> SelectorsConfig:
    return load_selectors(run_config.market)


@pytest.fixture(scope="session")
def evidence(run_config: RunConfig) -> Iterator[Evidence]:
    ev = Evidence(run_config.market)
    handler = logging.FileHandler(ev.path("run.log"), mode="a", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)
    yield ev
    logging.getLogger().removeHandler(handler)
    handler.close()


@pytest.fixture(scope="session")
def results(evidence: Evidence) -> Results:
    return Results(evidence.path("navigation_results.json"))


@pytest.fixture(scope="session")
def browser(run_config: RunConfig) -> Iterator[Browser]:
    with sync_playwright() as pw:
        b = launch_browser(pw, headless=run_config.headless)
        yield b
        b.close()


@pytest.fixture(scope="session")
def session_context(browser, run_config, market_config, selectors, evidence, results) -> Iterator[BrowserContext]:
    """Un único login por ejecución (o lote) y un contexto de trabajo compartido por todos los juegos."""
    checklist = Checklist(results, "sesion", run_config.market, run_config.provider, "-", (CHECK_LOGIN,))
    try:
        state = login(browser, market_config, selectors, evidence,
                      provider=run_config.provider, account=run_config.account, check=checklist.check)
    except Exception as exc:
        pytest.fail(f"Login: {type(exc).__name__}: {exc}", pytrace=False)
    with work_context(browser, market_config, evidence, state) as context:
        yield context
