"""Evaluación de los dos escenarios a partir de un ScenarioRecord.

Escenario 1 (spin_settlement): un giro pagado se liquida y
    balance_final = balance_inicial - apuesta + premio, con premio observado
    independientemente (nunca deducido del balance).
Escenario 2 (insufficient_funds): con saldo insuficiente aparece el mensaje
    específico del idioma, no se completa ningún giro pagado y el balance no
    cambia durante una ventana acotada.

Cada aserción devuelve PASS/FAIL/INCONCLUSIVE con referencias a evidencias.
El balance externo lo aporta y valida el equipo Playwright; sin él, el
escenario no puede ser PASS de extremo a extremo.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, List, Optional, Sequence, Tuple

from .consensus import consensus, spaced_indices
from .money import reconcile
from .scenario import FrameRecord, ScenarioRecord
from .verdict import AssertionResult, ScenarioReport, Verdict, combine

SPIN_SETTLEMENT = 'spin_settlement'
INSUFFICIENT_FUNDS = 'insufficient_funds'

PASS, FAIL, INCONCLUSIVE = Verdict.PASS, Verdict.FAIL, Verdict.INCONCLUSIVE


@dataclass(frozen=True)
class ExternalBalance:
    """Balance antes/después aportado y validado por el equipo Playwright."""

    before: Decimal
    after: Decimal


# --------------------------------------------------------------------------- escenarios

def evaluate_spin(record: ScenarioRecord, external: Optional[ExternalBalance] = None) -> ScenarioReport:
    before = record.before_frames
    settled = record.settled_frames()
    results = [_profile_calibrated(record), _spin_detected(record), _ready_before_click(record)]

    initial, result = _money('initial_balance', 'balance', before, record)
    results.append(result)
    wager, result = _money('wager', 'wager', before, record)
    results.append(result)
    results.append(_currency(before + settled, record))
    results.extend(_motion(record))
    results.append(AssertionResult(
        'ready_after_settle', PASS if settled else INCONCLUSIVE,
        f'{len(settled)} frames en reposo con control listo' if settled
        else 'Sin frames en reposo con control listo visible; reposo de rodillos no es liquidación',
        _frame_paths(settled)))
    final, result = _money('final_balance', 'balance', settled, record)
    results.append(result)
    payout, result = _money('payout', 'payout', settled, record)
    results.append(result)
    results.append(_reconciliation(initial, wager, payout, final, before + settled))
    results.append(_external(external, initial, final))

    observed = {'initial_balance': _s(initial), 'wager': _s(wager), 'payout': _s(payout), 'final_balance': _s(final)}
    return _report(SPIN_SETTLEMENT, record, results, observed)


def evaluate_insufficient(record: ScenarioRecord, external: Optional[ExternalBalance] = None) -> ScenarioReport:
    before = record.before_frames
    after = record.after_frames
    results = [_profile_calibrated(record), _spin_detected(record)]

    initial, result = _money('initial_balance', 'balance', before, record)
    results.append(result)
    results.append(_currency(before + after, record))
    results.append(_rejection_message(record))

    window = _window_frames(record)
    window_balance, balance_result = _balance_unchanged(record, window, initial)
    results.append(_no_paid_spin(record, initial, window_balance))
    results.append(balance_result)
    results.append(_external(external, initial, window_balance))

    observed = {'initial_balance': _s(initial), 'balance_in_window': _s(window_balance)}
    return _report(INSUFFICIENT_FUNDS, record, results, observed)


# --------------------------------------------------------------------------- aserciones comunes

def _profile_calibrated(record: ScenarioRecord) -> AssertionResult:
    if record.profile.calibrated:
        return AssertionResult('profile_calibrated', PASS, f'Perfil calibrado: {record.profile.game}')
    return AssertionResult('profile_calibrated', INCONCLUSIVE,
                           'Perfil no calibrado (calibrated=false); los resultados no son evidencia real')


def _spin_detected(record: ScenarioRecord) -> AssertionResult:
    if record.spin is None:
        return AssertionResult('spin_detected_before_click', INCONCLUSIVE,
                               'Spin no localizado con el umbral configurado; no se debió clicar')
    if record.click_timestamp is None:
        return AssertionResult('spin_detected_before_click', INCONCLUSIVE, 'Spin localizado pero sin clic registrado')
    return AssertionResult('spin_detected_before_click', PASS,
                           f'Spin en {record.spin.point} con confianza {record.spin.confidence:.3f}',
                           _frame_paths(record.before_frames[-1:]))


def _ready_before_click(record: ScenarioRecord) -> AssertionResult:
    last = record.before_frames[-1:]
    if last and last[0].ready.ready:
        return AssertionResult('ready_before_click', PASS, last[0].ready.reason, _frame_paths(last))
    reason = last[0].ready.reason if last else 'Sin frames previos al clic'
    return AssertionResult('ready_before_click', INCONCLUSIVE, reason, _frame_paths(last))


def _money(name: str, field: str, frames: Sequence[FrameRecord],
           record: ScenarioRecord) -> Tuple[Optional[Decimal], AssertionResult]:
    result = consensus(field, [f.readings[field] for f in frames], record.profile.consensus)
    if result.agreed:
        return Decimal(result.value), AssertionResult(name, PASS, f'{result.value} ({result.reason})', result.evidence)
    # Un OCR fallido o discrepante es desconocido: nunca cero.
    return None, AssertionResult(name, INCONCLUSIVE, f'Valor desconocido: {result.reason}', result.evidence)


def _currency(frames: Sequence[FrameRecord], record: ScenarioRecord) -> AssertionResult:
    expected = record.profile.expected_currency
    result = consensus('currency', [f.readings['currency'] for f in frames], record.profile.consensus)
    if not result.agreed:
        return AssertionResult('currency', INCONCLUSIVE, f'Moneda no confirmada: {result.reason}', result.evidence)
    if result.value != expected:
        return AssertionResult('currency', FAIL, f'Moneda observada {result.value}, esperada {expected}',
                               result.evidence)
    return AssertionResult('currency', PASS, f'Moneda {expected} observada ({result.reason})', result.evidence)


def _external(external: Optional[ExternalBalance], before: Optional[Decimal],
              after: Optional[Decimal]) -> AssertionResult:
    if external is None:
        return AssertionResult('external_balance', INCONCLUSIVE,
                               'Balance externo no aportado; la validación integral corresponde al equipo Playwright')
    if before is None or after is None:
        return AssertionResult('external_balance', INCONCLUSIVE, 'Balance visual desconocido; no comparable')
    if (external.before, external.after) == (before, after):
        return AssertionResult('external_balance', PASS, f'Coincide con el externo {external.before} -> {external.after}')
    return AssertionResult('external_balance', FAIL,
                           f'Visual {before} -> {after} distinto del externo {external.before} -> {external.after}')


# --------------------------------------------------------------------------- escenario 1

def _motion(record: ScenarioRecord) -> List[AssertionResult]:
    summary = record.motion
    after = record.after_frames
    paths = _frame_paths(after)
    if summary.started_at is not None:
        started = AssertionResult('reels_started', PASS, f'Movimiento desde t={summary.started_at}', paths)
    else:
        started = AssertionResult('reels_started', INCONCLUSIVE,
                                  'Sin movimiento tras el clic; puede ser un bloqueo', paths)

    if summary.quiet_at is not None:
        settled = AssertionResult('reels_settled', PASS, f'Reposo desde t={summary.quiet_at}', paths)
    elif summary.timed_out:
        settled = AssertionResult('reels_settled', INCONCLUSIVE, 'Timeout sin reposo; no reintentar', paths)
    else:
        settled = AssertionResult('reels_settled', INCONCLUSIVE, 'La secuencia termina sin reposo consolidado', paths)

    if summary.resumed_after_quiet:
        cascade = AssertionResult('no_cascade_or_bonus', INCONCLUSIVE,
                                  'Movimiento reanudado tras el reposo: posible cascada/bonus, requiere adaptación',
                                  paths)
    elif summary.quiet_at is None:
        cascade = AssertionResult('no_cascade_or_bonus', INCONCLUSIVE, 'No evaluable sin reposo', paths)
    else:
        cascade = AssertionResult('no_cascade_or_bonus', PASS, 'Sin reanudación de movimiento observada', paths)
    return [started, settled, cascade]


def _reconciliation(initial, wager, payout, final, frames: Sequence[FrameRecord]) -> AssertionResult:
    evidence = _reading_paths(frames, ('balance', 'wager', 'payout'))
    values = {'balance_inicial': initial, 'apuesta': wager, 'premio': payout, 'balance_final': final}
    unknown = [name for name, value in values.items() if value is None]
    if unknown:
        return AssertionResult('reconciliation', INCONCLUSIVE, f'Valores desconocidos: {unknown}', evidence)
    expected = initial - wager + payout
    if reconcile(initial, wager, payout, final):
        return AssertionResult('reconciliation', PASS, f'{initial} - {wager} + {payout} = {final}', evidence)
    return AssertionResult('reconciliation', FAIL,
                           f'{initial} - {wager} + {payout} = {expected}, observado {final}', evidence)


# --------------------------------------------------------------------------- escenario 2

def _rejection_message(record: ScenarioRecord) -> AssertionResult:
    matched = [f for f in record.after_frames if f.insufficient_message]
    evidence = tuple(f.readings['message'].crop_path for f in matched)
    settings = record.profile.consensus
    spaced = spaced_indices([f.timestamp for f in matched], settings.min_separation_seconds)
    if len(spaced) >= settings.min_readings:
        return AssertionResult('rejection_message', PASS,
                               f'Mensaje específico en {len(spaced)} frames: {matched[-1].readings["message"].raw_text!r}',
                               evidence)
    return AssertionResult('rejection_message', INCONCLUSIVE,
                           f'Mensaje específico en {len(spaced)} frames separados de {settings.min_readings} '
                           'requeridos; una palabra genérica no prueba rechazo', evidence)


def _window_frames(record: ScenarioRecord) -> Tuple[FrameRecord, ...]:
    """Frames posteriores al clic hasta el primero que alcanza el final de la ventana (incluido)."""
    if record.click_timestamp is None:
        return ()
    end = record.click_timestamp + record.profile.insufficient_window_seconds
    frames = []
    for frame in record.after_frames:
        frames.append(frame)
        if frame.timestamp >= end:
            break
    return tuple(frames)


def _window_covered(record: ScenarioRecord, window: Sequence[FrameRecord]) -> bool:
    end = (record.click_timestamp or 0) + record.profile.insufficient_window_seconds
    return bool(window) and window[-1].timestamp >= end


def _balance_unchanged(record: ScenarioRecord, window: Sequence[FrameRecord],
                       initial: Optional[Decimal]) -> Tuple[Optional[Decimal], AssertionResult]:
    name = 'balance_unchanged_in_window'
    seconds = record.profile.insufficient_window_seconds
    value, result = _money(name, 'balance', window, record)
    if not _window_covered(record, window):
        return value, AssertionResult(name, INCONCLUSIVE, f'Observación no cubre la ventana de {seconds}s',
                                      result.evidence)
    if value is None:
        return None, result
    if initial is None:
        return value, AssertionResult(name, INCONCLUSIVE, 'Balance inicial desconocido', result.evidence)
    if value != initial:
        return value, AssertionResult(name, FAIL, f'Balance cambió {initial} -> {value} en {seconds}s',
                                      result.evidence)
    return value, AssertionResult(name, PASS, f'Balance estable en {value} durante {seconds}s', result.evidence)


def _no_paid_spin(record: ScenarioRecord, initial: Optional[Decimal],
                  window_balance: Optional[Decimal]) -> AssertionResult:
    name = 'no_paid_spin_completed'
    paths = _frame_paths(record.after_frames)
    if record.click_timestamp is None:
        return AssertionResult(name, INCONCLUSIVE, 'Sin clic registrado', paths)
    if record.motion.started_at is None:
        if record.after_frames and _window_covered(record, _window_frames(record)):
            return AssertionResult(name, PASS, 'Sin movimiento de rodillos durante la ventana', paths)
        return AssertionResult(name, INCONCLUSIVE, 'Observación insuficiente tras el clic', paths)
    if initial is not None and window_balance is not None and window_balance != initial:
        return AssertionResult(name, FAIL, f'Movimiento y cambio de balance {initial} -> {window_balance}', paths)
    return AssertionResult(name, INCONCLUSIVE,
                           'Movimiento en la región de rodillos (¿overlay o giro?) sin cambio de balance demostrado',
                           paths)


# --------------------------------------------------------------------------- utilidades

def _frame_paths(frames: Iterable[FrameRecord]) -> Tuple[str, ...]:
    return tuple(f.frame_path for f in frames)


def _reading_paths(frames: Iterable[FrameRecord], fields: Sequence[str]) -> Tuple[str, ...]:
    return tuple(f.readings[name].crop_path for f in frames for name in fields)


def _s(value: Optional[Decimal]) -> Optional[str]:
    return None if value is None else str(value)


def _report(scenario: str, record: ScenarioRecord, results: List[AssertionResult], observed: dict) -> ScenarioReport:
    return ScenarioReport(scenario, record.profile.market, record.profile.game,
                          combine(results), tuple(results), observed)
