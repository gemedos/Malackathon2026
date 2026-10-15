"""Detector visual de control listo (botón Spin habilitado).

Listo = plantilla del Spin HABILITADO visible con confianza >= ready.threshold y,
si se aporta una plantilla del estado ocupado/deshabilitado, claramente mejor
que ella (margen ready.busy_margin). Debe calibrarse con capturas reales de
ambos estados: sin plantilla 'ocupado' un botón atenuado puede parecer listo.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

import numpy as np

from .matching import best_match
from .profile import GameProfile


@dataclass(frozen=True)
class ReadyObservation:
    ready: bool
    confidence: Optional[float]
    busy_confidence: Optional[float]
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


class ReadyDetector:
    def __init__(self, profile: GameProfile, ready_template: np.ndarray,
                 busy_template: Optional[np.ndarray] = None):
        self.profile = profile
        self.ready_template = ready_template
        self.busy_template = busy_template

    def _score(self, frame: np.ndarray, template: Optional[np.ndarray]) -> Optional[float]:
        if template is None:
            return None
        match = best_match(frame, template, self.profile.regions['spin_search'], self.profile.template_scales)
        return None if match is None else match.confidence

    def observe(self, frame: np.ndarray) -> ReadyObservation:
        settings = self.profile.ready
        ready = self._score(frame, self.ready_template)
        busy = self._score(frame, self.busy_template)
        if ready is None or ready < settings.threshold:
            return ReadyObservation(False, ready, busy, 'Spin habilitado no visible con confianza suficiente')
        if busy is not None and busy >= ready - settings.busy_margin:
            return ReadyObservation(False, ready, busy, 'Estado ocupado no distinguible del listo')
        return ReadyObservation(True, ready, busy, 'Spin habilitado visible')
