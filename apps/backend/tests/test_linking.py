from pathlib import Path

import pytest

from nyanko_api.database import Database
from nyanko_api.linking import (
    SeriesLink,
    UnlinkedSeriesError,
    require_link,
    resolve_link,
)
from nyanko_api.models import MediaItem


def _database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "nyanko.sqlite3")
    database.initialize()
    return database


def test_el_vinculo_confirmado_conserva_media_id_y_offset(tmp_path):
    database = _database(tmp_path)
    database.set_media_mapping(
        "local_archive",
        "0:Berserk",
        42,
        chapter_offset=100,
        manga_link=True,
    )

    assert require_link(database, "local_archive", "0:Berserk") == SeriesLink(
        source_name="local_archive",
        series_id="0:Berserk",
        media_id=42,
        chapter_offset=100,
    )


@pytest.mark.parametrize(
    ("chapter", "offset", "expected"),
    [(12.5, 100, 112.5), (12.5, 0, 12.5), (12, -10, 2)],
)
def test_el_capitulo_absoluto_conserva_decimales(chapter, offset, expected):
    link = SeriesLink("local_archive", "0:Berserk", 42, offset)

    assert link.absolute_chapter(chapter) == expected


def test_una_propuesta_fuerte_no_es_un_vinculo_confirmado(tmp_path):
    database = _database(tmp_path)

    with pytest.raises(UnlinkedSeriesError):
        require_link(database, "local_archive", "0:Berserk")

    mapping = database.sync_provider_library(
        "anilist",
        "AniList",
        [
            MediaItem(
                id=42,
                title="Berserk",
                status="CURRENT",
                progress=11,
                chapters=364,
                media_type="MANGA",
            )
        ],
        media_type="MANGA",
    )
    database.set_match_correction("berserk", 42)

    with database.connect() as connection:
        mappings_antes = connection.execute("SELECT COUNT(*) FROM media_mappings").fetchone()[0]

    # Leo el capítulo 12 de A, una propuesta difusa elige B y la app podría escribir en
    # el AniList real de B. pending_mutations lo reintentaría y no habría deshacer.
    with pytest.raises(UnlinkedSeriesError) as exc:
        require_link(database, "local_archive", "0:Berserk")

    assert mapping["42"] > 0
    assert exc.value.message
    assert "0:Berserk" in exc.value.message
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM pending_mutations").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM media_mappings").fetchone()[0] == mappings_antes


def test_preguntar_cien_veces_no_crea_el_vinculo(tmp_path):
    database = _database(tmp_path)

    for _ in range(100):
        assert resolve_link(database, "local_archive", "0:Berserk") is None

    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM media_mappings").fetchone()[0] == 0


def test_un_mapping_de_anime_no_es_un_vinculo_de_manga(tmp_path):
    database = _database(tmp_path)
    database.set_media_mapping("crunchyroll", "abc", 777, 3)

    # Este fallo no pasa por el escritor: sin el guarda de lectura, el id externo 777
    # saldría como canónico y linked=true aunque el usuario nunca confirmó el vínculo.
    with pytest.raises(ValueError):
        resolve_link(database, "crunchyroll", "abc")
    with pytest.raises(ValueError) as exc:
        require_link(database, "crunchyroll", "abc")

    assert not isinstance(exc.value, UnlinkedSeriesError)
    assert database.get_media_mapping("crunchyroll", "abc") == (777, 3)
