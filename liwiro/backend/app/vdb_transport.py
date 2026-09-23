# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

from __future__ import annotations

from app.vdb_commands import command_text

import base64
import ctypes
import json
import os
import socket
import struct
import sys
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse, urlunparse

import requests

from config import (
    Config,
    default_vdb_named_pipe_path,
    default_vdb_transport_mode,
    default_vdb_unix_socket_path,
    normalize_vdb_named_pipe_path as _normalize_config_named_pipe_path,
    supports_named_pipe_transport,
    supports_unix_socket_transport,
    vdb_host_platform,
)


_LEGACY_VDB_OPERATION_KEYS = frozenset({
    "tumi", "read", "create", "update", "delete", "list", "drop",
    "define", "use", "transaction", "script", "index", "find", "insert",
    "aggregate", "create_collection", "drop_collection", "drop_domain", "drop_db",
    "create_index", "drop_index", "list_indexes", "rebuild_indexes",
    "model_get", "model_delete", "script_create", "script_read", "script_execute",
    "script_delete", "script_list", "transaction_begin", "transaction_commit",
    "transaction_abort", "domain_status", "domain_suspend", "domain_resume",
    "help", "context", "whoami", "echo", "export",
})


def _validate_flat_vdb_payload(payload: dict | list) -> dict | list:
    """Validate trusted SDK action objects before converting them to command text."""
    if isinstance(payload, list):
        if not payload:
            raise ValueError("VDB batch command must contain at least one action")
        if any(isinstance(item, dict) and "commands" in item for item in payload):
            raise ValueError("VDB batch entries must be flat actions")
        return [_validate_flat_vdb_payload(item) for item in payload]
    if not isinstance(payload, dict):
        raise ValueError("Internal VDB actions must be objects")
    if "commands" in payload:
        if set(payload) != {"commands"} or not isinstance(payload["commands"], list) or not payload["commands"]:
            raise ValueError("VDB batch command must contain a non-empty commands array")
        if any(isinstance(item, dict) and "commands" in item for item in payload["commands"]):
            raise ValueError("VDB batch entries must be flat actions")
        return {"commands": [_validate_flat_vdb_payload(item) for item in payload["commands"]]}
    action = payload.get("action")
    if not isinstance(action, str) or not action.strip():
        raise ValueError("Internal VDB action objects require an action name")
    nested = sorted(_LEGACY_VDB_OPERATION_KEYS.intersection(payload))
    if nested:
        raise ValueError(
            "Nested internal VDB operation objects are not supported "
            f"(found: {', '.join(nested)})"
        )
    normalized = dict(payload)
    normalized["action"] = action.strip().lower()
    return normalized


def host_platform() -> str:
    return vdb_host_platform()


def resolve_vdb_named_pipe_path(config_source=None, explicit_path: str | None = None) -> str:
    if explicit_path and str(explicit_path).strip():
        return normalize_vdb_named_pipe_path(str(explicit_path).strip())

    if config_source is not None:
        value = config_source.get("VDB_NAMED_PIPE_PATH")
        if value and str(value).strip():
            return normalize_vdb_named_pipe_path(str(value).strip())

    env_path = os.getenv("VDB_NAMED_PIPE_PATH")
    if env_path and str(env_path).strip():
        return normalize_vdb_named_pipe_path(str(env_path).strip())

    configured = getattr(Config, "VDB_NAMED_PIPE_PATH", "")
    if configured and str(configured).strip():
        return normalize_vdb_named_pipe_path(str(configured).strip())

    return normalize_vdb_named_pipe_path(default_vdb_named_pipe_path())


def normalize_vdb_named_pipe_path(value: str | None) -> str:
    return _normalize_config_named_pipe_path(value)


def resolve_vdb_unix_socket_path(config_source=None, explicit_path: str | None = None) -> str:
    if explicit_path and str(explicit_path).strip():
        return str(explicit_path).strip()

    if config_source is not None:
        value = config_source.get("VDB_UNIX_SOCKET_PATH")
        if value and str(value).strip():
            return str(value).strip()

    env_path = os.getenv("VDB_UNIX_SOCKET_PATH") or os.getenv("VDB_INTERFACE_UNIXSOCKET_PATH")
    if env_path and str(env_path).strip():
        return str(env_path).strip()

    configured = getattr(Config, "VDB_UNIX_SOCKET_PATH", "")
    if configured and str(configured).strip():
        return str(configured).strip()

    fallback = default_vdb_unix_socket_path()
    if fallback:
        return fallback
    if os.path.exists("/run") and os.access("/run", os.W_OK):
        return "/run/vdb.sock"
    return os.path.join(tempfile.gettempdir(), "vdb.sock")


def normalize_vdb_transport_mode(value: str | None) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    if text in {"", "default", "auto"}:
        return default_vdb_transport_mode()
    if text in {"unixsocket", "unix_socket", "unix", "socket", "uds"}:
        return _compatible_vdb_transport_mode("unixsocket")
    if text in {"namedpipe", "named_pipe", "pipe", "ipc", "af_pipe"}:
        return _compatible_vdb_transport_mode("namedpipe")
    if text in {"http", "httpserver", "http_server", "tcp", "tcp_loopback"}:
        return "http"
    return default_vdb_transport_mode()


def _compatible_vdb_transport_mode(mode: str) -> str:
    normalized = str(mode or "").strip().lower()
    if normalized == "namedpipe":
        if supports_named_pipe_transport():
            return "namedpipe"
        if supports_unix_socket_transport():
            return "unixsocket"
        return "http"
    if normalized == "unixsocket":
        if supports_unix_socket_transport():
            return "unixsocket"
        if supports_named_pipe_transport():
            return "namedpipe"
        return "http"
    if normalized == "http":
        return "http"
    return default_vdb_transport_mode()


def resolve_vdb_transport_mode(config_source=None, explicit_mode: str | None = None) -> str:
    if explicit_mode is not None and str(explicit_mode).strip():
        return normalize_vdb_transport_mode(explicit_mode)

    if config_source is not None:
        value = config_source.get("VDB_TRANSPORT")
        if value is not None and str(value).strip():
            return normalize_vdb_transport_mode(value)

    env_mode = os.getenv("VDB_TRANSPORT")
    if env_mode is not None and str(env_mode).strip():
        return normalize_vdb_transport_mode(env_mode)

    return normalize_vdb_transport_mode(getattr(Config, "VDB_TRANSPORT", default_vdb_transport_mode()))


@lru_cache(maxsize=1)
def _local_host_aliases() -> set[str]:
    aliases = {"localhost", "127.0.0.1", "::1"}
    for candidate in (socket.gethostname(), socket.getfqdn()):
        text = str(candidate or "").strip().lower()
        if text:
            aliases.add(text)
    return aliases


@lru_cache(maxsize=1)
def _local_ip_addresses() -> set[str]:
    addresses = {"127.0.0.1", "::1"}
    for candidate in _local_host_aliases():
        try:
            for info in socket.getaddrinfo(candidate, None):
                host = str(info[4][0] or "").strip().lower()
                if host:
                    addresses.add(host)
        except OSError:
            continue
    return addresses


@lru_cache(maxsize=32)
def _resolved_host_addresses(host: str) -> tuple[str, ...]:
    try:
        results = []
        for info in socket.getaddrinfo(host, None):
            resolved = str(info[4][0] or "").strip().lower()
            if resolved and resolved not in results:
                results.append(resolved)
        return tuple(results)
    except OSError:
        return ()


def is_local_vdb_url(server_url: str | None) -> bool:
    text = str(server_url or "").strip()
    if not text:
        return True
    parsed = urlparse(text)
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False
    if host in _local_host_aliases() or host in _local_ip_addresses():
        return True
    return any(address in _local_ip_addresses() for address in _resolved_host_addresses(host))


def normalize_local_vdb_http_url(server_url: str | None) -> str:
    text = str(server_url or "").strip()
    if not text:
        return ""

    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        return text
    if not parsed.hostname or not is_local_vdb_url(text):
        return text

    auth_part = ""
    if parsed.username:
        auth_part = parsed.username
        if parsed.password:
            auth_part = f"{auth_part}:{parsed.password}"
        auth_part = f"{auth_part}@"
    port_part = f":{parsed.port}" if parsed.port else ""
    normalized = parsed._replace(netloc=f"{auth_part}127.0.0.1{port_part}")
    return urlunparse(normalized)


class VDBTransportError(Exception):
    pass


class VDBTransportConnectionError(VDBTransportError):
    pass


class VDBTransportProtocolError(VDBTransportError):
    pass


class VDBTransportRequestError(VDBTransportError):
    def __init__(self, status_code: int, message: str, payload: Any = None, raw_body: str = ""):
        super().__init__(message)
        self.status_code = int(status_code)
        self.payload = payload
        self.raw_body = raw_body


@dataclass
class _SocketResponse:
    status_code: int
    content_type: str
    body: Any


def _extract_error_message(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("error") or payload.get("message") or "").strip()
    if isinstance(payload, str):
        return payload.strip()
    return ""


def _decode_transport_response(raw_response: bytes, label: str) -> _SocketResponse:
    try:
        decoded = json.loads(raw_response.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise VDBTransportProtocolError(f"Invalid {label} response envelope") from exc

    if not isinstance(decoded, dict):
        raise VDBTransportProtocolError(f"Invalid {label} response envelope")

    return _SocketResponse(
        status_code=int(decoded.get("statusCode") or 0),
        content_type=str(decoded.get("contentType") or "application/json; charset=UTF-8"),
        body=decoded.get("body"),
    )


class VDBHttpTransport:
    def __init__(self, base_url: str):
        self.base_url = normalize_local_vdb_http_url(str(base_url or "").rstrip("/"))
        if not self.base_url:
            raise ValueError("VDB server URL is required for HTTP transport")

    def auth(self, username: str, password: str, timeout: int = 30) -> dict:
        return self._post("auth", auth=(username, password), timeout=timeout)

    def vql(self, session_id: str, payload: dict | list, timeout: int = 30) -> dict:
        payload = command_text(_validate_flat_vdb_payload(payload) if not isinstance(payload, str) else payload)
        return self._post("vdb", data=payload.encode("utf-8"), headers={"X-Session-Id": session_id, "Content-Type": "text/versa; charset=utf-8"}, timeout=timeout)

    def vdb(self, session_id: str, payload: dict | list, timeout: int = 30) -> dict:
        """Send canonical native Versa commands (vql is a compatibility alias)."""
        return self.vql(session_id, payload, timeout)

    def health(self, timeout: int = 5) -> dict:
        path = "health"
        url = f"{self.base_url}/{path}"
        try:
            response = requests.get(url, timeout=timeout)
        except requests.exceptions.RequestException as exc:
            raise VDBTransportConnectionError(str(exc)) from exc
        raw_body = response.text or ""
        if raw_body:
            try:
                payload = response.json()
            except json.JSONDecodeError as exc:
                raise VDBTransportProtocolError("Invalid health response") from exc
        else:
            payload = {}
        if not response.ok:
            message = _extract_error_message(payload) or raw_body or f"HTTP {response.status_code}"
            raise VDBTransportRequestError(response.status_code, message, payload=payload, raw_body=raw_body)
        return payload if isinstance(payload, dict) else {"data": payload}

    def _post(self, route: str, **kwargs):
        path = str(route or "").lstrip("/")
        url = f"{self.base_url}/{path}"
        try:
            response = requests.post(url, **kwargs)
        except requests.exceptions.RequestException as exc:
            raise VDBTransportConnectionError(str(exc)) from exc

        payload = None
        raw_body = response.text or ""
        if raw_body:
            try:
                payload = response.json()
            except json.JSONDecodeError as exc:
                raise VDBTransportProtocolError("Invalid server response") from exc
        else:
            payload = {}

        if not response.ok:
            message = ""
            if isinstance(payload, dict):
                message = str(payload.get("error") or payload.get("message") or "").strip()
            if not message:
                message = raw_body or f"HTTP {response.status_code}"
            raise VDBTransportRequestError(response.status_code, message, payload=payload, raw_body=raw_body)
        return payload if isinstance(payload, dict) else {"data": payload}


class VDBUnixSocketTransport:
    def __init__(self, socket_path: str):
        self.socket_path = resolve_vdb_unix_socket_path(explicit_path=socket_path)

    def auth(self, username: str, password: str, timeout: int = 30) -> dict:
        auth_header = "Basic " + base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        body = self._request(
            method="POST",
            path="/auth",
            headers={"Authorization": auth_header},
            body="",
            timeout=timeout,
        )
        if not isinstance(body, dict):
            raise VDBTransportProtocolError("Invalid auth response")
        return body

    def vql(self, session_id: str, payload: dict | list, timeout: int = 30) -> dict:
        payload = command_text(_validate_flat_vdb_payload(payload) if not isinstance(payload, str) else payload)
        body = self._request(
            method="POST",
            path="/vdb",
            headers={"X-Session-Id": session_id},
            body=payload,
            timeout=timeout,
        )
        if isinstance(body, dict):
            return body
        if isinstance(body, list):
            return {"responses": body}
        raise VDBTransportProtocolError("Invalid VQL response")

    def vdb(self, session_id: str, payload: dict | list, timeout: int = 30) -> dict:
        return self.vql(session_id, payload, timeout)

    def health(self, timeout: int = 5) -> dict:
        body = self._request(method="GET", path="/health", headers={}, body=None, timeout=timeout)
        if isinstance(body, dict):
            return body
        raise VDBTransportProtocolError("Invalid VDBUnixSocket health response")

    def _request(self, method: str, path: str, headers: dict | None, body: Any, timeout: int) -> Any:
        if not supports_unix_socket_transport():
            raise VDBTransportConnectionError("Unix sockets are not supported on this host")

        envelope = {
            "method": method,
            "path": path,
            "headers": headers or {},
            "body": "" if body is None else body,
        }
        payload = json.dumps(envelope).encode("utf-8")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(timeout)
                client.connect(self.socket_path)
                self._write_frame(client, payload)
                raw_response = self._read_frame(client)
        except FileNotFoundError as exc:
            raise VDBTransportConnectionError(f"Unix socket not found: {self.socket_path}") from exc
        except ConnectionRefusedError as exc:
            raise VDBTransportConnectionError(f"Unix socket refused connection: {self.socket_path}") from exc
        except socket.timeout as exc:
            raise VDBTransportConnectionError(f"Unix socket request timed out: {self.socket_path}") from exc
        except OSError as exc:
            raise VDBTransportConnectionError(str(exc)) from exc

        response = _decode_transport_response(raw_response, "VDBUnixSocket")
        if response.status_code >= 400:
            message = _extract_error_message(response.body) or f"Status {response.status_code}"
            raw_body = response.body if isinstance(response.body, str) else json.dumps(response.body)
            raise VDBTransportRequestError(response.status_code, message, payload=response.body, raw_body=raw_body)
        return response.body

    def _write_frame(self, client: socket.socket, payload: bytes) -> None:
        client.sendall(struct.pack(">I", len(payload)) + payload)

    def _read_frame(self, client: socket.socket) -> bytes:
        raw_len = self._read_exact(client, 4)
        if not raw_len:
            raise VDBTransportProtocolError("No response received from VDBUnixSocket")
        length = struct.unpack(">I", raw_len)[0]
        if length < 0 or length > 64 * 1024 * 1024:
            raise VDBTransportProtocolError(f"Invalid VDBUnixSocket frame length: {length}")
        return self._read_exact(client, length)

    def _read_exact(self, client: socket.socket, size: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < size:
            chunk = client.recv(size - len(chunks))
            if not chunk:
                raise VDBTransportProtocolError("Unexpected EOF from VDBUnixSocket")
            chunks.extend(chunk)
        return bytes(chunks)


INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
ERROR_FILE_NOT_FOUND = 2
ERROR_PIPE_BUSY = 231
ERROR_BROKEN_PIPE = 109
ERROR_NO_DATA = 232
ERROR_SEM_TIMEOUT = 121
_KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True) if sys.platform == "win32" else None


class _WinNamedPipeClient:
    def __init__(self, pipe_path: str, timeout: int):
        if sys.platform != "win32":
            raise VDBTransportConnectionError("Named pipes are only supported on Windows")
        self.pipe_path = normalize_vdb_named_pipe_path(pipe_path)
        self.timeout_ms = max(1, int(timeout * 1000))
        self.handle = None

    def __enter__(self):
        self.handle = _open_win_named_pipe(self.pipe_path, self.timeout_ms)
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def close(self) -> None:
        if self.handle:
            _KERNEL32.CloseHandle(self.handle)
            self.handle = None

    def send_frame(self, payload: bytes) -> None:
        _write_win_pipe_all(self.handle, struct.pack(">I", len(payload)) + payload, self.pipe_path)

    def recv_frame(self) -> bytes:
        raw_len = _read_win_pipe_exact(self.handle, 4, self.pipe_path)
        if not raw_len:
            raise VDBTransportProtocolError("No response received from VDBNamedPipe")
        length = struct.unpack(">I", raw_len)[0]
        if length < 0 or length > 64 * 1024 * 1024:
            raise VDBTransportProtocolError(f"Invalid VDBNamedPipe frame length: {length}")
        return _read_win_pipe_exact(self.handle, length, self.pipe_path)


def _open_win_named_pipe(pipe_path: str, timeout_ms: int):
    kernel32 = _KERNEL32
    if not kernel32.WaitNamedPipeW(ctypes.c_wchar_p(pipe_path), ctypes.c_uint32(timeout_ms)):
        error = ctypes.get_last_error()
        if error in {ERROR_FILE_NOT_FOUND, ERROR_PIPE_BUSY, ERROR_SEM_TIMEOUT}:
            raise VDBTransportConnectionError(f"Named pipe not found: {pipe_path}")
        raise VDBTransportConnectionError(f"Unable to open named pipe {pipe_path}: winerror={error}")

    handle = kernel32.CreateFileW(
        ctypes.c_wchar_p(pipe_path),
        ctypes.c_uint32(GENERIC_READ | GENERIC_WRITE),
        ctypes.c_uint32(0),
        None,
        ctypes.c_uint32(OPEN_EXISTING),
        ctypes.c_uint32(0),
        None,
    )
    if handle == INVALID_HANDLE_VALUE:
        error = ctypes.get_last_error()
        if error in {ERROR_FILE_NOT_FOUND, ERROR_PIPE_BUSY, ERROR_SEM_TIMEOUT}:
            raise VDBTransportConnectionError(f"Named pipe not found: {pipe_path}")
        raise VDBTransportConnectionError(f"Unable to open named pipe {pipe_path}: winerror={error}")
    return handle


def _read_win_pipe_exact(handle, size: int, pipe_path: str) -> bytes:
    kernel32 = _KERNEL32
    chunks = bytearray()
    while len(chunks) < size:
        remaining = size - len(chunks)
        buffer = (ctypes.c_char * remaining)()
        read_count = ctypes.c_uint32(0)
        ok = kernel32.ReadFile(handle, buffer, remaining, ctypes.byref(read_count), None)
        if not ok:
            error = ctypes.get_last_error()
            if error in {ERROR_BROKEN_PIPE, ERROR_NO_DATA}:
                raise VDBTransportProtocolError("Unexpected EOF from VDBNamedPipe")
            raise VDBTransportConnectionError(f"Named pipe read failed ({pipe_path}): winerror={error}")
        if read_count.value <= 0:
            raise VDBTransportProtocolError("Unexpected EOF from VDBNamedPipe")
        chunks.extend(buffer[:read_count.value])
    return bytes(chunks)


def _write_win_pipe_all(handle, payload: bytes, pipe_path: str) -> None:
    kernel32 = _KERNEL32
    total_written = 0
    while total_written < len(payload):
        chunk = payload[total_written:]
        buffer = (ctypes.c_char * len(chunk)).from_buffer_copy(chunk)
        written = ctypes.c_uint32(0)
        ok = kernel32.WriteFile(handle, buffer, len(chunk), ctypes.byref(written), None)
        if not ok:
            error = ctypes.get_last_error()
            raise VDBTransportConnectionError(f"Named pipe write failed ({pipe_path}): winerror={error}")
        if written.value <= 0:
            raise VDBTransportConnectionError(f"Named pipe write failed ({pipe_path}): zero bytes written")
        total_written += written.value


class VDBNamedPipeTransport:
    def __init__(self, pipe_path: str):
        self.pipe_path = resolve_vdb_named_pipe_path(explicit_path=pipe_path)

    def auth(self, username: str, password: str, timeout: int = 30) -> dict:
        auth_header = "Basic " + base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        body = self._request(
            method="POST",
            path="/auth",
            headers={"Authorization": auth_header},
            body="",
            timeout=timeout,
        )
        if not isinstance(body, dict):
            raise VDBTransportProtocolError("Invalid auth response")
        return body

    def vql(self, session_id: str, payload: dict | list, timeout: int = 30) -> dict:
        payload = command_text(_validate_flat_vdb_payload(payload) if not isinstance(payload, str) else payload)
        body = self._request(
            method="POST",
            path="/vdb",
            headers={"X-Session-Id": session_id},
            body=payload,
            timeout=timeout,
        )
        if isinstance(body, dict):
            return body
        if isinstance(body, list):
            return {"responses": body}
        raise VDBTransportProtocolError("Invalid VQL response")

    def vdb(self, session_id: str, payload: dict | list, timeout: int = 30) -> dict:
        return self.vql(session_id, payload, timeout)

    def health(self, timeout: int = 5) -> dict:
        body = self._request(method="GET", path="/health", headers={}, body=None, timeout=timeout)
        if isinstance(body, dict):
            return body
        raise VDBTransportProtocolError("Invalid named pipe health response")

    def _request(self, method: str, path: str, headers: dict | None, body: Any, timeout: int) -> Any:
        if not supports_named_pipe_transport():
            raise VDBTransportConnectionError("Named pipes are only supported on Windows")

        envelope = {
            "method": method,
            "path": path,
            "headers": headers or {},
            "body": "" if body is None else body,
        }
        payload = json.dumps(envelope).encode("utf-8")
        try:
            with _WinNamedPipeClient(self.pipe_path, timeout) as conn:
                conn.send_frame(payload)
                raw_response = conn.recv_frame()
        except OSError as exc:
            raise VDBTransportConnectionError(str(exc)) from exc

        response = _decode_transport_response(raw_response, "VDBNamedPipe")
        if response.status_code >= 400:
            message = _extract_error_message(response.body) or f"Status {response.status_code}"
            raw_body = response.body if isinstance(response.body, str) else json.dumps(response.body)
            raise VDBTransportRequestError(response.status_code, message, payload=response.body, raw_body=raw_body)
        return response.body


def build_local_vdb_transport(app):
    resolved_mode = resolve_vdb_transport_mode(getattr(app, "config", None))
    if resolved_mode == "namedpipe":
        return VDBNamedPipeTransport(resolve_vdb_named_pipe_path(getattr(app, "config", None)))
    return VDBUnixSocketTransport(resolve_vdb_unix_socket_path(getattr(app, "config", None)))


def build_configured_vdb_transport(app):
    return build_vdb_transport(app, transport_mode=resolve_vdb_transport_mode(getattr(app, "config", None)))


def build_vdb_transport(
    app,
    server_url: str | None = None,
    socket_path: str | None = None,
    named_pipe_path: str | None = None,
    transport_mode: str | None = None,
    prefer_socket: bool = True,
    allow_http_fallback: bool = True,
):
    resolved_mode = resolve_vdb_transport_mode(getattr(app, "config", None), transport_mode)
    resolved_socket_path = resolve_vdb_unix_socket_path(getattr(app, "config", None), socket_path)
    resolved_named_pipe_path = resolve_vdb_named_pipe_path(getattr(app, "config", None), named_pipe_path)
    if resolved_mode == "unixsocket":
        return VDBUnixSocketTransport(resolved_socket_path)
    if resolved_mode == "namedpipe":
        return VDBNamedPipeTransport(resolved_named_pipe_path)

    resolved_server_url = str(server_url or getattr(app, "config", {}).get("VDB_SERVER_URL") or "").strip()
    if resolved_server_url:
        return VDBHttpTransport(resolved_server_url)

    if allow_http_fallback or resolved_mode == "http":
        configured_url = str(getattr(Config, "VDB_SERVER_URL", "") or "").strip()
        if configured_url:
            return VDBHttpTransport(configured_url)

    if prefer_socket and is_local_vdb_url(server_url):
        if supports_named_pipe_transport():
            return VDBNamedPipeTransport(resolved_named_pipe_path)
        return VDBUnixSocketTransport(resolved_socket_path)

    raise ValueError("No VDB transport configuration is available")
