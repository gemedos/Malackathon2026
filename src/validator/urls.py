"""Normalización de texto, slugify y construcción de URLs del mercado."""

from __future__ import annotations

import re
import unicodedata

from validator.config import MarketConfig

# Variantes acentuadas que se aceptan al buscar texto sin distinguir tildes.
_ACCENT_CLASSES = {
    "a": "aáàäâã", "e": "eéèëê", "i": "iíìïî", "o": "oóòöôõ", "u": "uúùüû", "n": "nñ", "c": "cç",
}


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize(text: str) -> str:
    """Minúsculas, sin tildes y con espacios colapsados (para comparar nombres)."""
    return re.sub(r"\s+", " ", strip_accents(text).casefold()).strip()


def slugify(text: str) -> str:
    """'Pragmatic Play' -> 'pragmatic-play'."""
    slug = re.sub(r"[^a-z0-9]+", "-", strip_accents(text).lower())
    return slug.strip("-")


def fuzzy_pattern(text: str, exact: bool = False) -> re.Pattern[str]:
    """Regex que encuentra `text` sin distinguir mayúsculas, tildes ni espacios repetidos."""
    parts: list[str] = []
    for ch in normalize(text):
        if ch == " ":
            parts.append(r"\s+")
        elif ch in _ACCENT_CLASSES:
            parts.append(f"[{_ACCENT_CLASSES[ch]}]")
        else:
            parts.append(re.escape(ch))
    body = "".join(parts)
    return re.compile(rf"^\s*{body}\s*$" if exact else body, re.IGNORECASE)


def provider_slug(market: MarketConfig, provider: str) -> str:
    """Slug del proveedor: primero el override del YAML, si no slugify()."""
    for name, slug in market.provider_slugs.items():
        if normalize(name) == normalize(provider):
            return slug
    return slugify(provider)


def provider_url(market: MarketConfig, provider: str) -> str:
    path = market.provider_path_template.format(provider_slug=provider_slug(market, provider))
    return market.base_url.rstrip("/") + path


def lobby_url(market: MarketConfig) -> str:
    return market.base_url.rstrip("/") + market.lobby_path
