import pytest

from nyanko_api.config import Settings
from nyanko_api.models import MediaItem, SeasonMedia
from nyanko_api.providers import AniListProvider, ProviderRegistry


class StubProvider:
    name = "stub"
    display_name = "Stub"
    capabilities = None

    async def library(self, credential: str) -> list[MediaItem]:
        return []


def test_provider_registry_lookup():
    provider = StubProvider()
    registry = ProviderRegistry([provider])

    assert registry.get("stub") is provider
    assert registry.all() == [provider]


def test_provider_registry_rejects_duplicates():
    provider = StubProvider()

    with pytest.raises(ValueError, match="already registered"):
        ProviderRegistry([provider, provider])


def test_provider_registry_rejects_unknown_provider():
    registry = ProviderRegistry()

    with pytest.raises(KeyError, match="Unknown provider"):
        registry.get("missing")


@pytest.mark.asyncio
async def test_anilist_provider_loads_complete_season(monkeypatch):
    provider = AniListProvider(Settings())
    calls = []

    async def season(_credential, _season, _year, page, _per_page):
        calls.append(page)
        count = 50 if page == 1 else 1
        return [
            SeasonMedia(id=page * 100 + index, title=str(index), popularity=0)
            for index in range(count)
        ]

    monkeypatch.setattr(provider.client, "season", season)

    items = await provider.season("token", "SPRING", 2026)

    assert len(items) == 51
    assert calls == [1, 2]
