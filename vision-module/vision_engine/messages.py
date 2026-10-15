"""Detección de mensajes de saldo insuficiente con frases calibradas por mercado."""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Sequence, Tuple

from .errors import ProfileError

# Palabras que por sí solas NO prueban un rechazo. Un patrón que coincida con
# alguna de ellas aislada es demasiado genérico y se rechaza al cargar el perfil.
GENERIC_WORDS = (
    'balance', 'saldo', 'funds', 'fondos', 'credit', 'credito', 'insufficient',
    'insuficiente', 'insuficientes', 'not enough', 'error', 'deposit', 'deposito',
)


def normalize_text(text: str) -> str:
    """Minúsculas, sin tildes y con espacios colapsados."""
    decomposed = unicodedata.normalize('NFD', text.lower())
    without_marks = ''.join(c for c in decomposed if unicodedata.category(c) != 'Mn')
    return ' '.join(without_marks.split())


def compile_patterns(patterns: Iterable[str]) -> Tuple[re.Pattern, ...]:
    """Compila patrones (escritos en minúsculas y sin tildes) y rechaza los genéricos."""
    compiled = []
    for pattern in patterns:
        if not isinstance(pattern, str) or not pattern:
            raise ProfileError('Cada patrón de insuficiencia debe ser un texto no vacío')
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            raise ProfileError(f'Patrón inválido {pattern!r}: {exc}') from exc
        generic = [word for word in GENERIC_WORDS if regex.search(word)]
        if generic:
            raise ProfileError(f'Patrón {pattern!r} demasiado genérico: coincide con {generic}')
        compiled.append(regex)
    return tuple(compiled)


def matches_any(text: str, patterns: Sequence[re.Pattern]) -> bool:
    normalized = normalize_text(text)
    return any(pattern.search(normalized) for pattern in patterns)
