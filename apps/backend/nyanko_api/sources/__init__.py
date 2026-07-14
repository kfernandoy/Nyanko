from .contract import (
    SOURCE_API_VERSION,
    Source,
    SourceCapabilities,
    SourceChapter,
    SourceFetcher,
    SourcePage,
    SourceSeries,
)
from .errors import (
    SourceError,
    SourceNetworkError,
    SourceNotFoundError,
    SourceParseError,
    SourceRateLimitError,
    SourceUnsupportedError,
    source_error_action,
)
from .local_archive import LocalArchiveSource
from .registry import SourceRegistration, SourceRegistry, build_source_registry

SOURCES = [LocalArchiveSource]

__all__ = [
    "SOURCE_API_VERSION",
    "SOURCES",
    "LocalArchiveSource",
    "Source",
    "SourceCapabilities",
    "SourceChapter",
    "SourceError",
    "SourceFetcher",
    "SourceNetworkError",
    "SourceNotFoundError",
    "SourcePage",
    "SourceParseError",
    "SourceRateLimitError",
    "SourceRegistration",
    "SourceRegistry",
    "SourceSeries",
    "SourceUnsupportedError",
    "build_source_registry",
    "source_error_action",
]
