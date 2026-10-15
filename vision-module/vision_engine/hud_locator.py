"""Propone las regiones del HUD de un juego buscando sus ETIQUETAS («CRÉDITO», «APUESTA», «GANANCIA»...).

No adivina a ciegas: cada región propuesta se verifica leyendo un importe válido en ella. Lo que no se
puede verificar se marca como tal. Sirve para arrancar la calibración de un juego nuevo; el resultado se
revisa sobre una imagen anotada antes de darlo por bueno."""
from __future__ import annotations

import re
from difflib import SequenceMatcher
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from .imaging import preprocess_for_ocr, strip_trailing_symbol, to_gray
from .money import parse_money_lenient
from .ocr import MONEY_CHARS, tesseract_backend

LABELS = {
    'balance': re.compile(r'^(CREDITO|CREDIT|CREDITS|SALDO|BALANCE|CASH|GUTHABEN)$'),
    'wager': re.compile(r'^(APUESTA|BET|STAKE|EINSATZ|TOTALBET)$'),
    'payout': re.compile(r'^(GANANCIA|GANANCIAS|PREMIO|WIN|WINS|GEWINN)$'),
}
LABEL_WORDS = {
    'balance': ['CREDITO', 'CREDIT', 'SALDO', 'BALANCE', 'GUTHABEN'],
    'wager': ['APUESTA', 'EINSATZ', 'STAKE', 'TOTALBET'],
    'payout': ['GANANCIA', 'GANANCIAS', 'PREMIO', 'GEWINN'],
}
VALUE_WIDTH = 0.115          # ancho de la región del importe (fracción del ancho del juego)


@dataclass
class Word:
    text: str
    x: int
    y: int
    w: int
    h: int


@dataclass
class HudProposal:
    regions: Dict[str, List[float]] = field(default_factory=dict)    # normalizadas [x, y, w, h]
    verified: Dict[str, str] = field(default_factory=dict)           # campo -> importe leído
    notes: List[str] = field(default_factory=list)
    spin_candidates: List[Tuple[int, int, int, int]] = field(default_factory=list)   # x, y, w, h

    @property
    def score(self) -> int:
        return len(self.verified) * 2 + len(self.regions)


def _norm(text: str) -> str:
    text = unicodedata.normalize('NFD', text)
    return re.sub(r'[^A-Z]', '', ''.join(c for c in text if unicodedata.category(c) != 'Mn').upper())


BAND_TOP = 0.65              # el HUD está en la parte baja; se lee solo esa franja (el texto pequeño necesita ampliarse)
BAND_UPSCALE = 4
FUZZY = 0.62


def find_words(frame: np.ndarray, language: str = 'spa+eng') -> List[Word]:
    import pytesseract
    from .ocr import _locate_tesseract
    _locate_tesseract(pytesseract)
    height = frame.shape[0]
    top = int(BAND_TOP * height)
    gray = cv2.resize(to_gray(frame[top:]), None, fx=BAND_UPSCALE, fy=BAND_UPSCALE, interpolation=cv2.INTER_CUBIC)
    words: List[Word] = []
    for image in (gray, cv2.bitwise_not(gray)):
        for psm in (6, 11):
            try:
                data = pytesseract.image_to_data(image, lang=language, config=f'--psm {psm}',
                                                 output_type=pytesseract.Output.DICT)
            except pytesseract.TesseractError:
                data = pytesseract.image_to_data(image, lang='eng', config=f'--psm {psm}',
                                                 output_type=pytesseract.Output.DICT)
            for i, text in enumerate(data['text']):
                if text.strip() and float(data['conf'][i]) > 0:
                    words.append(Word(text, data['left'][i] // BAND_UPSCALE,
                                      data['top'][i] // BAND_UPSCALE + top,
                                      data['width'][i] // BAND_UPSCALE, data['height'][i] // BAND_UPSCALE))
    return words


def _score(field_name: str, text: str) -> float:
    """Parecido (0–1) entre una palabra del OCR y las etiquetas de un campo; 0 si es demasiado corta."""
    word = _norm(text)
    if len(word) < 3:
        return 0.0
    if LABELS[field_name].match(word):
        return 1.0
    if len(word) < 5:
        return 0.0
    return max((SequenceMatcher(None, word, v).ratio() for v in LABEL_WORDS[field_name] if len(v) >= 5), default=0.0)


def _matches(field_name: str, text: str) -> bool:
    """La palabra se asigna al campo que más se le parece (y solo si supera el umbral): «REDITO» es crédito."""
    scores = {name: _score(name, text) for name in LABELS}
    best = max(scores, key=scores.get)
    return best == field_name and scores[best] >= FUZZY


def _read_amount(frame: np.ndarray, x: int, y: int, w: int, h: int, language: str,
                 integer_ok: bool = False) -> Optional[str]:
    height, width = frame.shape[:2]
    x, y = max(0, x), max(0, y)
    w, h = min(w, width - x), min(h, height - y)
    if w < 10 or h < 6:
        return None
    processed = preprocess_for_ocr(frame[y:y + h, x:x + w], 4)
    config = f'--psm 7 -c tessedit_char_whitelist={MONEY_CHARS}'
    attempts = [(processed, False)]
    stripped = strip_trailing_symbol(processed)
    if stripped is not None:
        attempts.append((stripped, True))
    for image, symbol_removed in attempts:
        raw = tesseract_backend(image, language, config).strip()
        try:
            return str(parse_money_lenient(raw, ',', integer_ok and (symbol_removed or '€' in raw)))
        except ValueError:
            continue
    return None


def _candidates(label: Word, width: int, height: int) -> List[Tuple[str, Tuple[int, int, int, int]]]:
    pad = max(4, label.h // 3)
    side = (label.x + label.w + pad, label.y - label.h // 4, int(VALUE_WIDTH * width), int(label.h * 1.6))
    below = (label.x, label.y + label.h, int(VALUE_WIDTH * width), int(label.h * 1.8))
    return [('a la derecha de la etiqueta', side), ('debajo de la etiqueta', below)]


AMOUNT = re.compile(r'^\d{1,6}(?:[.,]\d{2})?$')


def _amount_anchors(words: List[Word], height: int) -> List[Word]:
    """Importes sueltos del HUD (sin duplicar las dos polaridades), de izquierda a derecha."""
    seen, anchors = set(), []
    symbols = [w for w in words if '€' in w.text]
    for word in words:
        text = word.text.strip().rstrip('€').strip()
        # Solo importes con símbolo de moneda (descarta números sueltos del juego, p. ej. de los rodillos).
        with_symbol = '€' in word.text or any(abs(s.y - word.y) <= word.h and -word.w <= s.x - word.x <= word.w + 3 * word.h
                                               for s in symbols)
        if word.y > 0.6 * height and with_symbol and AMOUNT.match(text) and (word.x // 10, word.y // 10) not in seen:
            seen.add((word.x // 10, word.y // 10))
            anchors.append(word)
    return sorted(anchors, key=lambda w: w.x)


def _value_box(anchor: Word) -> Tuple[int, int, int, int]:
    """Caja del importe con su símbolo; con margen vertical suficiente para que no se pierda la coma (baja del renglón)."""
    pad_x = max(3, anchor.h // 2)
    return (anchor.x - pad_x, anchor.y - int(anchor.h * 0.4), anchor.w + 2 * pad_x + int(anchor.h * 1.8),
            int(anchor.h * 1.9))


def _read_label(frame: np.ndarray, x: int, y: int, w: int, h: int, language: str) -> str:
    """Texto de una franja pequeña (etiqueta diminuta), ampliada mucho y probando ambas polaridades."""
    import pytesseract
    from .ocr import _locate_tesseract
    _locate_tesseract(pytesseract)
    height, width = frame.shape[:2]
    x, y = max(0, x), max(0, y)
    crop = frame[y:min(height, y + h), x:min(width, x + w)]
    if crop.size == 0:
        return ''
    gray = cv2.resize(to_gray(crop), None, fx=6, fy=6, interpolation=cv2.INTER_CUBIC)
    texts = []
    for image in (gray, cv2.bitwise_not(gray)):
        try:
            texts.append(pytesseract.image_to_string(image, lang=language, config='--psm 7').strip())
        except pytesseract.TesseractError:
            texts.append(pytesseract.image_to_string(image, lang='eng', config='--psm 7').strip())
    return ' '.join(t for t in texts if t)


def _locate_by_amounts(frame: np.ndarray, words: List[Word], language: str, proposal: HudProposal) -> None:
    """HUD con la etiqueta ENCIMA (o a la izquierda) del importe y tan pequeña que no se lee en la franja entera:
    se parte de cada importe legible y se lee su etiqueta con una ampliación mayor."""
    height, width = frame.shape[:2]
    for anchor in _amount_anchors(words, height):
        pad_y = max(2, anchor.h // 4)
        value_box = _value_box(anchor)
        label_boxes = [
            (anchor.x - int(anchor.w * 0.6), anchor.y - int(anchor.h * 2.2), int(anchor.w * 2.6), int(anchor.h * 1.9)),
            (anchor.x - int(anchor.h * 9), anchor.y - pad_y, int(anchor.h * 8.5), anchor.h + 2 * pad_y),
        ]
        for box in label_boxes:
            text = _read_label(frame, *box, language)
            scored = {name: max((_score(name, token) for token in text.split()), default=0.0) for name in LABELS}
            best = max(scored, key=scored.get)
            if scored[best] < 0.6 or best in proposal.regions and best in proposal.verified:
                continue
            amount = _read_amount(frame, *value_box, language, integer_ok=best == 'wager')
            if amount is None:
                continue
            x, y, w, h = value_box
            x, y = max(0, x), max(0, y)
            w, h = min(w, width - x), min(h, height - y)
            proposal.regions[best] = [round(x / width, 4), round(y / height, 4), round(w / width, 4), round(h / height, 4)]
            proposal.verified[best] = amount
            proposal.notes.append(f'{best}: importe {amount} con la etiqueta {text!r} '
                                  f'{"encima" if box is label_boxes[0] else "a la izquierda"}')
            break


def _assign_unlabelled(frame: np.ndarray, words: List[Word], language: str, proposal: HudProposal) -> None:
    """Etiquetas ilegibles pero importes legibles: el saldo es el mayor de los que quedan y el premio el otro.
    Es una HEURÍSTICA (no una lectura): queda anotada para revisarla en la imagen anotada."""
    missing = [name for name in ('balance', 'payout') if name not in proposal.verified]
    if not missing or 'wager' not in proposal.verified:
        return
    height, width = frame.shape[:2]
    taken = [proposal.regions['wager']]
    remaining = []
    for anchor in _amount_anchors(words, height):
        box = _value_box(anchor)
        centre = ((box[0] + box[2] / 2) / width, (box[1] + box[3] / 2) / height)
        if any(abs(centre[0] - (t[0] + t[2] / 2)) < t[2] / 2 and abs(centre[1] - (t[1] + t[3] / 2)) < t[3]
               for t in taken):
            continue
        amount = _read_amount(frame, *box, language)
        if amount is not None:
            remaining.append((float(amount), amount, box))
    remaining.sort(reverse=True)
    if len(remaining) < len(missing):
        return
    order = [name for name in ('balance', 'payout') if name in missing]
    for name, (_, amount, box) in zip(order, remaining[:len(order)]):
        x, y, w, h = box
        x, y = max(0, x), max(0, y)
        w, h = min(w, width - x), min(h, height - y)
        proposal.regions[name] = [round(x / width, 4), round(y / height, 4), round(w / width, 4), round(h / height, 4)]
        proposal.verified[name] = amount
        proposal.notes.append(f'{name}: importe {amount} asignado por tamaño relativo (etiqueta ilegible): REVISAR')


def find_spin_candidates(frame: np.ndarray, limit: int = 6) -> List[Tuple[int, int, int, int]]:
    """Círculos grandes en la zona inferior (salvo el extremo izquierdo) (x, y, ancho, alto), de más abajo a más arriba (el Spin suele ser el círculo más bajo). Solo una pista:
    el botón Spin no se puede identificar con certeza por forma, así que se numeran para elegirlo a ojo."""
    height, width = frame.shape[:2]
    gray = cv2.medianBlur(to_gray(frame), 5)
    circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=height // 8, param1=100, param2=35,
                               minRadius=int(0.04 * height), maxRadius=int(0.14 * height))
    found: List[Tuple[int, int, int, int]] = []
    if circles is None:
        return found
    for cx, cy, r in sorted(circles[0], key=lambda c: (-c[1], -c[2])):
        if cx > 0.3 * width and cy > 0.7 * height:
            cx, cy, r = int(cx), int(cy), int(r)
            found.append((max(0, cx - r), max(0, cy - r), min(2 * r, width), min(2 * r, height)))
    return found[:limit]


def locate_hud(frame: np.ndarray, language: str = 'spa+eng') -> HudProposal:
    height, width = frame.shape[:2]
    proposal = HudProposal()
    words = find_words(frame, language)
    for field_name, pattern in LABELS.items():
        labels = [w for w in words if _matches(field_name, w.text)]
        if not labels:
            proposal.notes.append(f'No se encontró la etiqueta de {field_name}')
            continue
        label = max(labels, key=lambda w: (w.y, w.h))
        chosen = None
        for where, (x, y, w, h) in _candidates(label, width, height):
            amount = _read_amount(frame, x, y, w, h, language)
            if amount is not None:
                chosen = (where, (x, y, w, h), amount)
                break
        if chosen is None:
            # Sin importe legible (p. ej. el premio vacío): se propone a la derecha, SIN verificar.
            _, (x, y, w, h) = _candidates(label, width, height)[0]
            proposal.notes.append(f'{field_name}: etiqueta {label.text!r} encontrada pero sin importe legible; '
                                  'región propuesta a la derecha SIN verificar')
        else:
            where, (x, y, w, h), amount = chosen
            proposal.verified[field_name] = amount
            proposal.notes.append(f'{field_name}: importe {amount} {where} {label.text!r}')
        x, y = max(0, x), max(0, y)
        w, h = min(w, width - x), min(h, height - y)
        proposal.regions[field_name] = [round(x / width, 4), round(y / height, 4),
                                        round(w / width, 4), round(h / height, 4)]
    if len(proposal.verified) < 3:
        _locate_by_amounts(frame, words, language, proposal)
    _assign_unlabelled(frame, words, language, proposal)
    if 'balance' not in proposal.regions and 'wager' in proposal.regions:
        x, y, w, h = proposal.regions['wager']
        x, y, w, h = int(x * width), int(y * height), int(w * width), int(h * height)
        for dy in (h, int(h * 1.2)):
            amount = _read_amount(frame, x, y - dy, w, h, language)
            if amount is not None:
                proposal.regions['balance'] = [round(x / width, 4), round((y - dy) / height, 4),
                                               round(w / width, 4), round(h / height, 4)]
                proposal.verified['balance'] = amount
                proposal.notes.append(f'balance: etiqueta no legible; importe {amount} encima de la apuesta '
                                      '(por posición, REVISAR en la imagen anotada)')
                break
    if 'balance' in proposal.regions:
        proposal.regions['currency'] = list(proposal.regions['balance'])
    proposal.notes = [n for n in proposal.notes
                      if not (n.startswith('No se encontró la etiqueta de ') and n.rsplit(' ', 1)[-1] in proposal.verified)]
    proposal.spin_candidates = find_spin_candidates(frame)
    return proposal


START_UPSCALE = 2
START_WORDS = ('CONTINUAR', 'CONTINUE', 'JUGAR', 'PLAY', 'START', 'EMPEZAR', 'COMENZAR', 'ENTRAR', 'ACEPTAR')


def find_start_button(frame: np.ndarray, language: str = 'spa+eng') -> Optional[Tuple[int, int]]:
    """Centro (x, y) del botón de una pantalla de inicio («CONTINUAR», «JUGAR»...), o None.

    Solo busca palabras de arranque en toda la captura; se usa ANTES de que exista el HUD, así que pulsarlo no
    puede apostar. Si hay varias, se elige la más baja (los botones de inicio van abajo)."""
    import pytesseract
    from .ocr import _locate_tesseract
    _locate_tesseract(pytesseract)
    top = int(0.55 * frame.shape[0])     # los botones de inicio están en la parte baja; leer solo esa franja es mucho más rápido
    gray = cv2.resize(to_gray(frame[top:]), None, fx=START_UPSCALE, fy=START_UPSCALE, interpolation=cv2.INTER_CUBIC)
    best: Optional[Tuple[int, int]] = None
    for image in (gray, cv2.bitwise_not(gray)):
        for psm in (6,):
            try:
                data = pytesseract.image_to_data(image, lang=language, config=f'--psm {psm}',
                                                 output_type=pytesseract.Output.DICT)
            except pytesseract.TesseractError:
                data = pytesseract.image_to_data(image, lang='eng', config=f'--psm {psm}',
                                                 output_type=pytesseract.Output.DICT)
            for i, text in enumerate(data['text']):
                word = _norm(text)
                if len(word) < 4 or float(data['conf'][i]) <= 0:
                    continue
                if any(SequenceMatcher(None, word, s).ratio() >= 0.8 for s in START_WORDS):
                    cx = (data['left'][i] + data['width'][i] // 2) // START_UPSCALE
                    cy = (data['top'][i] + data['height'][i] // 2) // START_UPSCALE + top
                    if best is None or cy > best[1]:
                        best = (cx, cy)
    return best
