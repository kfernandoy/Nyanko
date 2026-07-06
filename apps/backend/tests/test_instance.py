import socket

from nyanko_api import instance


def test_find_free_port_returns_valid_port():
    port = instance.find_free_port("127.0.0.1")
    assert 1024 <= port <= 65535


def test_resolve_port_prefers_configured_when_free():
    free = instance.find_free_port("127.0.0.1")
    assert instance.resolve_port("127.0.0.1", free) == free


def test_resolve_port_dynamic_when_zero():
    port = instance.resolve_port("127.0.0.1", 0)
    assert 1024 <= port <= 65535


def test_resolve_port_falls_back_when_taken():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        busy = taken.getsockname()[1]
        got = instance.resolve_port("127.0.0.1", busy)
        assert got != busy
        assert 1024 <= got <= 65535


def test_port_file_round_trip(tmp_path):
    port_file = tmp_path / "port"
    instance.write_port_file(port_file, 12345)
    assert instance.read_port_file(port_file) == 12345


def test_token_file_round_trip(tmp_path):
    token_file = tmp_path / "token"
    token = instance.generate_token()
    instance.write_token_file(token_file, token)
    assert instance.read_token_file(token_file) == token
