"""Resultados por check (escenario + mercado + proveedor + juego + nombre), sin credenciales.

`artifacts/<mercado>/results.json` es la fuente única del informe (scripts/report.py).
"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator

log = logging.getLogger("results")


@dataclass
class CheckResult:
    scenario: str
    market: str
    provider: str
    game: str
    check: str
    status: str            # pass | fail | inconclusive | not_run | error
    detail: str = ""
    evidence: str | None = None
    expected: str = ""
    observed: str = ""


@dataclass
class CheckOutcome:
    """Lo que rellena cada paso. `passed=False` sin excepción = fallo que no bloquea los siguientes."""

    detail: str = ""
    evidence: str | None = None
    passed: bool = True


@dataclass
class Results:
    path: Path
    items: list[CheckResult] = field(default_factory=list)

    def add(self, item: CheckResult) -> None:
        self.items.append(item)
        log.info("[%s] %s | %s | %s: %s %s", item.status.upper(), item.provider, item.game, item.check,
                 item.detail, item.evidence or "")
        self.write()  # se escribe en cada check: si el job se corta, no se pierde lo hecho

    def write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([asdict(i) for i in self.items], ensure_ascii=False, indent=2), encoding="utf-8"
        )


class Checklist:
    """Registra una lista ordenada de checks; si uno lanza excepción, el resto queda como not_run."""

    def __init__(self, results: Results, scenario: str, market: str, provider: str, game: str,
                 names: tuple[str, ...]) -> None:
        self.results = results
        self.base = dict(scenario=scenario, market=market, provider=provider, game=game)
        self.names = names
        self.done: list[str] = []
        self.failures: list[str] = []

    @contextmanager
    def check(self, name: str) -> Iterator[CheckOutcome]:
        outcome = CheckOutcome()
        try:
            yield outcome
        except Exception as exc:
            self._add(name, "fail", f"{type(exc).__name__}: {exc}", outcome.evidence)
            self.failures.append(name)
            for pending in self.names:
                if pending not in self.done:
                    self._add(pending, "not_run", f"bloqueado por '{name}'")
            raise
        if not outcome.passed:
            self.failures.append(f"{name}: {outcome.detail}")
        self._add(name, "pass" if outcome.passed else "fail", outcome.detail, outcome.evidence)

    def _add(self, name: str, status: str, detail: str, evidence: str | None = None) -> None:
        self.results.add(CheckResult(check=name, status=status, detail=detail, evidence=evidence, **self.base))
        self.done.append(name)
