import asyncio
import hashlib
import secrets
import time
from dataclasses import asdict
from difflib import SequenceMatcher
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Literal, TypeVar

from enum import StrEnum

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .anilist import AniListClient, AniListError
from .config import Settings, get_settings
from .database import Database
from .detectors import (
    ActiveWindowDetector,
    BrowserDetector,
    DetectorManager,
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
from .matcher import find_best_match
from .myanimelist import MyAnimeListClient, MyAnimeListCredential
from .secrets import (
    delete_anilist_token,
    delete_provider_credential,
    get_anilist_token,
    get_provider_credential,
    migrate_token_from_database,
    set_anilist_token,
    set_provider_credential,
)
from .models import (
    AccountInfo,
    AccountUpdate,
    AccountUpdateResult,
    AssociationCandidateInfo,
    ActivityItem,
    AnimeStatistics,       # ponytail: alias — eliminar cuando no queden referencias
    MediaStatistics,
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
    GlobalSearchResponse,
    HealthResponse,
    LibrarySearchResponse,
    LinkedIdentityInfo,
    MatchCorrectionRequest,
    MediaDetails,
    MediaEntryUpdate,
    MediaListEntry,
    MediaItem,
    MediaTagUpdate,
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
    SearchFilters,
    SeasonMedia,
    SyncStatusItem,
    SyncStatusResponse,
    UserPreferences,
    UserPreferencesUpdate,
)
from .normalizer import normalize, normalize_title
from .providers import MyAnimeListProvider, build_provider_registry


ModelT = TypeVar("ModelT", bound=BaseModel)


class CacheStatus(StrEnum):
    HIT = "hit"
    STALE = "stale"
    MISS = "miss"


_cache_refreshes: dict[tuple[str, str], asyncio.Task] = {}


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
        request.query_params.get("account") or "default",
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
    return await _refresh_mal_if_needed(provider, account, token, settings)


def account_cache_key(provider: str, account: str, resource: str) -> str:
    return f"{provider}:{account}:{resource}"


def _get_provider(settings: Settings, provider: str):
    return build_provider_registry(settings).get(provider)


async def _refresh_mal_if_needed(
    provider: str, account: str, token: str, settings: Settings
) -> str:
    if provider != "mal":
        return token
    credential = MyAnimeListCredential.loads(token)
    if not credential.needs_refresh:
        return token
    credential = await MyAnimeListClient(settings).refresh(credential)
    set_provider_credential("mal", account, credential.dumps())
    return credential.dumps()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


_PROVIDER_DISPLAY_NAMES = {"anilist": "AniList", "mal": "MyAnimeList"}


def _provider_display_name(provider: str) -> str:
    return _PROVIDER_DISPLAY_NAMES.get(provider, provider)


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
    raise HTTPException(
        status_code=502, detail=f"No se pudo completar la solicitud a {display_name}."
    ) from error


def raise_provider_auth_error(
    error: Exception, provider: str, account: str
) -> None:
    if isinstance(error, HTTPException):
        raise
    if isinstance(error, httpx.HTTPStatusError) and error.response.status_code in {401, 403}:
        delete_provider_credential(provider, account)
    raise_provider_http_error(error, provider)


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
    settings: Settings, database: Database, browser_detector: BrowserDetector | None = None
) -> DetectorManager:
    manager = DetectorManager(stability_seconds=settings.detection_stability_seconds)
    for detector in (
        browser_detector or BrowserDetector(),
        MpvDetector(),
        MpcHcDetector(),
        PotPlayerDetector(),
        VlcDetector(password=settings.vlc_password),
        SmtcDetector(),
        ActiveWindowDetector(),
    ):
        stored = database.get_setting(f"detector_enabled:{detector.name}")
        manager.register(detector, enabled=stored != "0")
    return manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
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

    yield

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
        sync_direction=update.sync_direction,
        is_primary=update.is_primary,
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    authenticated = bool(
        get_provider_credential(account["provider"], account["alias"])
    )
    return AccountInfo(**account, authenticated=authenticated)


@app.get("/api/associations", response_model=list[AssociationCandidateInfo])
def association_candidates(
    status: str = "pending", database: Database = Depends(get_database)
) -> list[AssociationCandidateInfo]:
    if status not in {"pending", "resolved", "dismissed", "separated"}:
        raise HTTPException(status_code=422, detail="Invalid association status")
    return [
        AssociationCandidateInfo.model_validate(candidate)
        for candidate in database.get_association_candidates(status)
    ]


@app.post("/api/associations/{candidate_id}/resolve")
def resolve_association(
    candidate_id: int, database: Database = Depends(get_database)
) -> dict[str, int]:
    try:
        return {"media_id": database.resolve_association_candidate(candidate_id)}
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/associations/{candidate_id}/dismiss", status_code=204)
def dismiss_association(
    candidate_id: int, database: Database = Depends(get_database)
) -> None:
    if not database.dismiss_association_candidate(candidate_id):
        raise HTTPException(status_code=404, detail="Association candidate not found")


@app.get("/api/associations/identities", response_model=list[LinkedIdentityInfo])
def linked_identities(
    database: Database = Depends(get_database),
) -> list[LinkedIdentityInfo]:
    return [
        LinkedIdentityInfo.model_validate(identity)
        for identity in database.get_linked_identities()
    ]


@app.post("/api/associations/identities/{identity_id}/separate")
def separate_identity(
    identity_id: int, database: Database = Depends(get_database)
) -> dict[str, int]:
    try:
        return {"media_id": database.separate_external_identity(identity_id)}
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


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
    account: str = "default",
    settings: Settings = Depends(get_settings), database: Database = Depends(get_database)
) -> dict[str, str]:
    try:
        state = secrets.token_urlsafe(32)
        database.set_setting("oauth_state", state)
        database.set_setting("oauth_account_alias", account)
        return {"url": AniListClient(settings).authorization_url(state)}
    except AniListError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/api/auth/mal/url")
def mal_auth_url(
    account: str = "default",
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> dict[str, str]:
    try:
        state = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(96)[:128]
        database.set_setting("mal_oauth_state", state)
        database.set_setting("mal_oauth_account_alias", account)
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
    account = database.get_setting("mal_oauth_account_alias") or "default"
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
        database.update_account(account_id, sync_direction="import")
        items = await client.library(credential.access_token)
        database.sync_provider_library("mal", "MyAnimeList", items, account)
        database.set_cache(
            f"mal:{account}:list",
            [item.model_dump(mode="json") for item in items],
            300,
        )
    except Exception as error:
        raise_provider_http_error(error, "MyAnimeList")
    return HTMLResponse(
        """<!doctype html><html lang="es"><head><meta charset="utf-8">
        <title>Nyanko conectado</title></head><body style="font-family:system-ui;padding:3rem">
        <h1>MyAnimeList conectado</h1><p>La biblioteca se importó en modo de solo lectura.</p>
        <script>window.setTimeout(() => window.close(), 1500)</script></body></html>"""
    )


@app.get("/api/auth/callback")
async def auth_callback(
    code: str,
    state: str,
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
):
    expected_state = database.get_setting("oauth_state")
    account = database.get_setting("oauth_account_alias") or "default"
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
    account: str = "default",
    provider: str = "anilist",
    database: Database = Depends(get_database),
) -> None:
    delete_provider_credential(provider, account)
    database.invalidate_cache(f"{provider}:{account}:")


@app.post("/api/providers/mal/import")
async def import_mal_library(
    account: str = "default",
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> dict[str, int]:
    try:
        credential = await valid_mal_credential(account, settings)
        provider = MyAnimeListProvider(settings)
        items = await provider.library(credential.dumps())
        database.sync_provider_library(
            provider.name, provider.display_name, items, account_alias=account
        )
        database.set_cache(
            f"mal:{account}:list",
            [item.model_dump(mode="json") for item in items],
            300,
        )
        return {"imported": len(items)}
    except HTTPException:
        raise
    except Exception as error:
        raise_provider_http_error(error, "MyAnimeList")


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
    try:
        media_provider = _get_provider(settings, provider)
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
    provider: str = "anilist",
    account: str = "default",
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> list[MediaItem]:
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
        return database.enrich_provider_library(media_provider.name, items)
    except Exception as error:
        raise_provider_auth_error(error, provider, account)


@app.get("/api/library/manga", response_model=list[MediaItem])
async def media_list_manga(
    response: Response,
    provider: str = "anilist",
    account: str = "default",
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> list[MediaItem]:
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
        return database.enrich_provider_library(media_provider.name, items)
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
    try:
        media_provider = _get_provider(settings, provider)
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


@app.get("/api/statistics/period", response_model=MediaStatistics)
async def statistics_period(
    from_date: str = Query(..., alias="from"),
    to_date: str = Query(..., alias="to"),
    media_type: Literal["ANIME", "MANGA"] = Query("ANIME", alias="type"),
    _: str = Depends(require_token),
    database: Database = Depends(get_database),
) -> MediaStatistics:
    return database.period_statistics(from_date, to_date, media_type.upper())


@app.get("/api/statistics/export", response_model=StatisticsResponse)
async def statistics_export(
    response: Response,
    provider: str = "anilist",
    account: str = "default",
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> StatisticsResponse:
    try:
        media_provider = _get_provider(settings, provider)
        stats, _ = await cached_value(
            database,
            account_cache_key(provider, account, "statistics:v2"),
            600,
            StatisticsResponse,
            lambda: media_provider.statistics(token),
        )
        response.headers["Content-Disposition"] = 'attachment; filename="nyanko-stats.json"'
        return stats
    except Exception as error:
        raise_provider_auth_error(error, provider, account)


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
        database.sync_media_details(media_provider.name, media_id, details)
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
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> BulkUpdateResult:
    """Propagate an edit to every writable connected account.

    Accounts configured as ``import`` are skipped. Failures are reported per
    account; successful destinations are not rolled back.
    """
    accounts = database.get_accounts()
    results: list[AccountUpdateResult] = []
    local_updated = False
    for account in accounts:
        if account["sync_direction"] == "import":
            continue
        provider_id = account["provider"]
        alias = account["alias"]
        raw = get_provider_credential(provider_id, alias)
        if not raw:
            results.append(
                AccountUpdateResult(
                    provider=provider_id, alias=alias, success=False, error="Sin autenticar"
                )
            )
            continue
        token = await _refresh_mal_if_needed(provider_id, alias, raw, settings)
        external_id = database.external_id_for_account(media_id, provider_id)
        if external_id is None:
            results.append(
                AccountUpdateResult(
                    provider=provider_id,
                    alias=alias,
                    success=False,
                    error="No vinculado a esta cuenta",
                )
            )
            continue
        try:
            media_provider = _get_provider(settings, provider_id)
            await media_provider.edit_entry(token, int(external_id), update)
            database.update_remote_library_entry(
                account["id"],
                media_id,
                status=update.status,
                progress=update.progress,
                score=update.score,
            )
            database.invalidate_cache(account_cache_key(provider_id, alias, ""))
            if account["is_primary"]:
                local_updated = True
            results.append(
                AccountUpdateResult(provider=provider_id, alias=alias, success=True)
            )
        except HTTPException as error:
            results.append(
                AccountUpdateResult(
                    provider=provider_id, alias=alias, success=False, error=error.detail
                )
            )
        except Exception as error:
            results.append(
                AccountUpdateResult(
                    provider=provider_id,
                    alias=alias,
                    success=False,
                    error=str(error),
                )
            )
    if not results:
        raise HTTPException(status_code=409, detail="No writable accounts found")
    if not any(result.success for result in results):
        raise HTTPException(
            status_code=502,
            detail={
                "message": "No se pudo guardar en ninguna cuenta",
                "results": [result.model_dump() for result in results],
            },
        )
    return BulkUpdateResult(results=results, local_updated=local_updated)


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
        if request.anime_title and request.season:
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
        episode=request.episode,
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
    return PlaybackMatchResponse(
        event_id=event_id,
        event_status=event_status,
        candidate=candidate,
        match=match,
        match_score=score,
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

    try:
        await media_provider.update_progress(
            token, ProgressUpdate(media_id=confirm.media_id, progress=confirm.progress)
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
        database.set_media_mapping(
            correction.site_adapter or "unknown",
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
        status=status,
        is_adult=is_adult,
        media_type=media_type,  # type: ignore[arg-type]
        sort=sort,
    )
    return await media_provider.discover(token, filters)


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
    return PlaybackPreferences(
        auto_confirm=database.get_setting(PLAYBACK_AUTO_CONFIRM_KEY) == "1",
        confidence_threshold=float(
            database.get_setting(PLAYBACK_CONFIDENCE_THRESHOLD_KEY) or "0.85"
        ),
        progress_policy=policy if policy else "end",
        progress_seconds=int(seconds_raw) if seconds_raw else 90,
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


@app.websocket("/api/playback/stream")
async def playback_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    previous = None
    try:
        while True:
            candidate = (
                None if is_detection_paused() else websocket.app.state.detector_manager.latest()
            )
            current = candidate.model_dump_json() if candidate else None
            if current != previous:
                await websocket.send_json(candidate.model_dump() if candidate else None)
                previous = current
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return
