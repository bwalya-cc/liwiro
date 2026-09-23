# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import json
import os
import socket
import struct
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.vdb_transport import (
    VDBHttpTransport,
    VDBNamedPipeTransport,
    VDBTransportConnectionError,
    VDBTransportProtocolError,
    VDBTransportRequestError,
    VDBUnixSocketTransport,
    build_vdb_transport,
    normalize_local_vdb_http_url,
    normalize_vdb_transport_mode,
)


class VDBTransportPayloadValidationTests(unittest.TestCase):
    def test_all_transports_reject_nested_vdb_payloads_before_io(self):
        transports = [
            VDBHttpTransport("http://127.0.0.1:1957"),
            VDBUnixSocketTransport("/tmp/vdb.sock"),
            VDBNamedPipeTransport(r"\\.\pipe\verun_vdb"),
        ]
        payload = {"action": "find", "collection": "users", "script": {"read": "x"}}
        for transport in transports:
            with self.subTest(transport=type(transport).__name__):
                with self.assertRaisesRegex(ValueError, "Nested internal VDB operation objects"):
                    transport.vql("sid", payload)

    def test_all_known_action_names_are_rejected_when_used_as_nested_envelopes(self):
        transport = VDBHttpTransport("http://127.0.0.1:1957")
        for nested_key in (
            "domain_status", "domain_suspend", "domain_resume", "aggregate",
            "create_collection", "drop_collection", "create_index", "script_execute",
        ):
            with self.subTest(nested_key=nested_key):
                with self.assertRaisesRegex(ValueError, "Nested internal VDB operation objects"):
                    transport.vql("sid", {"action": "echo", nested_key: {}})

    def test_action_is_normalized_before_transport_io(self):
        transport = VDBHttpTransport("http://127.0.0.1:1957")
        with patch.object(transport, "_post", return_value={"ok": True}) as request:
            transport.vql("sid", {"action": "  FIND  ", "collection": "users"})
        sent_payload = request.call_args.kwargs["data"].decode()
        self.assertEqual(sent_payload, 'read collection users')

    def test_batch_commands_accept_only_flat_actions(self):
        transport = VDBHttpTransport("http://127.0.0.1:1957")
        with patch.object(transport, "_post", return_value={"ok": True}) as request:
            transport.vql("sid", {"commands": [{"action": "ECHO", "value": "one"}, {"action": "context"}]})
        sent = request.call_args.kwargs["data"].decode()
        self.assertEqual(sent, 'echo value "one";\ncontext')
        with self.assertRaisesRegex(ValueError, "non-empty commands array"):
            transport.vql("sid", {"commands": [], "action": "echo"})
        with patch.object(transport, "_post", return_value={"ok": True}) as request:
            transport.vql("sid", [{"action": "ECHO", "value": "one"}, {"action": "context"}])
        self.assertEqual(request.call_args.kwargs["data"].decode(), 'echo value "one";\ncontext')
        with self.assertRaisesRegex(ValueError, "at least one action"):
            transport.vql("sid", [])
        with self.assertRaisesRegex(ValueError, "flat actions"):
            transport.vql("sid", {"commands": [{"commands": [{"action": "context"}]}]})

    def test_role_actions_serialize_to_readable_role_commands(self):
        transport = VDBHttpTransport("http://127.0.0.1:1957")
        with patch.object(transport, "_post", return_value={"ok": True}) as request:
            transport.vql("sid", {"action": "tumi", "operation": "create", "role": {
                "name": "REPORT_VIEWER", "permissions": ["DATA_ACCESS"],
                "scope": {"domain": "sales", "db": "main"},
            }})
        self.assertEqual(
            request.call_args.kwargs["data"].decode(),
            'create role REPORT_VIEWER = { permissions: [ "DATA_ACCESS" ], scope: { domain: "sales", db: "main" } };',
        )


class VDBUnixSocketTransportTests(unittest.TestCase):
    def test_auth_request_round_trip_over_unix_socket(self):
        response_bytes = _frame(json.dumps({
            "statusCode": 200,
            "contentType": "application/json; charset=UTF-8",
            "body": {"sessionId": "sid_123", "username": "liwiro", "role": "APPLICATION"},
        }).encode("utf-8"))
        fake_socket = _FakeSocket(response_bytes=response_bytes)

        with patch("app.vdb_transport.supports_unix_socket_transport", return_value=True), \
             patch("app.vdb_transport.socket.AF_UNIX", 1, create=True), \
             patch("app.vdb_transport.socket.socket", return_value=fake_socket):
            transport = VDBUnixSocketTransport("/tmp/vdb.sock")
            payload = transport.auth("liwiro", "pass", timeout=2)

        self.assertEqual(payload["sessionId"], "sid_123")
        request = _decode_request(fake_socket.sent_bytes)
        self.assertEqual(request["path"], "/auth")
        self.assertEqual(request["method"], "POST")
        self.assertIn("Authorization", request["headers"])

    def test_vql_error_raises_request_error(self):
        response_bytes = _frame(json.dumps({
            "statusCode": 401,
            "contentType": "application/json; charset=UTF-8",
            "body": {"error": "Invalid or expired session"},
        }).encode("utf-8"))
        fake_socket = _FakeSocket(response_bytes=response_bytes)

        with patch("app.vdb_transport.supports_unix_socket_transport", return_value=True), \
             patch("app.vdb_transport.socket.AF_UNIX", 1, create=True), \
             patch("app.vdb_transport.socket.socket", return_value=fake_socket):
            transport = VDBUnixSocketTransport("/tmp/vdb.sock")
            with self.assertRaises(VDBTransportRequestError) as ctx:
                transport.vql("sid_123", {"action": "list", "resource": "domains"}, timeout=2)

        self.assertEqual(ctx.exception.status_code, 401)
        self.assertIn("Invalid or expired session", str(ctx.exception))

    def test_invalid_socket_response_raises_protocol_error(self):
        fake_socket = _FakeSocket(response_bytes=_frame(b"not-json"))

        with patch("app.vdb_transport.supports_unix_socket_transport", return_value=True), \
             patch("app.vdb_transport.socket.AF_UNIX", 1, create=True), \
             patch("app.vdb_transport.socket.socket", return_value=fake_socket):
            transport = VDBUnixSocketTransport("/tmp/vdb.sock")
            with self.assertRaises(VDBTransportProtocolError):
                transport.auth("liwiro", "pass", timeout=2)

    def test_missing_socket_raises_connection_error(self):
        fake_socket = _FakeSocket(connect_error=FileNotFoundError("/tmp/vdb.sock"))

        with patch("app.vdb_transport.supports_unix_socket_transport", return_value=True), \
             patch("app.vdb_transport.socket.AF_UNIX", 1, create=True), \
             patch("app.vdb_transport.socket.socket", return_value=fake_socket):
            transport = VDBUnixSocketTransport("/tmp/vdb.sock")
            with self.assertRaises(VDBTransportConnectionError):
                transport.auth("liwiro", "pass", timeout=1)


class VDBNamedPipeTransportTests(unittest.TestCase):
    def test_auth_request_round_trip_over_named_pipe(self):
        response_bytes = _frame(json.dumps({
            "statusCode": 200,
            "contentType": "application/json; charset=UTF-8",
            "body": {"sessionId": "sid_999", "username": "liwiro", "role": "APPLICATION"},
        }).encode("utf-8"))
        fake_pipe = _FakeNamedPipe(response_bytes=response_bytes)

        with patch("app.vdb_transport.supports_named_pipe_transport", return_value=True), \
             patch("app.vdb_transport._WinNamedPipeClient", return_value=fake_pipe):
            transport = VDBNamedPipeTransport(r"\\.\pipe\verun_vdb")
            payload = transport.auth("liwiro", "pass", timeout=2)

        self.assertEqual(payload["sessionId"], "sid_999")
        request = _decode_request(fake_pipe.sent_bytes)
        self.assertEqual(request["path"], "/auth")
        self.assertEqual(request["method"], "POST")
        self.assertIn("Authorization", request["headers"])

    def test_named_pipe_missing_raises_connection_error(self):
        with patch("app.vdb_transport.supports_named_pipe_transport", return_value=True), \
             patch("app.vdb_transport._WinNamedPipeClient", side_effect=FileNotFoundError(r"\\.\pipe\verun_vdb")):
            transport = VDBNamedPipeTransport(r"\\.\pipe\verun_vdb")
            with self.assertRaises(VDBTransportConnectionError):
                transport.auth("liwiro", "pass", timeout=1)

    def test_named_pipe_path_normalization_strips_duplicate_prefix_and_control_chars(self):
        transport = VDBNamedPipeTransport("\\\\.\\pipe\\.\\pipe\verun_vdb")
        self.assertEqual(transport.pipe_path, r"\\.\pipe\verun_vdb")


class VDBTransportSelectionTests(unittest.TestCase):
    def test_build_vdb_transport_defaults_to_unix_socket(self):
        app = _FakeAppConfig({"VDB_TRANSPORT": "unixsocket", "VDB_UNIX_SOCKET_PATH": "/tmp/vdb.sock"})

        with patch("app.vdb_transport.supports_named_pipe_transport", return_value=False), \
             patch("app.vdb_transport.supports_unix_socket_transport", return_value=True):
            transport = build_vdb_transport(app)

        self.assertIsInstance(transport, VDBUnixSocketTransport)
        self.assertEqual(transport.socket_path, "/tmp/vdb.sock")

    def test_build_vdb_transport_uses_http_when_explicitly_configured(self):
        app = _FakeAppConfig({"VDB_TRANSPORT": "http", "VDB_SERVER_URL": "http://localhost:1957"})

        transport = build_vdb_transport(app)

        self.assertIsInstance(transport, VDBHttpTransport)
        self.assertEqual(transport.base_url, "http://127.0.0.1:1957")

    def test_runtime_app_transport_overrides_stale_environment_value(self):
        app = _FakeAppConfig({"VDB_TRANSPORT": "http", "VDB_SERVER_URL": "http://localhost:2957"})

        with patch.dict(os.environ, {"VDB_TRANSPORT": "unixsocket"}):
            transport = build_vdb_transport(app)

        self.assertIsInstance(transport, VDBHttpTransport)
        self.assertEqual(transport.base_url, "http://127.0.0.1:2957")

    def test_build_vdb_transport_uses_named_pipe_when_explicitly_configured(self):
        app = _FakeAppConfig({"VDB_TRANSPORT": "namedpipe", "VDB_NAMED_PIPE_PATH": r"\\.\pipe\verun_vdb"})

        with patch("app.vdb_transport.supports_named_pipe_transport", return_value=True), \
             patch("app.vdb_transport.supports_unix_socket_transport", return_value=False):
            transport = build_vdb_transport(app)

        self.assertIsInstance(transport, VDBNamedPipeTransport)
        self.assertEqual(transport.pipe_path, r"\\.\pipe\verun_vdb")

    def test_normalize_vdb_transport_mode_downgrades_named_pipe_on_non_windows_hosts(self):
        with patch("app.vdb_transport.supports_named_pipe_transport", return_value=False), \
             patch("app.vdb_transport.supports_unix_socket_transport", return_value=True):
            self.assertEqual(normalize_vdb_transport_mode("namedpipe"), "unixsocket")

    def test_normalize_vdb_transport_mode_downgrades_unix_socket_on_windows_hosts(self):
        with patch("app.vdb_transport.supports_named_pipe_transport", return_value=True), \
             patch("app.vdb_transport.supports_unix_socket_transport", return_value=False):
            self.assertEqual(normalize_vdb_transport_mode("unixsocket"), "namedpipe")

    def test_build_vdb_transport_avoids_unix_socket_on_windows_host(self):
        app = _FakeAppConfig({
            "VDB_TRANSPORT": "unixsocket",
            "VDB_UNIX_SOCKET_PATH": "/tmp/vdb.sock",
            "VDB_NAMED_PIPE_PATH": r"\\.\pipe\verun_vdb",
        })

        with patch("app.vdb_transport.supports_named_pipe_transport", return_value=True), \
             patch("app.vdb_transport.supports_unix_socket_transport", return_value=False):
            transport = build_vdb_transport(app)

        self.assertIsInstance(transport, VDBNamedPipeTransport)
        self.assertEqual(transport.pipe_path, r"\\.\pipe\verun_vdb")

    def test_normalize_local_vdb_http_url_rewrites_same_host_to_loopback(self):
        hostname = socket.gethostname()

        normalized = normalize_local_vdb_http_url(f"http://{hostname}:1957")

        self.assertEqual(normalized, "http://127.0.0.1:1957")


class _FakeSocket:
    def __init__(self, response_bytes: bytes | None = None, connect_error: Exception | None = None):
        self.response_bytes = response_bytes or b""
        self.connect_error = connect_error
        self.sent_bytes = b""
        self.timeout = None
        self.connected_to = None

    def settimeout(self, timeout):
        self.timeout = timeout

    def connect(self, path):
        if self.connect_error is not None:
            raise self.connect_error
        self.connected_to = path

    def sendall(self, data):
        self.sent_bytes += data

    def recv(self, size):
        if not self.response_bytes:
            return b""
        chunk = self.response_bytes[:size]
        self.response_bytes = self.response_bytes[size:]
        return chunk

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


class _FakeNamedPipe:
    def __init__(self, response_bytes: bytes | None = None):
        self.response_bytes = response_bytes or b""
        self.sent_bytes = b""
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def send_frame(self, payload):
        self.sent_bytes += _frame(payload)

    def recv_frame(self):
        if len(self.response_bytes) < 4:
            payload = self.response_bytes
        else:
            length = struct.unpack(">I", self.response_bytes[:4])[0]
            payload = self.response_bytes[4:4 + length]
        self.response_bytes = b""
        return payload

    def close(self):
        self.closed = True


def _frame(payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + payload


def _decode_request(frame: bytes):
    length = struct.unpack(">I", frame[:4])[0]
    payload = frame[4:4 + length]
    return json.loads(payload.decode("utf-8"))


class _FakeAppConfig:
    def __init__(self, config):
        self.config = dict(config or {})


if __name__ == "__main__":
    unittest.main()
