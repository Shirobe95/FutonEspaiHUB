"""Lectura de importes escritos por personas (precios, costes, ajustes de precio).

Regla acordada con Futón Espai:

* ``1.250``  -> 1250   (un punto seguido de exactamente 3 cifras y un entero de 1-3 cifras: separador de miles)
* ``1.25``   -> 1.25   (punto con 1, 2 o más de 3 cifras decimales: decimal)
* ``1,25``   -> 1.25   (la coma es siempre decimal)
* ``1.234,56`` y ``1,234.56`` -> 1234.56 (si hay punto y coma, manda el último como decimal)
* ``1.234.567`` -> 1234567 (varios puntos: miles)
* ``0.250``  -> 0.25   (un entero que empieza por 0 nunca es «miles»)
* ``nan``, ``inf``, vacío o texto -> no es un importe (``None``)

El único caso realmente ambiguo es «N.NNN» (por ejemplo 1.250): se toma como miles, y
``describe_amount_interpretation`` devuelve el texto para que la pantalla avise de cómo se leyó.
"""
from __future__ import annotations

import math
import re
from typing import Any

_STRIP = re.compile(r"(?i)\s| |eur(?:os?)?|€|\$|â‚¬")
_PLAIN = re.compile(r"^[+-]?\d+$")
_THOUSANDS_DOT = re.compile(r"^[+-]?[1-9]\d{0,2}\.\d{3}$")
_MULTI_THOUSANDS = re.compile(r"^[+-]?[1-9]\d{0,2}(\.\d{3}){2,}$")


def _clean(value: Any) -> str:
    return _STRIP.sub("", str(value)).strip()


def parse_amount(value: Any) -> float | None:
    """Importe como float, o ``None`` si no es un número finito."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    text = _clean(value)
    if not text:
        return None
    has_dot, has_comma = "." in text, "," in text
    if has_dot and has_comma:
        decimal = "." if text.rfind(".") > text.rfind(",") else ","
        thousands = "," if decimal == "." else "."
        text = text.replace(thousands, "").replace(decimal, ".")
    elif has_comma:
        if text.count(",") > 1:
            text = text.replace(",", "")
        else:
            text = text.replace(",", ".")
    elif has_dot:
        if _MULTI_THOUSANDS.match(text) or _THOUSANDS_DOT.match(text):
            text = text.replace(".", "")
        elif text.count(".") > 1:
            return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def is_ambiguous_amount(value: Any) -> bool:
    """True para «N.NNN»: se lee como miles, aunque también podría ser un decimal."""
    if value is None:
        return False
    text = _clean(value)
    return bool(_THOUSANDS_DOT.match(text))


def describe_amount_interpretation(value: Any) -> str | None:
    """Aviso para la interfaz cuando la lectura de lo escrito no es evidente."""
    if not is_ambiguous_amount(value):
        return None
    number = parse_amount(value)
    if number is None:
        return None
    shown = f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"«{str(value).strip()}» se ha leído como {shown} (el punto se toma como separador de miles)."
