"""Genera una DEMO SINTÉTICA de las cuatro combinaciones T01-T04 en demo/.

Sirve para ver el sistema completo funcionando en local (OCR real incluido).
Las imágenes las dibuja este script: NO son capturas de Betsson y sus
resultados no son evidencia de los escenarios reales.

    python scripts/make_demo.py [directorio]   # por defecto demo/
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

WIDTH, HEIGHT = 640, 400
REELS = (40, 40, 400, 220)
SPIN_AT, SPIN_SIZE = (520, 280), 80
HUD = {'currency': (10, 300, 60, 40), 'balance': (80, 300, 130, 40),
       'wager': (220, 300, 110, 40), 'payout': (340, 300, 120, 40)}
PAGE_SIZE, PAGE_BALANCE = (800, 200), (560, 20, 220, 50)
WHITE = (255, 255, 255)

PROFILE = {
    'game': 'DEMO-SINTETICA (no es Betsson)',
    'calibrated': True,   # calibrado para ESTAS imágenes sintéticas, no para un juego real
    'image_size': [WIDTH, HEIGHT],
    'decimal_separator': '.',
    'template_threshold': 0.85,
    'template_scales': [1.0],
    'insufficient_window_seconds': 2.0,
    'regions': {'spin_search': [470, 230, 170, 170], 'reels': list(REELS), 'message': list(REELS),
                **{name: list(box) for name, box in HUD.items()}},
    'betsson_page': {'image_size': list(PAGE_SIZE), 'balance': list(PAGE_BALANCE)},
}

# Saldos de cada combinación: (moneda, saldo inicial, apuesta, premio, saldo final)
SPIN_CASES = {'T01': ('betsson.com', 'EUR', '10.00', '1.00', '5.00', '14.00'),
              'T03': ('betsson.pe', 'PEN', '50.00', '2.00', '0.00', '48.00')}
INSUFFICIENT_CASES = {'T02': ('betsson.com', 'EUR', '0.50', '1.00', ('Insufficient balance', 'Please deposit to play')),
                      'T04': ('betsson.pe', 'PEN', '0.20', '0.50', ('Saldo insuficiente', 'Deposita para jugar'))}

BEFORE_TIMES = [0.0, 0.5, 1.0]
CLICK = 1.2
SPIN_TIMES = [(1.4, 1), (1.6, 2), (1.8, 3), (2.0, 4)]          # rodillos girando (semilla distinta)
SETTLE_TIMES = [2.2, 2.6, 3.0, 3.4, 3.6, 4.0, 4.4, 4.8]     # rodillos parados
REJECT_TIMES = [1.4, 1.8, 2.2, 2.6, 3.0, 3.4, 3.8]


def reels(frame, seed):
    rng = np.random.default_rng(seed)
    x0, y0, w, h = REELS
    cell_w, cell_h = w // 5, h // 3
    for col in range(5):
        for row in range(3):
            color = tuple(int(c) for c in rng.integers(30, 230, 3))
            cv2.rectangle(frame, (x0 + col * cell_w, y0 + row * cell_h),
                          (x0 + (col + 1) * cell_w - 4, y0 + (row + 1) * cell_h - 4), color, -1)


def text(frame, value, box, scale=1.0):
    x, y, _, h = box
    cv2.putText(frame, value, (x + 4, y + h - 10), cv2.FONT_HERSHEY_SIMPLEX, scale, WHITE, 2, cv2.LINE_AA)


def game_frame(spin_template, currency, balance, wager, payout, reel_seed, message=None):
    frame = np.full((HEIGHT, WIDTH, 3), 20, np.uint8)
    reels(frame, reel_seed)
    if message:
        x, y, w, h = REELS
        cv2.rectangle(frame, (x, y), (x + w - 1, y + h - 1), (60, 40, 40), -1)
        for i, line in enumerate(message):
            cv2.putText(frame, line, (x + 20, y + 90 + 50 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.9, WHITE, 2, cv2.LINE_AA)
    text(frame, currency, HUD['currency'], 0.8)
    text(frame, balance, HUD['balance'])
    text(frame, wager, HUD['wager'])
    if payout:
        text(frame, payout, HUD['payout'])
    sx, sy = SPIN_AT
    frame[sy:sy + SPIN_SIZE, sx:sx + SPIN_SIZE] = spin_template
    return frame


def page_frame(currency, balance):
    page = np.full((PAGE_SIZE[1], PAGE_SIZE[0], 3), 245, np.uint8)
    x, y, w, h = PAGE_BALANCE
    cv2.putText(page, f'{currency} {balance}', (x + 6, y + h - 14), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (30, 30, 30), 2,
                cv2.LINE_AA)
    return page


def write_sequence(folder: Path, frames):
    folder.mkdir(parents=True, exist_ok=True)
    items = []
    for i, (timestamp, image) in enumerate(frames):
        name = f'frame-{i:02d}.png'
        cv2.imwrite(str(folder / name), image)
        items.append({'file': name, 'timestamp': timestamp})
    (folder / 'sequence.json').write_text(json.dumps({'click_timestamp': CLICK, 'frames': items}, indent=2))


def main(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    spin = np.random.default_rng(7).integers(0, 256, (SPIN_SIZE, SPIN_SIZE, 3), dtype=np.uint8)
    cv2.imwrite(str(root / 'spin.png'), spin)
    for market, currency in (('betsson.com', 'EUR'), ('betsson.pe', 'PEN')):
        profile = {**PROFILE, 'market': market, 'expected_currency': currency}
        (root / f'profile-{market}.json').write_text(json.dumps(profile, indent=2))

    tests = []
    for tid, (market, currency, initial, wager, payout, final) in SPIN_CASES.items():
        deducted = f'{float(initial) - float(wager):.2f}'
        frames = [(t, game_frame(spin, currency, initial, wager, '0.00', 0)) for t in BEFORE_TIMES]
        frames += [(t, game_frame(spin, currency, deducted, wager, None, seed)) for t, seed in SPIN_TIMES]
        frames += [(t, game_frame(spin, currency, final, wager, payout, 99)) for t in SETTLE_TIMES]
        write_sequence(root / tid, frames)
        betsson = {'before': initial, 'after': final}
        if tid == 'T03':   # este caso lee el saldo Betsson por OCR desde capturas de la página
            betsson = {}
            for phase, value, times in (('before', initial, BEFORE_TIMES), ('after', final, [5.0, 5.5, 6.0])):
                betsson[phase] = []
                for i, t in enumerate(times):
                    name = f'{tid}/page-{phase}-{i}.png'
                    cv2.imwrite(str(root / name), page_frame(currency, value))
                    betsson[phase].append({'file': name, 'timestamp': t})
        tests.append({'profile': f'profile-{market}.json', 'scenario': 'spin', 'template': 'spin.png',
                      'sequence': f'{tid}/sequence.json', 'betsson': betsson})

    for tid, (market, currency, balance, wager, message) in INSUFFICIENT_CASES.items():
        frames = [(t, game_frame(spin, currency, balance, wager, '0.00', 0)) for t in BEFORE_TIMES]
        frames += [(t, game_frame(spin, currency, balance, wager, '0.00', 0, message)) for t in REJECT_TIMES]
        write_sequence(root / tid, frames)
        tests.append({'profile': f'profile-{market}.json', 'scenario': 'insufficient', 'template': 'spin.png',
                      'sequence': f'{tid}/sequence.json', 'betsson': {'before': balance, 'after': balance}})

    (root / 'plan.json').write_text(json.dumps({'tests': tests}, indent=2))
    print(f'Demo sintética generada en {root}/ — ejecutar: python offline.py matrix --plan {root}/plan.json')


if __name__ == '__main__':
    main(Path(sys.argv[1] if len(sys.argv) > 1 else 'demo'))
