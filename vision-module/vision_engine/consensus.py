"""Consenso temporal de OCR: misma lectura en >= N frames distintos y separados."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence, Tuple

from .errors import SequenceError
from .ocr import OcrReading
from .profile import ConsensusSettings


class ConsensusStatus(str, Enum):
    AGREED = 'agreed'
    INSUFFICIENT = 'insufficient'   # pocas lecturas válidas o poco separadas
    DISAGREEMENT = 'disagreement'   # lecturas válidas distintas entre sí


@dataclass(frozen=True)
class ConsensusResult:
    field: str
    status: ConsensusStatus
    value: Optional[str]
    reason: str
    evidence: Tuple[str, ...]

    @property
    def agreed(self) -> bool:
        return self.status is ConsensusStatus.AGREED


def spaced_indices(timestamps: Sequence[float], min_separation: float) -> List[int]:
    """Índices (de timestamps ordenados) separados al menos `min_separation` entre sí."""
    chosen: List[int] = []
    for index, timestamp in enumerate(timestamps):
        if not chosen or timestamp - timestamps[chosen[-1]] >= min_separation:
            chosen.append(index)
    return chosen


def consensus(field: str, readings: Sequence[OcrReading], settings: ConsensusSettings) -> ConsensusResult:
    """Acepta un valor solo si TODAS las lecturas válidas coinciden y hay suficientes.

    Cualquier discrepancia => DISAGREEMENT (INCONCLUSIVE para el llamador).
    Las lecturas fallidas no cuentan y nunca se sustituyen por un valor.
    """
    if any(r.field != field for r in readings):
        raise SequenceError(f'Lecturas de otro campo mezcladas en el consenso de {field!r}')
    if any(r.timestamp is None for r in readings):
        raise SequenceError('El consenso exige timestamps en todas las lecturas')
    ordered = sorted(readings, key=lambda r: r.timestamp)
    evidence = tuple(r.crop_path for r in ordered)
    valid = [r for r in ordered if r.value is not None]
    failed = len(ordered) - len(valid)

    values = sorted({r.value for r in valid})
    if len(values) > 1:
        return ConsensusResult(field, ConsensusStatus.DISAGREEMENT, None,
                               f'Lecturas discrepantes {values}', evidence)

    distinct_frames, seen = [], set()
    for reading in valid:
        if reading.sample_id not in seen:
            seen.add(reading.sample_id)
            distinct_frames.append(reading)
    spaced = spaced_indices([r.timestamp for r in distinct_frames], settings.min_separation_seconds)
    if len(spaced) < settings.min_readings:
        return ConsensusResult(
            field, ConsensusStatus.INSUFFICIENT, None,
            f'{len(spaced)} lecturas válidas separadas >= {settings.min_separation_seconds}s '
            f'de {settings.min_readings} requeridas ({failed} fallos OCR)', evidence)
    return ConsensusResult(field, ConsensusStatus.AGREED, values[0],
                           f'{len(spaced)} lecturas coincidentes ({failed} fallos OCR)', evidence)
