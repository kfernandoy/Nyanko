from nyanko_api import secrets
from nyanko_api.database import Database


def test_token_round_trip():
    secrets.set_anilist_token("abc123")
    assert secrets.get_anilist_token() == "abc123"


def test_delete_token():
    secrets.set_anilist_token("abc123")
    secrets.delete_anilist_token()
    assert secrets.get_anilist_token() is None


def test_set_none_deletes_token():
    secrets.set_anilist_token("abc123")
    secrets.set_anilist_token(None)
    assert secrets.get_anilist_token() is None


def test_credentials_are_isolated_by_account():
    secrets.set_anilist_token("first-token", "first")
    secrets.set_anilist_token("second-token", "second")

    assert secrets.get_anilist_token("first") == "first-token"
    assert secrets.get_anilist_token("second") == "second-token"

    secrets.delete_anilist_token("first")
    assert secrets.get_anilist_token("first") is None
    assert secrets.get_anilist_token("second") == "second-token"


def test_migrate_token_from_database(monkeypatch, tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    database.initialize()
    database.set_setting("anilist_access_token", "legacy-token")

    secrets.migrate_token_from_database(database)

    assert secrets.get_anilist_token() == "legacy-token"
    assert database.get_setting("anilist_access_token") is None
