import pytest
from keyring import backend, set_keyring


async def _noop_sleep(*args, **kwargs):
    return None


class _MemoryKeyring(backend.KeyringBackend):
    priority = 1

    def __init__(self):
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self._store.pop((service, username), None)


@pytest.fixture(autouse=True)
def _memory_keyring():
    set_keyring(_MemoryKeyring())
    yield


@pytest.fixture(autouse=True)
def _fast_rate_limit_sleep(monkeypatch):
    monkeypatch.setattr("nyanko_api.http.asyncio.sleep", _noop_sleep)
    yield
