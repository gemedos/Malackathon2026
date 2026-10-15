"""Banner de cookies: se prefiere rechazar las no esenciales."""

from __future__ import annotations

import logging

from validator.pages.base_page import BasePage

log = logging.getLogger(__name__)


class CookieBanner(BasePage):
    def handle(self, timeout: float | None = None) -> str:
        """Cierra el banner si aparece. Devuelve 'rechazadas', 'aceptadas' o 'sin banner'."""
        timeout = timeout if timeout is not None else self.nav.cookie_banner_timeout_ms
        cookies = self.selectors.cookies
        # Espera a que aparezca cualquier botón del banner (rechazar, configurar o aceptar).
        if self.find_first([*cookies.reject, *cookies.settings, *cookies.accept], timeout, what="cookies") is None:
            log.info("No apareció banner de cookies")
            return "sin banner"
        button = self.find_first(cookies.reject, 0, what="cookies-rechazar")
        if button is None:
            settings = self.find_first(cookies.settings, 0, what="cookies-configurar")
            if settings is not None:
                settings.click()
                button = self.find_first(cookies.reject, 5000, what="cookies-rechazar")
        outcome = "rechazadas"
        if button is None:
            button = self.find_first(cookies.accept, 1000, what="cookies-aceptar")
            outcome = "aceptadas"
        if button is None:
            log.info("No apareció banner de cookies")
            return "sin banner"
        button.click()
        self.page.wait_for_timeout(500)
        log.info("Banner de cookies cerrado: %s", outcome)
        return outcome
