"""Importes monetarios con Decimal. Nunca se adivina ni se rellena con cero."""
import re
from decimal import Decimal


def parse_money(text: str, decimal_separator: str = '.') -> Decimal:
    """Extrae UN importe con exactamente dos decimales y el separador del perfil.

    Rechaza (ValueError) texto vacío, varios números o formatos ambiguos en vez
    de adivinar. El separador depende de lo observado en el juego, no del dominio.
    """
    if decimal_separator not in ('.', ','):
        raise ValueError('Separador decimal inválido')
    group = ',' if decimal_separator == '.' else '.'
    pattern = (rf'(?:\d{{1,3}}(?:{re.escape(group)}\d{{3}})+|\d+)'
               rf'{re.escape(decimal_separator)}\d{{2}}')
    tokens = re.findall(r'[\d.,]+', text)
    if len(tokens) != 1 or not re.fullmatch(pattern, tokens[0]):
        raise ValueError(f'Importe ilegible o ambiguo: {text!r}')
    return Decimal(tokens[0].replace(group, '').replace(decimal_separator, '.'))


def parse_money_lenient(text: str, decimal_separator: str = '.', integer_ok: bool = False) -> Decimal:
    """Como parse_money, pero tolera que el OCR confunda la coma y el punto decimales.

    Un único importe con exactamente DOS decimales tras un único separador no puede ser un separador de miles
    (que exige tres dígitos), así que «1.60» y «1,60» valen lo mismo. Todo lo demás se rechaza igual.

    `integer_ok`: acepta un entero sin decimales («2 €»), solo si el llamador sabe que el importe lleva símbolo de
    moneda (hay juegos que muestran la apuesta sin decimales)."""
    try:
        return parse_money(text, decimal_separator)
    except ValueError:
        tokens = re.findall(r'[\d.,]+', text)
        if len(tokens) == 1 and re.fullmatch(r'\d+[.,]\d{2}', tokens[0]):
            return Decimal(tokens[0].replace(',', '.'))
        if integer_ok and len(tokens) == 1 and re.fullmatch(r'\d{1,6}', tokens[0]):
            return Decimal(tokens[0])
        raise


def reconcile(before: Decimal, wager: Decimal, payout: Decimal, after: Decimal) -> bool:
    """balance_final == balance_inicial - apuesta + premio (aritmética exacta)."""
    for value in (before, wager, payout, after):
        if not isinstance(value, Decimal):
            raise TypeError('reconcile exige Decimal; no usar float')
    return before - wager + payout == after
