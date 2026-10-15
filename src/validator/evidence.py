"""Evidencias (capturas, vídeo y traza) con reglas anti-secretos.

- Durante el login: solo capturas con máscara sobre TODOS los campos de entrada; sin vídeo ni traza.
- Tras el login: contexto nuevo con vídeo y traza; cada juego guarda los suyos en su carpeta.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from playwright.sync_api import Locator, Page

from validator import PROJECT_ROOT
from validator.urls import slugify

log = logging.getLogger(__name__)

ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
AUTH_DIR = PROJECT_ROOT / ".auth"


class Evidence:
    """Carpeta de evidencias: `artifacts/<mercado>/` o `artifacts/<mercado>/<proveedor>/<juego>/`."""

    def __init__(self, market: str, subdir: str | None = None) -> None:
        self.market = market
        self.root = ARTIFACTS_DIR / market
        self.dir = self.root / subdir if subdir else self.root
        self.dir.mkdir(parents=True, exist_ok=True)
        self.video_dir = self.root / "_video_tmp"   # grabación en curso; se mueve a la carpeta del juego
        self.trace_path = self.dir / "trace.zip"

    def for_game(self, provider: str, game: str) -> "Evidence":
        return Evidence(self.market, f"{slugify(provider)}/{slugify(game)}")

    def for_scenario(self, provider: str, game: str, scenario: str) -> "Evidence":
        """`artifacts/<mercado>/<proveedor>/<juego>/<escenario>/` (traza, vídeo y visión propios)."""
        return Evidence(self.market, f"{slugify(provider)}/{slugify(game)}/{scenario}")

    # -- rutas -------------------------------------------------------------

    def path(self, name: str) -> Path:
        return self.dir / name

    def relative(self, path: Path | None) -> str | None:
        if path is None:
            return None
        try:
            return path.resolve().relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            return path.as_posix()

    def storage_state_path(self, account: str) -> Path:
        AUTH_DIR.mkdir(parents=True, exist_ok=True)
        return AUTH_DIR / f"{self.market}-{account.lower()}.json"

    # -- capturas ------------------------------------------------------------

    def login_screenshot(self, page: Page, name: str, extra_mask: list[Locator] | None = None) -> Path | None:
        """Captura en el contexto de login: enmascara todos los inputs y los campos indicados."""
        mask = [page.locator("input"), page.locator("textarea"), *(extra_mask or [])]
        return self._shot(page, name, mask)

    def screenshot(self, page: Page, name: str) -> Path | None:
        """Captura en el contexto de trabajo (posterior al login)."""
        return self._shot(page, name, [])

    def element_screenshot(self, locator: Locator, name: str) -> Path | None:
        target = self.path(name)
        try:
            locator.screenshot(path=str(target), animations="allow")
        except Exception as exc:  # la evidencia nunca debe tapar el error real
            log.warning("No se pudo guardar la captura %s: %s", name, type(exc).__name__)
            return None
        log.info("Evidencia guardada: %s", self.relative(target))
        return target

    def _shot(self, page: Page, name: str, mask: list[Locator]) -> Path | None:
        target = self.path(name)
        try:
            page.screenshot(path=str(target), mask=mask, mask_color="#000000", full_page=False)
        except Exception as exc:
            log.warning("No se pudo guardar la captura %s: %s", name, type(exc).__name__)
            return None
        log.info("Evidencia guardada: %s", self.relative(target))
        return target

    # -- vídeo -----------------------------------------------------------------

    def save_videos(self, pages: list[Page], name: str = "video.webm") -> None:
        """Guarda el vídeo de cada página (ya cerrada) en la carpeta de evidencias."""
        for index, page in enumerate(pages):
            if page.video is None:
                continue
            target = self.path(name if index == 0 else f"{index}_{name}")
            try:
                page.video.save_as(target)
                page.video.delete()
                log.info("Vídeo guardado: %s", self.relative(target))
            except Exception as exc:
                log.warning("No se pudo guardar el vídeo: %s", type(exc).__name__)

    def cleanup(self) -> None:
        shutil.rmtree(self.video_dir, ignore_errors=True)
