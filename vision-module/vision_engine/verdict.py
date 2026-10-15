"""Veredictos por aserción y agregación en un informe de escenario."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, Tuple


class Verdict(str, Enum):
    PASS = 'PASS'                  # todas las evidencias requeridas observadas
    FAIL = 'FAIL'                  # violación demostrada
    INCONCLUSIVE = 'INCONCLUSIVE'  # falta evidencia (timeout, OCR ilegible, discrepancia...)


@dataclass(frozen=True)
class AssertionResult:
    name: str
    verdict: Verdict
    detail: str
    evidence: Tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {'name': self.name, 'verdict': self.verdict.value,
                'detail': self.detail, 'evidence': list(self.evidence)}


def combine(results: Iterable[AssertionResult]) -> Verdict:
    """FAIL si alguna violación demostrada; si no, INCONCLUSIVE si falta algo; PASS solo con todo."""
    verdicts = [r.verdict for r in results]
    if not verdicts:
        return Verdict.INCONCLUSIVE
    if Verdict.FAIL in verdicts:
        return Verdict.FAIL
    if Verdict.INCONCLUSIVE in verdicts:
        return Verdict.INCONCLUSIVE
    return Verdict.PASS


@dataclass(frozen=True)
class ScenarioReport:
    scenario: str
    market: str
    game: str
    verdict: Verdict
    assertions: Tuple[AssertionResult, ...]
    observed: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {'scenario': self.scenario, 'market': self.market, 'game': self.game,
                'verdict': self.verdict.value, 'observed': self.observed,
                'assertions': [a.to_dict() for a in self.assertions]}
