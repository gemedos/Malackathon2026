"""Catálogo de proveedores y juegos: scrape de betsson.es, carga y selección de juegos a probar.

El catálogo (`config/catalog/<mercado>.json`) alimenta los desplegables del workflow de GitHub
y la lista de juegos cuando se pide "todos los juegos del proveedor".
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from validator.config import CONFIG_DIR, MarketConfig
from validator.urls import normalize, provider_slug

log = logging.getLogger(__name__)

ALL_GAMES_OPTION = "(todos los juegos del proveedor)"
OPTION_SEPARATOR = " / "


class CatalogGame(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    slug: str
    type: str


class CatalogProvider(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    slug: str
    games: list[CatalogGame] = Field(default_factory=list)


class Catalog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market: str
    scraped_at: str
    source: str
    providers: list[CatalogProvider]

    # ----------------------------------------------------------------- consultas

    def provider(self, name: str) -> CatalogProvider:
        wanted = normalize(name)
        for p in self.providers:
            if normalize(p.name) == wanted or p.slug == wanted.replace(" ", "-"):
                return p
        raise CatalogError(f"Proveedor {name!r} no está en el catálogo. Disponibles: {[p.name for p in self.providers]}")

    def game_options(self) -> list[str]:
        """Opciones del desplegable de juego: 'Proveedor / Juego', ordenadas."""
        return [f"{p.name}{OPTION_SEPARATOR}{g.name}" for p in self.providers for g in p.games]

    def content_key(self) -> str:
        """Contenido sin la fecha, para saber si el scrape cambió algo."""
        return json.dumps([p.model_dump() for p in self.providers], ensure_ascii=False, sort_keys=True)


class CatalogError(RuntimeError):
    """Catálogo ausente, inválido o selección imposible."""


# --------------------------------------------------------------------- archivo


def catalog_path(market: str) -> Path:
    return CONFIG_DIR / "catalog" / f"{market}.json"


def load_catalog(market: str) -> Catalog:
    path = catalog_path(market)
    if not path.is_file():
        raise CatalogError(f"No existe {path}. Genera el catálogo con: python scripts/update_catalog.py")
    return Catalog.model_validate_json(path.read_text(encoding="utf-8"))


def save_catalog(catalog: Catalog) -> Path:
    path = catalog_path(catalog.market)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog.model_dump(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


# ------------------------------------------------------------------- selección


def split_game_option(value: str) -> tuple[str | None, str]:
    """'Pragmatic Play / Sweet Bonanza' -> ('Pragmatic Play', 'Sweet Bonanza'); 'Sweet Bonanza' -> (None, ...)."""
    if OPTION_SEPARATOR in value:
        provider, game = value.split(OPTION_SEPARATOR, 1)
        return provider.strip(), game.strip()
    return None, value.strip()


def select_games(catalog: Catalog, provider: str, game: str | None) -> tuple[str, list[str]]:
    """Resuelve (proveedor, juegos) a partir de lo elegido en el workflow o en el CLI.

    - Juego vacío o ALL_GAMES_OPTION: todos los juegos del proveedor.
    - 'Proveedor / Juego': el proveedor del juego manda (se avisa si difiere del elegido).
    - Nombre suelto: debe existir en el proveedor elegido.
    """
    if not game or game.strip() in ("", ALL_GAMES_OPTION):
        p = catalog.provider(provider)
        if not p.games:
            raise CatalogError(f"El proveedor {p.name!r} no tiene juegos en el catálogo")
        return p.name, [g.name for g in p.games]
    game_provider, game_name = split_game_option(game)  # si el juego trae proveedor, manda el suyo
    p = catalog.provider(game_provider or provider)
    match = next((g for g in p.games if normalize(g.name) == normalize(game_name)), None)
    if match is None:
        raise CatalogError(f"El juego {game_name!r} no está en el catálogo de {p.name!r}")
    return p.name, [match.name]


# ------------------------------------------------------------------------ scrape


def scrape_catalog(market: MarketConfig, headless: bool = True) -> Catalog:
    """Abre la página de proveedores como un navegador normal y captura las APIs del catálogo."""
    from playwright.sync_api import sync_playwright

    from validator.browser import launch_browser, new_context
    from validator.config import load_selectors
    from validator.pages.cookie_banner import CookieBanner

    cfg = market.catalog
    wanted = {cfg.games_api_path: "games", cfg.studios_api_path: "studios"}
    captured: dict[str, list] = {}
    page_url = market.base_url.rstrip("/") + cfg.providers_page_path
    link_prefix = market.provider_path_template.split("{provider_slug}")[0]

    with sync_playwright() as pw:
        browser = launch_browser(pw, headless=headless)
        try:
            context = new_context(browser, market)
            page = context.new_page()

            def on_response(response) -> None:
                path = response.url.split("?")[0].removeprefix(market.base_url.rstrip("/"))
                if path in wanted and response.ok:
                    try:
                        captured[wanted[path]] = response.json()
                        log.info("Capturada la API %s", path)
                    except Exception as exc:
                        log.warning("Respuesta no JSON en %s: %s", path, type(exc).__name__)

            page.on("response", on_response)
            page.goto(page_url, wait_until="domcontentloaded")
            CookieBanner(page, market, load_selectors(market.market)).handle()
            deadline = time.monotonic() + 60
            while len(captured) < len(wanted) and time.monotonic() < deadline:
                page.wait_for_timeout(500)
            for _ in range(6):  # la lista de proveedores puede cargarse al hacer scroll
                page.mouse.wheel(0, 2000)
                page.wait_for_timeout(500)
            slugs = _provider_slugs_in_page(page, link_prefix)
        finally:
            browser.close()

    missing = [name for name in wanted.values() if name not in captured]
    if missing:
        raise CatalogError(f"No se capturaron las APIs del catálogo: {missing}")
    return _build_catalog(market, captured["games"], captured["studios"], slugs, page_url)


def _provider_slugs_in_page(page, link_prefix: str) -> set[str]:
    """Slugs de los enlaces a páginas de proveedor (la web usa shadow DOM: se recorre entero)."""
    hrefs: list[str] = page.evaluate(
        """(prefix) => {
            const out = [];
            const walk = (root) => root.querySelectorAll('*').forEach((el) => {
                const href = el.tagName === 'A' ? (el.getAttribute('href') || '') : '';
                if (href.includes(prefix)) out.push(href);
                if (el.shadowRoot) walk(el.shadowRoot);
            });
            walk(document);
            return out;
        }""",
        link_prefix,
    )
    slugs = {h.split(link_prefix, 1)[1].strip("/").split("/")[0].split("?")[0] for h in hrefs}
    return {s for s in slugs if s}


def _build_catalog(market: MarketConfig, games: list, studios: list, page_slugs: set[str], source: str) -> Catalog:
    cfg = market.catalog
    providers: list[CatalogProvider] = []
    for studio in studios:
        name = str(studio.get("name") or studio.get("id") or "").strip()
        slug = provider_slug(market, name)
        if not name or slug not in page_slugs:
            continue  # sin página de proveedor (p. ej. apuestas deportivas)
        seen: set[str] = set()
        items: list[CatalogGame] = []
        for g in games:
            if g.get("gameStudio") != name or g.get("primaryType") not in cfg.game_types:
                continue
            game_name = str(g.get("name", "")).strip()
            if not game_name or normalize(game_name) in seen:
                continue
            seen.add(normalize(game_name))
            items.append(CatalogGame(id=g["id"], name=game_name, slug=g.get("slug", ""), type=g["primaryType"]))
        items.sort(key=lambda x: normalize(x.name))
        if items:
            providers.append(CatalogProvider(name=name, slug=slug, games=items))
    providers.sort(key=lambda p: normalize(p.name))

    total = sum(len(p.games) for p in providers)
    if len(providers) < cfg.min_providers or total < cfg.min_games:
        raise CatalogError(
            f"Scrape sospechoso: {len(providers)} proveedores y {total} juegos "
            f"(mínimos {cfg.min_providers}/{cfg.min_games}). No se actualiza el catálogo."
        )
    unmatched = sorted(page_slugs - {p.slug for p in providers})
    if unmatched:
        log.warning("Proveedores con página pero sin juegos de tipo %s: %s", cfg.game_types, unmatched)
    log.info("Catálogo: %d proveedores, %d juegos", len(providers), total)
    return Catalog(
        market=market.market,
        scraped_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        source=source,
        providers=providers,
    )
