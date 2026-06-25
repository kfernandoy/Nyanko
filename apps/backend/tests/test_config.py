import pytest

from nyanko_api.config import Settings


def test_allowed_origins_accepts_only_extension_origins():
    settings = Settings(
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
        Settings(extension_origins=origin).allowed_origins
