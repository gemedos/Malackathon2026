"""Login en betsson.es (solo en el contexto de login, sin vídeo ni traza)."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from playwright.sync_api import Locator

from validator.errors import EvidenceError
from validator.evidence import Evidence
from validator.pages.base_page import BasePage
from validator.secrets import Credentials

log = logging.getLogger(__name__)


class LoginBlockedError(EvidenceError):
    """El sitio pide CAPTCHA, 2FA o verificación por email. No se intenta saltar."""


class LoginFailedError(EvidenceError):
    """El login no se pudo completar o confirmar."""


class LoginPage(BasePage):
    def is_logged_in(self, timeout: float = 0) -> bool:
        sel = self.selectors.login
        return self.find_first(sel.logged_in, timeout, what="sesión-iniciada") is not None

    def login(self, credentials: Credentials, evidence: Evidence) -> str:
        """Autentica y confirma la sesión. Devuelve cómo se confirmó (para el informe)."""
        sel = self.selectors.login
        timeout = self.nav.default_timeout_ms

        self.ensure_site_available(evidence, login_context=True)
        username = self.find_first(sel.username, 2000, what="usuario")
        if username is None:
            # No se pidió login: si ya hay sesión se registra, si no se fuerza (Real Play lo requiere).
            if self.is_logged_in(2000):
                log.info("Ya había una sesión iniciada")
                return "sesión ya iniciada"
            opener = self.find_first(sel.open_button, timeout, what="abrir-login")
            if opener is None:
                self._fail(evidence, "login_no_button.png", "No se encontró el botón de inicio de sesión")
            opener.click()
            username = self.find_first(sel.username, timeout, what="usuario")
        self._check_verification(evidence)
        if username is None:
            self._fail(evidence, "login_no_form.png", "No apareció el campo de usuario del login")

        password = self.find_first(sel.password, timeout, what="contraseña")
        if password is None:
            self._fail(evidence, "login_no_password.png", "No apareció el campo de contraseña")

        username.fill(credentials.username)
        password.fill(credentials.password)
        self._submit(password)
        return self._confirm(evidence, [username, password])

    # ------------------------------------------------------------------ interno

    def _submit(self, password: Locator) -> None:
        """Pulsa el botón de envío del formulario del login (o Enter como último recurso)."""
        form = password.locator("xpath=ancestor::form[1]")
        scope = form if form.count() > 0 else None
        if scope is None:
            dialog = self.page.get_by_role("dialog")
            scope = dialog.first if dialog.count() > 0 else None
        button = None
        if scope is not None:
            button = self.find_first(self.selectors.login.submit, 2000, scope=scope, what="enviar-login")
        if button is not None:
            button.click()
        else:
            log.info("Sin botón de envío dentro del formulario: se usa Enter")
            password.press("Enter")

    def _confirm(self, evidence: Evidence, fields: list[Locator]) -> str:
        sel = self.selectors.login
        deadline = time.monotonic() + self.nav.login_confirm_timeout_ms / 1000
        while time.monotonic() < deadline:
            self._check_verification(evidence, fields)
            if self.is_any_visible(sel.error):
                self._fail(evidence, "login_rejected.png", "Login rechazado por el sitio (credenciales no válidas)", fields)
            if self.is_logged_in(0):
                log.info("Login confirmado por indicador de sesión")
                return "indicador de sesión visible"
            if not self.is_any_visible(sel.open_button) and not self.is_any_visible(sel.password):
                self.page.wait_for_timeout(1500)  # deja asentar la cabecera antes de concluir
                if self.is_logged_in(0) or not self.is_any_visible(sel.open_button):
                    log.info("Login confirmado: el botón de inicio de sesión desapareció")
                    return "botón de login desaparecido"
            self.page.wait_for_timeout(500)
        self._fail(evidence, "login_timeout.png", "No se pudo confirmar el login a tiempo", fields)
        raise AssertionError("inalcanzable")

    def _check_verification(self, evidence: Evidence, fields: list[Locator] | None = None) -> None:
        if self.is_any_visible(self.selectors.login.verification):
            shot = evidence.login_screenshot(self.page, "login_blocked.png", fields)
            raise LoginBlockedError("Login bloqueado por verificación adicional", evidence.relative(shot))

    def _fail(self, evidence: Evidence, shot: str, message: str, fields: list[Locator] | None = None) -> None:
        path: Path | None = evidence.login_screenshot(self.page, shot, fields)
        raise LoginFailedError(message, evidence.relative(path))
