from dataclasses import dataclass

from .database import Database, assert_manga_namespace


@dataclass(frozen=True, slots=True)
class SeriesLink:
    """Vínculo confirmado entre una serie de una fuente y la biblioteca.

    ``media_id`` es el id canónico (``media.id``), nunca el externo del proveedor. La
    Fase 5 lo convierte al escribir con ``database.external_id_for_account``.
    """

    source_name: str
    series_id: str
    media_id: int
    chapter_offset: int

    def absolute_chapter(self, chapter: float) -> float:
        return chapter + self.chapter_offset


class UnlinkedSeriesError(Exception):
    def __init__(self, source_name: str, series_id: str):
        self.message = (
            f"La serie {series_id!r} de {source_name!r} no está vinculada a ninguna "
            "entrada de tu biblioteca. Vincúlala para poder sincronizar el progreso."
        )
        super().__init__(self.message)


def resolve_link(
    database: Database, source_name: str, series_id: str
) -> SeriesLink | None:
    assert_manga_namespace(source_name, manga_link=True)
    # Sin la guarda anterior, un mapping legítimo de anime ('crunchyroll', 'abc') -> 777
    # saldría como vínculo confirmado de manga y como id canónico, aunque 777 sea externo.
    mapping = database.get_media_mapping_full(source_name, series_id)
    if mapping is None:
        return None
    # En manga, «hay fila» significa «el usuario confirmó». Lo sostienen el único escritor
    # del plan 04-03 y esta lectura, que no admite filas de otro namespace como vínculos.
    return SeriesLink(
        source_name=source_name,
        series_id=series_id,
        media_id=mapping["media_id"],
        chapter_offset=mapping["chapter_offset"],
    )


def require_link(database: Database, source_name: str, series_id: str) -> SeriesLink:
    # Esta es LA puerta de LNK-04: la Fase 5 la cruza ANTES de enqueue_mutation o
    # construiría una escritura duradera sobre una serie que el usuario no confirmó.
    link = resolve_link(database, source_name, series_id)
    if link is None:
        raise UnlinkedSeriesError(source_name, series_id)
    return link
