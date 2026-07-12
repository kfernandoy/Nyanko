from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, Protocol

from .anilist import AniListClient
from .config import Settings
from .models import (
    ActivityItem,
    GlobalSearchResponse,
    MediaDetails,
    MediaEntryUpdate,
    MediaItem,
    MediaListEntry,
    ProgressUpdate,
    SearchFilters,
    SearchResult,
    SeasonMedia,
    StatisticsResponse,
    UserPreferences,
    UserPreferencesUpdate,
)
from .kitsu import KitsuClient, KitsuCredential, KitsuError
from .myanimelist import MyAnimeListClient, MyAnimeListCredential, MyAnimeListError


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    library: bool = True
    search: bool = True
    details: bool = True
    batch_details: bool = False
    batch_manga_details: bool = False
    mutations: bool = True
    activity: bool = False
    statistics: bool = False
    seasons: bool = False
    manga: bool = False
    preferences: bool = False
    preferences_editable: bool = False


MediaType = Literal["ANIME", "MANGA"]


class MediaProvider(Protocol):
    name: str
    display_name: str
    capabilities: ProviderCapabilities

    async def library(self, credential: str) -> list[MediaItem]: ...

    async def search(
        self, credential: str, query: str, limit: int = 10
    ) -> list[SearchResult]: ...

    async def search_manga(
        self, credential: str, query: str, limit: int = 10
    ) -> list[SearchResult]: ...

    async def discover(
        self, credential: str, filters: SearchFilters
    ) -> GlobalSearchResponse: ...

    async def details(self, credential: str, external_id: int) -> MediaDetails: ...

    async def details_batch(
        self, credential: str, external_ids: list[int]
    ) -> list[MediaDetails]: ...

    async def update_progress(self, credential: str, update: ProgressUpdate) -> dict: ...

    async def edit_entry(
        self, credential: str, external_id: int, update: MediaEntryUpdate, media_type: MediaType = "ANIME"
    ) -> MediaListEntry: ...

    async def delete_entry(self, credential: str, entry_id: int) -> bool: ...

    async def activity(
        self, credential: str, page: int = 1, limit: int = 30
    ) -> list[ActivityItem]: ...

    async def season(
        self, credential: str, season: str, year: int
    ) -> list[SeasonMedia]: ...

    async def statistics(self, credential: str) -> StatisticsResponse: ...

    async def preferences(self, credential: str) -> UserPreferences: ...

    async def update_preferences(
        self, credential: str, update: UserPreferencesUpdate
    ) -> UserPreferences: ...

    async def library_manga(self, credential: str) -> list[MediaItem]: ...

    async def manga_details(self, credential: str, external_id: int) -> MediaDetails: ...

    async def manga_details_batch(
        self, credential: str, external_ids: list[int]
    ) -> list[MediaDetails]: ...


class AniListProvider:
    name = "anilist"
    display_name = "AniList"
    capabilities = ProviderCapabilities(
        activity=True,
        statistics=True,
        seasons=True,
        manga=True,
        preferences=True,
        preferences_editable=True,
        batch_details=True,
        batch_manga_details=True,
    )

    def __init__(self, settings: Settings):
        self.client = AniListClient(settings)

    async def library(self, credential: str) -> list[MediaItem]:
        return await self.client.media_list(credential)

    async def search(
        self, credential: str, query: str, limit: int = 10
    ) -> list[SearchResult]:
        return await self.client.search(credential, query, limit)

    async def search_manga(
        self, credential: str, query: str, limit: int = 10
    ) -> list[SearchResult]:
        return await self.client.search_manga(credential, query, limit)

    async def discover(
        self, credential: str, filters: SearchFilters
    ) -> GlobalSearchResponse:
        return await self.client.discover(credential, filters)

    async def details(self, credential: str, external_id: int) -> MediaDetails:
        return await self.client.media_details(credential, external_id)

    async def details_batch(
        self, credential: str, external_ids: list[int]
    ) -> list[MediaDetails]:
        return await self.client.media_details_batch(credential, external_ids)

    async def update_progress(self, credential: str, update: ProgressUpdate) -> dict:
        return await self.client.update_progress(credential, update)

    async def edit_entry(
        self, credential: str, external_id: int, update: MediaEntryUpdate, media_type: MediaType = "ANIME"
    ) -> MediaListEntry:
        return await self.client.edit_entry(credential, external_id, update)

    async def delete_entry(self, credential: str, entry_id: int) -> bool:
        return await self.client.delete_entry(credential, entry_id)

    async def activity(
        self, credential: str, page: int = 1, limit: int = 30
    ) -> list[ActivityItem]:
        return await self.client.activity(credential, page, limit)

    async def season(
        self, credential: str, season: str, year: int
    ) -> list[SeasonMedia]:
        items: list[SeasonMedia] = []
        page = 1
        while True:
            batch = await self.client.season(credential, season, year, page, 50)
            items.extend(batch)
            if len(batch) < 50:
                return items
            page += 1

    async def statistics(self, credential: str) -> StatisticsResponse:
        return await self.client.statistics(credential)

    async def preferences(self, credential: str) -> UserPreferences:
        return await self.client.preferences(credential)

    async def update_preferences(
        self, credential: str, update: UserPreferencesUpdate
    ) -> UserPreferences:
        return await self.client.update_preferences(credential, update)

    async def library_manga(self, credential: str) -> list[MediaItem]:
        return await self.client.media_list_manga(credential)

    async def manga_details(self, credential: str, external_id: int) -> MediaDetails:
        return await self.client.manga_details(credential, external_id)

    async def manga_details_batch(
        self, credential: str, external_ids: list[int]
    ) -> list[MediaDetails]:
        return await self.client.manga_details_batch(credential, external_ids)


class MyAnimeListProvider:
    name = "mal"
    display_name = "MyAnimeList"
    capabilities = ProviderCapabilities(
        search=True,
        details=True,
        mutations=True,
        manga=True,
        preferences=True,
    )

    def __init__(self, settings: Settings):
        self.client = MyAnimeListClient(settings)

    async def library(self, credential: str) -> list[MediaItem]:
        parsed = MyAnimeListCredential.loads(credential)
        return await self.client.library(parsed.access_token)

    async def search(
        self, credential: str, query: str, limit: int = 10
    ) -> list[SearchResult]:
        parsed = MyAnimeListCredential.loads(credential)
        return await self.client.search(parsed.access_token, query, limit)

    async def search_manga(
        self, credential: str, query: str, limit: int = 10
    ) -> list[SearchResult]:
        raise MyAnimeListError("MyAnimeList manga is not enabled")

    async def discover(self, credential: str, filters: SearchFilters) -> GlobalSearchResponse:
        parsed = MyAnimeListCredential.loads(credential)
        return await self.client.discover(parsed.access_token, filters)

    async def details(self, credential: str, external_id: int) -> MediaDetails:
        parsed = MyAnimeListCredential.loads(credential)
        return await self.client.details(parsed.access_token, external_id)

    async def update_progress(self, credential: str, update: ProgressUpdate) -> dict:
        parsed = MyAnimeListCredential.loads(credential)
        return await self.client.update_progress(parsed.access_token, update)

    async def edit_entry(
        self, credential: str, external_id: int, update: MediaEntryUpdate, media_type: MediaType = "ANIME"
    ) -> MediaListEntry:
        parsed = MyAnimeListCredential.loads(credential)
        return await self.client.edit_entry(parsed.access_token, external_id, update, media_type)

    async def delete_entry(self, credential: str, entry_id: int) -> bool:
        parsed = MyAnimeListCredential.loads(credential)
        return await self.client.delete_entry(parsed.access_token, entry_id)

    async def activity(
        self, credential: str, page: int = 1, limit: int = 30
    ) -> list[ActivityItem]:
        raise MyAnimeListError("MyAnimeList activity is not enabled")

    async def season(
        self, credential: str, season: str, year: int
    ) -> list[SeasonMedia]:
        raise MyAnimeListError("MyAnimeList seasons are not enabled")

    async def statistics(self, credential: str) -> StatisticsResponse:
        # No native stats API; the endpoint derives them from the synced library instead.
        raise MyAnimeListError("MyAnimeList statistics are derived locally")

    async def preferences(self, credential: str) -> UserPreferences:
        parsed = MyAnimeListCredential.loads(credential)
        return await self.client.preferences(parsed.access_token)

    async def update_preferences(
        self, credential: str, update: UserPreferencesUpdate
    ) -> UserPreferences:
        raise MyAnimeListError("MyAnimeList no permite editar preferencias desde la API")

    async def library_manga(self, credential: str) -> list[MediaItem]:
        parsed = MyAnimeListCredential.loads(credential)
        return await self.client.library_manga(parsed.access_token)

    async def manga_details(self, credential: str, external_id: int) -> MediaDetails:
        parsed = MyAnimeListCredential.loads(credential)
        return await self.client.manga_details(parsed.access_token, external_id)


class KitsuProvider:
    name = "kitsu"
    display_name = "Kitsu"
    capabilities = ProviderCapabilities(
        search=True,
        details=True,
        mutations=True,
        preferences=True,
        preferences_editable=True,
    )

    def __init__(self, settings: Settings):
        self.client = KitsuClient()

    async def library(self, credential: str) -> list[MediaItem]:
        parsed = KitsuCredential.loads(credential)
        return await self.client.library(parsed.access_token)

    async def search(self, credential: str, query: str, limit: int = 10) -> list[SearchResult]:
        parsed = KitsuCredential.loads(credential)
        return await self.client.search(parsed.access_token, query, limit)

    async def search_manga(self, credential: str, query: str, limit: int = 10) -> list[SearchResult]:
        raise KitsuError("Kitsu manga search is not yet enabled")

    async def discover(self, credential: str, filters: SearchFilters) -> GlobalSearchResponse:
        parsed = KitsuCredential.loads(credential)
        return await self.client.discover(parsed.access_token, filters)

    async def details(self, credential: str, external_id: int) -> MediaDetails:
        parsed = KitsuCredential.loads(credential)
        return await self.client.details(parsed.access_token, external_id)

    async def update_progress(self, credential: str, update: ProgressUpdate) -> dict:
        parsed = KitsuCredential.loads(credential)
        return await self.client.update_progress(parsed.access_token, update)

    async def edit_entry(self, credential: str, external_id: int, update: MediaEntryUpdate, media_type: MediaType = "ANIME") -> MediaListEntry:
        parsed = KitsuCredential.loads(credential)
        return await self.client.edit_entry(parsed.access_token, external_id, update)

    async def delete_entry(self, credential: str, entry_id: int) -> bool:
        parsed = KitsuCredential.loads(credential)
        return await self.client.delete_entry(parsed.access_token, entry_id)

    async def activity(self, credential: str, page: int = 1, limit: int = 30) -> list[ActivityItem]:
        raise KitsuError("Kitsu activity is not enabled")

    async def season(self, credential: str, season: str, year: int) -> list[SeasonMedia]:
        raise KitsuError("Kitsu seasons are not enabled")

    async def statistics(self, credential: str) -> StatisticsResponse:
        raise KitsuError("Kitsu statistics are not enabled")

    async def preferences(self, credential: str) -> UserPreferences:
        parsed = KitsuCredential.loads(credential)
        return await self.client.preferences(parsed.access_token)

    async def update_preferences(self, credential: str, update: UserPreferencesUpdate) -> UserPreferences:
        parsed = KitsuCredential.loads(credential)
        return await self.client.update_preferences(parsed.access_token, update)

    async def library_manga(self, credential: str) -> list[MediaItem]:
        raise KitsuError("Kitsu manga is not yet enabled")

    async def manga_details(self, credential: str, external_id: int) -> MediaDetails:
        raise KitsuError("Kitsu manga is not yet enabled")


class ProviderRegistry:
    def __init__(self, providers: Iterable[MediaProvider] = ()):
        self._providers: dict[str, MediaProvider] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: MediaProvider) -> None:
        if provider.name in self._providers:
            raise ValueError(f"Provider already registered: {provider.name}")
        self._providers[provider.name] = provider

    def get(self, name: str) -> MediaProvider:
        try:
            return self._providers[name]
        except KeyError as error:
            raise KeyError(f"Unknown provider: {name}") from error

    def all(self) -> list[MediaProvider]:
        return list(self._providers.values())


def build_provider_registry(settings: Settings) -> ProviderRegistry:
    return ProviderRegistry([AniListProvider(settings), MyAnimeListProvider(settings), KitsuProvider(settings)])
