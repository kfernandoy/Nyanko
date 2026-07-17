import re

__all__ = ["recognize_chapter"]


_MARCADOR_VOLUMEN = re.compile(
    r"\b(?:version|volume|season|ver|vol|v|s)[^a-z]*\d+(?:\.\d+)?",
    re.ASCII,
)
_MARCADOR_CAPITULO = re.compile(
    r"\b(?:chapter|ch|capitulo|cap)\.?\s*(\d+)(?:\.(\d+))?([a-z]+)?",
    re.ASCII,
)
_NUMERO = re.compile(r"(?<!\d)(\d+)(?:\.(\d+))?([a-z]+)?", re.ASCII)
_ESPACIO_ANTES_DEL_SUFIJO = re.compile(
    r"\s+(?=extra\b|special\b|omake\b)",
    re.ASCII,
)

# Estos decimales expresan ORDEN: cada variante va despues del capitulo base y
# antes del siguiente, sin chocar con un decimal explicito como 12.5.
_SUFIJO_EXTRA = 0.99
_SUFIJO_OMAKE = 0.98
_SUFIJO_ESPECIAL = 0.97
_SUFIJOS_CON_NOMBRE = {
    "extra": _SUFIJO_EXTRA,
    "omake": _SUFIJO_OMAKE,
    "special": _SUFIJO_ESPECIAL,
}


def _numero_de_la_coincidencia(coincidencia: re.Match[str]) -> float:
    entero = int(coincidencia.group(1))
    decimal = coincidencia.group(2)
    sufijo = coincidencia.group(3) or ""

    if decimal is not None:
        return float(f"{entero}.{decimal}")
    if sufijo in _SUFIJOS_CON_NOMBRE:
        return entero + _SUFIJOS_CON_NOMBRE[sufijo]
    if len(sufijo) == 1:
        posicion = ord(sufijo) - ord("a") + 1
        if 1 <= posicion <= 9:
            return entero + posicion / 10
    return float(entero)


def recognize_chapter(name: str, series_title: str | None = None) -> float | None:
    """Reconoce un capitulo sin inventar un numero cuando el nombre es ambiguo."""
    normalizado = name.casefold()
    if series_title:
        normalizado = normalizado.replace(series_title.casefold(), "", 1).strip()
    normalizado = normalizado.replace(",", ".").replace("-", ".")
    normalizado = _ESPACIO_ANTES_DEL_SUFIJO.sub("", normalizado)
    normalizado = _MARCADOR_VOLUMEN.sub("", normalizado)

    coincidencia = _MARCADOR_CAPITULO.search(normalizado)
    if coincidencia is not None:
        return _numero_de_la_coincidencia(coincidencia)

    coincidencias = list(_NUMERO.finditer(normalizado))
    if len(coincidencias) != 1:
        return None
    return _numero_de_la_coincidencia(coincidencias[0])
