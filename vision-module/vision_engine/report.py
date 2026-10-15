"""Matriz de pruebas T01-T04 e informe de texto en el formato RR-03 del reto."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Sequence, Tuple

from .evaluation import INSUFFICIENT_FUNDS, SPIN_SETTLEMENT
from .profile import Market
from .verdict import ScenarioReport

ERROR = 'ERROR'          # fallo de ejecución (entrada inválida, imagen ilegible...), no del juego
NOT_RUN = 'NOT RUN'      # combinación de la matriz sin ejecutar

TEST_MATRIX: Dict[Tuple[str, str], str] = {
    ('betsson.com', SPIN_SETTLEMENT): 'T01',
    ('betsson.com', INSUFFICIENT_FUNDS): 'T02',
    ('betsson.pe', SPIN_SETTLEMENT): 'T03',
    ('betsson.pe', INSUFFICIENT_FUNDS): 'T04',
}

SCENARIO_NAMES = {SPIN_SETTLEMENT: 'Completed Real Play Spin', INSUFFICIENT_FUNDS: 'Insufficient Balance'}

LABELS = {
    'profile_calibrated': 'Game profile calibrated',
    'spin_detected_before_click': 'Spin control located',
    'ready_before_click': 'Game ready',
    'initial_balance': 'Initial balance detected',
    'wager': 'Wager detected',
    'currency': 'Currency validated',
    'reels_started': 'Spin started',
    'reels_settled': 'Spin completed',
    'no_cascade_or_bonus': 'No bonus/cascade pending',
    'ready_after_settle': 'Game ready after spin',
    'final_balance': 'Final balance detected',
    'payout': 'Payout detected',
    'wager_consistent': 'Wager used matches displayed wager',
    'in_game_balance': 'In-game balance validated',
    'betsson_balance': 'Betsson balance validated',
    'rejection_message': 'Insufficient-balance message detected',
    'message_language': 'Message language validated',
    'in_game_balance_unchanged': 'In-game balance unchanged',
    'spin_rejected': 'Spin rejected (no paid spin completed)',
    'betsson_balance_unchanged': 'Betsson balance unchanged',
}


@dataclass(frozen=True)
class TestResult:
    test_id: str
    market: Market
    scenario: str
    status: str                          # PASS | FAIL | INCONCLUSIVE | ERROR | NOT RUN
    report: Optional[ScenarioReport] = None
    error: Optional[str] = None
    evidence_dir: Optional[str] = None

    def to_dict(self) -> dict:
        return {'test_id': self.test_id, 'market': self.market.name, 'language': self.market.language_name,
                'currency': self.market.currency, 'scenario': SCENARIO_NAMES[self.scenario],
                'status': self.status, 'error': self.error, 'evidence_dir': self.evidence_dir,
                'report': self.report.to_dict() if self.report else None}


def test_id(market: str, scenario: str) -> str:
    return TEST_MATRIX[(market, scenario)]


def overall_status(results: Sequence[TestResult]) -> str:
    """PASS solo si las cuatro combinaciones pasan."""
    statuses = {r.status for r in results}
    for status in ('FAIL', ERROR, 'INCONCLUSIVE', NOT_RUN):
        if status in statuses:
            return status
    return 'PASS' if len(results) == len(TEST_MATRIX) else NOT_RUN


def render_test(result: TestResult) -> str:
    lines = [f'TEST REPORT — {result.test_id}', '',
             f'Market: {result.market.name}',
             f'Language: {result.market.language_name}',
             f'Currency: {result.market.currency}']
    if result.report:
        lines.append(f'Game: {result.report.game}')
    lines += ['', f'Scenario: {SCENARIO_NAMES[result.scenario]}', '']
    if result.error:
        lines.append(f'EXECUTION ERROR: {result.error}')
    if result.report:
        for assertion in result.report.assertions:
            lines.append(f'{LABELS.get(assertion.name, assertion.name)}: {assertion.verdict.value}')
            lines.append(f'    {assertion.detail}')
    if result.evidence_dir:
        lines += ['', f'Evidence: {result.evidence_dir}']
    lines += ['', f'FINAL RESULT: {result.status}']
    return '\n'.join(lines)


def render_matrix(results: Sequence[TestResult]) -> str:
    header = ['SUMMARY', '']
    for r in results:
        header.append(f'{r.test_id}  {r.market.name:<12} {SCENARIO_NAMES[r.scenario]:<26} '
                      f'{r.market.currency}  {r.status}')
    header += ['', f'OVERALL: {overall_status(results)}', '', '=' * 60, '']
    return '\n'.join(header) + ('\n\n' + '=' * 60 + '\n\n').join(render_test(r) for r in results) + '\n'


def empty_matrix(markets: Mapping[str, Market]) -> Dict[str, TestResult]:
    """Las cuatro combinaciones en estado NOT RUN, para que ninguna desaparezca del informe."""
    return {tid: TestResult(tid, markets[market], scenario, NOT_RUN)
            for (market, scenario), tid in TEST_MATRIX.items()}
