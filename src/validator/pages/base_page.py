"""Base de los page objects: localización por listas de alternativas configuradas en YAML."""

from __future__ import annotations

import logging
import time
from typing import Union

from playwright.sync_api import FrameLocator, Locator, Page

from validator.config import MarketConfig, SelectorCandidate, SelectorsConfig
from validator.urls import fuzzy_pattern

log = logging.getLogger(__name__)

Scope = Union[Page, Locator, FrameLocator]
POLL_MS = 250


def build_locator(scope: Scope, candidate: SelectorCandidate) -> Locator:
    """Traduce un candidato del YAML a un locator de Playwright."""
    c = candidate

    def value(text: str):
        return fuzzy_pattern(text, exact=c.exact) if c.fuzzy else text

    if c.role is not None:
        if c.name is None:
            return scope.get_by_role(c.role)  # type: ignore[arg-type]
        return scope.get_by_role(c.role, name=value(c.name), exact=c.exact or None)  # type: ignore[arg-type]
    if c.label is not None:
        return scope.get_by_label(value(c.label), exact=c.exact or None)
    if c.placeholder is not None:
        return scope.get_by_placeholder(value(c.placeholder), exact=c.exact or None)
    if c.text is not None:
        return scope.get_by_text(value(c.text), exact=c.exact or None)
    if c.alt_text is not None:
        return scope.get_by_alt_text(value(c.alt_text), exact=c.exact or None)
    if c.title is not None:
        return scope.get_by_title(value(c.title), exact=c.exact or None)
    assert c.css is not None
    return scope.locator(c.css)


class BasePage:
    def __init__(self, page: Page, market: MarketConfig, selectors: SelectorsConfig) -> None:
        self.page = page
        self.market = market
        self.selectors = selectors
        self.nav = market.navigation

    def find_first(
        self,
        candidates: list[SelectorCandidate],
        timeout: float,
        *,
        scope: Scope | None = None,
        what: str = "elemento",
        **params: str,
    ) -> Locator | None:
        """Devuelve el primer candidato visible antes de `timeout` ms (o None).

        Todas las alternativas se sondean en cada vuelta, así una alternativa lenta
        no consume el tiempo de las demás. Registra en el log cuál funcionó.
        """
        if not candidates:
            return None
        root = scope if scope is not None else self.page
        rendered = [c.render(**params) for c in candidates]
        locators = [build_locator(root, c) for c in rendered]
        deadline = time.monotonic() + timeout / 1000
        while True:
            for candidate, locator in zip(rendered, locators):
                visible = self._first_visible(locator, last=candidate.last)
                if visible is not None:
                    log.info("find_first[%s]: funcionó %s", what, candidate.describe())
                    return visible
            if time.monotonic() >= deadline:
                quiet = what.startswith("pregame:") or what == "sesión-iniciada"
                (log.debug if quiet else log.info)("find_first[%s]: ninguna alternativa visible en %d ms", what, timeout)
                return None
            self.page.wait_for_timeout(POLL_MS)

    def is_any_visible(self, candidates: list[SelectorCandidate], *, scope: Scope | None = None, **params: str) -> bool:
        """Comprobación instantánea (sin espera)."""
        root = scope if scope is not None else self.page
        return any(
            self._first_visible(build_locator(root, c.render(**params))) is not None for c in candidates
        )

    @staticmethod
    def _first_visible(locator: Locator, limit: int = 10, last: bool = False) -> Locator | None:
        try:
            count = locator.count()
        except Exception:
            return None
        indexes = range(min(count, limit))
        for index in (reversed(indexes) if last else indexes):
            item = locator.nth(index)
            try:
                if item.is_visible():
                    return item
            except Exception:
                continue
        return None
