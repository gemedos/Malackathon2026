"""Navegación betsson.es -> juego en Real Play, un caso por juego y un resultado por check.

    pytest tests/test_navigation.py --provider "Pragmatic Play" --game "Sweet Bonanza"
    pytest tests/test_navigation.py --provider "Pragmatic Play"          # todos sus juegos
"""

from __future__ import annotations

import pytest

from validator.navigation import GAME_CHECKS, open_game
from validator.results import Checklist

SCENARIO = "navegacion"


def test_navigation(game, run_config, market_config, selectors, evidence, results, session_context) -> None:
    game_evidence = evidence.for_game(run_config.provider, game)
    checklist = Checklist(results, SCENARIO, run_config.market, run_config.provider, game, GAME_CHECKS)
    try:
        with open_game(session_context, market_config, selectors, game_evidence,
                       provider=run_config.provider, game=game, check=checklist.check) as session:
            assert session.bounding_box["width"] > 0
    except Exception as exc:
        pytest.fail(f"{type(exc).__name__}: {exc}", pytrace=False)
    assert not checklist.failures, "Checks fallidos: " + "; ".join(checklist.failures)
