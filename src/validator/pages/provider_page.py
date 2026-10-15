"""Página del proveedor: apertura (con plan B), búsqueda de la tarjeta y lanzamiento en Real Play."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from urllib.parse import urlparse

from playwright.sync_api import Locator

from validator.config import SelectorCandidate
from validator.pages.base_page import BasePage, build_locator
from validator.urls import lobby_url, normalize, provider_url

log = logging.getLogger(__name__)


class GameNotFoundError(RuntimeError):
    """No se encontró la tarjeta del juego."""


class DemoOnlyError(RuntimeError):
    """Solo hay opción de demo: Real Play no está disponible."""


class LaunchError(RuntimeError):
    """No se encontró forma de lanzar el juego en Real Play."""


@dataclass
class ProviderOpenResult:
    url: str
    status: int | None
    final_url: str
    plan_b: bool
    reason: str = ""


@dataclass
class CardMatch:
    locator: Locator
    name: str
    exact: bool
    others: list[str] = field(default_factory=list)


class ProviderPage(BasePage):
    # ----------------------------------------------------------------- apertura

    def open(self, provider: str) -> ProviderOpenResult:
        """Abre la URL del proveedor; si da 404 o redirige al lobby, usa el plan B (lobby)."""
        url = provider_url(self.market, provider)
        response = self.page.goto(url, wait_until="domcontentloaded")
        self._settle()
        status = response.status if response is not None else None
        final_url = self.page.url
        reason = self._unusable_reason(url, status, final_url)
        if not reason:
            log.info("URL de proveedor accesible: %s (HTTP %s)", url, status)
            return ProviderOpenResult(url, status, final_url, plan_b=False)
        log.warning("Plan B usado: %s. Se continúa desde el lobby del casino", reason)
        self.page.goto(lobby_url(self.market), wait_until="domcontentloaded")
        self._settle()
        return ProviderOpenResult(url, status, self.page.url, plan_b=True, reason=reason)

    def _unusable_reason(self, url: str, status: int | None, final_url: str) -> str:
        if status is not None and status >= 400:
            return f"HTTP {status} en {url}"
        expected = urlparse(url).path.rstrip("/").lower()
        actual = urlparse(final_url).path.rstrip("/").lower()
        if actual != expected:
            return f"redirección de {expected} a {actual or '/'}"
        if self.is_any_visible(self.selectors.lobby.not_found):
            return "la página muestra 'no encontrado'"
        return ""

    def _settle(self) -> None:
        try:
            self.page.wait_for_load_state("networkidle", timeout=self.nav.settle_timeout_ms)
        except Exception:
            log.info("La red no llegó a reposo en %d ms; se continúa", self.nav.settle_timeout_ms)

    # ------------------------------------------------------------ tarjeta del juego

    def find_game_card(self, game: str) -> CardMatch:
        """Busca la tarjeta por nombre visible, alt o aria-label, prefiriendo la coincidencia exacta.

        Orden: lo visible -> buscador -> scroll. Sin coincidencia exacta falla y lista las candidatas
        (abrir un juego parecido validaría el juego equivocado).
        """
        best = self._match_card(game, self.nav.card_search_timeout_ms)
        if best is None or not best.exact:
            best = self._better(best, self._search(game))
        scrolls = 0
        while (best is None or not best.exact) and scrolls < self.nav.max_scrolls:
            scrolls += 1
            more = self.find_first(self.selectors.lobby.load_more, 0, what="cargar-más")
            if more is not None:
                more.click()
            else:
                self.page.mouse.wheel(0, 1500)
            self.page.wait_for_timeout(800)
            best = self._better(best, self._match_card(game, 0))
        if best is None:
            raise GameNotFoundError(f"No se encontró el juego {game!r}")
        if not best.exact:
            names = sorted({best.name, *best.others})
            raise GameNotFoundError(f"Sin coincidencia exacta para {game!r}; candidatas: {names}")
        if best.others:
            log.info("Varias coincidencias para %r; elegida %r; resto: %s", game, best.name, best.others)
        return best

    @staticmethod
    def _better(current: CardMatch | None, new: CardMatch | None) -> CardMatch | None:
        if new is None:
            return current
        if current is None or (new.exact and not current.exact):
            return new
        return current

    def _search(self, game: str) -> CardMatch | None:
        lobby = self.selectors.lobby
        field_ = self.find_first(lobby.search_input, 1000, what="buscador")
        if field_ is None:
            opener = self.find_first(lobby.search_open, 3000, what="abrir-buscador")
            if opener is None:
                log.warning("No se encontró el buscador")
                return None
            opener.click()
            field_ = self.find_first(lobby.search_input, 5000, what="buscador")
        if field_ is None:
            return None
        field_.fill(game)
        self.page.wait_for_timeout(1500)
        return self._match_card(game, self.nav.card_search_timeout_ms)

    def _match_card(self, game: str, timeout: float) -> CardMatch | None:
        """Reúne las coincidencias de todas las alternativas y prefiere la exacta."""
        first = self.find_first(self.selectors.lobby.game_card, timeout, what="tarjeta-juego", game=game)
        if first is None:
            return None
        wanted = normalize(game)
        seen: list[tuple[str, Locator]] = []
        for candidate in self.selectors.lobby.game_card:
            locator = build_locator(self.page, candidate.render(game=game))
            for index in range(min(locator.count(), 20)):
                item = locator.nth(index)
                try:
                    if not item.is_visible():
                        continue
                    name = self._accessible_name(item)
                except Exception:
                    continue
                if name:
                    seen.append((name, item))
        exact = next(((n, loc) for n, loc in seen if normalize(n) == wanted), None)
        chosen_name, chosen = exact if exact else (seen[0] if seen else (game, first))
        others = sorted({n for n, _ in seen if normalize(n) != normalize(chosen_name)})
        return CardMatch(chosen, chosen_name, exact is not None, others)

    @staticmethod
    def _accessible_name(item: Locator) -> str:
        """Nombre del juego que representa el elemento (aria-label, alt, title o texto)."""
        for attr in ("aria-label", "alt", "title"):
            value = item.get_attribute(attr)
            if value and value.strip():
                return value.strip()
        # El buscador resalta la consulta (<mark>, <b>...): el nombre real es el texto del padre.
        if item.evaluate("e => ['MARK', 'B', 'STRONG', 'EM'].includes(e.tagName)"):
            item = item.locator("xpath=..")
        text = item.inner_text(timeout=1000).strip()
        return text.splitlines()[0].strip() if text else ""

    # ------------------------------------------------------------ lanzamiento

    def launch_real_play(self, card: CardMatch) -> str:
        """Hover/click en la tarjeta y pulsa el botón de Real Play. Falla si solo hay demo."""
        launch = self.selectors.game_launch
        card.locator.scroll_into_view_if_needed()
        card.locator.hover()
        self.page.wait_for_timeout(600)

        # El hover muestra el botón solo en la tarjeta activa: se busca en la página
        # (la web usa shadow DOM, así que no se acota por ancestros con XPath).
        button = self._find_label_button(launch.real_play, self.market.real_play_labels, 2000)
        if button is None and self.is_any_visible(launch.login_required):
            raise LaunchError("La web pide iniciar sesión para jugar: la sesión del login no se conservó")
        if button is None:
            # La tarjeta puede abrir una ficha del juego con los botones de lanzamiento.
            # Con hover, un overlay cubre la imagen: se pulsa en su posición, no en el <img>.
            box = card.locator.bounding_box()
            if box is None:
                raise LaunchError("La tarjeta del juego dejó de estar visible")
            self.page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            self.page.wait_for_timeout(1500)
            button = self._find_label_button(launch.real_play, self.market.real_play_labels, self.nav.launch_button_timeout_ms)
        if button is None:
            demo = self._find_label_button(launch.demo, self.market.demo_labels, 1000)
            if demo is not None:
                raise DemoOnlyError("Solo aparece la opción de demo: Real Play no disponible")
            if self._game_iframe_present():
                log.info("La tarjeta lanzó el juego directamente (sin botón explícito)")
                return "click en la tarjeta"
            raise LaunchError("No se encontró el botón de Real Play")
        label = (button.inner_text(timeout=1000) or "").strip()
        button.click()
        log.info("Real Play lanzado con el botón %r", label)
        return f"botón {label!r}"

    def _find_label_button(self, templates: list[SelectorCandidate], labels: list[str], timeout: float) -> Locator | None:
        """Busca un botón/enlace visible con alguno de los textos configurados."""
        candidates = [t.render(label=label) for label in labels for t in templates]
        return self.find_first(candidates, timeout, what="lanzar")

    def _game_iframe_present(self) -> bool:
        self.page.wait_for_timeout(2000)
        return self.is_any_visible(self.selectors.game.iframe)
