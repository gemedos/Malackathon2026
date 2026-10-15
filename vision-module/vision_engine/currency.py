"""Detección explícita de moneda en el texto OCR de la región `currency`."""
import re

# Marcadores reconocibles. Se incluyen monedas ajenas a los mercados para poder
# demostrar una moneda INCORRECTA (FAIL) en lugar de tratarla como ilegible.
CURRENCY_MARKERS = {
    'EUR': (r'\bEUR\b', r'€'),
    'PEN': (r'\bPEN\b', r'(?<![A-Z])S/'),
    'USD': (r'\bUSD\b', r'US\$'),
    'GBP': (r'\bGBP\b', r'£'),
}


def detect_currency(text: str) -> str:
    """Devuelve el código ISO observado o ValueError si es ilegible o ambiguo."""
    upper = text.upper()
    found = {code for code, patterns in CURRENCY_MARKERS.items()
             if any(re.search(pattern, upper) for pattern in patterns)}
    if not found:
        raise ValueError(f'Moneda ilegible: {text!r}')
    if len(found) > 1:
        raise ValueError(f'Moneda ambigua {sorted(found)}: {text!r}')
    return found.pop()
