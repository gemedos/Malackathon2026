"""Seguimiento temporal de movimiento en la región de rodillos.

`quiet_after_motion` es solo una señal visual: NO significa ronda liquidada.
La liquidación exige además control listo visible y lecturas monetarias estables.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import cv2
import numpy as np

from .errors import CalibrationError, SequenceError
from .geometry import ROI
from .imaging import to_gray
from .profile import MotionSettings


class MotionState(str, Enum):
    WAITING = 'waiting'                        # aún sin movimiento
    MOTION = 'motion'                          # movimiento o reposo todavía no consolidado
    QUIET_AFTER_MOTION = 'quiet_after_motion'  # reposo sostenido tras movimiento
    TIMEOUT = 'timeout'                        # se agotó el tiempo; resultado incierto


@dataclass(frozen=True)
class MotionObservation:
    timestamp: float
    state: MotionState
    delta: Optional[float]   # None en el frame de referencia

    def to_dict(self) -> dict:
        return {'timestamp': self.timestamp, 'state': self.state.value, 'delta': self.delta}


@dataclass(frozen=True)
class MotionSummary:
    started_at: Optional[float] = None
    quiet_at: Optional[float] = None
    resumed_after_quiet: bool = False   # posible cascada/bonus: requiere adaptación específica
    timed_out: bool = False

    def to_dict(self) -> dict:
        return dict(self.__dict__)


class MotionTracker:
    """El primer frame observado debe ser ANTERIOR al clic (referencia)."""

    def __init__(self, roi: ROI, settings: Optional[MotionSettings] = None):
        self.roi = roi
        self.settings = settings or MotionSettings()
        self._previous: Optional[np.ndarray] = None
        self._first_time: Optional[float] = None
        self._last_time: Optional[float] = None
        self._quiet_since: Optional[float] = None
        self._in_quiet = False
        self._summary = MotionSummary()

    @property
    def summary(self) -> MotionSummary:
        return self._summary

    def observe(self, frame: np.ndarray, timestamp: float) -> MotionObservation:
        if not math.isfinite(timestamp):
            raise SequenceError('Timestamp no finito')
        if self._last_time is not None and timestamp <= self._last_time:
            raise SequenceError('Los timestamps deben ser estrictamente crecientes (reloj monotónico)')
        self._last_time = timestamp
        gray = to_gray(self.roi.crop(frame))

        if self._previous is None:
            self._previous = gray
            self._first_time = timestamp
            return MotionObservation(timestamp, MotionState.WAITING, None)
        if gray.shape != self._previous.shape:
            raise CalibrationError('La resolución cambió durante la observación')

        delta = float(np.mean(cv2.absdiff(gray, self._previous)))
        self._previous = gray
        return MotionObservation(timestamp, self._classify(delta, timestamp), delta)

    def _classify(self, delta: float, timestamp: float) -> MotionState:
        s = self.settings
        summary = self._summary
        if timestamp - self._first_time > s.timeout_seconds:
            self._summary = _replace(summary, timed_out=True)
            return MotionState.TIMEOUT

        if delta > s.start_threshold:
            started_at = timestamp if summary.started_at is None else summary.started_at
            self._summary = _replace(summary, started_at=started_at,
                                     resumed_after_quiet=summary.resumed_after_quiet or self._in_quiet)
            self._quiet_since = None
            self._in_quiet = False
            return MotionState.MOTION

        if summary.started_at is None:
            return MotionState.WAITING

        if delta < s.quiet_threshold:
            # Umbral de reposo separado del de movimiento; nunca se exige diferencia cero.
            if self._quiet_since is None:
                self._quiet_since = timestamp
            if timestamp - self._quiet_since >= s.quiet_seconds:
                self._in_quiet = True
                if summary.quiet_at is None:
                    self._summary = _replace(summary, quiet_at=timestamp)
                return MotionState.QUIET_AFTER_MOTION
            return MotionState.MOTION

        # Entre ambos umbrales: no es reposo consolidado.
        self._quiet_since = None
        self._in_quiet = False
        return MotionState.MOTION


def _replace(summary: MotionSummary, **changes) -> MotionSummary:
    return MotionSummary(**{**summary.__dict__, **changes})
