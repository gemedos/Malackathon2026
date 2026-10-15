"""Saldo de la cuenta Betsson (cabecera de la web, fuera del juego).

Fuera del juego se permite el DOM (CLAUDE.md §4), pero la lectura se respalda con OCR de la captura
del mismo elemento: si DOM y OCR discrepan, la muestra no vale. Nunca se recarga la página del juego;
si la cabecera no está en ella, se lee desde una pestaña del lobby.
"""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from decimal import Decimal
from typing import Optional

from playwright.sync_api import BrowserContext, Locator, Page

from validator.config import MarketConfig, SelectorsConfig
from validator.pages.base_page import BasePage
from validator.urls import lobby_url
from vision_engine import OcrReading, VisionEngine, consensus, decode_png, parse_money
from vision_engine.ocr import BETSSON_BALANCE_FIELD

log = logging.getLogger(__name__)


class AccountBalanceReader:
    def __init__(self, context: BrowserContext, game_page: Page, market: MarketConfig,
                 selectors: SelectorsConfig, engine: VisionEngine) -> None:
        self.context = context
        self.game_page = game_page
        self.market = market
        self.selectors = selectors
        self.engine = engine
        self._lobby: Optional[Page] = None

    # ------------------------------------------------------------------ lecturas

    def sample(self, sample_id: str, refresh: bool = False) -> OcrReading:
        """Una muestra del saldo: OCR de la captura del elemento, contrastado con su texto DOM."""
        timestamp = time.monotonic()
        locator = self._locate(refresh)
        if locator is None:
            return OcrReading(BETSSON_BALANCE_FIELD, sample_id, timestamp, '', None,
                              'Saldo Betsson no visible (revisar account.balance en config/selectors)', '', '')
        reading = self.engine.read_image(decode_png(locator.screenshot()), BETSSON_BALANCE_FIELD, sample_id, timestamp)
        return _cross_check(reading, locator.inner_text(timeout=2000), self.market.number_format.decimal)

    def read_series(self, prefix: str, count: int, separation_s: float) -> list[OcrReading]:
        samples = []
        for index in range(count):
            samples.append(self.sample(f"{prefix}-{index:02d}"))
            if index < count - 1:
                self.game_page.wait_for_timeout(separation_s * 1000 + 100)
        return samples

    def poll_after(self, prefix: str, before: Optional[Decimal], count: int, *, expect_change: bool) -> list[OcrReading]:
        """Sondea hasta tener `count` muestras seguidas iguales; si se espera cambio, espera a que llegue
        (o a balance_min_wait_s). Devuelve las últimas `count` muestras para el consenso."""
        settings = self.market.vision
        start = time.monotonic()
        samples: list[OcrReading] = []
        while True:
            samples.append(self.sample(f"{prefix}-{len(samples):02d}", refresh=True))
            last = samples[-count:]
            agreed = consensus(BETSSON_BALANCE_FIELD, last, self.engine.profile.consensus)
            elapsed = time.monotonic() - start
            changed = agreed.agreed and before is not None and Decimal(agreed.value) != before
            if agreed.agreed and (elapsed >= settings.balance_min_wait_s or (expect_change and changed)):
                return last
            if elapsed >= settings.balance_poll_timeout_s:
                log.warning("Saldo Betsson sin lectura estable tras %.0f s", elapsed)
                return last
            self.game_page.wait_for_timeout(settings.balance_poll_interval_s * 1000)

    def close(self) -> None:
        if self._lobby is not None:
            self._lobby.close()
            self._lobby = None

    # ------------------------------------------------------------------ interno

    def _locate(self, refresh: bool) -> Optional[Locator]:
        candidates = self.selectors.account.balance
        if self._lobby is None:
            found = BasePage(self.game_page, self.market, self.selectors).find_first(candidates, 2000, what="saldo-betsson")
            if found is not None:
                return found
            log.info("Saldo Betsson no visible en la página del juego: se lee desde el lobby")
            self._lobby = self.context.new_page()
            self._lobby.goto(lobby_url(self.market), wait_until="domcontentloaded")
        elif refresh:
            self._lobby.reload(wait_until="domcontentloaded")
        return BasePage(self._lobby, self.market, self.selectors).find_first(
            candidates, self.market.navigation.default_timeout_ms, what="saldo-betsson")


def _cross_check(reading: OcrReading, dom_text: str, decimal_separator: str) -> OcrReading:
    try:
        dom = str(parse_money(dom_text, decimal_separator))
    except ValueError:
        dom = None
    raw = f"OCR: {reading.raw_text!r} | DOM: {dom_text.strip()!r}"
    if reading.value is not None and dom is not None and reading.value != dom:
        return replace(reading, raw_text=raw, value=None, error=f"OCR {reading.value} y DOM {dom} no coinciden")
    if reading.value is None and dom is not None:
        return replace(reading, raw_text=raw, value=dom, error=None)   # DOM permitido fuera del juego
    return replace(reading, raw_text=raw)
