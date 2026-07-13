"""El modelo de progreso, puro: sin BD, sin HTTP, sin imports del proyecto.

Aquí vive la ÚNICA definición de cómo el progreso cruza hacia el proveedor. Es un módulo
aparte a propósito: la alternativa es que esta lógica acabe embadurnada dentro de un
endpoint, entre el reader y el sync, y sin testear en ninguno de los dos.

Ver docs/specs/progress-model.md para el porqué de cada decisión.
"""
import math


def to_provider(chapter: float) -> int:
    """El capítulo local (10.5) → el entero que el proveedor acepta (10).

    Los trackers solo aceptan enteros (`$progress: Int!`). Este es el único sitio donde se
    aplica el floor, y solo se aplica al cruzar hacia el proveedor.
    """
    return math.floor(chapter)


def next_progress(chapter: float, tracker_progress: int | None) -> int | None:
    """El valor a enviar al tracker, o `None` si no hay nada que enviar.

    `None` no es un error: «no hay que subir nada» es un resultado normal, y el llamador lo
    trata como «no encolar». La comparación es contra `tracker_progress` — el espejo del
    proveedor (`Database.tracker_progress`) —, NO contra el progreso local, que la UI ya
    movió de forma optimista.

    Sin valor del tracker, falla cerrado: no se escribe a ciegas en la lista real del usuario.

    No recibe el estado del tracker a propósito: la guarda monotónica ya cubre la relectura,
    y una firma que pide un estado que el cuerpo no lee promete una consciencia que no tiene.
    Quien necesite esa señal llama a `is_reread`, que sí la lee.
    """
    if tracker_progress is None:
        return None
    candidate = to_provider(chapter)
    if candidate <= tracker_progress:
        # Guarda monotónica: nunca se retrocede el progreso del tracker. Cubre a la vez el
        # reenvío redundante (candidate == tracker), la regresión, y la relectura de una
        # serie terminada (ver is_reread: la UX de REPEATING la decide SYN-04, en la Fase 5).
        return None
    return candidate


def is_reread(
    chapter: float,
    tracker_progress: int | None,
    tracker_status: str | None,
) -> bool:
    """¿El usuario está releyendo una serie que el tracker da por terminada?

    `next_progress` ya devuelve `None` en este caso (la guarda monotónica lo cubre); esto es
    solo la SEÑAL, para que la Fase 5 no tenga que reimplementar la comprobación dentro de un
    endpoint. Desconocido no es relectura: sin valor del tracker no se afirma nada.
    """
    if tracker_progress is None or tracker_status != "COMPLETED":
        return False
    return to_provider(chapter) <= tracker_progress


def effective_chapter(progress: int, chapter_progress: float | None) -> float:
    """El capítulo que el usuario leyó de verdad, reconciliado AL LEER.

    `progress` (INTEGER) es siempre autoritativo. `chapter_progress` (REAL) solo vale
    mientras `floor(chapter_progress) == progress`; si no cuadran, el tracker se movió por
    debajo (p. ej. el sync de `database.py:2639`) y el decimal es basura.

    La regla se evalúa aquí, no se mantiene en los cuatro escritores de `progress`. Un
    invariante que hay que mantener en cuatro sitios es un invariante que se rompe.
    """
    if chapter_progress is None or to_provider(chapter_progress) != progress:
        return float(progress)
    return float(chapter_progress)
