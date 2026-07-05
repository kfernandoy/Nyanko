from __future__ import annotations

import time
from pathlib import Path

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

SERVICE_NAME = "app.nyanko.desktop"
TOKEN_USERNAME = "anilist_access_token"

# Cada lectura del keyring de Windows es una RPC de ~100-500 ms y require_token la
# hacía en CADA request autenticada (bloqueando el event loop). Las credenciales
# cambian rarísimo: caché en proceso, invalidada al escribir/borrar, con TTL por si
# algo externo toca el keyring.
_cred_cache: dict[tuple[str, str], tuple[float, str | None]] = {}
_CRED_TTL_SECONDS = 60.0

# ponytail: module-level dir set at lifespan startup; avoids threading the path through every caller
_credentials_dir: Path | None = None


def init_credentials_dir(data_dir: Path) -> None:
    global _credentials_dir
    _credentials_dir = data_dir / "credentials"
    _credentials_dir.mkdir(parents=True, exist_ok=True)


def _cred_file(provider: str, account_alias: str) -> Path | None:
    if _credentials_dir is None:
        return None
    return _credentials_dir / f"{provider}_{account_alias}.token"


def credential_username(provider: str, account_alias: str) -> str:
    return f"provider:{provider}:account:{account_alias}:access_token"


def get_provider_credential(provider: str, account_alias: str = "default") -> str | None:
    cache_key = (provider, account_alias)
    hit = _cred_cache.get(cache_key)
    if hit is not None and time.monotonic() - hit[0] < _CRED_TTL_SECONDS:
        return hit[1]
    value = _read_provider_credential(provider, account_alias)
    _cred_cache[cache_key] = (time.monotonic(), value)
    return value


def _read_provider_credential(provider: str, account_alias: str) -> str | None:
    try:
        credential = keyring.get_password(
            SERVICE_NAME, credential_username(provider, account_alias)
        )
        if credential is None and provider == "anilist" and account_alias == "default":
            credential = keyring.get_password(SERVICE_NAME, TOKEN_USERNAME)
        if credential is not None:
            return credential
    except KeyringError:
        pass
    # fallback: file-based storage for credentials too large for the keyring
    cred_file = _cred_file(provider, account_alias)
    if cred_file and cred_file.exists():
        return cred_file.read_text(encoding="utf-8")
    return None


def set_provider_credential(
    provider: str, account_alias: str, credential: str | None
) -> None:
    _cred_cache.pop((provider, account_alias), None)
    if credential:
        try:
            keyring.set_password(
                SERVICE_NAME, credential_username(provider, account_alias), credential
            )
            return
        except Exception:
            pass
        # fallback: write to file when keyring rejects (e.g. Windows CRED_MAX_CREDENTIAL_BLOB_SIZE)
        cred_file = _cred_file(provider, account_alias)
        if cred_file is None:
            raise RuntimeError("No credentials directory configured and keyring rejected the credential")
        cred_file.write_text(credential, encoding="utf-8")
    else:
        delete_provider_credential(provider, account_alias)


def delete_provider_credential(provider: str, account_alias: str = "default") -> None:
    _cred_cache.pop((provider, account_alias), None)
    try:
        keyring.delete_password(
            SERVICE_NAME, credential_username(provider, account_alias)
        )
    except PasswordDeleteError:
        pass
    if provider == "anilist" and account_alias == "default":
        try:
            keyring.delete_password(SERVICE_NAME, TOKEN_USERNAME)
        except PasswordDeleteError:
            pass
    cred_file = _cred_file(provider, account_alias)
    if cred_file and cred_file.exists():
        cred_file.unlink(missing_ok=True)


def get_anilist_token(account_alias: str = "default") -> str | None:
    return get_provider_credential("anilist", account_alias)


def set_anilist_token(token: str | None, account_alias: str = "default") -> None:
    set_provider_credential("anilist", account_alias, token)


def delete_anilist_token(account_alias: str = "default") -> None:
    delete_provider_credential("anilist", account_alias)


def migrate_token_from_database(database) -> None:
    """Move an existing token from SQLite settings to the system keyring."""
    legacy_token = database.get_setting("anilist_access_token")
    if legacy_token:
        set_anilist_token(legacy_token)
        database.delete_setting("anilist_access_token")
