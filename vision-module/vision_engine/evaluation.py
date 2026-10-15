"""Evaluación de los dos escenarios del reto a partir de un ScenarioRecord.

SC-01 Completed Real Play Spin: el giro empieza y termina visiblemente y
    balance_final = balance_inicial - apuesta + premio, tanto en el juego como
    en la cuenta Betsson. El premio se lee de su región, nunca se deduce.
SC-02 Insufficient Balance: aparece un mensaje de saldo insuficiente en el
    idioma del mercado, no se completa ningún giro pagado y ni el saldo del
    juego ni el de Betsson cambian.

Cada aserción devuelve PASS/FAIL/INCONCLUSIVE con referencias a evidencias.
INCONCLUSIVE significa "no se pudo verificar": nunca se informa PASS sin pruebas.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, List, Optional, Sequence, Tuple

from .consensus import consensus, spaced_indices
from .language import detect_language
from .messages import normalize_text
from .money import reconcile
from .ocr import BETSSON_BALANCE_FIELD, OcrReading
from .profile import ConsensusSettings
from .scenario import FrameRecord, ScenarioRecord
from .verdict import AssertionResult, ScenarioReport, Verdict, combine

SPIN_SETTLEMENT = 'spin_settlement'
INSUFFICIENT_FUNDS = 'insufficient_funds'

PASS, FAIL, INCONCLUSIVE = Verdict.PASS, Verdict.FAIL, Verdict.INCONCLUSIVE


@dataclass(frozen=True)
class BetssonBalance:
    """Saldo de la cuenta Betsson antes y después del intento. None = desconocido."""

    before: Optional[Decimal]
    after: Optional[Decimal]
    detail: str = ''
    evidence: Tuple[str, ...] = ()

    @classmethod
    def from_values(cls, before: Decimal, after: Decimal, source: str = 'aportado') -> 'BetssonBalance':
        return cls(before, after, f'saldo Betsson {source}')

    @classmethod
    def from_readings(cls, before: Sequence[OcrReading], after: Sequence[OcrReading],
                      settings: ConsensusSettings) -> 'BetssonBalance':
        """Consenso de >= 3 lecturas visuales del saldo Betsson antes y después."""
        first = consensus(BETSSON_BALANCE_FIELD, before, settings)
        last = consensus(BETSSON_BALANCE_FIELD, after, settings)
        return cls(Decimal(first.value) if first.agreed else None,
                   Decimal(last.value) if last.agreed else None,
                   f'antes: {first.reason}; después: {last.reason}', first.evidence + last.evidence)


# --------------------------------------------------------------------------- escenarios

def evaluate_spin(record: ScenarioRecord, betsson: Optional[BetssonBalance] = None) -> ScenarioReport:
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
    results.append(_wager_consistent(wager, settled, record))
    results.append(_reconciliation('in_game_balance', initial, wager, payout, final,
                                   _reading_paths(before + settled, ('balance', 'wager', 'payout'))))
    results.append(_betsson_reconciliation(betsson, wager, payout))

    observed = {'initial_balance': _s(initial), 'wager': _s(wager), 'payout': _s(payout),
                'final_balance': _s(final), **_betsson_observed(betsson)}
    return _report(SPIN_SETTLEMENT, record, results, observed)


def evaluate_insufficient(record: ScenarioRecord, betsson: Optional[BetssonBalance] = None) -> ScenarioReport:
    before = record.before_frames
    after = record.after_frames
    results = [_profile_calibrated(record), _spin_detected(record), _ready_before_click(record)]

    initial, result = _money('initial_balance', 'balance', before, record)
    results.append(result)
    results.append(_currency(before + after, record))
    results.append(_message_visible(record))
    message = _rejection_message(record)
    results.append(message)
    results.append(_message_language(record))

    window_balance, balance_result = _balance_unchanged(record, _window_frames(record), initial)
    results.append(balance_result)
    results.append(_spin_rejected(record, balance_result, message))
    results.append(_betsson_unchanged(betsson))

    observed = {'initial_balance': _s(initial), 'balance_in_window': _s(window_balance),
                **_betsson_observed(betsson)}
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


def _reconciliation(name: str, initial, wager, payout, final, evidence: Tuple[str, ...]) -> AssertionResult:
    values = {'saldo_inicial': initial, 'apuesta': wager, 'premio': payout, 'saldo_final': final}
    unknown = [key for key, value in values.items() if value is None]
    if unknown:
        return AssertionResult(name, INCONCLUSIVE, f'Valores desconocidos: {unknown}', evidence)
    expected = initial - wager + payout
    if reconcile(initial, wager, payout, final):
        return AssertionResult(name, PASS, f'{initial} - {wager} + {payout} = {final}', evidence)
    return AssertionResult(name, FAIL, f'{initial} - {wager} + {payout} = {expected}, observado {final}', evidence)


# --------------------------------------------------------------------------- SC-01

def _motion(record: ScenarioRecord) -> List[AssertionResult]:
    summary = record.motion
    paths = _frame_paths(record.after_frames)
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


def _wager_consistent(wager: Optional[Decimal], settled: Sequence[FrameRecord],
                      record: ScenarioRecord) -> AssertionResult:
    """La apuesta mostrada tras el giro es la misma que antes: se apostó lo que se veía."""
    after, result = _money('wager_consistent', 'wager', settled, record)
    if wager is None or after is None:
        return AssertionResult('wager_consistent', INCONCLUSIVE, 'Apuesta antes o después desconocida',
                               result.evidence)
    if after != wager:
        return AssertionResult('wager_consistent', FAIL, f'Apuesta cambió {wager} -> {after}', result.evidence)
    return AssertionResult('wager_consistent', PASS, f'Apuesta {wager} antes y después', result.evidence)


def _betsson_reconciliation(betsson: Optional[BetssonBalance], wager, payout) -> AssertionResult:
    if betsson is None:
        return AssertionResult('betsson_balance', INCONCLUSIVE, 'Saldo Betsson no aportado')
    result = _reconciliation('betsson_balance', betsson.before, wager, payout, betsson.after, betsson.evidence)
    if betsson.detail:
        return AssertionResult(result.name, result.verdict, f'{result.detail} ({betsson.detail})', result.evidence)
    return result


# --------------------------------------------------------------------------- SC-02

def _message_visible(record: ScenarioRecord) -> AssertionResult:
    """Aparece algún texto legible (>= 2 palabras) en la región de mensaje tras el intento."""
    frames = [f for f in record.after_frames
              if len(re.findall(r'[a-z]{2,}', normalize_text(f.readings['message'].raw_text))) >= 2]
    evidence = tuple(f.readings['message'].crop_path for f in frames)
    settings = record.profile.consensus
    count = len(spaced_indices([f.timestamp for f in frames], settings.min_separation_seconds))
    if count >= settings.min_readings:
        return AssertionResult('message_visible', PASS,
                               f'Texto visible en {count} frames: {frames[-1].readings["message"].raw_text!r}',
                               evidence)
    return AssertionResult('message_visible', INCONCLUSIVE,
                           f'Texto visible en {count} frames separados de {settings.min_readings} requeridos', evidence)


def _rejection_message(record: ScenarioRecord) -> AssertionResult:
    matched = [f for f in record.after_frames if f.insufficient_message]
    evidence = tuple(f.readings['message'].crop_path for f in matched)
    settings = record.profile.consensus
    spaced = spaced_indices([f.timestamp for f in matched], settings.min_separation_seconds)
    if len(spaced) >= settings.min_readings:
        return AssertionResult('rejection_message', PASS,
                               f'Mensaje en {len(spaced)} frames: {matched[-1].readings["message"].raw_text!r}',
                               evidence)
    return AssertionResult('rejection_message', INCONCLUSIVE,
                           f'Mensaje de saldo insuficiente en {len(spaced)} frames separados de '
                           f'{settings.min_readings} requeridos; una palabra genérica no prueba rechazo', evidence)


def _message_language(record: ScenarioRecord) -> AssertionResult:
    expected = record.profile.language
    settings = record.profile.consensus
    detected = {}
    for frame in record.after_frames:
        language = detect_language(frame.readings['message'].raw_text)
        if language is not None:
            detected.setdefault(language, []).append(frame)
    evidence = tuple(f.readings['message'].crop_path for frames in detected.values() for f in frames)

    def spaced(frames):
        return len(spaced_indices([f.timestamp for f in frames], settings.min_separation_seconds))

    expected_count = spaced(detected.get(expected, []))
    other = {language: spaced(frames) for language, frames in detected.items() if language != expected}
    name = record.profile.language_name
    if expected_count >= settings.min_readings and not other:
        return AssertionResult('message_language', PASS, f'Mensaje en {name} en {expected_count} frames', evidence)
    if expected_count == 0 and any(count >= settings.min_readings for count in other.values()):
        return AssertionResult('message_language', FAIL, f'Mensaje en {sorted(other)}, se esperaba {name}', evidence)
    return AssertionResult('message_language', INCONCLUSIVE,
                           f'Idioma no confirmado (esperado {name}: {expected_count} frames, otros: {other})', evidence)


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


def _balance_unchanged(record: ScenarioRecord, window: Sequence[FrameRecord],
                       initial: Optional[Decimal]) -> Tuple[Optional[Decimal], AssertionResult]:
    name = 'in_game_balance_unchanged'
    seconds = record.profile.insufficient_window_seconds
    value, result = _money(name, 'balance', window, record)
    end = (record.click_timestamp or 0) + seconds
    if not window or window[-1].timestamp < end:
        return value, AssertionResult(name, INCONCLUSIVE, f'Observación no cubre la ventana de {seconds}s',
                                      result.evidence)
    if value is None:
        return None, result
    if initial is None:
        return value, AssertionResult(name, INCONCLUSIVE, 'Saldo inicial desconocido', result.evidence)
    if value != initial:
        return value, AssertionResult(name, FAIL, f'Saldo cambió {initial} -> {value} en {seconds}s', result.evidence)
    return value, AssertionResult(name, PASS, f'Saldo estable en {value} durante {seconds}s', result.evidence)


def _spin_rejected(record: ScenarioRecord, balance: AssertionResult, message: AssertionResult) -> AssertionResult:
    """Un giro pagado descuenta la apuesta: saldo estable + (sin movimiento o mensaje de rechazo) => rechazado.

    El movimiento por sí solo no prueba un giro: el propio aviso puede aparecer sobre los rodillos.
    """
    name = 'spin_rejected'
    paths = _frame_paths(record.after_frames)
    if record.click_timestamp is None:
        return AssertionResult(name, INCONCLUSIVE, 'Sin clic registrado', paths)
    if balance.verdict is FAIL:
        return AssertionResult(name, FAIL, f'Giro pagado: {balance.detail}', balance.evidence)
    if balance.verdict is PASS and (record.motion.started_at is None or message.verdict is PASS):
        return AssertionResult(name, PASS, 'Saldo sin cambios y ningún giro pagado completado', paths)
    return AssertionResult(name, INCONCLUSIVE, 'No se puede demostrar el rechazo con lo observado', paths)


def _betsson_unchanged(betsson: Optional[BetssonBalance]) -> AssertionResult:
    name = 'betsson_balance_unchanged'
    if betsson is None:
        return AssertionResult(name, INCONCLUSIVE, 'Saldo Betsson no aportado')
    if betsson.before is None or betsson.after is None:
        return AssertionResult(name, INCONCLUSIVE, f'Saldo Betsson desconocido ({betsson.detail})', betsson.evidence)
    if betsson.before != betsson.after:
        return AssertionResult(name, FAIL, f'Saldo Betsson cambió {betsson.before} -> {betsson.after}',
                               betsson.evidence)
    return AssertionResult(name, PASS, f'Saldo Betsson estable en {betsson.before}', betsson.evidence)


# --------------------------------------------------------------------------- utilidades

def _frame_paths(frames: Iterable[FrameRecord]) -> Tuple[str, ...]:
    return tuple(f.frame_path for f in frames)


def _reading_paths(frames: Iterable[FrameRecord], fields: Sequence[str]) -> Tuple[str, ...]:
    return tuple(f.readings[name].crop_path for f in frames for name in fields)


def _s(value: Optional[Decimal]) -> Optional[str]:
    return None if value is None else str(value)


def _betsson_observed(betsson: Optional[BetssonBalance]) -> dict:
    if betsson is None:
        return {'betsson_before': None, 'betsson_after': None}
    return {'betsson_before': _s(betsson.before), 'betsson_after': _s(betsson.after)}


def _report(scenario: str, record: ScenarioRecord, results: List[AssertionResult], observed: dict) -> ScenarioReport:
    return ScenarioReport(scenario, record.profile.market, record.profile.game,
                          combine(results), tuple(results), observed)
