import keyring
from keyring.errors import KeyringError, PasswordDeleteError

SERVICE_NAME = "app.nyanko.desktop"
TOKEN_USERNAME = "anilist_access_token"


def credential_username(provider: str, account_alias: str) -> str:
    return f"provider:{provider}:account:{account_alias}:access_token"


def get_provider_credential(provider: str, account_alias: str = "default") -> str | None:
    try:
        credential = keyring.get_password(
            SERVICE_NAME, credential_username(provider, account_alias)
        )
        if credential is None and provider == "anilist" and account_alias == "default":
            credential = keyring.get_password(SERVICE_NAME, TOKEN_USERNAME)
        return credential
    except KeyringError:
        return None


def set_provider_credential(
    provider: str, account_alias: str, credential: str | None
) -> None:
    if credential:
        keyring.set_password(
            SERVICE_NAME, credential_username(provider, account_alias), credential
        )
    else:
        delete_provider_credential(provider, account_alias)


def delete_provider_credential(provider: str, account_alias: str = "default") -> None:
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
