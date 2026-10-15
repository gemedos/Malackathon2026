"""Registro de UN intento de Spin: frames antes del clic, clic único y frames después.

Este módulo no hace clics. Flujo con el equipo Playwright:

    recorder.observe_before(frame, t)       # >= 3 frames para consenso inicial
    hit = recorder.register_click(t)        # justo ANTES de clicar; falla si no hay Spin
    page.mouse.click(*page_point(hit.point, ...))   # exactamente un intento
    recorder.observe_after(frame, t)        # hasta settled_count() suficiente o timeout
    record = recorder.record()              # aquí se hace el OCR de todos los frames

Durante la captura solo se calculan movimiento y control listo (rápido); el OCR se
difiere a record() para no frenar el muestreo mientras giran los rodillos.

Tras un timeout no se reintenta: el resultado es INCONCLUSIVE.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import List, Mapping, Optional, Tuple

import numpy as np

from .consensus import spaced_indices
from .engine import VisionEngine
from .errors import SequenceError, SpinNotFoundError
from .matching import TemplateMatch
from .motion import MotionObservation, MotionState, MotionSummary, MotionTracker
from .ocr import MESSAGE_FIELD, OcrReading
from .profile import GameProfile
from .ready import ReadyDetector, ReadyObservation

BEFORE = 'before'
AFTER = 'after'


@dataclass(frozen=True)
class FrameRecord:
    sample_id: str
    timestamp: float
    phase: str                               # BEFORE | AFTER
    frame_path: str
    readings: Mapping[str, OcrReading]       # balance, wager, payout, currency, message
    ready: ReadyObservation
    motion: Optional[MotionObservation]      # None en frames previos al clic
    insufficient_message: bool

    def to_dict(self) -> dict:
        return {'sample_id': self.sample_id, 'timestamp': self.timestamp, 'phase': self.phase,
                'frame': self.frame_path, 'ready': self.ready.to_dict(),
                'motion': self.motion.to_dict() if self.motion else None,
                'insufficient_message': self.insufficient_message,
                'readings': {name: r.to_dict() for name, r in self.readings.items()}}


@dataclass(frozen=True)
class ScenarioRecord:
    profile: GameProfile
    spin: Optional[TemplateMatch]            # localización en el último frame previo al clic
    click_timestamp: Optional[float]         # None si no se llegó a hacer clic
    frames: Tuple[FrameRecord, ...]
    motion: MotionSummary

    @property
    def before_frames(self) -> Tuple[FrameRecord, ...]:
        return tuple(f for f in self.frames if f.phase == BEFORE)

    @property
    def after_frames(self) -> Tuple[FrameRecord, ...]:
        return tuple(f for f in self.frames if f.phase == AFTER)

    def busy_seen(self) -> bool:
        """¿Se vio el control Spin ocupado/atenuado tras el clic? (prueba de que el juego reaccionó)"""
        return any(not f.ready.ready for f in self.after_frames)

    def busy_runs(self) -> int:
        """Veces que el control pasó de ocupado a listo tras el clic (>1: cascada, bonus o giro extra)."""
        count, previous = 0, True
        for frame in self.after_frames:
            if frame.ready.ready and not previous:
                count += 1
            previous = frame.ready.ready
        return count

    def settled_frames(self) -> Tuple[FrameRecord, ...]:
        """Frames con la ronda liquidada y el control listo.

        settle='ready' (animación constante): frames listos posteriores al último frame ocupado, y de ellos la
        cola con el mismo crédito leído (el contador de premio puede estar animándose).
        settle='motion': reposo consolidado tras el último movimiento."""
        after = self.after_frames
        if self.profile.settle == 'ready' and self.busy_seen():
            last_busy = max(i for i, f in enumerate(after) if not f.ready.ready)
            stable, balance = [], None
            for frame in reversed([f for f in after[last_busy + 1:] if f.ready.ready]):
                reading = frame.readings.get('balance')
                value = reading.value if reading else None
                if value is None:
                    continue          # lectura ilegible aislada: no cuenta como estable ni rompe la cola
                if stable and value != balance:
                    break
                balance = value
                stable.append(frame)
            return tuple(reversed(stable))
        last_motion = max((i for i, f in enumerate(after) if f.motion.state is MotionState.MOTION), default=-1)
        return tuple(f for f in after[last_motion + 1:]
                     if f.motion.state is MotionState.QUIET_AFTER_MOTION and f.ready.ready)

    def to_dict(self) -> dict:
        return {'spin': self.spin.to_dict() if self.spin else None,
                'click_timestamp': self.click_timestamp, 'motion': self.motion.to_dict(),
                'frames': [f.to_dict() for f in self.frames]}


@dataclass(frozen=True)
class FrameObservation:
    """Lo que se sabe de un frame mientras se captura (sin OCR, que se hace al cerrar con record())."""

    sample_id: str
    timestamp: float
    phase: str
    ready: ReadyObservation
    motion: Optional[MotionObservation]


@dataclass
class _Pending:
    observation: FrameObservation
    frame: Optional[np.ndarray]   # se libera tras el OCR


class SpinAttemptRecorder:
    def __init__(self, engine: VisionEngine, spin_template: np.ndarray,
                 busy_template: Optional[np.ndarray] = None):
        self.engine = engine
        self.spin_template = spin_template
        self.ready_detector = ReadyDetector(engine.profile, spin_template, busy_template)
        self.tracker = MotionTracker(engine.roi('reels'), engine.profile.motion)
        self._pending: List[_Pending] = []
        self._records: List[FrameRecord] = []
        self._spin: Optional[TemplateMatch] = None
        self._last_before: Optional[Tuple[np.ndarray, float]] = None
        self._click_timestamp: Optional[float] = None
        self._last_timestamp: Optional[float] = None

    # ------------------------------------------------------------------ estado

    @property
    def clicked(self) -> bool:
        return self._click_timestamp is not None

    @property
    def click_timestamp(self) -> Optional[float]:
        return self._click_timestamp

    @property
    def spin(self) -> Optional[TemplateMatch]:
        return self._spin

    @property
    def last_motion_state(self) -> Optional[MotionState]:
        after = self._after()
        return after[-1].motion.state if after else None

    def settled_count(self) -> int:
        """Frames con la ronda liquidada y control listo, separados en el tiempo.

        settle='ready': listos tras el último frame ocupado. settle='motion': en reposo tras el último movimiento."""
        after = self._after()
        if self.engine.profile.settle == 'ready' and any(not o.ready.ready for o in after):
            last_busy = max(i for i, o in enumerate(after) if not o.ready.ready)
            ready = [o.timestamp for o in after[last_busy + 1:] if o.ready.ready]
            return len(spaced_indices(ready, self.engine.profile.consensus.min_separation_seconds))
        last_motion = max((i for i, o in enumerate(after) if o.motion.state is MotionState.MOTION), default=-1)
        settled = [o.timestamp for o in after[last_motion + 1:]
                   if o.motion.state is MotionState.QUIET_AFTER_MOTION and o.ready.ready]
        return len(spaced_indices(settled, self.engine.profile.consensus.min_separation_seconds))

    def after_count(self) -> int:
        return len(spaced_indices([o.timestamp for o in self._after()],
                                  self.engine.profile.consensus.min_separation_seconds))

    # ------------------------------------------------------------------ secuencia

    def observe_before(self, frame: np.ndarray, timestamp: float) -> FrameObservation:
        if self.clicked:
            raise SequenceError('El clic ya se registró; usar observe_after')
        self._advance(timestamp)
        self.engine.check_size(frame)
        self._spin = self.engine.locate_spin(frame, self.spin_template)
        self._last_before = (frame, timestamp)
        return self._keep(frame, timestamp, BEFORE, None)

    def register_click(self, timestamp: float) -> TemplateMatch:
        """Registra el ÚNICO intento. Devuelve dónde clicar o lanza si falta evidencia."""
        if self.clicked:
            raise SequenceError('Solo un intento de Spin por escenario; no reintentar')
        if self._last_before is None:
            raise SequenceError('Hay que observar al menos un frame ANTES del clic')
        if self._spin is None:
            raise SpinNotFoundError('Spin no identificado en el último frame previo; no clicar (INCONCLUSIVE)')
        self._advance(timestamp)
        frame, frame_time = self._last_before
        self.tracker.observe(frame, frame_time)   # referencia de movimiento previa al clic
        self._click_timestamp = timestamp
        return self._spin

    def observe_after(self, frame: np.ndarray, timestamp: float) -> FrameObservation:
        if not self.clicked:
            raise SequenceError('Registrar el clic antes de observar frames posteriores')
        self._advance(timestamp)
        self.engine.check_size(frame)
        return self._keep(frame, timestamp, AFTER, self.tracker.observe(frame, timestamp))

    def record(self) -> ScenarioRecord:
        """Hace el OCR pendiente (guardando evidencias) y devuelve el registro completo."""
        todo = self._pending[len(self._records):]
        # Tesseract corre en un proceso aparte: con hilos los frames se leen en paralelo (orden conservado).
        with ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 2)) as pool:
            self._records.extend(pool.map(self._read, todo))
        for pending in todo:
            pending.frame = None
        return ScenarioRecord(self.engine.profile, self._spin, self._click_timestamp,
                              tuple(self._records), self.tracker.summary)

    # ------------------------------------------------------------------ interno

    def _after(self) -> List[FrameObservation]:
        return [p.observation for p in self._pending if p.observation.phase == AFTER]

    def _advance(self, timestamp: float) -> None:
        if self._last_timestamp is not None and timestamp <= self._last_timestamp:
            raise SequenceError('Los timestamps deben ser estrictamente crecientes (reloj monotónico)')
        self._last_timestamp = timestamp

    def _keep(self, frame: np.ndarray, timestamp: float, phase: str,
              motion: Optional[MotionObservation]) -> FrameObservation:
        observation = FrameObservation(f'{phase}-{len(self._pending):03d}', timestamp, phase,
                                       self.ready_detector.observe(frame), motion)
        self._pending.append(_Pending(observation, frame.copy()))
        return observation

    def _read(self, pending: _Pending) -> FrameRecord:
        o, frame = pending.observation, pending.frame
        frame_path = self.engine.evidence.save_image(o.sample_id, 'frame', frame)
        readings = dict(self.engine.read_hud(frame, o.sample_id, o.timestamp))
        readings[MESSAGE_FIELD] = self.engine.read_message(frame, o.sample_id, o.timestamp)
        return FrameRecord(
            sample_id=o.sample_id, timestamp=o.timestamp, phase=o.phase, frame_path=frame_path,
            readings=readings, ready=o.ready, motion=o.motion,
            insufficient_message=self.engine.is_insufficient_message(readings[MESSAGE_FIELD].raw_text))
