import sys
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "data"
    return Path("apps/backend/data")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "apps/backend/.env"),
        env_prefix="NYANKO_",
        extra="ignore",
    )

    app_name: str = "Nyanko"
    api_host: str = "127.0.0.1"
    api_port: int = 8765
    desktop_url: str = "http://localhost:1420"
    data_dir: Path = _default_data_dir()
    anilist_client_id: str | None = None
    anilist_client_secret: str | None = None
    mal_client_id: str | None = None
    mal_client_secret: str | None = None
    vlc_password: str | None = None
    detection_stability_seconds: float = 3.0
    playback_deduplication_seconds: int = 300
    history_retention_days: int = 90
    extension_origins: str = ""

    @property
    def database_path(self) -> Path:
        return self.data_dir / "nyanko.sqlite3"

    @property
    def port_file(self) -> Path:
        return self.data_dir / "port"

    @property
    def instance_token_file(self) -> Path:
        return self.data_dir / "instance_token"

    @property
    def anilist_redirect_uri(self) -> str:
        return f"http://127.0.0.1:{self.api_port}/api/auth/callback"

    @property
    def mal_redirect_uri(self) -> str:
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
