"""Comprobación previa de red: el runner debe salir a internet desde España y betsson.es debe responder.

    python scripts/ci/geo_check.py                  # país de salida + sonda del sitio con Chromium
    python scripts/ci/geo_check.py --no-site-probe  # solo país de salida

Salida: 0 = OK · 1 = salida fuera de España, sitio bloqueado o verificación anti-bot · 2 = error de configuración
(ningún servicio de geolocalización respondió). Solo diagnostica: nunca intenta saltar un bloqueo.
Los servicios devuelven solo el código de país, así que la IP del runner no aparece en ningún log.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src")]

from validator.config import MarketConfig, current_market, load_market  # noqa: E402

GEO_CONFIG = ROOT / "config" / "ci" / "geo.yaml"
OK, BLOCKED, SETUP_ERROR = 0, 1, 2
HINT = "Usa egress=self-hosted, tailscale o wireguard (docs/GITHUB_ACTIONS_ES.md)."

log = logging.getLogger("geo_check")


@dataclass(frozen=True)
class SiteProbe:
    status: int | None
    url: str
    text: str


def load_geo_config(path: Path = GEO_CONFIG) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


# ------------------------------------------------------------------------- país


def fetch_country(url: str, timeout: float) -> str | None:
    """Código ISO de dos letras, o None si el servicio no responde o responde otra cosa."""
    request = urllib.request.Request(url, headers={"Accept": "text/plain"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(64).decode("ascii", "ignore").strip().upper()
    except Exception as exc:
        log.warning("Servicio de geolocalización sin respuesta (%s): %s", url, type(exc).__name__)
        return None
    return body if re.fullmatch(r"[A-Z]{2}", body) else None


def decide_country(readings: dict[str, str | None], expected: str) -> tuple[int, str]:
    seen = {name: country for name, country in readings.items() if country}
    if not seen:
        return SETUP_ERROR, "Ningún servicio de geolocalización respondió: no se puede confirmar el país de salida"
    wrong = {name: country for name, country in seen.items() if country != expected}
    if wrong:
        detected = ", ".join(f"{c} ({n})" for n, c in wrong.items())
        return BLOCKED, f"La salida a internet no es {expected}: detectado {detected}. {HINT}"
    return OK, f"Salida desde {expected} ({', '.join(seen)})"


# ------------------------------------------------------------------------ sitio


def classify_site(probe: SiteProbe, site: dict[str, Any]) -> tuple[int, str]:
    url, text = probe.url.lower(), probe.text.lower()
    if any(m in text for m in site.get("challenge_markers", [])):
        return BLOCKED, "betsson.es muestra una verificación anti-bot/CAPTCHA: no se intenta saltar"
    hit = next((m for m in site.get("blocked_text_markers", []) if m in text), None) or \
        next((m for m in site.get("blocked_url_markers", []) if m in url), None)
    if hit or probe.status in site.get("blocked_status", []):
        why = f"HTTP {probe.status}" if probe.status in site.get("blocked_status", []) else f"marcador {hit!r}"
        return BLOCKED, f"betsson.es bloquea esta conexión ({why}: bloqueo geográfico o WAF). {HINT}"
    if probe.status is None or probe.status >= 400:
        return BLOCKED, f"betsson.es no respondió correctamente (HTTP {probe.status})"
    return OK, f"betsson.es responde (HTTP {probe.status})"


def probe_site(market: MarketConfig, wait_ms: int, screenshot: Path | None) -> SiteProbe:
    """Abre la portada con el mismo navegador y contexto que los tests (sin login, sin vídeo ni traza)."""
    from playwright.sync_api import sync_playwright

    from validator.browser import launch_browser, new_context

    with sync_playwright() as pw:
        browser = launch_browser(pw, headless=True)
        try:
            page = new_context(browser, market).new_page()
            try:
                response = page.goto(market.base_url, wait_until="domcontentloaded")
            except Exception as exc:
                log.warning("La portada no cargó: %s", type(exc).__name__)
                return SiteProbe(None, market.base_url, "")
            page.wait_for_timeout(wait_ms)
            text = page.inner_text("body")[:20_000] if page.locator("body").count() else ""
            if screenshot is not None:   # portada sin formularios rellenos: no hay credenciales que enmascarar
                screenshot.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(screenshot))
            return SiteProbe(response.status if response else None, page.url, text)
        finally:
            browser.close()


# ------------------------------------------------------------------------ salida


def _write_github(rows: list[tuple[str, int, str]], country: str) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"country={country}\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        icon = {OK: "✅", BLOCKED: "❌", SETUP_ERROR: "⚠️"}
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("### Comprobación de salida por España\n\n| Comprobación | Resultado | Detalle |\n|---|---|---|\n")
            for name, code, detail in rows:
                fh.write(f"| {name} | {icon[code]} | {detail} |\n")
            fh.write("\n")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-site-probe", action="store_true", help="Solo comprueba el país de salida")
    args = parser.parse_args()

    cfg = load_geo_config()
    expected = str(cfg.get("expected_country", "ES")).upper()
    timeout = float(cfg.get("timeout_s", 8))
    readings = {s["name"]: fetch_country(s["url"], timeout) for s in cfg.get("country_services", [])}
    code, detail = decide_country(readings, expected)
    country = next((c for c in readings.values() if c), "??")
    rows = [("País de salida", code, detail)]

    if code == OK and not args.no_site_probe:
        market = load_market(current_market())
        site = cfg.get("site", {})
        shot = ROOT / "artifacts" / market.market / "geo-check.png"
        probe = probe_site(market, int(site.get("probe_wait_ms", 3000)), shot)
        site_code, site_detail = classify_site(probe, site)
        rows.append(("Sonda de betsson.es", site_code, site_detail))
        code = site_code

    for _, row_code, row_detail in rows:
        if row_code == OK:
            print(row_detail)
        else:
            print(f"::error::{row_detail}")
    _write_github(rows, country)
    return code


if __name__ == "__main__":
    sys.exit(main())
