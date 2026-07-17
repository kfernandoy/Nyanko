from inspect import signature
from typing import get_type_hints

import pytest

from nyanko_api.chapter_recognition import recognize_chapter


@pytest.mark.parametrize(
    ("nombre", "titulo_serie", "esperado"),
    [
        # La regex actual de local_archive.py:242-244 devuelve 12.0.
        pytest.param("Ch.12 extra", None, 12.99, id="extra-despues-del-capitulo"),
        pytest.param("Ch.12 omake", None, 12.98, id="omake-despues-del-capitulo"),
        pytest.param("12a", None, 12.1, id="primera-letra-como-decimal"),
        pytest.param("12b", None, 12.2, id="segunda-letra-como-decimal"),
        pytest.param("Ch.12 special", None, 12.97, id="especial-despues-del-capitulo"),
        pytest.param("Cap 12", None, 12.0, id="capitulo-simple"),
        pytest.param("Chapter 10.5", None, 10.5, id="decimal-explicito"),
        pytest.param("Cap 004", None, 4.0, id="ceros-a-la-izquierda"),
        # La regex actual de local_archive.py:242-244 devuelve 2.0.
        pytest.param("Vol.2 Ch.15", None, 15.0, id="ignora-el-volumen"),
        pytest.param(
            "Berserk 12",
            "Berserk",
            12.0,
            id="descuenta-el-titulo-de-la-serie",
        ),
        # La regex actual de local_archive.py:242-244 devuelve 100.0.
        pytest.param(
            "Mob Psycho 100 5",
            "Mob Psycho 100",
            5.0,
            id="descuenta-un-numero-del-titulo",
        ),
        pytest.param("Prologo", None, None, id="sin-numero"),
        pytest.param("", None, None, id="nombre-vacio"),
        pytest.param("12z", None, 12.0, id="letra-fuera-del-rango-decimal"),
    ],
)
def test_reconoce_el_numero_de_capitulo(nombre, titulo_serie, esperado):
    assert recognize_chapter(nombre, titulo_serie) == esperado


def test_la_firma_solo_acepta_texto_y_devuelve_numero_o_ausencia():
    firma = signature(recognize_chapter)

    assert tuple(firma.parameters) == ("name", "series_title")
    assert firma.parameters["series_title"].default is None
    assert get_type_hints(recognize_chapter) == {
        "name": str,
        "series_title": str | None,
        "return": float | None,
    }
