"""Calibración AUTOMÁTICA de un juego nuevo, sobre la sesión ya abierta (sin apostar).

Localiza el HUD por sus etiquetas/importes (vision_engine.hud_locator), pulsa pantallas de inicio («CONTINUAR»,
«JUGAR»...) mientras todavía no hay HUD y escribe config/games/<proveedor>/<juego>.yaml con `calibrated: true`.
La prueba posterior sigue verificando todo con saldos (nunca da PASS por una región mal puesta): una calibración
errónea acaba en INCONCLUSIVE, no en un aprobado falso."""

from __future__ import annotations

import logging
from pathlib import Path

import cv2

from validator.game.calibration import (GAMES_DIR, CalibrationMissingError, LoadedCalibration, calibration_path,
                                        load_calibration)
from validator.game.driver import GameDriver
from validator.pages.game_page import GameSession
from validator.urls import slugify
from vision_engine.hud_locator import HudProposal, find_spin_candidates, find_start_button, locate_hud

log = logging.getLogger(__name__)

OCR_LANGS = "spa+eng"
ATTEMPTS = 10
START_MAX_CLICKS = 4


def render_yaml(provider: str, game: str, size: tuple[int, int], proposal: HudProposal, spin_name: str,
                calibrated: bool) -> str:
    width, height = size
    lines = {name: "[" + ", ".join(str(v) for v in values) + "]" for name, values in proposal.regions.items()}
    mark = lambda name: "" if name in proposal.verified else "   # SIN VERIFICAR"   # noqa: E731
    notes = "\n".join(f"#   - {note}" for note in proposal.notes)
    return f"""# Calibración AUTOMÁTICA de {provider} / {game} (captura {width}x{height}). Revísala con la imagen anotada.
# Cómo se obtuvo:
{notes}
provider: "{provider}"
game: "{game}"
calibrated: {str(calibrated).lower()}
reference_size: [{width}, {height}]
spin_template: {spin_name}
busy_template: null
template_threshold: 0.8
template_scales: [0.85, 1.0, 1.15, 1.3, 1.45]
regions:
  spin_search: [0.0, 0.0, 1.0, 1.0]
  reels:       [0.2, 0.1, 0.6, 0.65]
  balance:     {lines["balance"]}{mark("balance")}
  wager:       {lines["wager"]}{mark("wager")}
  payout:      {lines.get("payout", "[0.35, 0.875, 0.3, 0.0556]")}{mark("payout")}
  currency:    {lines["currency"]}
  message:     [0.345, 0.37, 0.31, 0.16]
settle: ready
idle_patterns: ["haga su apuesta", "su apuest"]
payout_empty_is_zero: false
setup_clicks: []
insufficient_window_seconds: 5.0
motion: {{start_threshold: 8.0, quiet_threshold: 2.0, quiet_seconds: 1.0, timeout_seconds: 45.0}}
consensus: {{min_readings: 3, min_separation_seconds: 0.3}}
ready: {{threshold: 0.8, busy_margin: 0.05}}
"""


def write_calibration(provider: str, game: str, frame, proposal: HudProposal, *, calibrated: bool,
                      games_dir: Path = GAMES_DIR) -> Path:
    """Escribe el YAML y la plantilla provisional del Spin (el círculo más bajo de la zona inferior)."""
    if not {"balance", "wager"} <= set(proposal.regions):
        raise CalibrationMissingError("No se localizaron el saldo y la apuesta en pantalla")
    candidates = proposal.spin_candidates or find_spin_candidates(frame)
    if not candidates:
        raise CalibrationMissingError("Se localizó el HUD pero no el botón Spin (no hay ningún círculo candidato)")
    height, width = frame.shape[:2]
    path = calibration_path(provider, game, games_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    spin_name = f"{slugify(game)}-spin.png"
    x, y, w, h = candidates[0]
    cv2.imwrite(str(path.parent / spin_name), frame[y:y + h, x:x + w])
    path.write_text(render_yaml(provider, game, (width, height), proposal, spin_name, calibrated), encoding="utf-8")
    return path


def auto_calibrate(session: GameSession, driver: GameDriver, games_dir: Path = GAMES_DIR) -> LoadedCalibration:
    """Calibra `session.game` y devuelve la calibración cargada; CalibrationMissingError si no localiza el HUD."""
    start_clicks = 0
    last = "no se llegó a ver el juego"
    for _ in range(ATTEMPTS):
        if session.pregame is not None and session.pregame():
            driver.wait(500)
            continue
        frame = driver.capture()
        size = (frame.shape[1], frame.shape[0])
        proposal = locate_hud(frame, OCR_LANGS)
        if {"balance", "wager"} <= set(proposal.verified):
            path = write_calibration(session.provider, session.game, frame, proposal, calibrated=True,
                                     games_dir=games_dir)
            log.info("Calibración automática escrita en %s (verificado: %s)", path.name, sorted(proposal.verified))
            for note in proposal.notes:
                log.info("  %s", note)
            return load_calibration(session.provider, session.game, games_dir)
        last = "; ".join(proposal.notes) or last
        if start_clicks < START_MAX_CLICKS:
            point = find_start_button(frame, OCR_LANGS)
            if point is not None:
                log.info("Pantalla de inicio: pulsando el botón de arranque en %s", point)
                driver.click(point, size)
                start_clicks += 1
                driver.wait(3000)
                continue
        driver.wait(2000)
    raise CalibrationMissingError(f"No se pudo calibrar automáticamente {session.provider} / {session.game}: {last}")
