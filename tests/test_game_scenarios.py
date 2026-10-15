"""Escenarios 1 y 2 en betsson.es con dinero real. Solo se ejecutan si se piden explícitamente:

    pytest tests/test_game_scenarios.py -m real_money --provider "Pragmatic Play" --game "Sweet Bonanza"

Escenario 1 usa la cuenta FUNDED; Escenario 2, la cuenta EMPTY (preparada por los mentores).
El juego necesita calibración en config/games/<proveedor>/<juego>.yaml (scripts/calibrate.py);
sin ella el resultado es INCONCLUSIVE, nunca PASS.
"""

from __future__ import annotations

import pytest

from validator.checks import record_report
from validator.game.scenarios import INSUFFICIENT, SCENARIO_NAMES, SPIN, run_scenario
from validator.navigation import GAME_CHECKS, open_game
from validator.results import CheckResult, Checklist
from vision_engine import Verdict

pytestmark = pytest.mark.real_money


def test_escenario1_spin_completado(game, run_config, market_config, selectors, evidence, results, account_context):
    _run(SPIN, "FUNDED", game, run_config, market_config, selectors, evidence, results, account_context)


def test_escenario2_saldo_insuficiente(game, run_config, market_config, selectors, evidence, results, account_context):
    _run(INSUFFICIENT, "EMPTY", game, run_config, market_config, selectors, evidence, results, account_context)


def _run(kind, account, game, run_config, market_config, selectors, evidence, results, account_context) -> None:
    provider = run_config.provider
    scenario_evidence = evidence.for_scenario(provider, game, kind)
    checklist = Checklist(results, kind, run_config.market, provider, game, GAME_CHECKS)
    context = account_context(account)
    try:
        with open_game(context, market_config, selectors, scenario_evidence,
                       provider=provider, game=game, check=checklist.check) as session:
            outcome = run_scenario(kind, session, context, market_config, selectors, scenario_evidence.dir)
    except Exception as exc:   # error de ejecución (no es un FAIL del juego)
        results.add(CheckResult(scenario=kind, market=run_config.market, provider=provider, game=game,
                                check="Ejecución del escenario", status="error",
                                detail=f"{type(exc).__name__}: {exc}"))
        pytest.fail(f"{SCENARIO_NAMES[kind]}: ERROR de ejecución: {type(exc).__name__}: {exc}", pytrace=False)
    record_report(results, outcome.report, outcome.images, scenario_evidence, market_config,
                  scenario=kind, provider=provider, game=game)
    verdict = outcome.report.verdict
    failed = [f"{a.name}: {a.verdict.value}" for a in outcome.report.assertions if a.verdict is not Verdict.PASS]
    assert not checklist.failures, "Navegación: " + "; ".join(checklist.failures)
    assert verdict is Verdict.PASS, f"{SCENARIO_NAMES[kind]}: {verdict.value} ({'; '.join(failed)})"
