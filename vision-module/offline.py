"""Runner local: analiza capturas ya tomadas. No abre navegador ni hace clics.

    python offline.py inspect  --profile P --template T --image I
    python offline.py scenario --profile P --template T --sequence S --kind spin|insufficient
                               [--betsson-before X --betsson-after Y]
    python offline.py matrix   --plan PLAN.json

Escribe evidencias y report.txt / report.json en --out (por defecto reports/).
Código de salida: 0 PASS, 1 FAIL, 2 INCONCLUSIVE o NOT RUN, 3 ERROR de ejecución.
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, List, Mapping, Optional, Tuple

from vision_engine import (BetssonBalance, EvidenceStore, GameProfile, OcrUnavailableError, ReadyDetector,
                           SequenceError, SpinAttemptRecorder, SpinNotFoundError, TestResult, VisionEngine,
                           VisionError, evaluate_insufficient, evaluate_spin, load_image,
                           load_markets, load_template, render_matrix)
from vision_engine.evaluation import INSUFFICIENT_FUNDS, SPIN_SETTLEMENT
from vision_engine.report import ERROR, empty_matrix, overall_status, test_id

KINDS = {'spin': SPIN_SETTLEMENT, 'insufficient': INSUFFICIENT_FUNDS}
EVALUATORS = {SPIN_SETTLEMENT: evaluate_spin, INSUFFICIENT_FUNDS: evaluate_insufficient}
EXIT_CODES = {'PASS': 0, 'FAIL': 1, 'INCONCLUSIVE': 2, 'NOT RUN': 2, ERROR: 3}
EXECUTION_ERRORS = (VisionError, OcrUnavailableError, OSError, KeyError, TypeError, json.JSONDecodeError)


# --------------------------------------------------------------------------- CLI

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Validación visual offline de capturas del juego (sin navegador).')
    commands = parser.add_subparsers(dest='command', required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--profile', required=True, help='Perfil JSON del juego (config/profiles/...)')
    common.add_argument('--template', required=True, help='Recorte REAL del botón Spin habilitado')
    common.add_argument('--busy-template', help='Recorte REAL del botón ocupado/deshabilitado')
    common.add_argument('--out', default='reports', help='Directorio de salida')

    inspect = commands.add_parser('inspect', parents=[common], help='Analiza una captura aislada (diagnóstico)')
    inspect.add_argument('--image', required=True)

    scenario = commands.add_parser('scenario', parents=[common], help='Evalúa UN escenario de un mercado')
    scenario.add_argument('--kind', choices=sorted(KINDS), required=True)
    scenario.add_argument('--sequence', required=True,
                          help='JSON {"click_timestamp": t, "frames": [{"file": "x.png", "timestamp": t}, ...]}')
    scenario.add_argument('--betsson-before', help='Saldo Betsson antes del intento')
    scenario.add_argument('--betsson-after', help='Saldo Betsson después del intento')

    matrix = commands.add_parser('matrix', help='Ejecuta la matriz T01-T04 descrita en un plan JSON')
    matrix.add_argument('--plan', required=True)
    matrix.add_argument('--out', default='reports', help='Directorio de salida')
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == 'inspect':
            return run_inspect(args)
        if args.command == 'scenario':
            entry = {'profile': args.profile, 'template': args.template, 'busy_template': args.busy_template,
                     'scenario': args.kind, 'sequence': args.sequence}
            if args.betsson_before is not None or args.betsson_after is not None:
                entry['betsson'] = {'before': args.betsson_before, 'after': args.betsson_after}
            return finish([run_test(entry, Path.cwd(), Path(args.out))], Path(args.out), full_matrix=False)
        return run_matrix(Path(args.plan), Path(args.out))
    except EXECUTION_ERRORS as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return EXIT_CODES[ERROR]


# --------------------------------------------------------------------------- comandos

def run_inspect(args) -> int:
    """Diagnóstico de calibración sobre una sola captura. Nunca es un resultado de test."""
    profile = GameProfile.load(args.profile)
    evidence = EvidenceStore(Path(args.out) / 'inspect')
    engine = VisionEngine(profile, evidence)
    frame = load_image(args.image)
    template = load_template(args.template)
    busy = load_template(args.busy_template) if args.busy_template else None
    spin = engine.locate_spin(frame, template)
    message = engine.read_message(frame, 'inspect')
    result = {
        'status': 'INCONCLUSIVE',
        'reason': 'Captura aislada: sirve para calibrar, no valida ningún escenario',
        'profile_calibrated': profile.calibrated,
        'spin': spin.to_dict() if spin else None,
        'ready': ReadyDetector(profile, template, busy).observe(frame).to_dict(),
        'hud': {name: r.to_dict() for name, r in engine.read_hud(frame, 'inspect').items()},
        'message': message.to_dict(),
        'insufficient_phrase_detected': engine.is_insufficient_message(message.raw_text),
    }
    evidence.save_json('observations', result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return EXIT_CODES['INCONCLUSIVE']


def run_matrix(plan_path: Path, out: Path) -> int:
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    results = []
    for entry in plan['tests']:
        results.append(run_test(entry, plan_path.parent, out))
    return finish(results, out, full_matrix=True)


def run_test(entry: Mapping[str, Any], base: Path, out: Path) -> TestResult:
    """Ejecuta un escenario. Los errores de ejecución se informan como ERROR, no como FAIL."""
    profile = GameProfile.load(base / entry['profile'])
    scenario = KINDS[entry['scenario']]
    tid = test_id(profile.market, scenario)
    market = load_markets()[profile.market]
    evidence_dir = out / tid
    try:
        evidence = EvidenceStore(evidence_dir)
        engine = VisionEngine(profile, evidence)
        busy = entry.get('busy_template')
        recorder = SpinAttemptRecorder(engine, load_template(base / entry['template']),
                                       load_template(base / busy) if busy else None)
        notes = replay_sequence(recorder, base / entry['sequence'])
        record = recorder.record()
        betsson = load_betsson(entry.get('betsson'), engine, base)
        report = EVALUATORS[scenario](record, betsson)
        evidence.save_json('scenario', {**report.to_dict(), 'notes': notes, 'record': record.to_dict()})
        return TestResult(tid, market, scenario, report.verdict.value, report, evidence_dir=str(evidence_dir))
    except EXECUTION_ERRORS as exc:
        return TestResult(tid, market, scenario, ERROR, error=f'{type(exc).__name__}: {exc}',
                          evidence_dir=str(evidence_dir))


def finish(results: List[TestResult], out: Path, *, full_matrix: bool) -> int:
    if full_matrix:
        rows = empty_matrix(load_markets())
        for result in results:
            rows[result.test_id] = result
        results = [rows[tid] for tid in sorted(rows)]
        status = overall_status(results)
    else:
        status = results[0].status
    out.mkdir(parents=True, exist_ok=True)
    text = render_matrix(results)
    (out / 'report.txt').write_text(text, encoding='utf-8')
    (out / 'report.json').write_text(json.dumps({'overall': status, 'tests': [r.to_dict() for r in results]},
                                                indent=2, ensure_ascii=False), encoding='utf-8')
    print(text)
    print(f'Informe: {out / "report.txt"}')
    return EXIT_CODES[status]


# --------------------------------------------------------------------------- entradas

def replay_sequence(recorder: SpinAttemptRecorder, path: Path) -> List[str]:
    """Reproduce la secuencia: frames antes del clic, registro del clic y frames después."""
    click, frames = load_sequence(path)
    notes = []
    for frame_path, timestamp in frames:
        if timestamp < click:
            recorder.observe_before(load_image(frame_path), timestamp)
            continue
        if not recorder.clicked:
            try:
                recorder.register_click(click)
            except SpinNotFoundError as exc:
                notes.append(str(exc))   # sin clic no hay frames posteriores que evaluar
                break
        recorder.observe_after(load_image(frame_path), timestamp)
    return notes


def load_sequence(path: Path) -> Tuple[float, List[Tuple[Path, float]]]:
    """Rutas relativas al JSON. Frames con t < click van antes del clic; t > click, después."""
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or 'click_timestamp' not in data or 'frames' not in data:
        raise SequenceError('La secuencia debe ser {"click_timestamp": t, "frames": [...]}')
    click = float(data['click_timestamp'])
    frames = [(path.parent / item['file'], float(item['timestamp'])) for item in data['frames']]
    if any(t == click for _, t in frames):
        raise SequenceError('Ningún frame puede tener exactamente el timestamp del clic')
    if not any(t < click for _, t in frames):
        raise SequenceError('Se necesita al menos un frame ANTES del clic')
    return click, frames


def load_betsson(spec: Optional[Mapping[str, Any]], engine: VisionEngine, base: Path) -> Optional[BetssonBalance]:
    """Saldo Betsson como valores ({"before": "10.00", ...}) o como capturas de página
    ({"before": [{"file": ..., "timestamp": ...}, ...], ...}) leídas por OCR con consenso."""
    if spec is None:
        return None
    before, after = spec.get('before'), spec.get('after')
    if before is None or after is None:
        raise VisionError('El saldo Betsson necesita "before" y "after"')
    if isinstance(before, list) and isinstance(after, list):
        readings = {}
        for phase, items in (('before', before), ('after', after)):
            readings[phase] = [engine.read_betsson_balance(load_image(base / item['file']),
                                                           f'betsson-{phase}-{i:02d}', float(item['timestamp']))
                               for i, item in enumerate(items)]
        return BetssonBalance.from_readings(readings['before'], readings['after'], engine.profile.consensus)
    try:
        return BetssonBalance.from_values(Decimal(str(before)), Decimal(str(after)))
    except InvalidOperation as exc:
        raise VisionError('Saldo Betsson no es un decimal válido') from exc


if __name__ == '__main__':
    sys.exit(main())
