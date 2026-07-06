import sys
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _anchor_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent  # apps/backend


def _default_data_dir() -> Path:
    return _anchor_dir() / "data"


def _env_files() -> tuple[Path | str, ...]:
    # Resolve the .env by absolute path from this file's location, so credentials load no
    # matter which directory the backend (dev.py or the sidecar) was launched from. The
    # cwd-relative names stay as fallbacks for unusual layouts.
    backend_dir = Path(__file__).resolve().parent.parent  # apps/backend
    candidates: list[Path | str] = [backend_dir / ".env", ".env", "apps/backend/.env"]
    if getattr(sys, "frozen", False):
        candidates.insert(0, Path(sys.executable).parent / ".env")
    return tuple(candidates)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_prefix="NYANKO_",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "Nyanko"
    api_host: str = "127.0.0.1"
    api_port: int = 8765
    desktop_url: str = "http://localhost:1420"
    data_dir: Path = _default_data_dir()
    # Los client IDs son públicos por diseño (van en la URL de autorización que el
    # usuario ve): con default, el build distribuido funciona sin .env.
    anilist_client_id: str | None = "13519"
    anilist_client_secret: str | None = None  # AniList exige secreto (no soporta flujo público)
    # Broker de intercambio código→token (Supabase Edge Function): en builds
    # distribuidos el secreto de AniList vive SOLO ahí, nunca en el binario. Con
    # secreto local (dev), el intercambio es directo y el broker se ignora.
    anilist_token_broker_url: str | None = (
        "https://rzvsdzerhhzbjadxykyb.supabase.co/functions/v1/anilist-token"
    )
    anilist_redirect_uri_override: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NYANKO_ANILIST_REDIRECT_URI", "ANILIST_REDIRECT_URI"),
    )
    mal_client_id: str | None = "ca6bb15ca544f28b765383ef68a2ca8a"  # cliente público (PKCE)
    mal_client_secret: str | None = None
    mal_redirect_uri_override: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NYANKO_MAL_REDIRECT_URI", "MAL_REDIRECT_URI"),
    )
    vlc_password: str | None = None
    detection_stability_seconds: float = 3.0
    playback_deduplication_seconds: int = 300
    history_retention_days: int = 90
    extension_origins: str = ""

    @field_validator("data_dir", mode="after")
    @classmethod
    def _anchor_data_dir(cls, value: Path) -> Path:
        # Un data_dir relativo (p. ej. NYANKO_DATA_DIR=./data) se ancla a apps/backend,
        # no al cwd: cada cwd distinto creaba una base de datos nueva y divergente.
        if value.is_absolute():
            return value
        return _anchor_dir() / value

    @property
    def database_path(self) -> Path:
        return self.data_dir / "nyanko.sqlite3"

    @property
    def port_file(self) -> Path:
        return self.data_dir / "port"

    @property
    def assets_dir(self) -> Path:
        return self.data_dir / "assets"

    @property
    def instance_token_file(self) -> Path:
        return self.data_dir / "instance_token"

    @property
    def anilist_redirect_uri(self) -> str:
        if self.anilist_redirect_uri_override:
            return self.anilist_redirect_uri_override
        return f"http://127.0.0.1:{self.api_port}/api/auth/callback"

    @property
    def mal_redirect_uri(self) -> str:
        if self.mal_redirect_uri_override:
            return self.mal_redirect_uri_override
        return f"http://127.0.0.1:{self.api_port}/api/auth/mal/callback"

    @property
    def allowed_origins(self) -> list[str]:
        extension_origins = []
        for origin in self.extension_origins.split(","):
            origin = origin.strip()
            if not origin:
                continue
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"chrome-extension", "moz-extension"}
                or not parsed.netloc
                or origin != f"{parsed.scheme}://{parsed.netloc}"
            ):
                raise ValueError(f"Invalid extension origin: {origin}")
            extension_origins.append(origin)
        return [
            self.desktop_url,
            "tauri://localhost",
            "http://tauri.localhost",
            *extension_origins,
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
