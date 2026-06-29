import asyncio
import hashlib
import threading
import json
import logging
import os
import secrets
import time

logger = logging.getLogger(__name__)
from dataclasses import asdict
from difflib import SequenceMatcher
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal, TypeVar

from enum import StrEnum

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
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
    SmtcDetector,
    VlcDetector,
    is_detection_paused,
    looks_finished,
    set_detection_paused,
)
from .instance import find_free_port, generate_token, read_token_file, write_port_file, write_token_file
from .matcher import build_token_index, find_best_match, find_best_search_match, match_from_index, rank_matches
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
)
from .normalizer import normalize, normalize_title
from .providers import MyAnimeListProvider, build_provider_registry
from .scanner import iter_video_files, parse_file
from . import torrents as torrents_mod


ModelT = TypeVar("ModelT", bound=BaseModel)


class CacheStatus(StrEnum):
    HIT = "hit"
    STALE = "stale"
    MISS = "miss"


_cache_refreshes: dict[tuple[str, str], asyncio.Task] = {}
DEFAULT_ACCOUNT_ALIAS = "default"

# Caché signature -> link (poblada al construir el feed; el frontend solo manda la signature).
_torrent_link_cache: dict[str, str] = {}
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


def _overlay_recent_edits(
    database: Database, provider: str, account: str, items: list
) -> list:
    overrides = database.recent_remote_overrides(provider, account)
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
    normalized_query = normalize_title(query).casefold()
    titles = [
        item.title,
        item.title_romaji,
        item.title_english,
        item.title_native,
        *(item.synonyms or []),
    ]
    return any(
        normalized_query in normalize_title(title).casefold()
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
            database, account_cache_key(provider, account, "list"), 300, MediaItem,
            lambda: media_provider.library(token),
        )
    return database.enrich_provider_library(media_provider.name, library)


async def _compute_torrent_feed(
    database: Database, library: list[MediaItem],
) -> list[torrents_mod.FeedItem]:
    filters = database.list_torrent_filters()
    seen = database.list_seen_signatures()
    discarded = {s for s in seen if database.is_torrent_discarded(s)}
    parsed: list[torrents_mod.ParsedTorrent] = []
    for source in database.list_torrent_sources():
        if not source["enabled"]:
            continue
        try:
            xml_text = _fetch_torrent_xml(source["url"])
        except Exception:
            logger.warning("No se pudo leer la fuente de torrents %s", source["url"])
            continue
        parsed.extend(torrents_mod.parse_feed(xml_text, source["id"]))
    feed = torrents_mod.build_feed(parsed, library, filters, seen, discarded)
    _torrent_link_cache.update({item.signature: item.link for item in feed})
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
    return new_count


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

    yield

    app.state.torrent_checker.stop()
    app.state.detector_manager.stop()


app = FastAPI(title="Nyanko API", version="0.1.0", lifespan=lifespan)
settings = get_settings()
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
        account_id = database.ensure_account(
            "mal", account, credential_ref=f"keyring:mal:{account}"
        )
    except Exception as error:
        logger.exception("MAL OAuth callback failed")
        raise_provider_http_error(error, "MyAnimeList")
    try:
        items = await client.library(credential.access_token)
        database.sync_provider_library("mal", "MyAnimeList", items, account)
        database.set_cache(
            f"mal:{account}:list",
            [item.model_dump(mode="json") for item in items],
            300,
        )
    except Exception:
        pass  # ponytail: sync fails silently; user can sync manually from settings
    return HTMLResponse(
        """<!doctype html><html lang="es"><head><meta charset="utf-8">
        <title>Nyanko conectado</title></head><body style="font-family:system-ui;padding:3rem">
        <h1>MyAnimeList conectado</h1><p>La biblioteca se sincronizó correctamente.</p>
        <script>window.setTimeout(() => window.close(), 1500)</script></body></html>"""
    )


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
            300,
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
    return HTMLResponse(
        """<!doctype html><html lang="es"><head><meta charset="utf-8">
        <title>Nyanko conectado</title></head><body style="font-family:system-ui;padding:3rem">
        <h1>AniList conectado</h1><p>Puedes cerrar esta ventana y volver a Nyanko.</p>
        <script>window.setTimeout(() => window.close(), 1200)</script></body></html>"""
    )


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
            300,
        )
        return {"imported": len(items)}
    except HTTPException:
        raise
    except Exception as error:
        raise_provider_http_error(error, "MyAnimeList")


SCAN_ON_STARTUP_KEY = "scan_on_startup"


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


@app.post("/api/library/scan", response_model=ScanSummary)
def scan_library_folders(
    database: Database = Depends(get_database),
) -> ScanSummary:
    folders = database.get_library_folders()
    library = _scan_match_library(database)
    token_index = build_token_index(library)
    rows: list[dict] = []
    for path in iter_video_files(folders):
        parsed_title, episode = parse_file(path)
        media_id: int | None = None
        if parsed_title and library:
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


@app.get("/api/library/scan-settings", response_model=ScanSettings)
def get_scan_settings(database: Database = Depends(get_database)) -> ScanSettings:
    return ScanSettings(scan_on_startup=database.get_setting(SCAN_ON_STARTUP_KEY) == "1")


@app.put("/api/library/scan-settings", response_model=ScanSettings)
def set_scan_settings(
    body: ScanSettings,
    database: Database = Depends(get_database),
) -> ScanSettings:
    database.set_setting(SCAN_ON_STARTUP_KEY, "1" if body.scan_on_startup else "0")
    return body


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
            f"season:{selected_season}:{selected_year}",
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
        return [
            MediaItem.model_validate(item)
            for item in database.get_combined_library("ANIME", provider, account)
        ]
    if view != "provider":
        raise HTTPException(status_code=422, detail="Invalid library view")
    if token is None:
        raise HTTPException(
            status_code=401,
            detail=f"{provider} account is not authenticated: {account}",
        )
    try:
        media_provider = _get_provider(settings, provider)
        items, status = await cached_list(
            database,
            account_cache_key(provider, account, "list"),
            300,
            MediaItem,
            lambda: media_provider.library(token),
        )
        response.headers["X-Cache-Status"] = status.value
        database.sync_provider_library(
            media_provider.name, media_provider.display_name, items, account_alias=account
        )
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
        return [
            MediaItem.model_validate(item)
            for item in database.get_combined_library("MANGA", provider, account)
        ]
    if view != "provider":
        raise HTTPException(status_code=422, detail="Invalid library view")
    if token is None:
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
        items, status = await cached_list(
            database,
            account_cache_key(provider, account, "list:manga"),
            300,
            MediaItem,
            lambda: media_provider.library_manga(token),
        )
        response.headers["X-Cache-Status"] = status.value
        database.sync_provider_library(
            media_provider.name,
            media_provider.display_name,
            items,
            account_alias=account,
            media_type="MANGA",
        )
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
    try:
        media_provider = _get_provider(settings, provider)
        result = await media_provider.update_progress(token, update)
        database.invalidate_cache(account_cache_key(provider, account, ""))
        return result
    except Exception as error:
        raise_provider_auth_error(error, provider, account)


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
            120,
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
                f"season:{selected_season}:{selected_year}",
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
    media_provider = _get_provider(settings, provider)
    if not media_provider.capabilities.statistics:
        # provider has no stats API — derive from locally synced library
        return database.local_statistics(provider, account)
    try:
        stats, status = await cached_value(
            database,
            account_cache_key(provider, account, "statistics:v2"),
            600,
            StatisticsResponse,
            lambda: media_provider.statistics(token),
        )
        response.headers["X-Cache-Status"] = status.value
        return stats
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
    media_provider = _get_provider(settings, provider)
    response.headers["Content-Disposition"] = 'attachment; filename="nyanko-stats.json"'
    if not media_provider.capabilities.statistics:
        return database.local_statistics(provider, account)
    try:
        stats, _ = await cached_value(
            database,
            account_cache_key(provider, account, "statistics:v2"),
            600,
            StatisticsResponse,
            lambda: media_provider.statistics(token),
        )
        return stats
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
        media_provider = _get_provider(settings, provider)
        details, status = await cached_value(
            database,
            account_cache_key(provider, account, f"media:{media_id}"),
            900,
            MediaDetails,
            lambda: media_provider.details(token, media_id),
        )
        response.headers["X-Cache-Status"] = status.value
        canonical_id = database.sync_media_details(media_provider.name, media_id, details)
        details.canonical_id = canonical_id
        if details.list_entry is None and canonical_id:
            raw = database.get_remote_entry(provider, account, canonical_id)
            if raw:
                payload = json.loads(raw["original_payload"]) if raw.get("original_payload") else {}
                details.list_entry = MediaListEntry(
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
        return details
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
        return details
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
    try:
        media_provider = _get_provider(settings, provider_id)
        await media_provider.edit_entry(token, int(external_id), update)
        if account:
            database.update_remote_library_entry(
                account["id"], media_id,
                status=update.status, progress=update.progress, score=update.score,
            )
            database.invalidate_cache(account_cache_key(provider_id, alias, ""))
        local_updated = bool(account and account["is_primary"])
        return BulkUpdateResult(
            results=[AccountUpdateResult(provider=provider_id, alias=alias, success=True)],
            local_updated=local_updated,
        )
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail={"message": str(error), "results": [AccountUpdateResult(provider=provider_id, alias=alias, success=False, error=str(error)).model_dump()]},
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
    # "Load unpacked" install. ponytail: assumes the from-source layout; a packaged
    # build would ship dist/ as a bundled resource and resolve it differently.
    if not x_nyanko_instance or not secrets.compare_digest(
        x_nyanko_instance, request.app.state.instance_token
    ):
        raise HTTPException(status_code=403, detail="Nyanko instance token required")
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
    database.create_extension_client(pairing.label or "Navegador", _token_hash(token), expires_at)
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
    library, _ = await cached_list(
        database,
        account_cache_key(provider, account, "list"),
        300,
        MediaItem,
        lambda: media_provider.library(token),
    )
    canonical_mapping = database.sync_provider_library(
        media_provider.name, media_provider.display_name, library, account_alias=account
    )
    library = database.enrich_provider_library(media_provider.name, library)
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
        match, score = find_best_match(
            request.raw_title,
            request.anime_title,
            request.season,
            library,
            corrections=corrections_map,
            search_hints=search_hints,
        )
        if request.site_identifier and match is not None and score >= 0.85:
            database.set_media_mapping(
                site_mapping_provider, request.site_identifier, match.id
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
                else canonical_mapping.get(str(match.id)) if match is not None else None
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
            if (
                entry_status == "REPEATING"
                and match.episodes is not None
                and progress >= match.episodes
            ):
                # Final episode of a rewatch: complete it and bump the rewatch counter.
                current_repeat = details.list_entry.repeat if details.list_entry else 0
                await media_provider.edit_entry(
                    token, match.id,
                    MediaEntryUpdate(status="COMPLETED", progress=progress, repeat=current_repeat + 1),
                )
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
        episode=_display_episode(request.episode, match),
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
    finishes_rewatch = (
        entry_status == "REPEATING"
        and details.episodes is not None
        and confirm.progress >= details.episodes
    )

    try:
        if finishes_rewatch:
            # Final episode of a rewatch: complete it and bump the rewatch counter.
            current_repeat = details.list_entry.repeat if details.list_entry else 0
            await media_provider.edit_entry(
                token, confirm.media_id,
                MediaEntryUpdate(status="COMPLETED", progress=confirm.progress, repeat=current_repeat + 1),
            )
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
        database.set_media_mapping(
            confirm.site_adapter or event["source"], confirm.site_identifier, confirm.media_id
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
    library, status = await cached_list(
        database,
        account_cache_key(provider, account, "list"),
        300,
        MediaItem,
        lambda: media_provider.library(token),
    )
    response.headers["X-Cache-Status"] = status.value
    database.sync_provider_library(
        media_provider.name, media_provider.display_name, library, account_alias=account
    )
    library = database.enrich_provider_library(media_provider.name, library)

    normalized_query = normalize_title(q).casefold()
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
            normalized_query in normalize_title(title).casefold()
            for title in titles
            if title
        ):
            results.append(item)
    if not results:
        match, score = find_best_match(q, q, None, library, min_score=0.25)
        if match is not None and score >= 0.25:
            results.append(match)
    return LibrarySearchResponse(results=results)


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
    try:
        response = await media_provider.discover(token, filters)
        return GlobalSearchResponse(
            results=_apply_discovery_filters(response.results, filters),
            has_next_page=response.has_next_page,
        )
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
    sid = database.add_torrent_source(body.name, body.url, body.enabled)
    return TorrentSource(id=sid, name=body.name, url=body.url, enabled=body.enabled)


@app.put("/api/torrents/sources/{source_id}", response_model=TorrentSource)
def update_torrent_source(source_id: int, body: TorrentSourceInput, database: Database = Depends(get_database)) -> TorrentSource:
    database.update_torrent_source(source_id, body.name, body.url, body.enabled)
    return TorrentSource(id=source_id, name=body.name, url=body.url, enabled=body.enabled)


@app.delete("/api/torrents/sources/{source_id}", status_code=204)
def delete_torrent_source(source_id: int, database: Database = Depends(get_database)) -> None:
    database.delete_torrent_source(source_id)


@app.get("/api/torrents/filters", response_model=list[TorrentFilter])
def torrent_filters(database: Database = Depends(get_database)) -> list[TorrentFilter]:
    return [TorrentFilter(**f) for f in database.list_torrent_filters()]


@app.post("/api/torrents/filters", response_model=TorrentFilter)
def add_torrent_filter(body: TorrentFilterInput, database: Database = Depends(get_database)) -> TorrentFilter:
    fid = database.add_torrent_filter(body.field, body.op, body.value, body.action, body.enabled, body.priority)
    return TorrentFilter(id=fid, **body.model_dump())


@app.put("/api/torrents/filters/{filter_id}", response_model=TorrentFilter)
def update_torrent_filter(filter_id: int, body: TorrentFilterInput, database: Database = Depends(get_database)) -> TorrentFilter:
    database.update_torrent_filter(filter_id, body.field, body.op, body.value, body.action, body.enabled, body.priority)
    return TorrentFilter(id=filter_id, **body.model_dump())


@app.delete("/api/torrents/filters/{filter_id}", status_code=204)
def delete_torrent_filter(filter_id: int, database: Database = Depends(get_database)) -> None:
    database.delete_torrent_filter(filter_id)


@app.get("/api/torrents/settings", response_model=TorrentSettings)
def get_torrent_settings(database: Database = Depends(get_database)) -> TorrentSettings:
    return _get_torrent_settings(database)


@app.put("/api/torrents/settings", response_model=TorrentSettings)
def put_torrent_settings(body: TorrentSettings, database: Database = Depends(get_database)) -> TorrentSettings:
    database.set_setting("torrent_auto_check", "1" if body.auto_check else "0")
    database.set_setting("torrent_interval_min", str(body.interval_min))
    database.set_setting("torrent_download_mode", body.download_mode)
    database.set_setting("torrent_watch_folder", body.watch_folder)
    database.set_setting("torrent_preferred_resolution", body.preferred_resolution)
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
    return [TorrentItem(**asdict(item)) for item in feed]


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
    if settings_t.download_mode == "folder" and link.endswith(".torrent"):
        folder = Path(settings_t.watch_folder)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{body.signature}.torrent"
        response = httpx.get(link, timeout=20.0, follow_redirects=True)
        response.raise_for_status()
        path.write_bytes(response.content)
        return TorrentDownloadResponse(action="saved", path=str(path))
    return TorrentDownloadResponse(action="magnet", link=link)


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
