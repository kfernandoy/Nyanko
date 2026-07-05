import pytest

from nyanko_api.config import Settings


def test_allowed_origins_accepts_only_extension_origins():
    settings = Settings(
        _env_file=None,
        extension_origins="chrome-extension://abc, moz-extension://def"
    )

    assert settings.allowed_origins[-2:] == [
        "chrome-extension://abc",
        "moz-extension://def",
    ]


@pytest.mark.parametrize(
    "origin",
    ["*", "https://example.com", "chrome-extension://abc/path"],
)
def test_allowed_origins_rejects_broad_or_malformed_values(origin):
    with pytest.raises(ValueError, match="Invalid extension origin"):
        Settings(_env_file=None, extension_origins=origin).allowed_origins


def test_redirect_uri_overrides_are_respected():
    settings = Settings(
        _env_file=None,
        anilist_redirect_uri_override="http://localhost:9000/anilist/callback",
        mal_redirect_uri_override="http://localhost:9000/mal/callback",
    )

    assert settings.anilist_redirect_uri == "http://localhost:9000/anilist/callback"
    assert settings.mal_redirect_uri == "http://localhost:9000/mal/callback"
