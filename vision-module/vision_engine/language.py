"""Idioma de un mensaje visible (inglés/español) por palabras frecuentes.

Heurística deliberadamente simple: solo decide si hay al menos dos palabras
del idioma y claramente más que del otro; si no, devuelve None (desconocido).
"""
from __future__ import annotations

import re
from typing import Optional

from .messages import normalize_text

_WORDS = {
    'en': {'the', 'you', 'your', 'not', 'enough', 'insufficient', 'balance', 'funds', 'please',
           'to', 'of', 'is', 'are', 'have', 'deposit', 'credit', 'money', 'low', 'too', 'bet'},
    'es': {'el', 'la', 'los', 'las', 'de', 'tu', 'su', 'tienes', 'tiene', 'saldo', 'fondos',
           'insuficiente', 'insuficientes', 'suficiente', 'suficientes', 'para', 'por', 'deposita',
           'apuesta', 'hay', 'dinero', 'credito'},
}
MIN_WORDS = 2


def detect_language(text: str) -> Optional[str]:
    tokens = re.findall(r'[a-z]+', normalize_text(text))
    counts = {language: sum(token in words for token in tokens) for language, words in _WORDS.items()}
    best = max(counts, key=counts.get)
    others = [count for language, count in counts.items() if language != best]
    if counts[best] >= MIN_WORDS and all(counts[best] > count for count in others):
        return best
    return None
