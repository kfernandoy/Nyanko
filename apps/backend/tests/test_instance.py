from nyanko_api import instance


def test_find_free_port_returns_valid_port():
    port = instance.find_free_port("127.0.0.1")
    assert 1024 <= port <= 65535


def test_port_file_round_trip(tmp_path):
    port_file = tmp_path / "port"
    instance.write_port_file(port_file, 12345)
    assert instance.read_port_file(port_file) == 12345


def test_token_file_round_trip(tmp_path):
    token_file = tmp_path / "token"
    token = instance.generate_token()
    instance.write_token_file(token_file, token)
    assert instance.read_token_file(token_file) == token
