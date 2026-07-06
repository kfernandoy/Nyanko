import json
import os
import sys
from typing import Any

from ..models import PlaybackCandidate
from ..normalizer import normalize
from .base import Detector, DetectorInfo, looks_finished


class MpvDetector(Detector):
    name = "mpv"
    priority = 30
    trusted_evidence = True

    def __init__(self, socket_path: str | None = None):
        self.socket_path = socket_path or self._default_socket_path()

    @staticmethod
    def _default_socket_path() -> str:
        if sys.platform == "win32":
            return r"\\.\pipe\mpvsocket"
        return os.path.expanduser("~/.config/mpv/socket")

    def info(self) -> DetectorInfo:
        return DetectorInfo(name=self.name, available=self._socket_exists(), priority=self.priority)

    def _socket_exists(self) -> bool:
        if sys.platform == "win32":
            return True  # Named pipes are created dynamically; availability is checked at query time.
        return os.path.exists(self.socket_path)

    def detect(self) -> PlaybackCandidate | None:
        # mpv's IPC protocol is newline-delimited JSON over a Unix socket or Windows named pipe.
        # We use a small helper that talks to the socket via mpv's documented IPC protocol.
        try:
            title_payload = self._send_command({"command": ["get_property", "media-title"]})
            if title_payload is None:
                return None
            title = title_payload.get("data")
            if not title:
                return None
            normalized = normalize(title)
            if normalized.anime_title is None:
                return None
            position = self._get_property_float("time-pos")
            duration = self._get_property_float("duration")
            return PlaybackCandidate(
                source=self.name,
                raw_title=title,
                anime_title=normalized.anime_title,
                season=normalized.season,
                episode=normalized.episode.number if normalized.episode else None,
                episode_type=normalized.episode.type if normalized.episode else None,
                confidence=min(1.0, normalized.confidence + 0.1),
                position_seconds=position,
                duration_seconds=duration,
                paused=self._get_property_bool("pause"),
                finished=looks_finished(position, duration),
            )
        except Exception:
            return None

    def _request_property(self, name: str) -> Any | None:
        payload = self._send_command({"command": ["get_property", name]})
        return self._parse_property_value(payload)

    @staticmethod
    def _parse_property_value(payload: dict | None) -> Any | None:
        if payload is None:
            return None
        error = payload.get("error")
        if error and error != "success":
            return None
        return payload.get("data")

    def _get_property_float(self, name: str) -> float | None:
        value = self._request_property(name)
        return self._parse_float(value)

    def _get_property_bool(self, name: str) -> bool | None:
        value = self._request_property(name)
        return self._parse_bool(value)

    @staticmethod
    def _parse_float(value: Any) -> float | None:
        if isinstance(value, (int, float)) and value >= 0:
            return float(value)
        return None

    @staticmethod
    def _parse_bool(value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        return None

    def _send_command(self, command: dict) -> dict | None:
        if sys.platform == "win32":
            return self._send_command_windows(command)
        return self._send_command_unix(command)

    def _send_command_windows(self, command: dict) -> dict | None:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        GENERIC_READ_WRITE = 0xC0000000
        OPEN_EXISTING = 3
        INVALID_HANDLE_VALUE = -1

        handle = kernel32.CreateFileW(
            self.socket_path,
            GENERIC_READ_WRITE,
            0,
            None,
            OPEN_EXISTING,
            0,
            None,
        )
        if handle == INVALID_HANDLE_VALUE:
            return None

        try:
            message = json.dumps(command) + "\n"
            written = wintypes.DWORD()
            kernel32.WriteFile(handle, message.encode(), len(message.encode()), ctypes.byref(written), None)

            buffer = ctypes.create_string_buffer(4096)
            read = wintypes.DWORD()
            kernel32.ReadFile(handle, buffer, 4096, ctypes.byref(read), None)
            response = buffer.raw[: read.value].decode().strip()
            # mpv may send event lines before the response; take the last JSON object.
            for line in reversed(response.splitlines()):
                line = line.strip()
                if line:
                    try:
                        return json.loads(line)
                    except json.JSONDecodeError:
                        continue
            return None
        finally:
            kernel32.CloseHandle(handle)

    def _send_command_unix(self, command: dict) -> dict | None:
        import socket

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            try:
                sock.connect(self.socket_path)
            except (FileNotFoundError, ConnectionRefusedError):
                return None
            sock.sendall((json.dumps(command) + "\n").encode())
            data = b""
            while b"\n" not in data:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
            for line in reversed(data.decode().splitlines()):
                line = line.strip()
                if line:
                    try:
                        return json.loads(line)
                    except json.JSONDecodeError:
                        continue
            return None
