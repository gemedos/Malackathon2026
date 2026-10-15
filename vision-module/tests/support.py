"""Utilidades de prueba. Todo es SINTÉTICO: verifica lógica, no compatibilidad con juegos reales."""
from pathlib import Path

import numpy as np

from vision_engine.motion import MotionObservation, MotionState, MotionSummary
from vision_engine.ocr import OcrReading
from vision_engine.profile import GameProfile
from vision_engine.ready import ReadyObservation
from vision_engine.scenario import AFTER, BEFORE, FrameRecord, ScenarioRecord
from vision_engine.matching import TemplateMatch
from vision_engine.geometry import ROI
from vision_engine.currency import detect_currency
from vision_engine.money import parse_money

ROOT = Path(__file__).resolve().parent.parent

# Perfil pequeño (200x100) para pruebas rápidas. NO representa ningún juego real.
SYNTHETIC_PROFILE = {
    'game': 'sintetico-pruebas',
    'calibrated': True,
    'image_size': [200, 100],
    'market': 'betsson.com',
    'expected_currency': 'EUR',
    'decimal_separator': '.',
    'template_threshold': 0.85,
    'template_scales': [1.0],
    'insufficient_patterns': [r'\binsufficient (?:balance|funds)\b'],
    'insufficient_window_seconds': 2.0,
    'regions': {
        'spin_search': [140, 40, 60, 60],
        'reels': [0, 0, 130, 50],
        'balance': [0, 60, 40, 20],
        'wager': [45, 60, 40, 20],
        'payout': [90, 60, 40, 20],
        'currency': [0, 82, 30, 15],
        'message': [0, 0, 130, 50],
    },
}


def synthetic_profile(**overrides) -> GameProfile:
    return GameProfile.from_dict({**SYNTHETIC_PROFILE, **overrides})


def noise_template(size=20, seed=0) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 256, (size, size, 3), dtype=np.uint8)


def frame_with(template=None, at=(150, 60), size=(200, 100)) -> np.ndarray:
    frame = np.zeros((size[1], size[0], 3), np.uint8)
    if template is not None:
        x, y = at
        h, w = template.shape[:2]
        frame[y:y + h, x:x + w] = template
    return frame


def reading(field, text, sample_id, timestamp) -> OcrReading:
    value, error = None, None
    try:
        if field in ('balance', 'wager', 'payout'):
            value = str(parse_money(text))
        elif field == 'currency':
            value = detect_currency(text)
    except ValueError as exc:
        error = str(exc)
    return OcrReading(field, sample_id, timestamp, text, value, error,
                      f'{sample_id}-{field}.png', f'{sample_id}-{field}-ocr.png')


def frame_record(index, timestamp, phase, *, balance='10.00', wager='1.00', payout='0.00',
                 currency='EUR', message='', ready=True, state=None, insufficient=False) -> FrameRecord:
    sample_id = f'{phase}-{index:03d}'
    texts = {'balance': balance, 'wager': wager, 'payout': payout, 'currency': currency, 'message': message}
    motion = None if phase == BEFORE else MotionObservation(timestamp, state, 0.0)
    return FrameRecord(sample_id, timestamp, phase, f'{sample_id}-frame.png',
                       {f: reading(f, t, sample_id, timestamp) for f, t in texts.items()},
                       ReadyObservation(ready, 0.99 if ready else 0.2, None, 'sintético'), motion, insufficient)


def scenario_record(frames, *, click=1.2, summary=MotionSummary(), profile=None, spin=True) -> ScenarioRecord:
    match = TemplateMatch((160.0, 70.0), 0.99, 1.0, ROI(150, 60, 20, 20)) if spin else None
    return ScenarioRecord(profile or synthetic_profile(), match, click, tuple(frames), summary)


def before_frames(**kwargs):
    return [frame_record(i, t, BEFORE, **kwargs) for i, t in enumerate((0.0, 0.5, 1.0))]


def after(index, timestamp, state, **kwargs):
    return frame_record(index, timestamp, AFTER, state=state, **kwargs)


M, Q, W, T = MotionState.MOTION, MotionState.QUIET_AFTER_MOTION, MotionState.WAITING, MotionState.TIMEOUT
