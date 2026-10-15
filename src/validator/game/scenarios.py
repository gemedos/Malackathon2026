"""Escenarios dentro del juego ya cargado (GameSession), verificados por lo que se ve en pantalla.

Flujo de un intento (un único clic en Spin, nunca se reintenta):

    saldo Betsson antes (>= 3 muestras) -> >= 3 capturas del juego antes del clic -> clic en el Spin
    localizado -> capturas hasta reposo + control listo (Escenario 1) o ventana de rechazo (Escenario 2)
    -> OCR de todos los frames -> saldo Betsson después (con sondeo) -> reglas deterministas
    de vision_engine.evaluation -> un resultado por check con su evidencia.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import cv2

from validator.config import MarketConfig, SelectorsConfig
from validator.game.account import AccountBalanceReader
from validator.game.calibration import (GAMES_DIR, CalibrationMissingError, LoadedCalibration, MinBet,
                                        build_profile, load_calibration)
from validator.game.driver import GameDriver
from validator.pages.game_page import GameSession
from vision_engine.matching import best_match
from vision_engine import (AssertionResult, BetssonBalance, MotionState, ScenarioRecord, ScenarioReport,
                           SpinAttemptRecorder, SpinNotFoundError, Verdict, VisionEngine, evaluate_insufficient,
                           evaluate_spin)
from vision_engine.annotate import annotate, strip
from vision_engine.errors import CalibrationError
from vision_engine.verdict import combine

log = logging.getLogger(__name__)

SPIN = "spin_completado"
INSUFFICIENT = "saldo_insuficiente"
SCENARIO_NAMES = {SPIN: "Escenario 1 — Spin completado en Real Play", INSUFFICIENT: "Escenario 2 — Saldo insuficiente"}
POLL_MS = 150
STRIP_FRAMES = 8


@dataclass
class ScenarioOutcome:
    scenario: str
    report: ScenarioReport
    record: ScenarioRecord | None = None
    images: dict[str, str] = field(default_factory=dict)   # before / after / strip -> ruta de la evidencia
    notes: list[str] = field(default_factory=list)


def run_scenario(kind: str, session: GameSession, context, market: MarketConfig, selectors: SelectorsConfig,
                 evidence_dir: Path, games_dir: Path = GAMES_DIR) -> ScenarioOutcome:
    """Ejecuta un escenario sobre el juego abierto. Los fallos de ejecución se propagan (ERROR, no FAIL)."""
    if kind not in SCENARIO_NAMES:
        raise ValueError(f"Escenario desconocido: {kind!r}")
    try:
        loaded = load_calibration(session.provider, session.game, games_dir)
    except CalibrationMissingError as exc:
        return _not_calibrated(kind, market, session, str(exc))

    driver = GameDriver(session)
    first = driver.capture()
    frame_size = (first.shape[1], first.shape[0])
    profile = build_profile(loaded.calibration, market, frame_size)
    engine = VisionEngine(profile, evidence_dir / "vision")
    spin_template, busy_template = loaded.templates()
    _reach_hud(session, driver, engine, loaded.splash_template(), frame_size)
    extra = [_setup(driver, loaded, frame_size)] if loaded.calibration.setup_clicks else []
    if loaded.calibration.min_bet is not None:
        extra.append(_lower_to_min_bet(driver, engine, loaded.calibration.min_bet, frame_size, spin_template))

    account = AccountBalanceReader(context, session.page, market, selectors, engine)
    n, separation = profile.consensus.min_readings, profile.consensus.min_separation_seconds
    notes: list[str] = []
    try:
        betsson_before = account.read_series("betsson-antes", n, separation)
        recorder = SpinAttemptRecorder(engine, spin_template, busy_template)
        for _ in range(n):
            recorder.observe_before(driver.capture(), time.monotonic())
            driver.wait(separation * 1000 + 100)
        clicked = _click_spin(recorder, driver, frame_size, notes)
        if clicked:
            _observe_after(kind, recorder, driver)
        record = recorder.record()
        betsson = None
        if clicked:
            before_value = BetssonBalance.from_readings(betsson_before, betsson_before, profile.consensus).before
            after = account.poll_after("betsson-despues", before_value, n, expect_change=(kind == SPIN))
            betsson = BetssonBalance.from_readings(betsson_before, after, profile.consensus)
    finally:
        account.close()

    report = (evaluate_spin if kind == SPIN else evaluate_insufficient)(record, betsson)
    if extra:
        assertions = (*report.assertions[:3], *extra, *report.assertions[3:])
        report = ScenarioReport(report.scenario, report.market, report.game, combine(assertions), assertions,
                                report.observed)
    images = _evidence_images(record, profile, evidence_dir / "vision")
    log.info("%s: %s (%s)", SCENARIO_NAMES[kind], report.verdict.value, report.observed)
    return ScenarioOutcome(kind, report, record, images, notes)


# --------------------------------------------------------------------------- pasos

HUD_TIMEOUT_S = 120
SPLASH_MAX_CLICKS = 3


def _reach_hud(session: GameSession, driver: GameDriver, engine: VisionEngine, splash_template, frame_size) -> None:
    """Llega hasta el juego jugable: resuelve pantallas previas que aparezcan y pulsa el Spin de la
    «pantalla de carga» (si el proveedor la tiene) hasta que el OCR lee crédito y apuesta."""
    profile = engine.profile
    deadline = time.monotonic() + HUD_TIMEOUT_S
    clicks, index = 0, 0
    while time.monotonic() < deadline:
        if session.pregame is not None and session.pregame():
            driver.wait(500)
            continue
        frame = driver.capture()
        sample = f"hud-{index:03d}"
        index += 1
        balance = engine.read_field(frame, "balance", sample)
        wager = engine.read_field(frame, "wager", sample)
        if balance.value is not None and wager.value is not None:
            log.info("HUD visible (crédito %s, apuesta %s)", balance.value, wager.value)
            return
        if splash_template is not None and clicks < SPLASH_MAX_CLICKS:
            hit = best_match(frame, splash_template, engine.roi("spin_search"), profile.template_scales)
            if hit is not None and hit.confidence >= profile.template_threshold:
                log.info("Pantalla de carga: pulsando Spin (%.2f)", hit.confidence)
                driver.click(hit.point, frame_size)
                clicks += 1
                driver.wait(3000)
                continue
        driver.wait(1000)
    raise CalibrationError(f"No se llegó al HUD del juego en {HUD_TIMEOUT_S}s (crédito/apuesta ilegibles)")


def _setup(driver: GameDriver, loaded: LoadedCalibration, frame_size: tuple[int, int]) -> AssertionResult:
    checks = driver.run_setup(loaded.calibration.setup_clicks, frame_size)
    failed = [c for c in checks if not c.changed]
    detail = ", ".join(f"{c.name} (Δ={c.delta:.1f})" for c in checks)
    if failed:
        return AssertionResult("game_setup", Verdict.INCONCLUSIVE,
                               f"Clics de preparación sin cambio visible (no cuentan): {detail}")
    return AssertionResult("game_setup", Verdict.PASS, f"Preparación verificada visualmente: {detail}")


MIN_BET_READS = 3          # lecturas iguales y consecutivas de la apuesta para aceptar su valor
MIN_BET_CONFIRMATIONS = 2  # clics seguidos sin bajada para dar la apuesta por mínima (uno solo puede perderse)


def _read_wager(driver: GameDriver, engine: VisionEngine, sample: str) -> Decimal | None:
    """Apuesta visible, solo si MIN_BET_READS lecturas seguidas coinciden. Un OCR fallido nunca es un valor."""
    values = []
    for i in range(MIN_BET_READS):
        values.append(engine.read_field(driver.capture(), "wager", f"{sample}-{i}").value)
        driver.wait(150)
    if None in values or len(set(values)) != 1:
        return None
    return Decimal(values[0])


def _spin_visible(driver: GameDriver, engine: VisionEngine, spin_template) -> bool:
    profile = engine.profile
    hit = best_match(driver.capture(), spin_template, engine.roi("spin_search"), profile.template_scales)
    return hit is not None and hit.confidence >= profile.template_threshold


def _close_bet_panel(driver: GameDriver, engine: VisionEngine, cfg: MinBet, frame_size: tuple[int, int],
                     spin_template) -> bool:
    """Cierra el panel de apuesta con su «×» SOLO si tapa el Spin; el cierre se verifica viendo el Spin otra vez."""
    width, height = frame_size
    point = (cfg.close_point[0] * (width - 1), cfg.close_point[1] * (height - 1))  # type: ignore[index]
    for attempt in range(2):
        if _spin_visible(driver, engine, spin_template):
            return True
        log.info("El Spin no se ve tras fijar la apuesta: cerrando el panel de apuesta (intento %d)", attempt + 1)
        driver.click(point, frame_size)
        driver.wait(cfg.settle_ms)
    return _spin_visible(driver, engine, spin_template)


def _lower_to_min_bet(driver: GameDriver, engine: VisionEngine, cfg: MinBet,
                      frame_size: tuple[int, int], spin_template=None) -> AssertionResult:
    """Pulsa «−» hasta que la apuesta visible deja de bajar. Cada clic se verifica leyendo la apuesta por OCR."""
    current = _read_wager(driver, engine, "minbet-000")
    if current is None:
        return AssertionResult("min_bet", Verdict.INCONCLUSIVE, "Apuesta ilegible antes de bajarla a la mínima")
    start, lowered, unchanged = current, 0, 0
    width, height = frame_size
    point = (cfg.point[0] * (width - 1), cfg.point[1] * (height - 1))
    for n in range(1, cfg.max_clicks + 1):
        driver.click(point, frame_size)
        driver.wait(cfg.settle_ms)
        after = _read_wager(driver, engine, f"minbet-{n:03d}")
        if after is None:
            return AssertionResult("min_bet", Verdict.INCONCLUSIVE, f"Apuesta ilegible tras el clic {n} en «−»")
        if after > current:
            return AssertionResult("min_bet", Verdict.INCONCLUSIVE,
                                   f"«−» subió la apuesta ({current} -> {after}): revisa min_bet.point")
        if after == current:
            unchanged += 1
            if unchanged >= MIN_BET_CONFIRMATIONS:
                log.info("Apuesta mínima: %s (desde %s, %d bajadas)", after, start, lowered)
                detail = f"Apuesta mínima {after} (desde {start}; {lowered} bajadas leídas por OCR)"
                if cfg.close_point is not None and spin_template is not None:
                    if not _close_bet_panel(driver, engine, cfg, frame_size, spin_template):
                        return AssertionResult("min_bet", Verdict.INCONCLUSIVE,
                                               f"{detail}; el panel de apuesta sigue tapando el Spin")
                return AssertionResult("min_bet", Verdict.PASS, detail)
        else:
            current, lowered, unchanged = after, lowered + 1, 0
    return AssertionResult("min_bet", Verdict.INCONCLUSIVE,
                           f"La apuesta seguía bajando tras {cfg.max_clicks} clics ({start} -> {current})")


SPIN_EXTRA_FRAMES = 6     # frames previos extra si una animación tapa el Spin en el último (Sweet Bonanza: destello)
SPIN_EXTRA_WAIT_MS = 400


def _click_spin(recorder: SpinAttemptRecorder, driver: GameDriver, frame_size: tuple[int, int],
                notes: list[str]) -> bool:
    """Un único clic, y solo sobre un frame previo en el que el Spin se ve con confianza suficiente.

    Si en el último frame no se identifica (p. ej. un destello pasa por encima del botón), se observan hasta
    SPIN_EXTRA_FRAMES frames más ANTES de clicar; register_click no consume el intento cuando falta evidencia."""
    for extra in range(SPIN_EXTRA_FRAMES + 1):
        try:
            hit = recorder.register_click(time.monotonic())
            break
        except SpinNotFoundError as exc:
            if extra == SPIN_EXTRA_FRAMES:
                notes.append(str(exc))
                log.warning("%s", exc)
                return False
            log.info("Spin no identificado en el último frame previo: se observa otro antes de clicar (%d/%d)",
                     extra + 1, SPIN_EXTRA_FRAMES)
            driver.wait(SPIN_EXTRA_WAIT_MS)
            recorder.observe_before(driver.capture(), time.monotonic())
    driver.click(hit.point, frame_size)   # exactamente un intento
    return True


def _observe_after(kind: str, recorder: SpinAttemptRecorder, driver: GameDriver) -> None:
    """Observa hasta tener evidencia suficiente o agotar el tiempo (nunca indefinidamente)."""
    profile = recorder.engine.profile
    # Margen sobre el consenso mínimo. En juegos de animación constante (settle=ready) el contador de crédito
    # puede seguir subiendo al volver el Spin: se piden más frames listos para tener una cola estable.
    needed = profile.consensus.min_readings + (3 if profile.settle == "ready" else 1)
    deadline = recorder.click_timestamp + profile.motion.timeout_seconds + 2
    while True:
        observation = recorder.observe_after(driver.capture(), time.monotonic())
        now = time.monotonic()
        if kind == SPIN and recorder.settled_count() >= needed:
            return
        if (kind == INSUFFICIENT and now - recorder.click_timestamp >= profile.insufficient_window_seconds + 1
                and recorder.after_count() >= needed):
            return
        if observation.motion.state is MotionState.TIMEOUT or now >= deadline:
            log.warning("Fin de la observación por timeout (%s)", observation.motion.state.value)
            return
        driver.wait(POLL_MS)


def _not_calibrated(kind: str, market: MarketConfig, session: GameSession, reason: str) -> ScenarioOutcome:
    assertion = AssertionResult("profile_calibrated", Verdict.INCONCLUSIVE, reason)
    report = ScenarioReport(kind, market.market, f"{session.provider} / {session.game}", Verdict.INCONCLUSIVE,
                            (assertion,))
    log.warning("%s", reason)
    return ScenarioOutcome(kind, report, notes=[reason])


# --------------------------------------------------------------------------- evidencias

def _labels(frame_record) -> dict[str, str]:
    labels = {}
    for name, reading in frame_record.readings.items():
        labels[name] = reading.value or (reading.raw_text[:30] if reading.raw_text else "ilegible")
    return labels


def _evidence_images(record: ScenarioRecord, profile, out_dir: Path) -> dict[str, str]:
    """Capturas anotadas (antes / después con valores leídos) y tira de fotogramas del intento."""
    images: dict[str, str] = {}
    out_dir.mkdir(parents=True, exist_ok=True)
    for key, frames in (("before", record.before_frames), ("after", record.after_frames)):
        if frames:
            frame = cv2.imread(frames[-1].frame_path)
            if frame is not None:
                path = out_dir / f"annotated-{key}.png"
                cv2.imwrite(str(path), annotate(frame, profile.regions, _labels(frames[-1])))
                images[key] = str(path)
    after = record.after_frames
    if after and record.click_timestamp is not None:
        step = max(1, len(after) // STRIP_FRAMES)
        chosen = list(after[::step])[:STRIP_FRAMES - 1] + [after[-1]]
        frames = [cv2.imread(f.frame_path) for f in chosen]
        captions = [f"t={f.timestamp - record.click_timestamp:+.1f}s {f.motion.state.value}" for f in chosen]
        if all(f is not None for f in frames):
            path = out_dir / "spin-strip.png"
            cv2.imwrite(str(path), strip(frames, captions))
            images["strip"] = str(path)
    return images
