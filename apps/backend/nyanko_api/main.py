import asyncio
import hashlib
import threading
import json
import logging
import os
import secrets
import subprocess
import sys
import time
import mimetypes
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)
from dataclasses import asdict
from difflib import SequenceMatcher
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TypeVar
from urllib.parse import urlsplit

from enum import StrEnum

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .anilist import AniListClient, AniListError
from .config import Settings, get_settings
from .database import Database
from .detectors import (
    ActiveWindowDetector,
    BrowserDetector,
    DetectorManager,
    MediaPlayerWindowDetector,
    MpcHcDetector,
    MpvDetector,
    PotPlayerDetector,
    ProcessDetector,
    SmtcDetector,
    VlcDetector,
    is_detection_paused,
    looks_finished,
    set_detection_paused,
)
from .instance import find_free_port, generate_token, read_token_file, write_port_file, write_token_file
from .matcher import build_token_index, find_best_match, find_best_search_match, match_from_index, rank_matches
from .stats import statistics_from_items
from .kitsu import KitsuClient, KitsuCredential, KitsuError
from .myanimelist import MyAnimeListClient, MyAnimeListCredential, MyAnimeListError
from .secrets import (
    delete_anilist_token,
    delete_provider_credential,
    get_anilist_token,
    get_provider_credential,
    init_credentials_dir,
    migrate_token_from_database,
    set_anilist_token,
    set_provider_credential,
)
from .models import (
    AccountInfo,
    AccountUpdate,
    AccountUpdateResult,
    ActivityItem,
    StatisticsResponse,
    BulkUpdateResult,
    CacheStatusItem,
    CacheStatusResponse,
    ConflictInfo,
    ConflictResolution,
    DetectorUpdate,
    ExtensionClientInfo,
    ExtensionPairingResponse,
    ExtensionPairRequest,
    ExtensionPlaybackEvent,
    ExtensionRotateRequest,
    ExtensionTokenResponse,
    FuzzyDate,
    GlobalSearchResponse,
    HealthResponse,
    LibraryFolder,
    LibraryFolderCreate,
    LibrarySearchResponse,
    MatchCorrectionRequest,
    MediaDetails,
    MediaEntryUpdate,
    MediaListEntry,
    MediaItem,
    MediaTagUpdate,
    PendingLocalItem,
    PlaybackCandidate,
    PlaybackConfirmRequest,
    PlaybackEvent,
    PlaybackIgnoreRequest,
    PlaybackMatchRequest,
    PlaybackMatchResponse,
    PlaybackPreferences,
    PlaybackRetryResponse,
    PlaybackUndoResponse,
    ProgressUpdate,
    ProviderCapabilitiesResponse,
    ProviderInfo,
    ScanSettings,
    ScanSummary,
    SearchFilters,
    SearchResult,
    SeasonMedia,
    SyncStatusItem,
    SyncStatusResponse,
    UserPreferences,
    UserPreferencesUpdate,
    DiscoverSettingsUpdate,
    WontWatchItem,
    WontWatchRequest,
    WontWatchState,
    TorrentSource,
    TorrentSourceInput,
    TorrentFilter,
    TorrentFilterInput,
    TorrentSettings,
    TorrentItem,
    TorrentActionRequest,
    TorrentDownloadResponse,
    LocalSeries,
    LocalAssociateRequest,
)
from .normalizer import fold_title, folded_title, normalize, normalize_title
from .providers import MyAnimeListProvider, build_provider_registry
from .scanner import iter_video_files, parse_file
from . import torrents as torrents_mod


ModelT = TypeVar("ModelT", bound=BaseModel)


class CacheStatus(StrEnum):
    HIT = "hit"
    STALE = "stale"
    MISS = "miss"


_cache_refreshes: dict[tuple[str, str], asyncio.Task] = {}
_media_refreshes: dict[tuple[str, str, str, str, int], asyncio.Task] = {}
_library_asset_warmers: dict[tuple[str, str, str, str], asyncio.Task] = {}
_library_detail_warmers: dict[tuple[str, str, str, str], asyncio.Task] = {}
# Progreso del backfill de detalles, para la barra de la UI. Una entrada por warm_key.
_backfill_progress: dict[tuple[str, str, str, str], dict] = {}
DEFAULT_ACCOUNT_ALIAS = "default"

# Caché signature -> link (poblada al construir el feed; el frontend solo manda la signature).
_torrent_link_cache: dict[str, str] = {}
# Caché signature -> {media_title, episode} para subcarpeta y append de episodio.
_torrent_item_cache: dict[str, dict] = {}
# Contador de novedades calculado por el loop de fondo (Task 5).
_torrent_unread: dict[str, int] = {"count": 0}


def schedule_cache_refresh(
    database: Database, key: str, refresh: Callable[[], Awaitable[None]]
) -> None:
    refresh_key = (str(database.path), key)
    if task := _cache_refreshes.get(refresh_key):
        if not task.done():
            return

    async def run() -> None:
        try:
            await refresh()
        except Exception:
            pass
        finally:
            _cache_refreshes.pop(refresh_key, None)

    _cache_refreshes[refresh_key] = asyncio.create_task(run())


async def cached_value(
    database: Database,
    key: str,
    ttl_seconds: int,
    model: type[ModelT],
    loader: Callable[[], Awaitable[ModelT]],
) -> tuple[ModelT, CacheStatus]:
    record = database.get_cache_record(key)
    if record is not None and not record.stale:
        return model.model_validate(record.payload), CacheStatus.HIT
    if record is not None:
        async def refresh() -> None:
            value = await loader()
            database.set_cache(key, value.model_dump(mode="json"), ttl_seconds)

        schedule_cache_refresh(database, key, refresh)
        return model.model_validate(record.payload), CacheStatus.STALE
    value = await loader()
    database.set_cache(key, value.model_dump(mode="json"), ttl_seconds)
    return value, CacheStatus.MISS


async def cached_list(
    database: Database,
    key: str,
    ttl_seconds: int,
    model: type[ModelT],
    loader: Callable[[], Awaitable[list[ModelT]]],
) -> tuple[list[ModelT], CacheStatus]:
    record = database.get_cache_record(key)
    if record is not None and not record.stale:
        return [model.model_validate(item) for item in record.payload], CacheStatus.HIT
    if record is not None:
        async def refresh() -> None:
            values = await loader()
            database.set_cache(
                key,
                [value.model_dump(mode="json") for value in values],
                ttl_seconds,
            )

        schedule_cache_refresh(database, key, refresh)
        return [model.model_validate(item) for item in record.payload], CacheStatus.STALE
    values = await loader()
    database.set_cache(key, [value.model_dump(mode="json") for value in values], ttl_seconds)
    return values, CacheStatus.MISS


def get_database(settings: Settings = Depends(get_settings)) -> Database:
    return Database(settings.database_path)


# Biblioteca validada+enriquecida por clave de caché: validar ~2300 modelos pydantic
# y enriquecerlos en cada request costaba segundos en los caminos calientes
# (re-match cada 8 s, búsqueda del panel). Se invalida cuando cambia updated_at.
_library_memo: dict[tuple[str, str], tuple[int, list]] = {}


async def _playback_library(
    database: Database, provider: str, account: str, token: str, media_provider
) -> tuple[list, CacheStatus]:
    key = account_cache_key(provider, account, "list")
    memo_key = (str(database.path), key)
    meta = database.get_cache_meta(key)
    memo = _library_memo.get(memo_key)
    if meta is not None and memo is not None and memo[0] == meta[0]:
        if not meta[1]:
            return memo[1], CacheStatus.HIT

        async def refresh() -> None:
            values = await media_provider.library(token)
            database.set_cache(key, [v.model_dump(mode="json") for v in values], 300)
            database.sync_provider_library(
                media_provider.name, media_provider.display_name, values, account_alias=account
            )

        schedule_cache_refresh(database, key, refresh)
        return memo[1], CacheStatus.STALE
    library, status = await cached_list(
        database, key, 300, MediaItem, lambda: media_provider.library(token)
    )
    if status != CacheStatus.HIT:
        database.sync_provider_library(
            media_provider.name, media_provider.display_name, library, account_alias=account
        )
    enriched = database.enrich_provider_library(media_provider.name, library)
    meta = database.get_cache_meta(key)
    if meta is not None:
        _library_memo[memo_key] = (meta[0], enriched)
    return enriched, status


def get_active_account(request: Request) -> tuple[str, str]:
    return (
        request.query_params.get("provider") or "anilist",
        DEFAULT_ACCOUNT_ALIAS,
    )


async def require_token(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> str:
    provider, account = get_active_account(request)
    token = get_provider_credential(provider, account)
    if not token:
        raise HTTPException(
            status_code=401,
            detail=f"{provider} account is not authenticated: {account}",
        )
    token = await _refresh_mal_if_needed(provider, account, token, settings)
    return await _refresh_kitsu_if_needed(provider, account, token, settings)


async def optional_token(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> str | None:
    provider, account = get_active_account(request)
    token = get_provider_credential(provider, account)
    if not token:
        return None
    token = await _refresh_mal_if_needed(provider, account, token, settings)
    return await _refresh_kitsu_if_needed(provider, account, token, settings)


def account_cache_key(provider: str, account: str, resource: str) -> str:
    return f"{provider}:{account}:{resource}"


def _asset_dir(settings: Settings, provider: str, external_id: int | str) -> Path:
    return settings.assets_dir / provider / str(external_id)


def _api_base_url(settings: Settings) -> str:
    host = settings.api_host if settings.api_host not in {"", "0.0.0.0", "::"} else "127.0.0.1"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"http://{host}:{settings.api_port}"


def _asset_url(settings: Settings, provider: str, external_id: int | str, filename: str) -> str:
    return f"{_api_base_url(settings)}/assets/{provider}/{external_id}/{filename}"


def _find_local_asset_filename(
    settings: Settings, provider: str, external_id: int | str, stem: str
) -> str | None:
    directory = _asset_dir(settings, provider, external_id)
    if not directory.exists():
        return None
    for path in directory.glob(f"{stem}.*"):
        if path.is_file():
            return path.name
    return None


def _local_asset_url(
    settings: Settings, provider: str, external_id: int | str, stem: str
) -> str | None:
    filename = _find_local_asset_filename(settings, provider, external_id, stem)
    if filename is None:
        return None
    return _asset_url(settings, provider, external_id, filename)


def _guess_asset_extension(url: str, content_type: str | None) -> str:
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";", 1)[0].strip())
        if guessed:
            return guessed
    suffix = Path(urlsplit(url).path).suffix
    if suffix and len(suffix) <= 5:
        return suffix
    return ".jpg"


async def _download_asset(
    settings: Settings, url: str | None, provider: str, external_id: int | str, stem: str
) -> str | None:
    if not url:
        return None
    directory = _asset_dir(settings, provider, external_id)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
    except Exception:
        return None
    extension = _guess_asset_extension(url, response.headers.get("content-type"))
    target = directory / f"{stem}{extension}"

    # El backfill de la biblioteca baja miles de imágenes; escribir a disco en el event
    # loop lo bloqueaba y congelaba toda la app "al principio". Va a un hilo.
    def _write_file() -> None:
        tmp = directory / f"{stem}{extension}.tmp"
        tmp.write_bytes(response.content)
        tmp.replace(target)
        for stale in directory.glob(f"{stem}.*"):
            if stale != target and stale.is_file():
                stale.unlink(missing_ok=True)

    await asyncio.to_thread(_write_file)
    return _asset_url(settings, provider, external_id, target.name)


def _localize_media_details_assets(
    settings: Settings, provider: str, details: MediaDetails
) -> MediaDetails:
    updates: dict[str, object] = {}
    if local_cover := _local_asset_url(settings, provider, details.id, "cover"):
        updates["cover_image"] = local_cover
    if local_banner := _local_asset_url(settings, provider, details.id, "banner"):
        updates["banner_image"] = local_banner
    if details.relations:
        updates["relations"] = [
            rel.model_copy(
                update={"cover_image": _local_asset_url(settings, provider, rel.id, "cover") or rel.cover_image}
            )
            for rel in details.relations
        ]
    if details.recommendations:
        updates["recommendations"] = [
            rec.model_copy(
                update={"cover_image": _local_asset_url(settings, provider, rec.id, "cover") or rec.cover_image}
            )
            for rec in details.recommendations
        ]
    return details.model_copy(update=updates) if updates else details


def _missing_detail_assets(settings: Settings, provider: str, external_id: int, details: MediaDetails) -> bool:
    return (
        bool(details.cover_image) and _local_asset_url(settings, provider, external_id, "cover") is None
    ) or (
        bool(details.banner_image) and _local_asset_url(settings, provider, external_id, "banner") is None
    )


async def _download_detail_assets(
    database: Database,
    settings: Settings,
    provider: str,
    external_id: int,
    details: MediaDetails,
    *,
    include_related: bool = True,
) -> None:
    if include_related:
        cover_local = await _download_asset(settings, details.cover_image, provider, external_id, "cover")
        banner_local = await _download_asset(settings, details.banner_image, provider, external_id, "banner")
    else:
        # Backfill masivo: lo que ya está en disco solo se registra, no se re-baja.
        # La apertura de una card (include_related=True) sí re-descarga y refresca.
        cover_local = _local_asset_url(settings, provider, external_id, "cover") or await _download_asset(
            settings, details.cover_image, provider, external_id, "cover"
        )
        banner_local = _local_asset_url(settings, provider, external_id, "banner") or await _download_asset(
            settings, details.banner_image, provider, external_id, "banner"
        )
    await asyncio.to_thread(
        database.set_media_asset_paths,
        provider,
        external_id,
        cover_image_local=cover_local,
        banner_image_local=banner_local,
    )
    if not include_related:
        return

    semaphore = asyncio.Semaphore(6)

    async def download_cover(item) -> None:
        # Ya en disco: no re-descargar. Antes cada refresh de card re-bajaba TODAS las
        # carátulas de relaciones/recomendaciones aunque ya existieran.
        if not item.cover_image or _local_asset_url(settings, provider, item.id, "cover"):
            return
        async with semaphore:
            await _download_asset(settings, item.cover_image, provider, item.id, "cover")

    await asyncio.gather(
        *(download_cover(item) for item in [*details.relations, *details.recommendations])
    )


def _persist_detail_text(
    database: Database,
    provider: str,
    account: str,
    details: MediaDetails,
    media_type: str = "ANIME",
) -> None:
    """Escrituras síncronas del texto del detalle. Bloquea mientras corre, así que
    en el backfill se invoca vía asyncio.to_thread para no frenar el event loop."""
    external_id = details.id
    database.set_cache(
        account_cache_key(
            provider, account, f"media:manga:{external_id}" if media_type == "MANGA" else f"media:{external_id}"
        ),
        details.model_dump(mode="json"),
        900,
    )
    database.set_setting(f"score_format:{provider}", details.score_format)
    database.sync_media_details(provider, external_id, details, media_type=media_type)


async def _persist_media_detail(
    database: Database,
    settings: Settings,
    provider: str,
    account: str,
    details: MediaDetails,
    *,
    media_type: str = "ANIME",
    include_related: bool = True,
    download_assets: bool = True,
) -> None:
    _persist_detail_text(database, provider, account, details, media_type)
    # download_assets=False: el texto queda disponible ya; las imágenes se bajan aparte
    # (en el backfill por lotes, en paralelo) para no serializar el guardado del texto.
    if download_assets:
        await _download_detail_assets(
            database, settings, provider, details.id, details, include_related=include_related
        )


async def _refresh_media_detail(
    database: Database,
    settings: Settings,
    provider: str,
    account: str,
    external_id: int,
    token: str,
    *,
    media_type: str = "ANIME",
    include_related: bool = True,
) -> None:
    media_provider = _get_provider(settings, provider)
    details = (
        await media_provider.manga_details(token, external_id)
        if media_type == "MANGA"
        else await media_provider.details(token, external_id)
    )
    await _persist_media_detail(
        database, settings, provider, account, details,
        media_type=media_type, include_related=include_related,
    )


# El loop solo guarda referencias débiles a las tasks: sin retener la referencia,
# una task de fondo puede ser recolectada a mitad de ejecución y morir en silencio.
_background_tasks: set[asyncio.Task] = set()


def _spawn_background(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _schedule_detail_asset_download(
    database: Database,
    settings: Settings,
    provider: str,
    external_id: int,
    details: MediaDetails,
) -> None:
    # En segundo plano: la card responde con las URLs del proveedor y las copias
    # locales quedan listas para la próxima apertura. Esperarlas bloqueaba el modal.
    async def run() -> None:
        try:
            await _download_detail_assets(database, settings, provider, external_id, details)
        except Exception:
            pass

    _spawn_background(run())


def _schedule_media_refresh(
    database: Database,
    settings: Settings,
    provider: str,
    account: str,
    external_id: int,
    token: str,
    *,
    media_type: str = "ANIME",
) -> None:
    refresh_key = (str(database.path), provider, account, media_type, external_id)
    if task := _media_refreshes.get(refresh_key):
        if not task.done():
            return

    async def run() -> None:
        try:
            await _refresh_media_detail(
                database, settings, provider, account, external_id, token, media_type=media_type
            )
        except Exception:
            pass
        finally:
            _media_refreshes.pop(refresh_key, None)

    _media_refreshes[refresh_key] = asyncio.create_task(run())


def _warm_library_assets(
    database: Database,
    settings: Settings,
    provider: str,
    account: str,
    items: list[MediaItem],
    *,
    media_type: str = "ANIME",
) -> None:
    warm_key = (str(database.path), provider, account, media_type)
    if task := _library_asset_warmers.get(warm_key):
        if not task.done():
            return

    covers = database.persisted_cover_map(provider, [str(item.id) for item in items])
    candidates = [
        item for item in items if item.cover_image and str(item.id) not in covers
    ]
    if not candidates:
        return

    async def run() -> None:
        semaphore = asyncio.Semaphore(6)

        async def warm(item: MediaItem) -> None:
            async with semaphore:
                cover_local = await _download_asset(
                    settings, item.cover_image, provider, item.id, "cover"
                )
                if cover_local:
                    await asyncio.to_thread(
                        database.set_media_asset_paths,
                        provider, item.id, cover_image_local=cover_local,
                    )

        try:
            await asyncio.gather(*(warm(item) for item in candidates))
        finally:
            _library_asset_warmers.pop(warm_key, None)

    _library_asset_warmers[warm_key] = asyncio.create_task(run())


def _warm_library_details(
    database: Database,
    settings: Settings,
    provider: str,
    account: str,
    items: list[MediaItem],
    token: str,
    *,
    media_type: str = "ANIME",
) -> None:
    """Backfill en segundo plano de los detalles (sinopsis, estudios, etc.) de la
    biblioteca, para que la primera apertura de una card ya salga completa."""
    warm_key = (str(database.path), provider, account, media_type)
    if task := _library_detail_warmers.get(warm_key):
        if not task.done():
            return

    # Refresco por CAMBIO (no por TTL): re-baja el detalle si no está persistido, o si el
    # updatedAt del proveedor (fresco, viene en la lista) supera al guardado — señal de que
    # la metadata (sinopsis/episodios/relaciones) cambió. prev is None = detalle cacheado
    # antes de esta feature: se re-baja una vez para poblar el updatedAt.
    stored = database.persisted_details_updated_at(provider, [str(item.id) for item in items])

    def _needs_refresh(item: MediaItem) -> bool:
        key = str(item.id)
        if key not in stored:
            return True  # aún no persistido
        if item.media_updated_at is None:
            return False  # el proveedor no da updatedAt (MAL/Kitsu): nada que comparar
        prev = stored[key]
        # prev None = cacheado antes de esta feature → re-bajar una vez para poblar el dato.
        return prev is None or item.media_updated_at > prev

    pending = [item.id for item in items if _needs_refresh(item)]
    if not pending:
        _backfill_progress.pop(warm_key, None)
        return

    _backfill_progress[warm_key] = {"done": 0, "total": len(pending), "active": True}
    media_provider = _get_provider(settings, provider)
    # include_related=False: las carátulas de relaciones/recomendaciones se bajan al
    # abrir la card; el backfill solo persiste el texto y las imágenes propias.
    if media_type == "MANGA":
        use_batch = getattr(media_provider.capabilities, "batch_manga_details", False)
        batch_fetch = getattr(media_provider, "manga_details_batch", None)
    else:
        use_batch = getattr(media_provider.capabilities, "batch_details", False)
        batch_fetch = getattr(media_provider, "details_batch", None)
    use_batch = use_batch and batch_fetch is not None

    async def run() -> None:
        try:
            if use_batch:
                # 50 detalles por request (AniList): baja el backfill de horas a minutos.
                # El texto se persiste lote a lote sin pausas; las imágenes se bajan en
                # segundo plano (6 a la vez) sin frenar el texto del siguiente lote.
                semaphore = asyncio.Semaphore(6)
                downloads: list[asyncio.Task] = []

                async def _download_one(details: MediaDetails) -> None:
                    async with semaphore:
                        try:
                            await _download_detail_assets(
                                database, settings, provider, details.id, details,
                                include_related=False,
                            )
                        except Exception:
                            pass

                for start in range(0, len(pending), 50):
                    chunk = pending[start:start + 50]
                    try:
                        details_list = await batch_fetch(token, chunk)
                    except Exception:
                        # El lote se reintenta en el próximo warm, PERO se registra: un
                        # `continue` mudo aquí hizo que un timeout sistemático (query de 50
                        # ids ~27 s contra un cliente de 15 s) se manifestara solo como
                        # "Actualizando biblioteca 0/N" clavado, sin una sola línea en
                        # ningún log. Indiagnosticable. El coste de este log es 1 línea por
                        # lote fallido; el de no tenerlo, una tarde de bisección.
                        logger.warning(
                            "backfill: lote de %d detalles falló (%s/%s); se reintenta en el próximo warm",
                            len(chunk), provider, media_type, exc_info=True,
                        )
                        continue
                    # Todo el lote en UNA transacción, en un hilo: no bloquea el event
                    # loop (abrir una card durante el backfill seguía respondiendo) y no
                    # satura el lock de escritura como sí hacían 50 conexiones sueltas.
                    try:
                        await asyncio.to_thread(
                            database.persist_details_batch, provider, details_list, media_type
                        )
                    except Exception:
                        logger.warning(
                            "backfill: no se pudo persistir un lote de %d detalles (%s/%s)",
                            len(details_list), provider, media_type, exc_info=True,
                        )
                        continue
                    downloads.extend(
                        asyncio.create_task(_download_one(d)) for d in details_list
                    )
                    if progress := _backfill_progress.get(warm_key):
                        progress["done"] += len(chunk)
                    # Ceder el loop entre lotes: sin esto el backfill de una biblioteca
                    # enorme lo acaparaba y abrir una card daba timeout ("no respondió a
                    # tiempo"). Da una ventana a las peticiones interactivas.
                    await asyncio.sleep(0.4)
                # El texto (lo que hace que la card muestre info) ya está: ocultar la barra
                # aunque las imágenes sigan bajándose en segundo plano.
                if progress := _backfill_progress.get(warm_key):
                    progress["active"] = False
                if downloads:
                    await asyncio.gather(*downloads)
            else:
                for external_id in pending:
                    try:
                        await _refresh_media_detail(
                            database, settings, provider, account, external_id, token,
                            media_type=media_type, include_related=False,
                        )
                    except Exception:
                        continue  # ponytail: item fallido se reintenta en el próximo warm
                    finally:
                        if progress := _backfill_progress.get(warm_key):
                            progress["done"] += 1
                        await asyncio.sleep(0.1)
        finally:
            if progress := _backfill_progress.get(warm_key):
                progress["active"] = False
            _library_detail_warmers.pop(warm_key, None)

    _library_detail_warmers[warm_key] = asyncio.create_task(run())


def _local_library_items(
    database: Database, settings: Settings, provider: str, account: str, media_type: str,
    *, scoped: bool = False,
) -> list[MediaItem]:
    # scoped=True: solo la biblioteca del proveedor/cuenta activos (vista por
    # proveedor). scoped=False: une todas las cuentas (vista "combined").
    items = [
        MediaItem.model_validate(item)
        for item in database.get_combined_library(
            media_type, provider, account,
            only_provider=provider if scoped else None,
            only_account=account if scoped else None,
        )
    ]
    covers = database.persisted_cover_map(provider, [str(item.id) for item in items])
    return [
        item.model_copy(update={"cover_image": local})
        if (local := covers.get(str(item.id)))
        else item
        for item in items
    ]


def _list_entry_from_remote(raw: dict | None) -> MediaListEntry | None:
    if not raw:
        return None
    payload = json.loads(raw["original_payload"]) if raw.get("original_payload") else {}
    return MediaListEntry(
        id=raw["id"],
        status=raw["status"],
        score=raw["score"] or 0.0,
        progress=raw["progress"] or 0,
        repeat=payload.get("repeat") or 0,
        private=payload.get("private") or False,
        notes=payload.get("notes"),
        started_at=_coerce_fuzzy_date(payload.get("started_at")),
        completed_at=_coerce_fuzzy_date(payload.get("completed_at")),
    )


def _persisted_detail_is_light(
    database: Database, provider: str, external_id: int
) -> bool:
    """¿HAY una fila persistida y le faltan los bloques pesados (backfill ligero)?

    El backfill baja `_ANIME_LIST_FIELDS` / `_MANGA_LIST_FIELDS`: todo lo que la grid
    pinta, pero SIN characters/staff/relations/recommendations, que son el 95% del coste
    de la request contra AniList y solo se ven al abrir la ficha. Cuando el usuario abre
    una ficha así, hay que completarla con un fetch real: si no, el camino de abajo la
    serviría desde la BD sin reparto ni relaciones, y para siempre.

    Devuelve False cuando NO hay fila (el "skeleton"): ese caso ya tiene su propio camino
    —servir al instante lo que se sepa y refrescar en segundo plano— y no se toca.

    ponytail: heurística de "los cuatro vacíos" en vez de una columna nueva en la BD. Un
    anime de AniList sin reparto NI staff NI relaciones NI recomendaciones no existe en la
    práctica. Techo conocido: para un título tan oscuro que de verdad no tenga ninguno de
    los cuatro, cada apertura hará un fetch (cacheado 900 s por `cached_value`) — ficha
    lenta, no dato incorrecto. Si molesta, la salida es una columna `related_fetched`.
    """
    canonical = database.canonical_media_id(provider, external_id)
    if canonical is None:
        return False
    row = database.get_persisted_media_details(provider, canonical)
    if row is None:
        return False
    return not (row.characters or row.staff or row.relations or row.recommendations)


def _local_media_details(
    database: Database, provider: str, account: str, external_id: int
) -> MediaDetails | None:
    """Detalle local persistido, con fallback al skeleton normalizado.

    Si ya hubo un fetch completo del detalle, usar esa copia local evita depender
    del TTL del blob cacheado. Si no existe aún, caer al skeleton normalizado."""
    canonical = database.canonical_media_id(provider, external_id)
    if canonical is None:
        return None
    persisted = database.get_persisted_media_details(provider, canonical)
    if persisted is not None:
        raw = database.get_remote_entry(provider, account, canonical)
        if raw:
            persisted.list_entry = _list_entry_from_remote(raw)
        return persisted
    raw = database.get_remote_entry(provider, account, canonical)
    payload = json.loads(raw["original_payload"]) if raw and raw.get("original_payload") else {}
    title = database.primary_title(canonical) or payload.get("title")
    if not title:
        return None
    # El formato exacto se persiste la primera vez que llega un detalle real del
    # proveedor; hasta entonces POINT_10 (correcto para MAL/Kitsu).
    score_format = database.get_setting(f"score_format:{provider}") or "POINT_10"
    return MediaDetails(
        id=external_id,
        title=title,
        title_romaji=payload.get("title_romaji"),
        title_english=payload.get("title_english"),
        title_native=payload.get("title_native"),
        synonyms=payload.get("synonyms") or [],
        site_url=payload.get("site_url") or "",
        cover_image=payload.get("cover_image"),
        format=payload.get("format"),
        media_type=payload.get("media_type") or "ANIME",
        episodes=payload.get("episodes"),
        chapters=payload.get("chapters"),
        volumes=payload.get("volumes"),
        season_year=payload.get("year"),
        genres=payload.get("genres") or [],
        studios=[],
        score_format=score_format,
        canonical_id=canonical,
        list_entry=_list_entry_from_remote(raw),
    )


def _overlay_recent_edits(
    database: Database, provider: str, account: str, items: list
) -> list:
    overrides = database.recent_remote_overrides(provider, account)
    # Los cambios aún en cola también se superponen: la lista en vivo debe reflejar
    # la edición aunque el proveedor todavía no la haya recibido.
    for external_id, changes in database.pending_mutation_overrides(provider, account).items():
        overrides.setdefault(external_id, {}).update(changes)
    if not overrides:
        return items
    result = []
    for item in items:
        override = overrides.get(str(item.id))
        if override is None:
            result.append(item)
            continue
        changes = {k: v for k, v in override.items() if k in {"status", "progress", "score"} and v is not None}
        result.append(item.model_copy(update=changes) if changes else item)
    return result


def _get_provider(settings: Settings, provider: str):
    return build_provider_registry(settings).get(provider)


async def _refresh_mal_if_needed(
    provider: str, account: str, token: str, settings: Settings
) -> str:
    if provider != "mal":
        return token
    try:
        credential = MyAnimeListCredential.loads(token)
        if not credential.needs_refresh:
            return token
        credential = await MyAnimeListClient(settings).refresh(credential)
        set_provider_credential("mal", account, credential.dumps())
        return credential.dumps()
    except MyAnimeListError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


_PROVIDER_DISPLAY_NAMES = {"anilist": "AniList", "mal": "MyAnimeList", "kitsu": "Kitsu"}


def _provider_display_name(provider: str) -> str:
    return _PROVIDER_DISPLAY_NAMES.get(provider, provider)


def _matches_discovery_query(item: SearchResult, query: str) -> bool:
    normalized_query = fold_title(normalize_title(query))
    titles = [
        item.title,
        item.title_romaji,
        item.title_english,
        item.title_native,
        *(item.synonyms or []),
    ]
    return any(
        normalized_query in fold_title(normalize_title(title))
        for title in titles
        if title
    )


def _apply_discovery_filters(
    results: list[SearchResult], filters: SearchFilters
) -> list[SearchResult]:
    genre = normalize_title(filters.genre or "").casefold()
    filtered: list[SearchResult] = []
    for item in results:
        if filters.query and not _matches_discovery_query(item, filters.query):
            continue
        if filters.format and item.format != filters.format:
            continue
        if filters.status and item.status != filters.status:
            continue
        if filters.year is not None and item.year != filters.year:
            continue
        if genre and not any(
            normalize_title(value).casefold() == genre for value in item.genres or []
        ):
            continue
        filtered.append(item)
    return filtered


def raise_provider_http_error(error: Exception, provider: str) -> None:
    display_name = _provider_display_name(provider)
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        if status in {401, 403}:
            raise HTTPException(
                status_code=401,
                detail=f"La sesión de {display_name} venció o fue revocada; vuelve a conectar la cuenta.",
            ) from error
        if status == 429:
            raise HTTPException(
                status_code=429,
                detail=f"{display_name} limitó temporalmente las solicitudes; inténtalo más tarde.",
            ) from error
        raise HTTPException(
            status_code=502, detail=f"{display_name} respondió HTTP {status}."
        ) from error
    if isinstance(error, (httpx.TimeoutException, httpx.NetworkError)):
        raise HTTPException(
            status_code=503,
            detail=f"{display_name} no está disponible o la conexión agotó el tiempo de espera.",
        ) from error
    if "not configured" in str(error).lower():
        # Missing local OAuth credentials (e.g. no client ID baked into this build) — a
        # configuration state, not a provider/gateway failure. Make it clear and non-alarming.
        raise HTTPException(
            status_code=503,
            detail=f"{display_name} no está configurado en esta instalación.",
        ) from error
    if isinstance(error, MyAnimeListError):
        raise HTTPException(status_code=502, detail=str(error)) from error
    # Unexpected (non-HTTP) error — usually a response the parser didn't anticipate.
    # Log the traceback so the generic 502 doesn't hide the real cause.
    logger.exception("Unexpected %s provider error", display_name)
    raise HTTPException(
        status_code=502,
        detail=f"No se pudo completar la solicitud a {display_name}.",
    ) from error


def raise_provider_auth_error(
    error: Exception, provider: str, account: str
) -> None:
    if isinstance(error, HTTPException):
        raise
    if isinstance(error, httpx.HTTPStatusError) and error.response.status_code in {401, 403}:
        delete_provider_credential(provider, account)
    raise_provider_http_error(error, provider)


def _is_extension_origin(origin: str | None) -> bool:
    # The browser sets Origin on cross-origin requests and forbids page JS from forging
    # it, so an extension origin proves the request came from the extension, not a web
    # page. A non-browser local process can still spoof it (see EXTENSION_TRANSPORT.md).
    return bool(origin) and origin.startswith(("chrome-extension://", "moz-extension://"))


def require_extension_token(
    authorization: str | None = Header(default=None),
    database: Database = Depends(get_database),
) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Extension token required")
    if not database.validate_extension_token(_token_hash(token)):
        raise HTTPException(status_code=401, detail="Invalid or expired extension token")
    return token


def _build_detector_manager(
    settings: Settings,
    database: Database,
    browser_detector: BrowserDetector | None = None,
) -> DetectorManager:
    manager = DetectorManager(stability_seconds=settings.detection_stability_seconds)
    for detector in (
        browser_detector or BrowserDetector(),
        MpvDetector(),
        MpcHcDetector(),
        PotPlayerDetector(),
        VlcDetector(password=settings.vlc_password),
        ProcessDetector(),
        SmtcDetector(),
        MediaPlayerWindowDetector(),
        ActiveWindowDetector(),
    ):
        stored = database.get_setting(f"detector_enabled:{detector.name}")
        manager.register(detector, enabled=stored != "0")
    return manager


_TORRENT_KEYS = {
    "auto_check": ("torrent_auto_check", "1"),
    "interval_min": ("torrent_interval_min", "60"),
    "download_mode": ("torrent_download_mode", "magnet"),
    "watch_folder": ("torrent_watch_folder", ""),
    "preferred_resolution": ("torrent_preferred_resolution", "1080p"),
    "on_new": ("torrent_on_new", "notify"),
    "client_path": ("torrent_client_path", ""),
    "folder_per_series": ("torrent_folder_per_series", "0"),
    "append_episode": ("torrent_append_episode", "0"),
    "use_anime_folder": ("torrent_use_anime_folder", "0"),
    "filters_enabled": ("torrent_filters_enabled", "1"),
    "global_discard_not_in_list": ("torrent_global_discard_not_in_list", "1"),
    "global_discard_seen": ("torrent_global_discard_seen", "1"),
    "global_prefer_resolution": ("torrent_global_prefer_resolution", "1"),
}


def _fetch_torrent_xml(url: str) -> str:
    response = httpx.get(url, timeout=20.0, follow_redirects=True,
                         headers={"User-Agent": "Nyanko/0.1"})
    response.raise_for_status()
    return response.text


def _get_torrent_settings(database: Database) -> TorrentSettings:
    def value(key, default):
        return database.get_setting(key) or default
    return TorrentSettings(
        auto_check=value(*_TORRENT_KEYS["auto_check"]) == "1",
        interval_min=int(value(*_TORRENT_KEYS["interval_min"])),
        download_mode=value(*_TORRENT_KEYS["download_mode"]),
        watch_folder=value(*_TORRENT_KEYS["watch_folder"]),
        preferred_resolution=value(*_TORRENT_KEYS["preferred_resolution"]),
        on_new=value(*_TORRENT_KEYS["on_new"]),
        client_path=value(*_TORRENT_KEYS["client_path"]),
        folder_per_series=value(*_TORRENT_KEYS["folder_per_series"]) == "1",
        append_episode=value(*_TORRENT_KEYS["append_episode"]) == "1",
        use_anime_folder=value(*_TORRENT_KEYS["use_anime_folder"]) == "1",
        filters_enabled=value(*_TORRENT_KEYS["filters_enabled"]) == "1",
        global_discard_not_in_list=value(*_TORRENT_KEYS["global_discard_not_in_list"]) == "1",
        global_discard_seen=value(*_TORRENT_KEYS["global_discard_seen"]) == "1",
        global_prefer_resolution=value(*_TORRENT_KEYS["global_prefer_resolution"]) == "1",
    )


async def _load_library_for_torrents(
    database: Database, settings: Settings, provider: str, account: str, token: str,
    force: bool = False,
) -> list[MediaItem]:
    media_provider = _get_provider(settings, provider)
    if force:
        key = account_cache_key(provider, account, "list")
        library = await media_provider.library(token)
        database.set_cache(key, [v.model_dump(mode="json") for v in library], 300)
    else:
        library, _ = await cached_list(
            database, account_cache_key(provider, account, "list"), 900, MediaItem,
            lambda: media_provider.library(token),
        )
    return database.enrich_provider_library(media_provider.name, library)


async def _compute_torrent_feed(
    database: Database, library: list[MediaItem],
) -> list[torrents_mod.FeedItem]:
    filters = database.list_torrent_filters()
    seen = database.list_seen_signatures()
    discarded = database.list_discarded_signatures()
    parsed: list[torrents_mod.ParsedTorrent] = []
    for source in database.list_torrent_sources():
        if not source["enabled"] or source["kind"] != "release":
            continue
        try:
            xml_text = await asyncio.to_thread(_fetch_torrent_xml, source["url"])
        except Exception:
            logger.warning("No se pudo leer la fuente de torrents %s", source["url"])
            continue
        parsed.extend(torrents_mod.parse_feed(xml_text, source["id"]))
    settings_t = _get_torrent_settings(database)
    # Episodios ya en disco por id externo, para el elemento local_available y la
    # descarga a la carpeta existente de la serie.
    local_by_canonical = database.get_local_episodes_by_media()
    local_episodes: dict[int, set[int]] = {}
    canonical_by_external: dict[int, int] = {}
    for item in library:
        if item.canonical_id is None:
            continue
        canonical_by_external[item.id] = item.canonical_id
        episodes = local_by_canonical.get(item.canonical_id)
        if episodes:
            local_episodes[item.id] = set(episodes)
    # build_feed es CPU puro (fuzzy-match de cada torrent vs la biblioteca); en el event
    # loop congelaba toda la app varios segundos. Fuera del loop.
    feed = await asyncio.to_thread(
        torrents_mod.build_feed,
        parsed, library, filters, seen, discarded,
        filters_enabled=settings_t.filters_enabled,
        globals_={
            "discard_not_in_list": settings_t.global_discard_not_in_list,
            "discard_seen": settings_t.global_discard_seen,
            "prefer_resolution": settings_t.global_prefer_resolution,
        },
        preferred_resolution=settings_t.preferred_resolution,
        local_episodes=local_episodes,
    )
    _torrent_link_cache.update({item.signature: item.link for item in feed})
    _torrent_item_cache.update({
        item.signature: {
            "media_title": item.media_title,
            "episode": item.episode,
            "canonical_id": canonical_by_external.get(item.media_id) if item.media_id else None,
        }
        for item in feed
    })
    return feed


def _cached_library(database: Database, provider: str, account: str) -> list[MediaItem]:
    record = database.get_cache_record(account_cache_key(provider, account, "list"))
    if record is None:
        return []
    return [MediaItem.model_validate(item) for item in record.payload]


async def _torrent_check_once(database: Database) -> int:
    primary = database.primary_account()
    if primary is None:
        return 0
    provider, account = primary
    library = _cached_library(database, provider, account)
    if not library:
        return 0
    feed = await _compute_torrent_feed(database, library)
    new_count = sum(1 for item in feed if item.is_new)
    _torrent_unread["count"] = new_count
    if new_count and _get_torrent_settings(database).on_new == "download":
        await asyncio.to_thread(_auto_download_new, database, feed)
    return new_count


async def _send_mutation(settings: Settings, row: dict) -> None:
    provider_id = row["provider_id"]
    alias = row["account_alias"]
    token = get_provider_credential(provider_id, alias)
    if not token:
        raise RuntimeError(f"Cuenta no autenticada: {provider_id}:{alias}")
    token = await _refresh_mal_if_needed(provider_id, alias, token, settings)
    token = await _refresh_kitsu_if_needed(provider_id, alias, token, settings)
    media_provider = _get_provider(settings, provider_id)
    payload = json.loads(row["payload"])
    if row["kind"] == "edit_entry":
        await media_provider.edit_entry(
            token, int(row["external_id"]), MediaEntryUpdate(**payload)
        )
    elif row["kind"] == "update_progress":
        await media_provider.update_progress(token, ProgressUpdate(**payload))
    else:
        raise RuntimeError(f"Tipo de mutación desconocido: {row['kind']}")


MUTATION_MAX_ATTEMPTS = 8


class MutationWorker:
    """Vacía pending_mutations en segundo plano con backoff exponencial.

    La UI ya reflejó el cambio localmente; aquí solo se confirma contra el proveedor
    y se actualiza el evento del historial (pending → confirmed/failed)."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        database = Database(self._settings.database_path)
        while not self._stop.is_set():
            try:
                self._drain(database)
            except Exception:
                logger.exception("Fallo en el ciclo de la cola de mutaciones")
            self._stop.wait(3)

    def _drain(self, database: Database) -> None:
        for row in database.due_mutations(int(time.time())):
            if self._stop.is_set():
                return
            try:
                asyncio.run(_send_mutation(self._settings, row))
            except Exception as error:
                attempts = int(row["attempts"]) + 1
                if attempts >= MUTATION_MAX_ATTEMPTS:
                    database.mark_mutation_failed(row["id"], str(error))
                    if row["event_id"]:
                        database.update_playback_event(
                            row["event_id"], status="failed", error_message=str(error)
                        )
                else:
                    delay = min(600, 10 * 2**attempts)
                    database.mark_mutation_retry(
                        row["id"], attempts, int(time.time()) + delay, str(error)
                    )
                continue
            database.mark_mutation_done(row["id"])
            if row["event_id"]:
                database.update_playback_event(row["event_id"], status="confirmed")
            database.invalidate_cache(
                account_cache_key(row["provider_id"], row["account_alias"], "")
            )

    def stop(self) -> None:
        self._stop.set()


class LibraryWatcher:
    """Vigilante de carpetas de la biblioteca (equivalente ligero del monitor de Taiga):
    re-escanea solo cuando aparecen, cambian o desaparecen archivos de video.

    # ponytail: sondeo cada 2 min con firma (ruta, mtime, tamaño); pasar a
    # ReadDirectoryChangesW/watchdog si alguna vez hace falta reacción inmediata.
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._signature: int | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        database = Database(self._settings.database_path)
        while not self._stop.is_set():
            try:
                if database.get_setting(SCAN_WATCH_KEY) == "1":
                    signature = self._compute_signature(database)
                    if self._signature is None:
                        # Primera pasada tras activar: solo tomar la línea base.
                        self._signature = signature
                    elif signature != self._signature:
                        self._signature = signature
                        run_library_scan(database)
                else:
                    self._signature = None
            except Exception:
                logger.exception("Fallo en el vigilante de carpetas")
            self._stop.wait(120)

    @staticmethod
    def _compute_signature(database: Database) -> int:
        parts: list[tuple[str, int, int]] = []
        for path in iter_video_files(database.get_library_folders()):
            try:
                stat = os.stat(path)
            except OSError:
                continue
            parts.append((path, int(stat.st_mtime), stat.st_size))
        return hash(tuple(sorted(parts)))

    def stop(self) -> None:
        self._stop.set()


class TorrentChecker:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        database = Database(self._settings.database_path)
        while not self._stop.is_set():
            try:
                config = _get_torrent_settings(database)
                if config.auto_check:
                    asyncio.run(_torrent_check_once(database))
                interval = max(5, config.interval_min) * 60
            except Exception:
                logger.exception("Fallo en el ciclo de torrents")
                interval = 600
            self._stop.wait(interval)

    def stop(self) -> None:
        self._stop.set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # El backfill hace mucho trabajo en hilos (asyncio.to_thread: persistir, escribir
    # imágenes). El executor por defecto es pequeño (min(32, cpu+4)) y el backfill lo
    # saturaba, dejando sin hilo al card-open (que también usa to_thread) → cards lentas
    # de 1-10s. Con más holgura, lo interactivo no espera detrás del backfill.
    asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=32))
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    init_credentials_dir(settings.data_dir)
    database = Database(settings.database_path)
    database.initialize()
    database.prune_playback_events(settings.history_retention_days)
    migrate_token_from_database(database)
    if get_anilist_token():
        database.ensure_account(
            "anilist", "default", credential_ref="keyring:anilist:default"
        )

    instance_token = read_token_file(settings.instance_token_file) or generate_token()
    write_token_file(settings.instance_token_file, instance_token)
    app.state.instance_token = instance_token

    if settings.api_port == 0:
        settings.api_port = find_free_port(settings.api_host)
    write_port_file(settings.port_file, settings.api_port)

    app.state.browser_detector = BrowserDetector()
    app.state.detector_manager = _build_detector_manager(
        settings, database, app.state.browser_detector
    )
    app.state.detector_manager.start_polling()
    app.state.torrent_checker = TorrentChecker(settings)
    app.state.torrent_checker.start()
    app.state.mutation_worker = MutationWorker(settings)
    app.state.mutation_worker.start()
    app.state.library_watcher = LibraryWatcher(settings)
    app.state.library_watcher.start()

    yield

    app.state.library_watcher.stop()
    app.state.mutation_worker.stop()
    app.state.torrent_checker.stop()
    app.state.detector_manager.stop()


app = FastAPI(title="Nyanko API", version="0.1.0", lifespan=lifespan)
settings = get_settings()
app.mount("/assets", StaticFiles(directory=settings.assets_dir, check_dir=False), name="assets")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=r"^(?:chrome|moz)-extension://[a-zA-Z0-9_-]+$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Nyanko-Instance"],
)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception in %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/")
def root() -> dict[str, str]:
    return {
        "status": "ok",
        "message": "Nyanko local API. Empareja la extensión desde Ajustes en la aplicación.",
    }


@app.get("/api/health", response_model=HealthResponse)
def health(
    provider: str = "anilist", account: str = "default"
) -> HealthResponse:
    return HealthResponse(authenticated=bool(get_provider_credential(provider, account)))


@app.get("/api/providers", response_model=list[ProviderInfo])
def providers(
    settings: Settings = Depends(get_settings), database: Database = Depends(get_database)
) -> list[ProviderInfo]:
    registry = build_provider_registry(settings)
    stored_accounts = database.get_accounts()
    return [
        ProviderInfo(
            name=provider.name,
            display_name=provider.display_name,
            authenticated=any(
                account["provider"] == provider.name
                and bool(get_provider_credential(provider.name, account["alias"]))
                for account in stored_accounts
            ),
            capabilities=ProviderCapabilitiesResponse.model_validate(
                asdict(provider.capabilities)
            ),
        )
        for provider in registry.all()
    ]


@app.get("/api/accounts", response_model=list[AccountInfo])
def accounts(database: Database = Depends(get_database)) -> list[AccountInfo]:
    return [
        AccountInfo(
            **account,
            authenticated=bool(
                get_provider_credential(account["provider"], account["alias"])
            ),
        )
        for account in database.get_accounts()
    ]


@app.put("/api/accounts/{account_id}", response_model=AccountInfo)
def update_account(
    account_id: int,
    update: AccountUpdate,
    database: Database = Depends(get_database),
) -> AccountInfo:
    account = database.update_account(
        account_id,
        is_primary=update.is_primary,
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    authenticated = bool(
        get_provider_credential(account["provider"], account["alias"])
    )
    return AccountInfo(**account, authenticated=authenticated)


@app.get("/api/conflicts", response_model=list[ConflictInfo])
def list_conflicts(
    status: str = "pending",
    database: Database = Depends(get_database),
) -> list[ConflictInfo]:
    if status not in {"pending", "resolved", "dismissed"}:
        raise HTTPException(status_code=422, detail="Invalid conflict status")
    return [
        ConflictInfo.model_validate(conflict)
        for conflict in database.get_conflicts(status)
    ]


@app.post("/api/conflicts/{conflict_id}/resolve", response_model=ConflictInfo)
def resolve_conflict(
    conflict_id: int,
    resolution: ConflictResolution,
    database: Database = Depends(get_database),
) -> ConflictInfo:
    conflict = database.get_conflicts_by_id(conflict_id)
    if conflict is None:
        raise HTTPException(status_code=404, detail="Conflict not found")
    if conflict["status"] != "pending":
        raise HTTPException(status_code=409, detail="Conflict is not pending")
    if resolution.resolution == "manual" and resolution.value is None:
        raise HTTPException(
            status_code=422, detail="Manual resolution requires a value"
        )
    if resolution.resolution == "local":
        resolved_value = conflict["local_value"]
    elif resolution.resolution == "remote":
        resolved_value = conflict["remote_value"]
    else:
        resolved_value = resolution.value
    if not database.resolve_conflict(
        conflict_id, f"resolved_{resolution.resolution}", resolved_value
    ):
        raise HTTPException(status_code=409, detail="Conflict could not be resolved")
    if conflict["field"] == "progress":
        try:
            progress_value = int(resolved_value) if resolved_value is not None else None
        except ValueError:
            progress_value = None
        if progress_value is not None:
            database.update_account_progress(
                conflict["account_id"], conflict["media_id"], progress_value
            )
    elif conflict["field"] == "status" and resolved_value is not None:
        database.update_account_status(
            conflict["account_id"], conflict["media_id"], resolved_value
        )
    updated = database.get_conflicts_by_id(conflict_id)
    if updated is None:
        raise HTTPException(status_code=500, detail="Failed to load resolved conflict")
    return ConflictInfo.model_validate(updated)


@app.post("/api/conflicts/{conflict_id}/dismiss", response_model=ConflictInfo)
def dismiss_conflict(
    conflict_id: int, database: Database = Depends(get_database)
) -> ConflictInfo:
    if not database.dismiss_conflict(conflict_id):
        raise HTTPException(status_code=404, detail="Conflict not found")
    updated = database.get_conflicts_by_id(conflict_id)
    if updated is None:
        raise HTTPException(status_code=500, detail="Failed to load dismissed conflict")
    return ConflictInfo.model_validate(updated)


@app.get("/api/instance")
def instance(request: Request) -> dict[str, str]:
    return {"token": request.app.state.instance_token}


# Página de "conectado" tras el OAuth (AniList/MAL). Fondo de la app, gatito centrado que
# aparece como confirmación y luego el texto. __PROVIDER__ se reemplaza; sin f-string para
# no chocar con las llaves del CSS.
_OAUTH_SUCCESS_HTML = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Nyanko</title>
<style>
:root { color-scheme: dark; }
html, body { height: 100%; margin: 0; }
body { display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 20px; min-height: 100vh; padding: 2rem; text-align: center;
  background: radial-gradient(circle at 50% 32%, #1a1730, #080b12 62%);
  color: #eef0f6; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
.kit { width: 108px; height: 108px; color: #7c6cf0; transform-origin: center bottom;
  animation: pop .5s cubic-bezier(.2, 1.4, .4, 1) both; }
.kit .eye, .kit .nose { fill: #140d28; }
.kit .eye { transform-box: fill-box; transform-origin: center; animation: blink 4s .7s ease-in-out infinite; }
h1 { margin: 0; font-size: 22px; font-weight: 700; letter-spacing: -.02em; animation: rise .5s .18s both; }
p { margin: 0; color: #8a90a4; font-size: 14px; animation: rise .5s .3s both; }
@keyframes pop { 0% { transform: scale(0); } 100% { transform: scale(1); } }
@keyframes rise { 0% { opacity: 0; transform: translateY(8px); } 100% { opacity: 1; transform: none; } }
@keyframes blink { 0%, 90%, 100% { transform: scaleY(1); } 94% { transform: scaleY(.12); } }
@media (prefers-reduced-motion: reduce) { * { animation: none !important; } }
</style></head><body>
<svg class="kit" viewBox="0 0 40 40" role="img" aria-label="Nyanko">
  <g fill="currentColor"><path d="M8 18 L9 4 L19 12 Z"/><path d="M32 18 L31 4 L21 12 Z"/><circle cx="20" cy="24" r="13"/></g>
  <ellipse class="eye" cx="15" cy="24" rx="2.2" ry="3"/><ellipse class="eye" cx="25" cy="24" rx="2.2" ry="3"/>
  <path class="nose" d="M18.4 28 H21.6 L20 29.9 Z"/>
</svg>
<h1>__PROVIDER__ conectado</h1>
<p>Ya puedes cerrar esta ventana.</p>
<script>window.setTimeout(() => window.close(), 2400)</script>
</body></html>"""


def _oauth_success_page(provider_label: str) -> HTMLResponse:
    return HTMLResponse(_OAUTH_SUCCESS_HTML.replace("__PROVIDER__", provider_label))


@app.get("/api/auth/url")
def auth_url(
    account: str = DEFAULT_ACCOUNT_ALIAS,
    settings: Settings = Depends(get_settings), database: Database = Depends(get_database)
) -> dict[str, str]:
    try:
        state = secrets.token_urlsafe(32)
        database.set_setting("oauth_state", state)
        database.set_setting("oauth_account_alias", DEFAULT_ACCOUNT_ALIAS)
        return {"url": AniListClient(settings).authorization_url(state)}
    except AniListError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/api/auth/mal/url")
def mal_auth_url(
    account: str = DEFAULT_ACCOUNT_ALIAS,
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> dict[str, str]:
    try:
        state = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(96)[:128]
        database.set_setting("mal_oauth_state", state)
        database.set_setting("mal_oauth_account_alias", DEFAULT_ACCOUNT_ALIAS)
        database.set_setting("mal_oauth_code_verifier", code_verifier)
        return {
            "url": MyAnimeListClient(settings).authorization_url(state, code_verifier)
        }
    except Exception as error:
        raise_provider_http_error(error, "MyAnimeList")


async def valid_mal_credential(
    account: str, settings: Settings
) -> MyAnimeListCredential:
    stored = get_provider_credential("mal", account)
    if not stored:
        raise HTTPException(status_code=401, detail="MyAnimeList authentication required")
    token = await _refresh_mal_if_needed("mal", account, stored, settings)
    return MyAnimeListCredential.loads(token)


@app.get("/api/auth/mal/callback")
async def mal_auth_callback(
    code: str,
    state: str,
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
):
    expected_state = database.get_setting("mal_oauth_state")
    account = database.get_setting("mal_oauth_account_alias") or DEFAULT_ACCOUNT_ALIAS
    code_verifier = database.get_setting("mal_oauth_code_verifier")
    database.delete_setting("mal_oauth_state")
    database.delete_setting("mal_oauth_account_alias")
    database.delete_setting("mal_oauth_code_verifier")
    if (
        not expected_state
        or not code_verifier
        or not secrets.compare_digest(state, expected_state)
    ):
        raise HTTPException(status_code=400, detail="Invalid MyAnimeList OAuth state")
    try:
        client = MyAnimeListClient(settings)
        credential = await client.exchange_code(code, code_verifier)
        set_provider_credential("mal", account, credential.dumps())
        database.ensure_provider("mal", "MyAnimeList")
        database.ensure_account(
            "mal", account, credential_ref=f"keyring:mal:{account}"
        )
    except Exception as error:
        logger.exception("MAL OAuth callback failed")
        raise_provider_http_error(error, "MyAnimeList")
    async def import_library() -> None:
        # En segundo plano: la lista de MAL es paginada y lenta (~1 req/s) y hacerla
        # inline dejaba el navegador "cargando" minutos tras el Allow.
        try:
            items = await client.library(credential.access_token)
            database.sync_provider_library("mal", "MyAnimeList", items, account)
            database.set_cache(
                f"mal:{account}:list",
                [item.model_dump(mode="json") for item in items],
                900,
            )
        except Exception:
            pass  # ponytail: sync fails silently; user can sync manually from settings

    _spawn_background(import_library())
    return _oauth_success_page("MyAnimeList")


async def _refresh_kitsu_if_needed(provider: str, account: str, token: str, settings: Settings) -> str:
    if provider != "kitsu":
        return token
    try:
        credential = KitsuCredential.loads(token)
        if not credential.needs_refresh:
            return token
        credential = await KitsuClient().refresh(credential)
        set_provider_credential("kitsu", account, credential.dumps())
        return credential.dumps()
    except KitsuError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


class KitsuLoginRequest(BaseModel):
    username: str
    password: str
    account: str = DEFAULT_ACCOUNT_ALIAS


@app.post("/api/auth/kitsu/connect")
async def kitsu_connect(
    body: KitsuLoginRequest,
    database: Database = Depends(get_database),
):
    try:
        client = KitsuClient()
        credential = await client.login(body.username, body.password)
        set_provider_credential("kitsu", body.account, credential.dumps())
        database.ensure_provider("kitsu", "Kitsu")
        account_id = database.ensure_account(
            "kitsu", body.account, credential_ref=f"keyring:kitsu:{body.account}"
        )
        database.update_account(account_id, is_primary=True)
    except Exception as error:
        logger.exception("Kitsu login failed")
        raise_provider_http_error(error, "kitsu")
    try:
        items = await client.library(credential.access_token)
        database.sync_provider_library("kitsu", "Kitsu", items, body.account)
        database.set_cache(
            f"kitsu:{body.account}:list",
            [item.model_dump(mode="json") for item in items],
            900,
        )
    except Exception:
        pass  # ponytail: sync fails silently; user can sync manually from settings
    return {"ok": True}


@app.get("/api/auth/callback")
async def auth_callback(
    code: str,
    state: str,
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
):
    expected_state = database.get_setting("oauth_state")
    account = database.get_setting("oauth_account_alias") or DEFAULT_ACCOUNT_ALIAS
    database.delete_setting("oauth_state")
    database.delete_setting("oauth_account_alias")
    if not expected_state or not secrets.compare_digest(state, expected_state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    try:
        token = await AniListClient(settings).exchange_code(code)
    except Exception as error:
        raise_provider_auth_error(error, "anilist", account)
    set_anilist_token(token, account)
    database.ensure_account(
        "anilist", account, credential_ref=f"keyring:anilist:{account}"
    )
    database.invalidate_cache(account_cache_key("anilist", account, ""))
    return _oauth_success_page("AniList")


@app.post("/api/auth/logout", status_code=204)
def logout(
    account: str = DEFAULT_ACCOUNT_ALIAS,
    provider: str = "anilist",
    database: Database = Depends(get_database),
) -> None:
    delete_provider_credential(provider, DEFAULT_ACCOUNT_ALIAS)
    database.invalidate_cache(f"{provider}:{DEFAULT_ACCOUNT_ALIAS}:")


@app.post("/api/providers/mal/import")
async def import_mal_library(
    account: str = DEFAULT_ACCOUNT_ALIAS,
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> dict[str, int]:
    try:
        credential = await valid_mal_credential(DEFAULT_ACCOUNT_ALIAS, settings)
        provider = MyAnimeListProvider(settings)
        items = await provider.library(credential.dumps())
        database.sync_provider_library(
            provider.name, provider.display_name, items, account_alias=DEFAULT_ACCOUNT_ALIAS
        )
        database.set_cache(
            f"mal:{DEFAULT_ACCOUNT_ALIAS}:list",
            [item.model_dump(mode="json") for item in items],
            900,
        )
        return {"imported": len(items)}
    except HTTPException:
        raise
    except Exception as error:
        raise_provider_http_error(error, "MyAnimeList")


SCAN_ON_STARTUP_KEY = "scan_on_startup"
SCAN_WATCH_KEY = "scan_watch_folders"


def _scan_match_library(database: Database) -> list[MediaItem]:
    """Build the local library as MediaItems for filename matching (no network)."""
    primary = database.get_setting("primary_provider") or "anilist"
    items: list[MediaItem] = []
    for entry in database.get_combined_library("ANIME", primary, DEFAULT_ACCOUNT_ALIAS):
        canonical_id = entry.get("canonical_id")
        if canonical_id is None:
            continue
        items.append(
            MediaItem(
                id=int(canonical_id),
                title=entry.get("title") or "",
                status=entry.get("status") or "",
                progress=int(entry.get("progress") or 0),
                episodes=entry.get("episodes"),
                title_romaji=entry.get("title_romaji"),
                title_english=entry.get("title_english"),
                title_native=entry.get("title_native"),
                synonyms=entry.get("synonyms") or [],
            )
        )
    return items


@app.get("/api/library/folders", response_model=list[LibraryFolder])
def list_library_folders(
    database: Database = Depends(get_database),
) -> list[LibraryFolder]:
    return [LibraryFolder.model_validate(folder) for folder in database.get_library_folders()]


@app.post("/api/library/folders", response_model=LibraryFolder)
def add_library_folder(
    body: LibraryFolderCreate,
    database: Database = Depends(get_database),
) -> LibraryFolder:
    path = body.path.strip()
    if not path or not os.path.isdir(path):
        raise HTTPException(status_code=422, detail="La carpeta no existe")
    return LibraryFolder.model_validate(database.add_library_folder(path, body.recursive))


@app.delete("/api/library/folders/{folder_id}", status_code=204)
def delete_library_folder(
    folder_id: int,
    database: Database = Depends(get_database),
) -> None:
    if not database.delete_library_folder(folder_id):
        raise HTTPException(status_code=404, detail="Carpeta no encontrada")


def run_library_scan(database: Database) -> ScanSummary:
    """Escaneo completo de carpetas: usado por el endpoint y el vigilante de carpetas."""
    folders = database.get_library_folders()
    library = _scan_match_library(database)
    token_index = build_token_index(library)
    overrides = database.get_local_match_overrides()
    rows: list[dict] = []
    for path in iter_video_files(folders):
        parsed_title, episode = parse_file(path)
        media_id: int | None = None
        if parsed_title:
            # Las asociaciones manuales mandan sobre el matching difuso y sobreviven
            # a cada re-escaneo (misma clave normalizada que las correcciones de playback).
            media_id = overrides.get(normalize_title(parsed_title))
        if media_id is None and parsed_title and library:
            # Token-pruned fuzzy match: only compare against library entries sharing a word,
            # so a 2000+ entry list stays fast instead of scanning every entry per file.
            match, _score = match_from_index(parsed_title, token_index)
            if match is not None:
                media_id = match.id
        rows.append(
            {"path": path, "media_id": media_id, "episode": episode, "parsed_title": parsed_title}
        )
    database.replace_local_files(rows)
    return ScanSummary.model_validate(database.get_local_files_summary())


@app.post("/api/library/scan", response_model=ScanSummary)
def scan_library_folders(
    database: Database = Depends(get_database),
) -> ScanSummary:
    return run_library_scan(database)


@app.post("/api/library/local/associate", status_code=204)
async def associate_local_series(
    request: Request,
    body: LocalAssociateRequest,
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> None:
    """(Re)asocia manualmente un grupo de archivos locales a una obra del catálogo.

    Si la obra aún no está en la lista del usuario, se agrega al proveedor con el
    estado que él elija y se registra localmente de inmediato. La corrección se
    persiste en match_corrections (la misma que usa la detección de reproducción)
    para que sobreviva a re-escaneos y mejore también el matching futuro.
    """
    provider, account = get_active_account(request)
    if body.from_media_id is not None:
        patterns = {
            normalize_title(title)
            for title in database.get_local_parsed_titles(body.from_media_id)
        }
    else:
        patterns = {normalize_title(body.title)}
    patterns.discard("")

    if body.external_id is None:
        for pattern in patterns:
            database.delete_match_correction(pattern)
        database.set_local_files_media(
            None, from_media_id=body.from_media_id, parsed_title=body.title
        )
        return

    canonical = database.canonical_media_id(provider, body.external_id)
    # El id canónico puede existir sin entrada de lista (p. ej. por abrir el detalle):
    # lo decisivo es si la obra está en la biblioteca de la cuenta, no si tiene id.
    in_library = canonical is not None and database.has_remote_library_entry(
        provider, account, canonical
    )
    if not in_library:
        # No está en la lista: crear la entrada en el proveedor con el estado elegido.
        status = body.status or "PLANNING"
        token = await require_token(request, settings)
        media_provider = _get_provider(settings, provider)
        try:
            await media_provider.update_progress(
                token, ProgressUpdate(media_id=body.external_id, progress=0, status=status)
            )
        except Exception as error:
            raise_provider_auth_error(error, provider, account)
        if body.media is not None:
            item = MediaItem(
                **body.media.model_dump(exclude={"status", "average_score", "popularity"}),
                status=status,
                progress=0,
            )
            database.sync_provider_library(
                provider, _provider_display_name(provider), [item], account_alias=account
            )
        database.invalidate_cache(account_cache_key(provider, account, ""))
        canonical = database.canonical_media_id(provider, body.external_id)
    if canonical is None:
        raise HTTPException(
            status_code=422,
            detail="No se pudo registrar la serie; sincroniza la biblioteca e intenta de nuevo",
        )
    for pattern in patterns:
        database.set_match_correction(pattern, body.external_id, provider)
    database.set_local_files_media(
        canonical, from_media_id=body.from_media_id, parsed_title=body.title
    )


@app.get("/api/library/pending-local", response_model=list[PendingLocalItem])
def pending_local_episodes(
    database: Database = Depends(get_database),
) -> list[PendingLocalItem]:
    """Series on your list with a local episode you haven't watched yet (ep > progress)."""
    local = database.get_local_episodes_by_media()
    if not local:
        return []
    primary = database.get_setting("primary_provider") or "anilist"
    pending: list[PendingLocalItem] = []
    for entry in database.get_combined_library("ANIME", primary, DEFAULT_ACCOUNT_ALIAS):
        if entry.get("status") not in ("CURRENT", "PLANNING"):
            continue
        canonical_id = entry.get("canonical_id")
        episodes = local.get(int(canonical_id)) if canonical_id is not None else None
        if not episodes:
            continue
        progress = int(entry.get("progress") or 0)
        ahead = sorted(ep for ep in episodes if ep > progress)
        if not ahead:
            continue
        pending.append(
            PendingLocalItem(
                media_id=int(canonical_id),
                external_id=int(entry["id"]),
                title=entry.get("title") or "",
                cover_image=entry.get("cover_image"),
                progress=progress,
                next_episode=ahead[0],
                next_path=episodes[ahead[0]],
                available_count=len(ahead),
            )
        )
    pending.sort(key=lambda item: item.title.casefold())
    return pending


@app.get("/api/library/backfill")
def backfill_status() -> dict:
    """Progreso del backfill de detalles (para la barra de la UI). Agrega las entradas
    activas; done/total en items de la biblioteca cuyo detalle se está persistiendo."""
    active = [p for p in _backfill_progress.values() if p.get("active")]
    if not active:
        return {"active": False, "done": 0, "total": 0}
    return {
        "active": True,
        "done": sum(p["done"] for p in active),
        "total": sum(p["total"] for p in active),
    }


@app.get("/api/library/scan-settings", response_model=ScanSettings)
def get_scan_settings(database: Database = Depends(get_database)) -> ScanSettings:
    return ScanSettings(
        scan_on_startup=database.get_setting(SCAN_ON_STARTUP_KEY) == "1",
        watch_folders=database.get_setting(SCAN_WATCH_KEY) == "1",
    )


@app.put("/api/library/scan-settings", response_model=ScanSettings)
def set_scan_settings(
    body: ScanSettings,
    database: Database = Depends(get_database),
) -> ScanSettings:
    database.set_setting(SCAN_ON_STARTUP_KEY, "1" if body.scan_on_startup else "0")
    database.set_setting(SCAN_WATCH_KEY, "1" if body.watch_folders else "0")
    return body


@app.get("/api/library/local", response_model=list[LocalSeries])
def local_library(database: Database = Depends(get_database)) -> list[LocalSeries]:
    """Series escaneadas con portada/progreso de la biblioteca y episodio local reproducible."""
    local_episodes = database.get_local_episodes_by_media()
    primary = database.get_setting("primary_provider") or "anilist"
    library = {
        int(entry["canonical_id"]): entry
        for entry in database.get_combined_library("ANIME", primary, DEFAULT_ACCOUNT_ALIAS)
        if entry.get("canonical_id") is not None
    }
    result: list[LocalSeries] = []
    for series in database.get_local_series():
        item = LocalSeries(**series)
        entry = library.get(item.media_id) if item.media_id is not None else None
        if entry is not None:
            item.external_id = int(entry["id"])
            item.provider = entry.get("provider")
            item.account_alias = entry.get("account_alias")
            item.cover_image = entry.get("cover_image")
            item.episodes = entry.get("episodes")
            item.progress = int(entry.get("progress") or 0)
            # Variantes de título para respetar el idioma preferido del usuario.
            item.title_romaji = entry.get("title_romaji")
            item.title_english = entry.get("title_english")
            item.title_native = entry.get("title_native")
        episodes = local_episodes.get(item.media_id) if item.media_id is not None else None
        if episodes:
            ahead = sorted(ep for ep in episodes if ep > (item.progress or 0))
            next_episode = ahead[0] if ahead else min(episodes)
            item.next_episode = next_episode
            item.next_path = episodes[next_episode]
        result.append(item)
    return result


@app.post("/api/data/clear", status_code=204)
def clear_local_data(
    database: Database = Depends(get_database),
) -> None:
    for account in database.get_accounts():
        delete_provider_credential(account["provider"], account["alias"])
    delete_anilist_token()
    database.clear_all_data()


@app.get("/api/cache/status", response_model=CacheStatusResponse)
def cache_status(database: Database = Depends(get_database)) -> CacheStatusResponse:
    entries = [CacheStatusItem.model_validate(item) for item in database.get_cache_status()]
    return CacheStatusResponse(
        entries=entries,
        last_updated=max((entry.updated_at for entry in entries), default=None),
    )


@app.post("/api/sync", status_code=204)
def force_sync(
    provider: str = "anilist",
    account: str = "default",
    database: Database = Depends(get_database),
    _: str = Depends(require_token),
) -> None:
    _ = _get_provider(get_settings(), provider)
    database.invalidate_cache(account_cache_key(provider, account, ""))


def _build_sync_status(
    database: Database,
    provider: str,
    account: str,
    selected_season: str,
    selected_year: int,
) -> SyncStatusResponse:
    def resource_status(resource: str) -> SyncStatusItem:
        record = database.get_cache_record(
            account_cache_key(provider, account, resource)
        )
        if record is None:
            return SyncStatusItem()
        return SyncStatusItem(updated_at=record.updated_at, stale=record.stale)

    season_record = database.get_cache_record(
        account_cache_key(
            provider,
            account,
            # v3: SeasonMedia sumó description/genres/cover_color; la clave nueva
            # evita servir caché sin esos campos
            f"season:v3:{selected_season}:{selected_year}",
        )
    )
    season_status = (
        SyncStatusItem(updated_at=season_record.updated_at, stale=season_record.stale)
        if season_record is not None
        else SyncStatusItem()
    )
    return SyncStatusResponse(
        library=resource_status("list"),
        activity=resource_status("activity"),
        statistics=resource_status("statistics"),
        season=season_status,
    )


@app.get("/api/sync/status", response_model=SyncStatusResponse)
def sync_status(
    season: str | None = None,
    year: int | None = None,
    provider: str = "anilist",
    account: str = "default",
    database: Database = Depends(get_database),
    _: str = Depends(require_token),
) -> SyncStatusResponse:
    now = datetime.now(UTC)
    seasons = ("WINTER", "SPRING", "SUMMER", "FALL")
    selected_season = (season or seasons[(now.month - 1) // 3]).upper()
    if selected_season not in seasons:
        raise HTTPException(status_code=422, detail="Invalid anime season")
    selected_year = year or now.year
    if selected_year < 1970 or selected_year > now.year + 2:
        raise HTTPException(status_code=422, detail="Invalid season year")
    return _build_sync_status(
        database, provider, account, selected_season, selected_year
    )


@app.get("/api/preferences", response_model=UserPreferences)
@app.get("/api/anilist/preferences", response_model=UserPreferences, include_in_schema=False)
async def user_preferences(
    response: Response,
    provider: str = "anilist",
    account: str = "default",
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> UserPreferences:
    media_provider = _get_provider(settings, provider)
    if not media_provider.capabilities.preferences:
        return UserPreferences(username="", title_language="ROMAJI", score_format="POINT_10", display_adult_content=False)
    try:
        preferences, status = await cached_value(
            database,
            account_cache_key(provider, account, "preferences"),
            300,
            UserPreferences,
            lambda: media_provider.preferences(token),
        )
        response.headers["X-Cache-Status"] = status.value
        return preferences
    except Exception as error:
        raise_provider_auth_error(error, provider, account)


@app.put("/api/preferences", response_model=UserPreferences)
@app.put("/api/anilist/preferences", response_model=UserPreferences, include_in_schema=False)
async def update_user_preferences(
    update: UserPreferencesUpdate,
    provider: str = "anilist",
    account: str = "default",
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> UserPreferences:
    try:
        media_provider = _get_provider(settings, provider)
        preferences = await media_provider.update_preferences(token, update)
        database.invalidate_cache(account_cache_key(provider, account, ""))
        database.set_cache(
            account_cache_key(provider, account, "preferences"),
            preferences.model_dump(mode="json"),
            300,
            provider_id=provider,
            account_alias=account,
            resource="preferences",
        )
        return preferences
    except Exception as error:
        raise_provider_auth_error(error, provider, account)


@app.get("/api/library/tags", response_model=list[str])
def list_library_tags(database: Database = Depends(get_database)) -> list[str]:
    return database.get_all_tags()


@app.get("/api/library/tags/{media_id}", response_model=list[str])
def get_library_tags(
    media_id: int,
    database: Database = Depends(get_database),
) -> list[str]:
    return database.get_media_tags(media_id)


@app.post("/api/library/tags", status_code=204)
def add_library_tag(
    update: MediaTagUpdate,
    database: Database = Depends(get_database),
) -> None:
    database.add_media_tag(update.media_id, update.tag)


@app.delete("/api/library/tags/{media_id}/{tag}", status_code=204)
def remove_library_tag(
    media_id: int,
    tag: str,
    database: Database = Depends(get_database),
) -> None:
    database.remove_media_tag(media_id, tag)


def _enrich_cached_library(
    database: Database, provider_name: str, provider: str, account: str, payload: list
) -> tuple[list[MediaItem], str]:
    """Validación + enrich + overlay + serialización de la biblioteca cacheada.

    Se ejecuta en un hilo (asyncio.to_thread): con bibliotecas grandes son varios
    segundos de CPU que, corriendo en el event loop, congelaban TODA la API — cualquier
    navegación durante la carga daba "El servicio local no respondió a tiempo"."""
    items = [MediaItem.model_validate(item) for item in payload]
    enriched = database.enrich_provider_library(provider_name, items)
    overlaid = _overlay_recent_edits(database, provider, account, enriched)
    body = json.dumps([item.model_dump(mode="json") for item in overlaid])
    return overlaid, body


@app.get("/api/library", response_model=list[MediaItem])
@app.get("/api/anilist/list", response_model=list[MediaItem], include_in_schema=False)
async def media_list(
    response: Response,
    view: str = "provider",
    provider: str = "anilist",
    account: str = "default",
    token: str | None = Depends(optional_token),
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> list[MediaItem]:
    if view == "combined":
        return _local_library_items(database, settings, provider, account, "ANIME")
    if view != "provider":
        raise HTTPException(status_code=422, detail="Invalid library view")
    cache_key = account_cache_key(provider, account, "list")
    if token is None:
        local_items = _local_library_items(database, settings, provider, account, "ANIME", scoped=True)
        if local_items:
            response.headers["X-Cache-Status"] = CacheStatus.STALE.value
            return local_items
        raise HTTPException(
            status_code=401,
            detail=f"{provider} account is not authenticated: {account}",
        )
    try:
        media_provider = _get_provider(settings, provider)

        async def refresh() -> None:
            values = await media_provider.library(token)
            database.set_cache(cache_key, [value.model_dump(mode="json") for value in values], 900)
            database.sync_provider_library(
                media_provider.name, media_provider.display_name, values, account_alias=account
            )
            _warm_library_assets(database, settings, provider, account, values)
            _warm_library_details(database, settings, provider, account, values, token)

        # Con caché vigente se responde directo desde sqlite; el escaneo de la
        # biblioteca local y el sync por item solo corren al refrescar de red —
        # hacerlos por request bloqueaba el event loop varios segundos.
        record = database.get_cache_record(cache_key)
        if record is not None:
            if record.stale:
                schedule_cache_refresh(database, cache_key, refresh)
            status_value = (
                CacheStatus.STALE if record.stale else CacheStatus.HIT
            ).value
            # Trabajo pesado (validar ~2300 modelos + enrich + overlay + serializar)
            # fuera del event loop, para no congelar el resto de la API mientras carga.
            enriched, body = await asyncio.to_thread(
                _enrich_cached_library,
                database, media_provider.name, provider, account, record.payload,
            )
            # También en HIT: tras un reinicio el backfill de carátulas/detalles retoma
            # sin esperar al próximo refresh de red. Con todo descargado es una consulta
            # corta que no programa nada. (Se agenda en el loop, no en el hilo de arriba.)
            _warm_library_assets(database, settings, provider, account, enriched)
            _warm_library_details(database, settings, provider, account, enriched, token)
            return Response(
                content=body,
                media_type="application/json",
                headers={"X-Cache-Status": status_value},
            )
        # Sin caché: primer arranque en frío de este proveedor/cuenta.
        local_items = _local_library_items(database, settings, provider, account, "ANIME", scoped=True)
        if local_items:
            schedule_cache_refresh(database, cache_key, refresh)
            response.headers["X-Cache-Status"] = CacheStatus.STALE.value
            return _overlay_recent_edits(database, provider, account, local_items)
        items = await media_provider.library(token)
        database.set_cache(cache_key, [value.model_dump(mode="json") for value in items], 900)
        database.sync_provider_library(
            media_provider.name, media_provider.display_name, items, account_alias=account
        )
        response.headers["X-Cache-Status"] = CacheStatus.MISS.value
        _warm_library_assets(database, settings, provider, account, items)
        _warm_library_details(database, settings, provider, account, items, token)
        # enrich ya aplica las carátulas locales persistidas (persisted_cover_map);
        # globear el disco por item aquí costaba >10s con bibliotecas grandes.
        enriched = database.enrich_provider_library(media_provider.name, items)
        return _overlay_recent_edits(database, provider, account, enriched)
    except Exception as error:
        raise_provider_auth_error(error, provider, account)


@app.get("/api/library/manga", response_model=list[MediaItem])
async def media_list_manga(
    response: Response,
    view: str = "provider",
    provider: str = "anilist",
    account: str = "default",
    token: str | None = Depends(optional_token),
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> list[MediaItem]:
    if view == "combined":
        return _local_library_items(database, settings, provider, account, "MANGA")
    if view != "provider":
        raise HTTPException(status_code=422, detail="Invalid library view")
    cache_key = account_cache_key(provider, account, "list:manga")
    if token is None:
        local_items = _local_library_items(database, settings, provider, account, "MANGA", scoped=True)
        if local_items:
            response.headers["X-Cache-Status"] = CacheStatus.STALE.value
            return local_items
        raise HTTPException(
            status_code=401,
            detail=f"{provider} account is not authenticated: {account}",
        )
    try:
        media_provider = _get_provider(settings, provider)
        if not media_provider.capabilities.manga:
            raise HTTPException(
                status_code=400,
                detail=f"{media_provider.display_name} no soporta manga",
            )

        async def refresh() -> None:
            values = await media_provider.library_manga(token)
            database.set_cache(cache_key, [value.model_dump(mode="json") for value in values], 900)
            database.sync_provider_library(
                media_provider.name,
                media_provider.display_name,
                values,
                account_alias=account,
                media_type="MANGA",
            )
            _warm_library_assets(database, settings, provider, account, values, media_type="MANGA")
            _warm_library_details(database, settings, provider, account, values, token, media_type="MANGA")

        record = database.get_cache_record(cache_key)
        if record is not None:
            if record.stale:
                schedule_cache_refresh(database, cache_key, refresh)
            status_value = (
                CacheStatus.STALE if record.stale else CacheStatus.HIT
            ).value
            # Igual que en anime: validar/enrich/overlay/serializar fuera del event loop.
            enriched, body = await asyncio.to_thread(
                _enrich_cached_library,
                database, media_provider.name, provider, account, record.payload,
            )
            _warm_library_assets(database, settings, provider, account, enriched, media_type="MANGA")
            _warm_library_details(database, settings, provider, account, enriched, token, media_type="MANGA")
            return Response(
                content=body,
                media_type="application/json",
                headers={"X-Cache-Status": status_value},
            )
        local_items = _local_library_items(database, settings, provider, account, "MANGA", scoped=True)
        if local_items:
            schedule_cache_refresh(database, cache_key, refresh)
            response.headers["X-Cache-Status"] = CacheStatus.STALE.value
            return _overlay_recent_edits(database, provider, account, local_items)
        items = await media_provider.library_manga(token)
        database.set_cache(cache_key, [value.model_dump(mode="json") for value in items], 900)
        database.sync_provider_library(
            media_provider.name,
            media_provider.display_name,
            items,
            account_alias=account,
            media_type="MANGA",
        )
        response.headers["X-Cache-Status"] = CacheStatus.MISS.value
        _warm_library_assets(database, settings, provider, account, items, media_type="MANGA")
        _warm_library_details(database, settings, provider, account, items, token, media_type="MANGA")
        enriched = database.enrich_provider_library(media_provider.name, items)
        return _overlay_recent_edits(database, provider, account, enriched)
    except Exception as error:
        raise_provider_auth_error(error, provider, account)


@app.post("/api/library/progress")
@app.post("/api/anilist/progress", include_in_schema=False)
async def update_progress(
    update: ProgressUpdate,
    provider: str = "anilist",
    account: str = "default",
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> dict:
    # Efecto local inmediato + cola: la respuesta no espera al proveedor.
    accounts = database.get_accounts()
    account_row = next(
        (a for a in accounts if a["provider"] == provider and a["alias"] == account), None
    )
    canonical = database.canonical_media_id(provider, update.media_id)
    if account_row and canonical:
        database.update_remote_library_entry(
            account_row["id"], canonical,
            status=update.status, progress=update.progress,
        )
    title = (database.primary_title(canonical) if canonical else None) or f"#{update.media_id}"
    event_id = database.insert_playback_event(
        source="edit",
        raw_title=title,
        anime_title=title,
        episode=update.progress,
        status="pending",
        provider_id=provider,
        account_id=account_row["id"] if account_row else None,
        canonical_media_id=canonical,
    )
    database.update_playback_event(
        event_id, status="pending",
        media_id=update.media_id, progress_after=update.progress,
    )
    database.enqueue_mutation(
        provider, account, "update_progress", update.media_id,
        update.model_dump(mode="json", exclude_none=True),
        media_id=canonical, event_id=event_id,
    )
    return {"queued": True}


@app.get("/api/activity", response_model=list[ActivityItem])
@app.get("/api/anilist/activity", response_model=list[ActivityItem], include_in_schema=False)
async def activity(
    response: Response,
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=50),
    provider: str = "anilist",
    account: str = "default",
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> list[ActivityItem]:
    try:
        media_provider = _get_provider(settings, provider)
        items, status = await cached_list(
            database,
            account_cache_key(
                provider, account, "activity" if page == 1 else f"activity:page:{page}"
            ),
            300,
            ActivityItem,
            lambda: media_provider.activity(token, page, per_page),
        )
        response.headers["X-Cache-Status"] = status.value
        return items
    except Exception as error:
        raise_provider_auth_error(error, provider, account)


@app.get("/api/season", response_model=list[SeasonMedia])
@app.get("/api/anilist/season", response_model=list[SeasonMedia], include_in_schema=False)
async def season(
    response: Response,
    season: str | None = None,
    year: int | None = None,
    provider: str = "anilist",
    account: str = "default",
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> list[SeasonMedia]:
    now = datetime.now(UTC)
    seasons = ("WINTER", "SPRING", "SUMMER", "FALL")
    selected_season = (season or seasons[(now.month - 1) // 3]).upper()
    if selected_season not in seasons:
        raise HTTPException(status_code=422, detail="Invalid anime season")
    selected_year = year or now.year
    if selected_year < 1970 or selected_year > now.year + 2:
        raise HTTPException(status_code=422, detail="Invalid season year")
    try:
        media_provider = _get_provider(settings, provider)
        items, status = await cached_list(
            database,
            account_cache_key(
                provider,
                account,
                f"season:v3:{selected_season}:{selected_year}",
            ),
            3600,
            SeasonMedia,
            lambda: media_provider.season(token, selected_season, selected_year),
        )
        response.headers["X-Cache-Status"] = status.value
        return items
    except Exception as error:
        raise_provider_auth_error(error, provider, account)


@app.get("/api/statistics", response_model=StatisticsResponse)
@app.get("/api/anilist/statistics", response_model=StatisticsResponse, include_in_schema=False)
async def statistics(
    response: Response,
    provider: str = "anilist",
    account: str = "default",
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> StatisticsResponse:
    # ponytail: derive from live library — native distributions are unreliable (empty for some accounts)
    try:
        media_provider = _get_provider(settings, provider)
        anime, cache_status = await cached_list(
            database, account_cache_key(provider, account, "list"), 900, MediaItem,
            lambda: media_provider.library(token),
        )
        response.headers["X-Cache-Status"] = cache_status.value
        if media_provider.capabilities.manga:
            manga, _ = await cached_list(
                database, account_cache_key(provider, account, "list:manga"), 900, MediaItem,
                lambda: media_provider.library_manga(token),
            )
        else:
            manga = []
        return statistics_from_items(anime, manga)
    except Exception as error:
        raise_provider_auth_error(error, provider, account)


@app.get("/api/statistics/export", response_model=StatisticsResponse)
async def statistics_export(
    response: Response,
    provider: str = "anilist",
    account: str = "default",
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> StatisticsResponse:
    # ponytail: derive from live library — native distributions are unreliable (empty for some accounts)
    try:
        media_provider = _get_provider(settings, provider)
        response.headers["Content-Disposition"] = 'attachment; filename="nyanko-stats.json"'
        anime, _ = await cached_list(
            database, account_cache_key(provider, account, "list"), 900, MediaItem,
            lambda: media_provider.library(token),
        )
        if media_provider.capabilities.manga:
            manga, _ = await cached_list(
                database, account_cache_key(provider, account, "list:manga"), 900, MediaItem,
                lambda: media_provider.library_manga(token),
            )
        else:
            manga = []
        return statistics_from_items(anime, manga)
    except Exception as error:
        raise_provider_auth_error(error, provider, account)


def _coerce_fuzzy_date(value: object) -> FuzzyDate:
    # Stored remote payloads keep dates as ISO strings ("YYYY-MM-DD"), but some carry the
    # raw FuzzyDate dict. Accept both so rebuilding a MediaListEntry never crashes.
    if isinstance(value, dict):
        return FuzzyDate(**value)
    if isinstance(value, str) and value:
        parts = value.split("-")
        try:
            year = int(parts[0])
        except (ValueError, IndexError):
            return FuzzyDate()
        month = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
        day = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        return FuzzyDate(year=year, month=month, day=day)
    return FuzzyDate()


@app.get("/api/media/{media_id}", response_model=MediaDetails)
@app.get(
    "/api/anilist/media/{media_id}", response_model=MediaDetails, include_in_schema=False
)
async def media_details(
    response: Response,
    media_id: int,
    provider: str = "anilist",
    account: str = "default",
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> MediaDetails:
    try:
        key = account_cache_key(provider, account, f"media:{media_id}")
        record = database.get_cache_record(key)
        if record is not None and not record.stale:
            details = MediaDetails.model_validate(record.payload)
            # sync_media_details ESCRIBE en la DB y _localize hace globs de disco; en el
            # event loop, mientras corre el backfill, bloqueaban el card-open ("El servicio
            # local no respondió a tiempo"). Fuera del loop.
            def _finish_hit() -> MediaDetails:
                details.canonical_id = database.sync_media_details(provider, media_id, details)
                return _localize_media_details_assets(settings, provider, details)

            result = await asyncio.to_thread(_finish_hit)
            response.headers["X-Cache-Status"] = CacheStatus.HIT.value
            return result
        persisted = await asyncio.to_thread(
            _local_media_details, database, provider, account, media_id
        )
        if persisted is not None and await asyncio.to_thread(
            _persisted_detail_is_light, database, provider, media_id
        ):
            # Fila persistida por el backfill LIGERO: tiene el texto y las portadas, pero no
            # el reparto ni las relaciones. Descartarla aquí hace que el camino de red de
            # abajo baje el detalle COMPLETO (DETAIL_QUERY) y lo persista. Sin esto, el
            # camino de abajo serviría la fila tal cual y la ficha se quedaría sin reparto
            # para siempre — nunca vuelve a pedir nada si ya hay fila.
            # Cuesta un fetch (~3 s, con el spinner que ya existe) la PRIMERA vez que se abre
            # cada ficha; a partir de ahí es un HIT instantáneo. A cambio, el backfill de la
            # biblioteca entera pasa de ~15 min a ~2 min.
            persisted = None
        if persisted is not None:
            missing = await asyncio.to_thread(
                _missing_detail_assets, settings, provider, media_id, persisted
            )
            # El detalle persistido por el backfill ya está completo (con list_entry
            # local). Refrescar SOLO si faltan imágenes propias: marcar STALE en cada
            # apertura disparaba un fetch de red + re-descarga de TODAS las carátulas de
            # relaciones por card → el "blink" de 1-2s. El progreso/score del usuario se
            # mantiene al día por el sync de la biblioteca, no por este refresh.
            if missing:
                _schedule_media_refresh(database, settings, provider, account, media_id, token)
                response.headers["X-Cache-Status"] = CacheStatus.STALE.value
            else:
                response.headers["X-Cache-Status"] = CacheStatus.HIT.value
            return await asyncio.to_thread(
                _localize_media_details_assets, settings, provider, persisted
            )
        media_provider = _get_provider(settings, provider)
        details, status = await cached_value(
            database,
            key,
            900,
            MediaDetails,
            lambda: media_provider.details(token, media_id),
        )
        response.headers["X-Cache-Status"] = status.value
        database.set_setting(f"score_format:{provider}", details.score_format)
        canonical_id = database.sync_media_details(media_provider.name, media_id, details)
        details.canonical_id = canonical_id
        _schedule_detail_asset_download(database, settings, provider, media_id, details)
        if details.list_entry is None and canonical_id:
            details.list_entry = _list_entry_from_remote(
                database.get_remote_entry(provider, account, canonical_id)
            )
        return _localize_media_details_assets(settings, provider, details)
    except Exception as error:
        raise_provider_auth_error(error, provider, account)


@app.get("/api/media/{media_id}/manga", response_model=MediaDetails)
async def manga_details(
    response: Response,
    media_id: int,
    provider: str = "anilist",
    account: str = "default",
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> MediaDetails:
    try:
        record = database.get_cache_record(
            account_cache_key(provider, account, f"media:manga:{media_id}")
        )
        if record is not None and not record.stale:
            details = MediaDetails.model_validate(record.payload)
            # Escritura + globs fuera del event loop (ver media_details): durante el
            # backfill bloqueaban el card-open.
            def _finish_hit() -> MediaDetails:
                details.canonical_id = database.sync_media_details(
                    provider, media_id, details, media_type="MANGA"
                )
                return _localize_media_details_assets(settings, provider, details)

            result = await asyncio.to_thread(_finish_hit)
            response.headers["X-Cache-Status"] = CacheStatus.HIT.value
            return result
        persisted = await asyncio.to_thread(
            _local_media_details, database, provider, account, media_id
        )
        if persisted is not None and persisted.media_type == "MANGA":
            missing = await asyncio.to_thread(
                _missing_detail_assets, settings, provider, media_id, persisted
            )
            # Ver media_details: HIT si está completo; refrescar solo si faltan imágenes.
            if missing:
                _schedule_media_refresh(
                    database, settings, provider, account, media_id, token, media_type="MANGA"
                )
                response.headers["X-Cache-Status"] = CacheStatus.STALE.value
            else:
                response.headers["X-Cache-Status"] = CacheStatus.HIT.value
            return await asyncio.to_thread(
                _localize_media_details_assets, settings, provider, persisted
            )
        media_provider = _get_provider(settings, provider)
        if not media_provider.capabilities.manga:
            raise HTTPException(
                status_code=400,
                detail=f"{media_provider.display_name} no soporta manga",
            )
        details, status = await cached_value(
            database,
            account_cache_key(provider, account, f"media:manga:{media_id}"),
            900,
            MediaDetails,
            lambda: media_provider.manga_details(token, media_id),
        )
        response.headers["X-Cache-Status"] = status.value
        database.sync_media_details(
            media_provider.name, media_id, details, media_type="MANGA"
        )
        _schedule_detail_asset_download(database, settings, provider, media_id, details)
        return _localize_media_details_assets(settings, provider, details)
    except Exception as error:
        raise_provider_auth_error(error, provider, account)


@app.put("/api/media/{media_id}/entry", response_model=MediaListEntry)
@app.put(
    "/api/anilist/media/{media_id}/entry",
    response_model=MediaListEntry,
    include_in_schema=False,
)
async def edit_media_entry(
    media_id: int,
    update: MediaEntryUpdate,
    provider: str = "anilist",
    account: str = "default",
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> MediaListEntry:
    try:
        media_provider = _get_provider(settings, provider)
        entry = await media_provider.edit_entry(token, media_id, update)
        database.invalidate_cache(account_cache_key(provider, account, "list"))
        database.invalidate_cache(account_cache_key(provider, account, "activity"))
        database.invalidate_cache(account_cache_key(provider, account, "statistics"))
        database.invalidate_cache(
            account_cache_key(provider, account, f"media:{media_id}")
        )
        return entry
    except Exception as error:
        raise_provider_auth_error(error, provider, account)


def _apply_entry_rules(
    database: Database, provider_id: str, alias: str, media_id: int, update: MediaEntryUpdate
) -> None:
    """Reglas al editar la lista, en el embudo común para que apliquen desde el modal,
    el menú contextual y el +1: completar rellena el progreso al total y fecha de
    completado hoy; empezar a ver registra hoy como fecha de inicio."""
    existing = _list_entry_from_remote(
        database.get_remote_entry(provider_id, alias, media_id)
    )
    today = date.today()
    fuzzy_today = FuzzyDate(year=today.year, month=today.month, day=today.day)
    if update.status == "COMPLETED":
        total = database.media_total_units(media_id)
        if total and (update.progress is None or update.progress < total):
            update.progress = total
        already_completed = existing is not None and bool(
            existing.completed_at and existing.completed_at.year
        )
        if update.completed_at is None and not already_completed:
            update.completed_at = fuzzy_today
    if (
        update.status in ("CURRENT", "REPEATING", "COMPLETED")
        and update.started_at is None
        and not (existing and existing.started_at and existing.started_at.year)
    ):
        update.started_at = fuzzy_today


@app.post("/api/library/bulk-update", response_model=BulkUpdateResult)
async def bulk_update_library_entry(
    media_id: int,
    update: MediaEntryUpdate,
    request: Request,
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> BulkUpdateResult:
    """Update the entry in the active provider's account only."""
    provider_id, alias = get_active_account(request)
    accounts = database.get_accounts()
    account = next(
        (a for a in accounts if a["provider"] == provider_id and a["alias"] == alias), None
    )
    external_id = database.external_id_for_account(media_id, provider_id)
    if external_id is None:
        raise HTTPException(
            status_code=404,
            detail=f"El anime no está vinculado a la cuenta de {_provider_display_name(provider_id)}",
        )
    _apply_entry_rules(database, provider_id, alias, media_id, update)
    # Efecto local inmediato + envío al proveedor en cola: la UI no espera a la API.
    if account:
        extra = update.model_dump(
            mode="json", exclude_none=True, include={"repeat", "notes", "private"},
        )
        # Fechas como texto YYYY-MM-DD: es el formato del payload local (el dict
        # FuzzyDate crudo rompía la validación de MediaItem en la vista combinada).
        for field in ("started_at", "completed_at"):
            value = getattr(update, field)
            if value is not None and value.year:
                extra[field] = f"{value.year:04d}-{(value.month or 1):02d}-{(value.day or 1):02d}"
        database.update_remote_library_entry(
            account["id"], media_id,
            status=update.status, progress=update.progress, score=update.score,
            extra_payload=extra or None,
        )
    title = database.primary_title(media_id) or f"#{external_id}"
    event_id = database.insert_playback_event(
        source="edit",
        raw_title=title,
        anime_title=title,
        episode=update.progress,
        status="pending",
        provider_id=provider_id,
        account_id=account["id"] if account else None,
        canonical_media_id=media_id,
    )
    if update.progress is not None:
        database.update_playback_event(
            event_id, status="pending",
            media_id=int(external_id), progress_after=update.progress,
        )
    database.enqueue_mutation(
        provider_id, alias, "edit_entry", external_id,
        update.model_dump(mode="json", exclude_none=True),
        media_id=media_id, event_id=event_id,
    )
    local_updated = bool(account and account["is_primary"])
    return BulkUpdateResult(
        results=[AccountUpdateResult(provider=provider_id, alias=alias, success=True)],
        local_updated=local_updated,
    )


@app.delete("/api/library/entry/{entry_id}", status_code=204)
@app.delete("/api/anilist/entry/{entry_id}", status_code=204, include_in_schema=False)
async def delete_media_entry(
    entry_id: int,
    provider: str = "anilist",
    account: str = "default",
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> None:
    try:
        media_provider = _get_provider(settings, provider)
        deleted = await media_provider.delete_entry(token, entry_id)
        if not deleted:
            raise HTTPException(
                status_code=409, detail=f"{media_provider.display_name} did not delete the entry"
            )
        database.invalidate_cache(account_cache_key(provider, account, "list"))
        database.invalidate_cache(account_cache_key(provider, account, "activity"))
        database.invalidate_cache(account_cache_key(provider, account, "statistics"))
        database.invalidate_cache(account_cache_key(provider, account, "media:"))
    except HTTPException:
        raise
    except Exception as error:
        raise_provider_auth_error(error, provider, account)


@app.post("/api/extension/pairing", response_model=ExtensionPairingResponse)
def start_extension_pairing(
    request: Request,
    x_nyanko_instance: str | None = Header(default=None),
    database: Database = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> ExtensionPairingResponse:
    expected = request.app.state.instance_token
    if not x_nyanko_instance or not secrets.compare_digest(x_nyanko_instance, expected):
        raise HTTPException(status_code=403, detail="Nyanko instance token required")
    code = secrets.token_urlsafe(8)
    expires_at = int(time.time()) + 600
    database.set_setting("extension_pairing_hash", _token_hash(code))
    database.set_setting("extension_pairing_expires_at", str(expires_at))
    return ExtensionPairingResponse(
        code=code,
        expires_at=expires_at,
        api_url=f"http://{settings.api_host}:{settings.api_port}",
    )


@app.post("/api/extension/pair", response_model=ExtensionTokenResponse)
def pair_extension(
    pairing: ExtensionPairRequest,
    database: Database = Depends(get_database),
) -> ExtensionTokenResponse:
    expected_hash = database.get_setting("extension_pairing_hash")
    expires_raw = database.get_setting("extension_pairing_expires_at")
    if (
        not expected_hash
        or not expires_raw
        or int(expires_raw) <= int(time.time())
        or not secrets.compare_digest(_token_hash(pairing.code), expected_hash)
    ):
        raise HTTPException(status_code=401, detail="Invalid or expired pairing code")
    database.delete_setting("extension_pairing_hash")
    database.delete_setting("extension_pairing_expires_at")
    token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + 30 * 24 * 60 * 60
    database.create_extension_client(pairing.label, _token_hash(token), expires_at)
    return ExtensionTokenResponse(token=token, expires_at=expires_at)


@app.get("/api/extension/bundle")
def extension_bundle(
    request: Request,
    x_nyanko_instance: str | None = Header(default=None),
) -> dict[str, str | None]:
    # Where the unpacked extension lives, so the app can open the folder for a guided
    # "Load unpacked" install. Packaged: Tauri ships dist/ as an `extension/` resource
    # next to the sidecar exe; from source: apps/extension/dist.
    if not x_nyanko_instance or not secrets.compare_digest(
        x_nyanko_instance, request.app.state.instance_token
    ):
        raise HTTPException(status_code=403, detail="Nyanko instance token required")
    if getattr(sys, "frozen", False):
        dist = Path(sys.executable).parent / "extension"
    else:
        dist = Path(__file__).resolve().parents[3] / "apps" / "extension" / "dist"
    return {
        name: str(dist / name) if (dist / name).is_dir() else None
        for name in ("chromium", "firefox")
    }


@app.post("/api/extension/auto-pair", response_model=ExtensionTokenResponse)
def auto_pair_extension(
    pairing: ExtensionRotateRequest,
    origin: str | None = Header(default=None),
    database: Database = Depends(get_database),
) -> ExtensionTokenResponse:
    # Invisible token: the extension acquires one itself, no manual code. Gated on the
    # browser-set Origin so web pages can't mint tokens; only the extension can.
    if not _is_extension_origin(origin):
        raise HTTPException(status_code=403, detail="Extension origin required")
    token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + 30 * 24 * 60 * 60
    label = pairing.label or "Navegador"
    # Un solo cliente activo por navegador: revoca los previos con la misma etiqueta para
    # que re-emparejar (token caducado/revocado) no acumule duplicados.
    database.revoke_extension_clients_by_label(label)
    database.create_extension_client(label, _token_hash(token), expires_at)
    return ExtensionTokenResponse(token=token, expires_at=expires_at)


@app.post("/api/extension/token/rotate", response_model=ExtensionTokenResponse)
def rotate_extension_token(
    update: ExtensionRotateRequest,
    token: str = Depends(require_extension_token),
    database: Database = Depends(get_database),
) -> ExtensionTokenResponse:
    new_token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + 30 * 24 * 60 * 60
    if not database.rotate_extension_token(
        _token_hash(token), _token_hash(new_token), expires_at, update.label
    ):
        raise HTTPException(status_code=409, detail="Extension token could not be rotated")
    return ExtensionTokenResponse(token=new_token, expires_at=expires_at)


@app.get("/api/extension/clients", response_model=list[ExtensionClientInfo])
def extension_clients(
    request: Request,
    x_nyanko_instance: str | None = Header(default=None),
    database: Database = Depends(get_database),
) -> list[ExtensionClientInfo]:
    if not x_nyanko_instance or not secrets.compare_digest(
        x_nyanko_instance, request.app.state.instance_token
    ):
        raise HTTPException(status_code=403, detail="Nyanko instance token required")
    return [
        ExtensionClientInfo.model_validate(client)
        for client in database.get_extension_clients()
    ]


@app.delete("/api/extension/clients/{client_id}", status_code=204)
def revoke_extension_client(
    client_id: int,
    request: Request,
    x_nyanko_instance: str | None = Header(default=None),
    database: Database = Depends(get_database),
) -> None:
    if not x_nyanko_instance or not secrets.compare_digest(
        x_nyanko_instance, request.app.state.instance_token
    ):
        raise HTTPException(status_code=403, detail="Nyanko instance token required")
    if not database.revoke_extension_client(client_id):
        raise HTTPException(status_code=404, detail="Extension client not found")


@app.post("/api/extension/events", status_code=202)
def extension_playback_event(
    event: ExtensionPlaybackEvent,
    request: Request,
    _: str = Depends(require_extension_token),
) -> None:
    parsed = normalize(event.raw_title)
    request.app.state.browser_detector.push(
        PlaybackCandidate(
            source="browser",
            raw_title=event.raw_title,
            anime_title=event.anime_title or parsed.anime_title,
            season=event.season if event.season is not None else parsed.season,
            episode=(
                event.episode
                if event.episode is not None
                else parsed.episode.number if parsed.episode else None
            ),
            episode_type=parsed.episode.type if parsed.episode else None,
            confidence=parsed.confidence,
            process_name="browser",
            position_seconds=event.position_seconds,
            duration_seconds=event.duration_seconds,
            paused=event.paused,
            finished=looks_finished(event.position_seconds, event.duration_seconds),
            page_url=event.page_url,
            site_identifier=event.site_identifier,
            content_kind=event.content_kind,
            site_adapter=event.site_adapter,
            search_hints=event.search_hints,
            next_episode_url=event.next_episode_url,
        )
    )


@app.get("/api/detectors")
def list_detectors(request: Request) -> list[dict[str, str | bool | int]]:
    return [
        {
            "name": info.name,
            "available": info.available,
            "priority": info.priority,
            "enabled": info.enabled,
        }
        for info in request.app.state.detector_manager.list()
    ]


@app.put("/api/detectors/{name}", status_code=204)
def update_detector(
    name: str,
    update: DetectorUpdate,
    request: Request,
    database: Database = Depends(get_database),
) -> None:
    if not request.app.state.detector_manager.set_enabled(name, update.enabled):
        raise HTTPException(status_code=404, detail="Unknown detector")
    database.set_setting(f"detector_enabled:{name}", "1" if update.enabled else "0")


def _display_episode(episode: int | None, match: MediaItem | None) -> int | None:
    """Sanitise the detected episode for display against the matched media.

    Movies have no episode (a number in the filename is usually a year), and a series
    episode must not exceed the catalogue total — which already accounts for platforms
    that merge seasons into one absolute-numbered entry.
    """
    if episode is None or match is None:
        return episode
    if (match.format or "").upper() == "MOVIE" or match.episodes == 1:
        return None
    if match.episodes is not None and episode > match.episodes:
        return match.episodes
    return episode


@app.post("/api/playback/match", response_model=PlaybackMatchResponse)
async def match_playback(
    request: PlaybackMatchRequest,
    provider: str = "anilist",
    account: str = "default",
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> PlaybackMatchResponse:
    media_provider = _get_provider(settings, provider)
    library, _list_status = await _playback_library(
        database, provider, account, token, media_provider
    )
    account_id = database.ensure_account(media_provider.name, account)
    mapping = None
    site_mapping_provider = request.site_adapter or request.source
    if request.site_identifier:
        mapping = database.get_media_mapping(
            site_mapping_provider, request.site_identifier
        )

    match: MediaItem | None = None
    score = 0.0
    episode_offset = 0
    # True when the only match came from the provider catalogue (the series is not on the
    # user's list yet). We never auto-confirm those — adding a new series is a deliberate
    # action via the "Add to Watching" button — only auto-update entries already tracked.
    match_from_search = False
    # Provider catalogue hits for the title (when searched), reused to offer suggestions.
    catalogue_results: list[SearchResult] = []
    if mapping is not None:
        mapped_id, episode_offset = mapping
        match = next((item for item in library if item.id == mapped_id), None)
        if match is None:
            details, _ = await cached_value(
                database,
                account_cache_key(provider, account, f"media:{mapped_id}"),
                900,
                MediaDetails,
                lambda: media_provider.details(token, mapped_id),
            )
            canonical_id = database.sync_media_details(
                media_provider.name, mapped_id, details
            )
            match = _media_item_from_details(
                details, mapped_id, media_provider.name
            ).model_copy(update={"canonical_id": canonical_id})
        if match:
            score = 1.0

    if match is None:
        raw_key = normalize_title(request.raw_title)
        anime_key = normalize_title(request.anime_title) if request.anime_title else None
        corrections = database.get_match_correction(raw_key)
        if corrections is None and anime_key:
            corrections = database.get_match_correction(anime_key)
        if corrections is None:
            all_corrections = database.get_all_match_corrections(media_provider.name)
            search_targets = [raw_key]
            if anime_key:
                search_targets.append(anime_key)
            best_correction_id: int | None = None
            best_ratio = 0.0
            for pattern, media_id in all_corrections.items():
                for target in search_targets:
                    ratio = SequenceMatcher(None, pattern.casefold(), target.casefold()).ratio()
                    if ratio > best_ratio and ratio >= 0.8:
                        best_ratio = ratio
                        best_correction_id = media_id
            corrections = best_correction_id
        corrections_map = None
        if corrections is not None:
            corrections_map = {request.raw_title: corrections, raw_key: corrections}
            if request.anime_title and anime_key:
                corrections_map[request.anime_title] = corrections
                corrections_map[anime_key] = corrections
        search_hints = list(request.search_hints)
        # Only hint a season variant for season >= 2. "Title season 1" adds nothing (season 1
        # is just "Title") and the literal word "season" cross-matches any library entry named
        # "... Season N", inflating unrelated scores (e.g. Wistoria → Vinland Saga Season 2).
        if request.anime_title and request.season and request.season > 1:
            search_hints.append(f"{request.anime_title} season {request.season}")
            search_hints.append(f"{request.anime_title} {request.season}")
        # En un hilo: el fuzzy sobre ~2300 títulos bloqueaba el event loop y las
        # búsquedas manuales del panel expiraban ("no respondió a tiempo").
        match, score = await asyncio.to_thread(
            find_best_match,
            request.raw_title,
            request.anime_title,
            request.season,
            library,
            corrections=corrections_map,
            search_hints=search_hints,
        )
        if request.site_identifier and match is not None and score >= 0.85:
            # Preservar el offset aprendido: sin pasarlo, el default 0 lo borraba en cada
            # re-match fuerte.
            database.set_media_mapping(
                site_mapping_provider, request.site_identifier, match.id, episode_offset
            )
        # Search the provider catalogue (like Discover) whenever the library match isn't
        # strong — don't assume a weak local hit is what's playing. AniList/MAL/Kitsu index
        # English, Romaji and Native titles, so the query resolves regardless of the page's
        # title language. The catalogue result overrides only if it scores better.
        if (match is None or score < 0.85) and (request.anime_title or request.raw_title):
            # Resolve the series via the provider catalogue even when it isn't in the
            # library yet (MALSync-style), or when the local match looks unreliable.
            search_title = request.anime_title or request.raw_title
            best, best_score = None, 0.0
            discovered = None
            try:
                # Cached: while a series stays unconfirmed the desktop re-matches every
                # few seconds; don't search the provider on every poll.
                discovered, _ = await cached_value(
                    database,
                    account_cache_key(provider, account, f"discover:adult:{normalize_title(search_title)}"),
                    300,
                    GlobalSearchResponse,
                    lambda: media_provider.discover(
                        token,
                        SearchFilters(
                            query=search_title, page=1, per_page=20,
                            media_type="ANIME", sort="SCORE",
                            # Always include adult results: we're resolving what the user is
                            # actively watching, so an NSFW title must match. The adult filter
                            # is a Discover/browse preference, not a tracking one.
                            is_adult=True,
                        ),
                    ),
                )
            except Exception:
                # Surface the failure instead of silently dropping to "no match" — a swallowed
                # discover error looks identical to a genuine miss.
                logger.exception("playback catalogue search failed for %r", search_title)
            if discovered is not None:
                catalogue_results = discovered.results
                best, best_score = find_best_search_match(
                    request.raw_title, request.anime_title, catalogue_results,
                    search_hints=search_hints,
                )
                if best is None and catalogue_results:
                    # The provider matched the title server-side across English/Romaji/Native
                    # even though local re-scoring was too strict (e.g. its result omits the
                    # English title that the page used). Trust its top hit, at confirm-required
                    # confidence so it is shown but never auto-saved.
                    best, best_score = catalogue_results[0], max(best_score, 0.6)
            if best is not None and best_score > score:
                details, _ = await cached_value(
                    database,
                    account_cache_key(provider, account, f"media:{best.id}"),
                    900,
                    MediaDetails,
                    lambda: media_provider.details(token, best.id),
                )
                canonical_id = database.sync_media_details(
                    media_provider.name, best.id, details
                )
                match = _media_item_from_details(
                    details, best.id, media_provider.name
                ).model_copy(update={"canonical_id": canonical_id})
                score = best_score
                # On the list already (title just didn't match locally) → still auto-updatable.
                match_from_search = details.list_entry is None
                # Only cache strong matches: the mapping path returns score 1.0, so a
                # weak cache could drive a wrong auto-confirm. Weaker hits stay a
                # suggestion the user confirms (which then persists it).
                if request.site_identifier and best_score >= 0.85:
                    database.set_media_mapping(
                        site_mapping_provider, request.site_identifier, match.id
                    )
    recent_event = database.get_recent_matching_playback_event(
        request.source,
        request.raw_title,
        request.episode,
        settings.playback_deduplication_seconds,
    )
    if recent_event and recent_event["status"] in {"pending", "ignored", "confirmed"}:
        event_id = recent_event["id"]
        event_status = recent_event["status"]
    else:
        event_id = database.insert_playback_event(
            source=request.source,
            raw_title=request.raw_title,
            anime_title=request.anime_title,
            episode=request.episode,
            status="pending",
            provider_id=media_provider.name,
            account_id=account_id,
            canonical_media_id=(
                match.canonical_id
                if match is not None and match.canonical_id is not None
                else database.canonical_media_id(media_provider.name, match.id)
                if match is not None else None
            ),
        )
        event_status = "pending"

    preferences = _get_playback_preferences(database)
    if (
        preferences.auto_confirm
        and event_status == "pending"
        and match is not None
        and not match_from_search
        and match.status != "COMPLETED"  # a finished series re-watched waits for "Reviendo"
        and score >= preferences.confidence_threshold
        and _playback_ready_for_auto_confirm(request, preferences)
    ):
        effective_episode = request.episode + episode_offset if request.episode is not None else None
        if effective_episode is not None and match.episodes is not None:
            progress = min(effective_episode, match.episodes)
        elif effective_episode is not None:
            progress = effective_episode
        else:
            progress = 1
        try:
            details, _ = await cached_value(
                database,
                account_cache_key(provider, account, f"media:{match.id}"),
                900,
                MediaDetails,
                lambda: media_provider.details(token, match.id),
            )
            previous_progress = details.list_entry.progress if details.list_entry else 0
            entry_status = details.list_entry.status if details.list_entry else match.status
            if match.episodes is not None and progress >= match.episodes:
                # Último episodio: completar explícitamente (MAL no auto-completa;
                # y así el progreso queda al total y las fechas puestas en local y
                # en el proveedor). Rewatch además suma al contador.
                entry_update = MediaEntryUpdate(status="COMPLETED", progress=progress)
                if entry_status == "REPEATING":
                    entry_update.repeat = (details.list_entry.repeat if details.list_entry else 0) + 1
                canonical = match.canonical_id or database.canonical_media_id(
                    media_provider.name, match.id
                )
                if canonical:
                    _apply_entry_rules(database, provider, account, canonical, entry_update)
                await media_provider.edit_entry(token, match.id, entry_update)
            else:
                await media_provider.update_progress(
                    token, ProgressUpdate(media_id=match.id, progress=progress)
                )
            database.update_playback_event(
                event_id,
                status="confirmed",
                media_id=match.id,
                progress_before=previous_progress,
                progress_after=progress,
                provider_id=media_provider.name,
                account_id=account_id,
                canonical_media_id=(
                    match.canonical_id
                    or database.canonical_media_id(media_provider.name, match.id)
                ),
            )
            database.invalidate_cache(account_cache_key(provider, account, ""))
            # Reflect the just-saved progress in the returned match so Now Playing shows the
            # new episode immediately; the desktop blocks re-matching once confirmed, so a
            # stale progress here would otherwise persist until the next episode.
            match = match.model_copy(update={"progress": progress})
            event_status = "confirmed"
        except Exception as error:
            database.update_playback_event(
                event_id,
                status="failed",
                media_id=match.id,
                progress_after=progress,
                provider_id=media_provider.name,
                account_id=account_id,
                canonical_media_id=(
                    match.canonical_id
                    or database.canonical_media_id(media_provider.name, match.id)
                ),
                error_message=str(error),
            )
            event_status = "failed"

    candidate = PlaybackCandidate(
        source=request.source,
        raw_title=request.raw_title,
        anime_title=request.anime_title,
        season=request.season,
        # Mostrar el episodio con el offset aplicado (Crunchyroll ep 76 → 1152) para que
        # la tarjeta y la confirmación usen el número absoluto correcto.
        episode=_display_episode(
            request.episode + episode_offset if request.episode is not None else None,
            match,
        ),
        episode_type=request.episode_type,
        confidence=request.confidence,
        position_seconds=request.position_seconds,
        duration_seconds=request.duration_seconds,
        paused=request.paused,
        page_url=request.page_url,
        site_identifier=request.site_identifier,
        content_kind=request.content_kind,
        site_adapter=request.site_adapter,
        search_hints=request.search_hints,
    )
    # Alternative entries to offer when the match is weak/ambiguous/wrong, so detection
    # never silently assumes an irrelevant series. Library entries first (ranked by
    # relevance), then the provider catalogue hits for the title (when we searched), so the
    # panel mirrors Discover without needing to open the "Corregir/Buscar" card.
    suggestions: list[MediaItem] = []
    seen_ids: set[int] = {match.id} if match is not None else set()
    for _, item in rank_matches(
        request.raw_title, request.anime_title, library,
        search_hints=list(request.search_hints), limit=6,
    ):
        if item.id in seen_ids:
            continue
        suggestions.append(item)
        seen_ids.add(item.id)
        if len(suggestions) >= 5:
            break
    for result in catalogue_results:
        if len(suggestions) >= 5:
            break
        if result.id in seen_ids:
            continue
        suggestions.append(_media_item_from_search(result, media_provider.name))
        seen_ids.add(result.id)

    return PlaybackMatchResponse(
        event_id=event_id,
        event_status=event_status,
        candidate=candidate,
        match=match,
        match_score=score,
        suggestions=suggestions,
    )


@app.post("/api/playback/confirm", status_code=204)
async def confirm_playback(
    confirm: PlaybackConfirmRequest,
    provider: str = "anilist",
    account: str = "default",
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> None:
    event = (
        database.get_playback_event(confirm.event_id)
        if confirm.event_id is not None
        else database.get_last_playback_event()
    )
    if event is None or event["status"] != "pending":
        raise HTTPException(status_code=409, detail="No pending playback event")

    media_provider = _get_provider(settings, provider)
    details, _ = await cached_value(
        database,
        account_cache_key(provider, account, f"media:{confirm.media_id}"),
        900,
        MediaDetails,
        lambda: media_provider.details(token, confirm.media_id),
    )
    previous_progress = details.list_entry.progress if details.list_entry else 0
    # New series (not on the list yet): add it as "Watching". For entries already on the
    # list, leave status untouched so we don't clobber Completed/Paused/etc.
    new_status = "CURRENT" if details.list_entry is None else None
    entry_status = details.list_entry.status if details.list_entry else None
    finishes = details.episodes is not None and confirm.progress >= details.episodes

    try:
        if finishes:
            # Último episodio: completar explícitamente (MAL no auto-completa; así el
            # progreso queda al total y las fechas puestas). Rewatch suma al contador.
            entry_update = MediaEntryUpdate(status="COMPLETED", progress=confirm.progress)
            if entry_status == "REPEATING":
                entry_update.repeat = (details.list_entry.repeat if details.list_entry else 0) + 1
            canonical = details.canonical_id or database.canonical_media_id(
                media_provider.name, confirm.media_id
            )
            if canonical:
                _apply_entry_rules(database, provider, account, canonical, entry_update)
            await media_provider.edit_entry(token, confirm.media_id, entry_update)
        else:
            await media_provider.update_progress(
                token,
                ProgressUpdate(
                    media_id=confirm.media_id, progress=confirm.progress, status=new_status
                ),
            )
    except Exception as error:
        database.update_playback_event(
            event["id"],
            status="failed",
            media_id=confirm.media_id,
            progress_before=previous_progress,
            progress_after=confirm.progress,
            provider_id=media_provider.name,
            account_id=database.ensure_account(media_provider.name, account),
            canonical_media_id=database.canonical_media_id(
                media_provider.name, confirm.media_id
            ),
            error_message=str(error),
        )
        raise_provider_auth_error(error, provider, account)

    database.update_playback_event(
        event["id"],
        status="confirmed",
        media_id=confirm.media_id,
        progress_before=previous_progress,
        progress_after=confirm.progress,
        provider_id=media_provider.name,
        account_id=database.ensure_account(media_provider.name, account),
        canonical_media_id=database.canonical_media_id(
            media_provider.name, confirm.media_id
        ),
    )
    database.invalidate_cache(account_cache_key(provider, account, ""))
    # Remember this confirmation so the next episode of the same series resolves on its
    # own: by stable site identifier and by series title (covers sites whose per-episode
    # title differs from the library entry, e.g. Crunchyroll English vs AniList romaji).
    if confirm.site_identifier:
        # Key the mapping the same way match reads it (`site_adapter or source`), so the
        # next episode finds it. event["source"] is "browser" for extension playback.
        # Aprender el offset estacional→absoluto: si el usuario confirmó un episodio
        # distinto al detectado (Crunchyroll "Season 22 ep 76" → 1152), guardarlo con el
        # identificador de la temporada para que los próximos episodios se auto-mapeen.
        # El evento guarda el episodio crudo detectado, así que el offset es consistente.
        detected = event["episode"]
        offset = confirm.progress - int(detected) if detected is not None else 0
        database.set_media_mapping(
            confirm.site_adapter or event["source"], confirm.site_identifier,
            confirm.media_id, offset,
        )
    if event["anime_title"]:
        database.set_match_correction(normalize_title(event["anime_title"]), confirm.media_id)


@app.post("/api/playback/retry/{event_id}", response_model=PlaybackRetryResponse)
async def retry_playback(
    event_id: int,
    provider: str = "anilist",
    account: str = "default",
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> PlaybackRetryResponse:
    event = database.get_playback_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Playback event not found")
    if event["status"] not in {"pending", "failed"}:
        raise HTTPException(status_code=409, detail="Playback event cannot be retried")
    # Si el evento nació de la cola de mutaciones, basta con reactivarla.
    if database.requeue_mutation_by_event(event_id):
        database.update_playback_event(event_id, status="pending")
        return PlaybackRetryResponse(
            retried=True,
            media_id=event["media_id"] or 0,
            progress=event["progress_after"] or 0,
        )
    media_id = event["media_id"]
    progress = event["progress_after"]
    if media_id is None or progress is None:
        raise HTTPException(
            status_code=409, detail="Playback event is missing media or progress"
        )

    media_provider = _get_provider(settings, provider)
    try:
        await media_provider.update_progress(
            token, ProgressUpdate(media_id=media_id, progress=progress)
        )
    except Exception as error:
        database.update_playback_event(
            event_id,
            status="failed",
            error_message=str(error),
        )
        raise_provider_auth_error(error, provider, account)

    database.update_playback_event(
        event_id,
        status="confirmed",
        provider_id=media_provider.name,
        account_id=database.ensure_account(media_provider.name, account),
        canonical_media_id=database.canonical_media_id(media_provider.name, media_id),
    )
    database.invalidate_cache(account_cache_key(provider, account, ""))
    return PlaybackRetryResponse(retried=True, media_id=media_id, progress=progress)


@app.post("/api/playback/ignore", status_code=204)
def ignore_playback(
    ignore: PlaybackIgnoreRequest,
    database: Database = Depends(get_database),
) -> None:
    event = database.get_playback_event(ignore.event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Playback event not found")
    if event["status"] != "pending":
        raise HTTPException(status_code=409, detail="Playback event is not pending")
    database.update_playback_event(ignore.event_id, status="ignored")


@app.get("/api/playback/history", response_model=list[PlaybackEvent])
def playback_history(
    status: str | None = None,
    source: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 100,
    database: Database = Depends(get_database),
) -> list[PlaybackEvent]:
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 500")
    allowed_statuses = {"pending", "confirmed", "ignored", "undone", "failed"}
    if status and status not in allowed_statuses:
        raise HTTPException(status_code=422, detail="Invalid playback status")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="Invalid date range")
    return [
        PlaybackEvent.model_validate(event)
        for event in database.get_recent_playback_events(
            limit,
            status=status,
            source=source,
            date_from=date_from.isoformat() if date_from else None,
            date_to=date_to.isoformat() if date_to else None,
        )
    ]


@app.delete("/api/playback/history", status_code=204)
def clear_playback_history(database: Database = Depends(get_database)) -> None:
    database.clear_playback_events()


@app.post("/api/playback/undo", response_model=PlaybackUndoResponse)
async def undo_playback(
    provider: str = "anilist",
    account: str = "default",
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> PlaybackUndoResponse:
    last_event = database.get_last_playback_event()
    if last_event is None or last_event["status"] != "confirmed":
        return PlaybackUndoResponse(undone=False)

    media_id = last_event["media_id"]
    restored_progress = last_event["progress_before"]
    if media_id is None or restored_progress is None:
        return PlaybackUndoResponse(undone=False)

    media_provider = _get_provider(settings, provider)
    await media_provider.update_progress(
        token, ProgressUpdate(media_id=media_id, progress=restored_progress)
    )
    database.update_playback_event(last_event["id"], status="undone")
    database.invalidate_cache(account_cache_key(provider, account, ""))
    return PlaybackUndoResponse(
        undone=True, media_id=media_id, restored_progress=restored_progress
    )


@app.post("/api/playback/correction", status_code=204)
def create_match_correction(
    correction: MatchCorrectionRequest,
    database: Database = Depends(get_database),
) -> None:
    database.set_match_correction(normalize_title(correction.raw_title), correction.media_id)
    if correction.anime_title:
        database.set_match_correction(normalize_title(correction.anime_title), correction.media_id)
    if correction.site_identifier:
        # Match reads the mapping as `site_adapter or source` (source "browser"); key it the
        # same here so a manual correction makes the next episode resolve automatically.
        database.set_media_mapping(
            correction.site_adapter or "browser",
            correction.site_identifier,
            correction.media_id,
        )


@app.delete("/api/playback/correction/{raw_title}", status_code=204)
def delete_match_correction(
    raw_title: str,
    database: Database = Depends(get_database),
) -> None:
    database.delete_match_correction(normalize_title(raw_title))


@app.get("/api/library/search", response_model=LibrarySearchResponse)
async def search_library(
    response: Response,
    q: str,
    provider: str = "anilist",
    account: str = "default",
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> LibrarySearchResponse:
    if len(q.strip()) < 2:
        raise HTTPException(status_code=400, detail="Query too short")

    media_provider = _get_provider(settings, provider)
    library, status = await _playback_library(
        database, provider, account, token, media_provider
    )
    response.headers["X-Cache-Status"] = status.value

    def scan() -> list[MediaItem]:
        # En un hilo (CPU puro) y con normalización cacheada: los títulos de la
        # biblioteca no cambian entre búsquedas.
        normalized_query = folded_title(q)
        results: list[MediaItem] = []
        for item in library:
            titles = [
                item.title,
                item.title_romaji,
                item.title_english,
                item.title_native,
                *item.synonyms,
            ]
            if any(
                normalized_query in folded_title(title)
                for title in titles
                if title
            ):
                results.append(item)
        if not results:
            match, score = find_best_match(q, q, None, library, min_score=0.25)
            if match is not None and score >= 0.25:
                results.append(match)
        return results

    return LibrarySearchResponse(results=await asyncio.to_thread(scan))


@app.get("/api/search/media", response_model=GlobalSearchResponse)
@app.get("/api/anilist/search", response_model=GlobalSearchResponse, include_in_schema=False)
async def global_search(
    q: str,
    page: int = 1,
    per_page: int = 20,
    genre: str | None = None,
    format: str | None = None,
    year: int | None = None,
    season: str | None = None,
    status: str | None = None,
    is_adult: bool = False,
    media_type: str = "ANIME",
    sort: str = "POPULARITY",
    provider: str = "anilist",
    account: str = "default",
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> GlobalSearchResponse:
    if page < 1:
        raise HTTPException(status_code=422, detail="Invalid page")
    if per_page < 1 or per_page > 50:
        raise HTTPException(status_code=422, detail="Invalid page size")
    if media_type not in {"ANIME", "MANGA"}:
        raise HTTPException(status_code=422, detail="Invalid media type")
    if sort not in {"POPULARITY", "SCORE"}:
        raise HTTPException(status_code=422, detail="Invalid sort")
    media_provider = _get_provider(settings, provider)
    if media_type == "MANGA" and not media_provider.capabilities.manga:
        raise HTTPException(
            status_code=400,
            detail=f"{media_provider.display_name} no soporta manga",
        )
    filters = SearchFilters(
        query=q.strip(),
        page=page,
        per_page=per_page,
        genre=genre,
        format=format,
        year=year,
        season=season,
        status=status,
        is_adult=is_adult,
        media_type=media_type,  # type: ignore[arg-type]
        sort=sort,
    )

    # Descubrir también se cachea (SWR): volver a una búsqueda/página reciente es
    # instantáneo y se refresca en segundo plano. Clave por combinación de filtros.
    key_hash = hashlib.sha1(filters.model_dump_json().encode("utf-8")).hexdigest()[:16]
    key = account_cache_key(provider, account, f"discover:{key_hash}")

    async def loader() -> GlobalSearchResponse:
        response = await media_provider.discover(token, filters)
        return GlobalSearchResponse(
            results=_apply_discovery_filters(response.results, filters),
            has_next_page=response.has_next_page,
        )

    try:
        value, _status = await cached_value(database, key, 1800, GlobalSearchResponse, loader)
        return value
    except Exception as error:
        raise_provider_auth_error(error, provider, account)


_WONT_WATCH_SETTING = "discover_show_wont_watch"


@app.get("/api/discover/wont-watch", response_model=WontWatchState)
def list_wont_watch(
    provider: str = "anilist", database: Database = Depends(get_database)
) -> WontWatchState:
    show = (database.get_setting(_WONT_WATCH_SETTING) or "true") == "true"
    return WontWatchState(
        items=[WontWatchItem(**row) for row in database.wont_watch_list(provider)],
        show_marked=show,
    )


@app.post("/api/discover/wont-watch", status_code=204)
def add_wont_watch(
    body: WontWatchRequest,
    provider: str = "anilist",
    database: Database = Depends(get_database),
) -> None:
    database.add_wont_watch(provider, str(body.media_id), body.title, body.cover_image)


@app.delete("/api/discover/wont-watch/{media_id}", status_code=204)
def remove_wont_watch(
    media_id: int,
    provider: str = "anilist",
    database: Database = Depends(get_database),
) -> None:
    database.remove_wont_watch(provider, str(media_id))


@app.put("/api/discover/settings", status_code=204)
def update_discover_settings(
    body: DiscoverSettingsUpdate, database: Database = Depends(get_database)
) -> None:
    database.set_setting(_WONT_WATCH_SETTING, "true" if body.show_marked else "false")


@app.get("/api/search/manga", response_model=GlobalSearchResponse)
async def manga_search(
    q: str,
    limit: int = 10,
    provider: str = "anilist",
    account: str = "default",
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
) -> GlobalSearchResponse:
    if not q.strip():
        raise HTTPException(status_code=422, detail="Query is required")
    if limit < 1 or limit > 50:
        raise HTTPException(status_code=422, detail="Invalid limit")
    media_provider = _get_provider(settings, provider)
    if not media_provider.capabilities.manga:
        raise HTTPException(
            status_code=400,
            detail=f"{media_provider.display_name} no soporta manga",
        )
    try:
        results = await media_provider.search_manga(token, q.strip(), limit)
        return GlobalSearchResponse(results=results, has_next_page=False)
    except Exception as error:
        raise_provider_auth_error(error, provider, account)


@app.get("/api/playback/active", response_model=PlaybackCandidate | None)
def active_playback(request: Request) -> PlaybackCandidate | None:
    if is_detection_paused():
        return None
    return request.app.state.detector_manager.latest()


@app.post("/api/detection/pause", status_code=204)
def pause_detection() -> None:
    set_detection_paused(True)


@app.post("/api/detection/resume", status_code=204)
def resume_detection() -> None:
    set_detection_paused(False)


@app.get("/api/detection/status")
def detection_status() -> dict[str, bool]:
    return {"paused": is_detection_paused()}


PLAYBACK_AUTO_CONFIRM_KEY = "playback_auto_confirm"
PLAYBACK_CONFIDENCE_THRESHOLD_KEY = "playback_confidence_threshold"
PLAYBACK_PROGRESS_POLICY_KEY = "playback_progress_policy"
PLAYBACK_PROGRESS_SECONDS_KEY = "playback_progress_seconds"


def _get_playback_preferences(database: Database) -> PlaybackPreferences:
    policy = database.get_setting(PLAYBACK_PROGRESS_POLICY_KEY)
    seconds_raw = database.get_setting(PLAYBACK_PROGRESS_SECONDS_KEY)
    # Default ON: auto-update a tracked series ~20s into the episode. Explicit "0" disables.
    return PlaybackPreferences(
        auto_confirm=(database.get_setting(PLAYBACK_AUTO_CONFIRM_KEY) or "1") != "0",
        confidence_threshold=float(
            database.get_setting(PLAYBACK_CONFIDENCE_THRESHOLD_KEY) or "0.85"
        ),
        progress_policy=policy if policy else "seconds",
        progress_seconds=int(seconds_raw) if seconds_raw else 20,
    )


def _playback_ready_for_auto_confirm(
    request: PlaybackMatchRequest, preferences: PlaybackPreferences
) -> bool:
    if not preferences.auto_confirm or request.content_kind != "episode":
        return False
    if request.finished:
        return True
    policy = preferences.progress_policy
    if policy == "always":
        return True
    if policy == "never":
        return False
    if policy == "start":
        return request.position_seconds is not None and request.position_seconds > 0
    if policy == "seconds":
        return (
            request.position_seconds is not None
            and request.position_seconds >= preferences.progress_seconds
        )
    if request.position_seconds is None or request.duration_seconds is None:
        return True
    if request.duration_seconds < 60:
        return False
    if policy == "middle":
        return request.position_seconds / request.duration_seconds >= 0.5
    if policy == "end":
        return (
            request.position_seconds / request.duration_seconds >= 0.95
            or request.duration_seconds - request.position_seconds <= 60
        )
    return (
        request.position_seconds / request.duration_seconds >= 0.8
        or request.duration_seconds - request.position_seconds <= 90
    )


def _media_item_from_details(
    details: MediaDetails, media_id: int, provider: str
) -> MediaItem:
    entry = details.list_entry
    return MediaItem(
        id=media_id,
        title=details.title,
        status=entry.status if entry else details.status or "UNKNOWN",
        progress=entry.progress if entry else 0,
        score=entry.score if entry else None,
        episodes=details.episodes,
        cover_image=details.cover_image,
        title_romaji=details.title_romaji,
        title_english=details.title_english,
        title_native=details.title_native,
        synonyms=details.synonyms,
        genres=details.genres,
        year=details.season_year,
        format=details.format,
        site_url=details.site_url,
        canonical_id=None,
        provider=provider,
    )


def _media_item_from_search(result: SearchResult, provider: str) -> MediaItem:
    # Lightweight MediaItem for a catalogue suggestion (not on the list): no progress,
    # carries the airing status so the frontend treats it as an "add" target.
    return MediaItem(
        id=result.id,
        title=result.title,
        status=result.status or "UNKNOWN",
        progress=0,
        episodes=result.episodes,
        cover_image=result.cover_image,
        title_romaji=result.title_romaji,
        title_english=result.title_english,
        title_native=result.title_native,
        synonyms=result.synonyms,
        genres=result.genres,
        year=result.year,
        format=result.format,
        provider=provider,
    )


def _set_playback_preferences(
    database: Database, preferences: PlaybackPreferences
) -> None:
    database.set_setting(
        PLAYBACK_AUTO_CONFIRM_KEY, "1" if preferences.auto_confirm else "0"
    )
    database.set_setting(
        PLAYBACK_CONFIDENCE_THRESHOLD_KEY, str(preferences.confidence_threshold)
    )
    database.set_setting(PLAYBACK_PROGRESS_POLICY_KEY, preferences.progress_policy)
    database.set_setting(
        PLAYBACK_PROGRESS_SECONDS_KEY, str(preferences.progress_seconds)
    )


@app.get("/api/playback/preferences", response_model=PlaybackPreferences)
def get_playback_preferences(
    database: Database = Depends(get_database),
) -> PlaybackPreferences:
    return _get_playback_preferences(database)


@app.put("/api/playback/preferences", response_model=PlaybackPreferences)
def update_playback_preferences(
    preferences: PlaybackPreferences,
    database: Database = Depends(get_database),
) -> PlaybackPreferences:
    _set_playback_preferences(database, preferences)
    return _get_playback_preferences(database)


@app.get("/api/torrents/sources", response_model=list[TorrentSource])
def torrent_sources(database: Database = Depends(get_database)) -> list[TorrentSource]:
    return [TorrentSource(**s) for s in database.list_torrent_sources()]


@app.post("/api/torrents/sources", response_model=TorrentSource)
def add_torrent_source(body: TorrentSourceInput, database: Database = Depends(get_database)) -> TorrentSource:
    sid = database.add_torrent_source(body.name, body.url, body.enabled, kind=body.kind)
    return TorrentSource(id=sid, name=body.name, url=body.url, enabled=body.enabled, kind=body.kind)


@app.put("/api/torrents/sources/{source_id}", response_model=TorrentSource)
def update_torrent_source(source_id: int, body: TorrentSourceInput, database: Database = Depends(get_database)) -> TorrentSource:
    database.update_torrent_source(source_id, body.name, body.url, body.enabled, kind=body.kind)
    return TorrentSource(id=source_id, name=body.name, url=body.url, enabled=body.enabled, kind=body.kind)


@app.delete("/api/torrents/sources/{source_id}", status_code=204)
def delete_torrent_source(source_id: int, database: Database = Depends(get_database)) -> None:
    database.delete_torrent_source(source_id)


@app.get("/api/torrents/filters", response_model=list[TorrentFilter])
def torrent_filters(database: Database = Depends(get_database)) -> list[TorrentFilter]:
    return [TorrentFilter(**f) for f in database.list_torrent_filters()]


@app.post("/api/torrents/filters", response_model=TorrentFilter)
def add_torrent_filter(body: TorrentFilterInput, database: Database = Depends(get_database)) -> TorrentFilter:
    fid = database.add_torrent_filter(
        body.name, body.action, body.match, body.scope, body.enabled,
        [c.model_dump() for c in body.conditions], body.anime_ids)
    return TorrentFilter(id=fid, **body.model_dump())


@app.put("/api/torrents/filters/{filter_id}", response_model=TorrentFilter)
def update_torrent_filter(filter_id: int, body: TorrentFilterInput, database: Database = Depends(get_database)) -> TorrentFilter:
    database.update_torrent_filter(
        filter_id, body.name, body.action, body.match, body.scope, body.enabled,
        [c.model_dump() for c in body.conditions], body.anime_ids)
    return TorrentFilter(id=filter_id, **body.model_dump())


@app.delete("/api/torrents/filters/{filter_id}", status_code=204)
def delete_torrent_filter(filter_id: int, database: Database = Depends(get_database)) -> None:
    database.delete_torrent_filter(filter_id)


@app.get("/api/torrents/settings", response_model=TorrentSettings)
def get_torrent_settings(database: Database = Depends(get_database)) -> TorrentSettings:
    return _get_torrent_settings(database)


def _safe_folder_name(name: str) -> str:
    import re as _re
    return _re.sub(r'[<>:"/\\|?*]', "_", name).strip() or "serie"


@app.put("/api/torrents/settings", response_model=TorrentSettings)
def put_torrent_settings(body: TorrentSettings, database: Database = Depends(get_database)) -> TorrentSettings:
    database.set_setting("torrent_auto_check", "1" if body.auto_check else "0")
    database.set_setting("torrent_interval_min", str(body.interval_min))
    database.set_setting("torrent_download_mode", body.download_mode)
    database.set_setting("torrent_watch_folder", body.watch_folder)
    database.set_setting("torrent_preferred_resolution", body.preferred_resolution)
    database.set_setting("torrent_on_new", body.on_new)
    database.set_setting("torrent_client_path", body.client_path)
    database.set_setting("torrent_folder_per_series", "1" if body.folder_per_series else "0")
    database.set_setting("torrent_append_episode", "1" if body.append_episode else "0")
    database.set_setting("torrent_use_anime_folder", "1" if body.use_anime_folder else "0")
    database.set_setting("torrent_filters_enabled", "1" if body.filters_enabled else "0")
    database.set_setting("torrent_global_discard_not_in_list", "1" if body.global_discard_not_in_list else "0")
    database.set_setting("torrent_global_discard_seen", "1" if body.global_discard_seen else "0")
    database.set_setting("torrent_global_prefer_resolution", "1" if body.global_prefer_resolution else "0")
    return _get_torrent_settings(database)


@app.get("/api/torrents/feed", response_model=list[TorrentItem])
async def torrent_feed(
    refresh: bool = False,
    provider: str = "anilist",
    account: str = "default",
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> list[TorrentItem]:
    library = await _load_library_for_torrents(database, settings, provider, account, token, force=refresh)
    feed = await _compute_torrent_feed(database, library)
    for item in feed:
        database.mark_torrent_seen(item.signature, item.media_id)
    _torrent_unread["count"] = 0
    covers = {item.id: item.cover_image for item in library if item.cover_image}
    return [
        TorrentItem(
            **asdict(item),
            cover_image=covers.get(item.media_id) if item.media_id is not None else None,
        )
        for item in feed
    ]


@app.get("/api/torrents/unread-count")
def torrent_unread_count(database: Database = Depends(get_database)) -> dict:
    return {"count": _torrent_unread.get("count", 0)}


@app.post("/api/torrents/download", response_model=TorrentDownloadResponse)
def torrent_download(
    body: TorrentActionRequest,
    database: Database = Depends(get_database),
) -> TorrentDownloadResponse:
    settings_t = _get_torrent_settings(database)
    link = _torrent_link_cache.get(body.signature)
    if link is None:
        raise HTTPException(status_code=404, detail="signature desconocida; refresca el feed")
    database.set_torrent_downloaded(body.signature, None)
    # "torrent" (botón archivo) equivale al modo folder; "magnet" fuerza abrir el enlace.
    mode = body.mode or settings_t.download_mode
    if mode in ("folder", "torrent") and link.endswith(".torrent"):
        if not settings_t.watch_folder:
            raise HTTPException(status_code=400, detail="watch_folder no configurado; añádelo en Ajustes de Torrents")
        path = _save_torrent_file(database, settings_t, body.signature, link)
        return TorrentDownloadResponse(action="saved", path=path)
    return TorrentDownloadResponse(action="magnet", link=link, client_path=settings_t.client_path or None)


def _save_torrent_file(
    database: Database, settings_t: TorrentSettings, sig: str, link: str
) -> str:
    folder = Path(settings_t.watch_folder)
    meta = _torrent_item_cache.get(sig, {})
    # Prioridad estilo Taiga: la carpeta donde ya viven los episodios de la serie;
    # si no hay, la carpeta vigilada (con subcarpeta por serie si está activo).
    existing = (
        database.local_series_folder(meta["canonical_id"])
        if settings_t.use_anime_folder and meta.get("canonical_id")
        else None
    )
    if existing:
        folder = Path(existing)
    elif settings_t.folder_per_series and meta.get("media_title"):
        folder = folder / _safe_folder_name(meta["media_title"])
    folder.mkdir(parents=True, exist_ok=True)
    name = sig
    if settings_t.append_episode and meta.get("episode") is not None:
        name = f"{name} - {int(meta['episode']):02d}"
    path = folder / f"{name}.torrent"
    response = httpx.get(link, timeout=20.0, follow_redirects=True)
    response.raise_for_status()
    path.write_bytes(response.content)
    return str(path)


def _auto_download_new(database: Database, feed: list[torrents_mod.FeedItem]) -> int:
    """Descarga automática de episodios nuevos (on_new = download), estilo Taiga."""
    settings_t = _get_torrent_settings(database)
    downloaded = 0
    for item in feed:
        if not item.is_new:
            continue
        # El link viene tal cual de un RSS configurable (a menudo http plano): sin
        # allowlist, un feed malicioso puede colar una ruta local/UNC y os.startfile
        # la ejecutaría. Solo esquemas de descarga legítimos.
        scheme = (item.link or "").split(":", 1)[0].lower()
        if scheme not in {"http", "https", "magnet"}:
            logger.warning("Link de torrent con esquema no permitido: %s", item.raw_title)
            continue
        try:
            if settings_t.download_mode == "folder" and item.link.endswith(".torrent"):
                if not settings_t.watch_folder:
                    continue
                _save_torrent_file(database, settings_t, item.signature, item.link)
            elif settings_t.client_path:
                subprocess.Popen([settings_t.client_path, item.link])
            elif hasattr(os, "startfile"):
                os.startfile(item.link)  # asociación del SO (cliente por defecto)
            else:
                continue
        except Exception:
            logger.warning("No se pudo descargar automáticamente %s", item.raw_title)
            continue
        database.set_torrent_downloaded(item.signature, item.media_id)
        downloaded += 1
    return downloaded


@app.post("/api/torrents/discard", status_code=204)
def torrent_discard(body: TorrentActionRequest, database: Database = Depends(get_database)) -> None:
    database.set_torrent_discarded(body.signature, None)


@app.websocket("/api/playback/stream")
async def playback_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    previous = None
    try:
        while True:
            candidate = (
                None if is_detection_paused() else websocket.app.state.detector_manager.latest()
            )
            # Stream position updates (every ~5s as events arrive) so the desktop can
            # re-evaluate the match until it auto-confirms. The desktop stops re-matching
            # once confirmed, and no longer blanks the panel on confirm, so this no longer
            # flickers.
            current = candidate.model_dump_json() if candidate else None
            if current != previous:
                await websocket.send_json(candidate.model_dump() if candidate else None)
                previous = current
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return
