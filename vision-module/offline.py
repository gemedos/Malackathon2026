"""Runner offline: analiza capturas ya tomadas. No abre navegador ni hace clics.

    python offline.py inspect  --profile P --template T --image I [--out D]
    python offline.py scenario --profile P --template T --sequence S --kind spin|insufficient
                               [--busy-template B] [--external-before X --external-after Y] [--out D]

Código de salida: 0 PASS, 1 FAIL, 2 INCONCLUSIVE, 3 error de entrada/calibración.
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import List, Optional, Tuple

from vision_engine import (EvidenceStore, ExternalBalance, GameProfile, ReadyDetector, SequenceError,
                           SpinAttemptRecorder, SpinNotFoundError, Verdict, VisionEngine, VisionError,
                           evaluate_insufficient, evaluate_spin, load_image, load_template)

EXIT_CODES = {Verdict.PASS: 0, Verdict.FAIL: 1, Verdict.INCONCLUSIVE: 2}
EXIT_ERROR = 3
EVALUATORS = {'spin': evaluate_spin, 'insufficient': evaluate_insufficient}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Inspección offline de capturas del juego (sin navegador).')
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--profile', required=True, help='Perfil JSON calibrado')
    common.add_argument('--template', required=True, help='Recorte REAL del botón Spin habilitado')
    common.add_argument('--busy-template', help='Recorte REAL del botón en estado ocupado/deshabilitado')
    common.add_argument('--out', default='evidence', help='Directorio de evidencias')
    commands = parser.add_subparsers(dest='command', required=True)

    inspect = commands.add_parser('inspect', parents=[common],
                                  help='Analiza una captura aislada (siempre INCONCLUSIVE)')
    inspect.add_argument('--image', required=True)

    scenario = commands.add_parser('scenario', parents=[common], help='Evalúa una secuencia de un único intento')
    scenario.add_argument('--kind', choices=sorted(EVALUATORS), required=True)
    scenario.add_argument('--sequence', required=True,
                          help='JSON {"click_timestamp": t, "frames": [{"file": "x.png", "timestamp": t}, ...]}')
    scenario.add_argument('--external-before', help='Balance externo previo (lo aporta Playwright)')
    scenario.add_argument('--external-after', help='Balance externo posterior (lo aporta Playwright)')
    return parser


def run_inspect(args, profile: GameProfile, evidence: EvidenceStore) -> int:
    engine = VisionEngine(profile, evidence)
    frame = load_image(args.image)
    template = load_template(args.template)
    busy = load_template(args.busy_template) if args.busy_template else None
    spin = engine.locate_spin(frame, template)
    message = engine.read_message(frame, 'initial')
    result = {
        'status': Verdict.INCONCLUSIVE.value,
        'reason': 'Captura aislada: no ejecuta ni valida un escenario completo',
        'profile_calibrated': profile.calibrated,
        'spin': spin.to_dict() if spin else None,
        'ready': ReadyDetector(profile, template, busy).observe(frame).to_dict(),
        'hud': {name: r.to_dict() for name, r in engine.read_hud(frame, 'initial').items()},
        'message': message.to_dict(),
        'insufficient_phrase_detected': engine.is_insufficient_message(message.raw_text),
    }
    _emit(evidence, 'observations', result)
    return EXIT_CODES[Verdict.INCONCLUSIVE]


def run_scenario(args, profile: GameProfile, evidence: EvidenceStore) -> int:
    external = _external_balance(args.external_before, args.external_after)
    click_timestamp, frames = load_sequence(Path(args.sequence))
    busy = load_template(args.busy_template) if args.busy_template else None
    recorder = SpinAttemptRecorder(VisionEngine(profile, evidence), load_template(args.template), busy)

    notes = []
    for path, timestamp in frames:
        if timestamp < click_timestamp:
            recorder.observe_before(load_image(path), timestamp)
            continue
        if not recorder.clicked:
            try:
                recorder.register_click(click_timestamp)
            except SpinNotFoundError as exc:
                notes.append(str(exc))   # sin clic no hay frames posteriores que evaluar
                break
        recorder.observe_after(load_image(path), timestamp)

    record = recorder.record()
    report = EVALUATORS[args.kind](record, external)
    _emit(evidence, 'scenario', {**report.to_dict(), 'notes': notes, 'record': record.to_dict()})
    return EXIT_CODES[report.verdict]


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


def _external_balance(before: Optional[str], after: Optional[str]) -> Optional[ExternalBalance]:
    if before is None and after is None:
        return None
    if before is None or after is None:
        raise VisionError('Indicar ambos --external-before y --external-after')
    try:
        return ExternalBalance(Decimal(before), Decimal(after))
    except InvalidOperation as exc:
        raise VisionError('Balance externo no es un decimal válido') from exc


def _emit(evidence: EvidenceStore, name: str, data: dict) -> None:
    evidence.save_json(name, data)
    print(json.dumps(data, indent=2, ensure_ascii=False))


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        profile = GameProfile.load(args.profile)
        evidence = EvidenceStore(args.out)
        if not profile.calibrated:
            print('AVISO: perfil no calibrado; los resultados no son evidencia real.', file=sys.stderr)
        runner = run_inspect if args.command == 'inspect' else run_scenario
        return runner(args, profile, evidence)
    except (VisionError, OSError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return EXIT_ERROR


if __name__ == '__main__':
    sys.exit(main())
