from __future__ import annotations

import sys
import time
from pathlib import Path

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

# Dev y app instalada comparten el llavero del usuario de Windows: con un solo
# nombre de servicio, la app instalada "hereda" los tokens de desarrollo y salta
# el login. El build congelado usa el nombre canónico; dev, su propio namespace.
SERVICE_NAME = (
    "app.nyanko.desktop" if getattr(sys, "frozen", False) else "app.nyanko.desktop.dev"
)
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


# El fallback a fichero es inevitable: los JWT de MAL exceden el límite del
# credential blob de Windows. En Windows lo ciframos con DPAPI por usuario
# (CryptProtectData) para no dejar tokens en texto plano; en otras plataformas
# no hay DPAPI y se guarda tal cual (solo el usuario dueño de la carpeta lee).
_DPAPI_MAGIC = b"NYDPAPI1\n"


def _dpapi_crypt(data: bytes, protect: bool) -> bytes | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char)),
            ]

        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        buf = ctypes.create_string_buffer(data, len(data))
        in_blob = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        out_blob = DATA_BLOB()
        fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
        if not fn(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
        ):
            raise ctypes.WinError()
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            kernel32.LocalFree(out_blob.pbData)
    except Exception:
        return None


def _write_cred_file(cred_file: Path, credential: str) -> None:
    protected = _dpapi_crypt(credential.encode("utf-8"), protect=True)
    if protected is not None:
        cred_file.write_bytes(_DPAPI_MAGIC + protected)
    else:
        cred_file.write_text(credential, encoding="utf-8")


def _read_cred_file(cred_file: Path) -> str | None:
    raw = cred_file.read_bytes()
    if raw.startswith(_DPAPI_MAGIC):
        plain = _dpapi_crypt(raw[len(_DPAPI_MAGIC) :], protect=False)
        return plain.decode("utf-8") if plain is not None else None
    # Fichero antiguo en texto plano: devuélvelo y migra a formato cifrado.
    credential = raw.decode("utf-8")
    _write_cred_file(cred_file, credential)
    return credential


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
        return _read_cred_file(cred_file)
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
        _write_cred_file(cred_file, credential)
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
