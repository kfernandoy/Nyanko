from __future__ import annotations

from typing import Literal

SourceErrorAction = Literal["reintentar", "actualizar_la_fuente", "esperar"]


class SourceError(RuntimeError):
    pass


class SourceNetworkError(SourceError):
    pass


class SourceParseError(SourceError):
    pass


class SourceRateLimitError(SourceError):
    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class SourceNotFoundError(SourceError):
    pass


class SourceUnsupportedError(SourceError):
    pass


def source_error_action(error: SourceError) -> SourceErrorAction:
    if isinstance(error, SourceRateLimitError):
        return "esperar"
    if isinstance(error, SourceNetworkError):
        return "reintentar"
    return "actualizar_la_fuente"
