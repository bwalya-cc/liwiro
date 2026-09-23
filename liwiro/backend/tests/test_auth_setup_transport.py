# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from flask import Flask


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import _initialize_vdb_runtime, _resolve_vdb_workdir, create_app


class AuthSetupTransportTests(unittest.TestCase):
    def test_vdb_workdir_is_writable_and_can_be_configured_separately_from_verun_root(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ", {"LIWIRO_VDB_WORKDIR": str(Path(tmpdir) / "vdb-workdir")}, clear=False
        ):
            workdir = _resolve_vdb_workdir()
            self.assertTrue(workdir.is_dir())
            self.assertTrue((workdir / "logs").parent.is_dir())
            self.assertNotEqual(workdir.name, "vdb")

    def _build_app(self):
        with patch("app.main._initialize_vdb_runtime", return_value=(True, "ok")), \
             patch("app.main._reconcile_service_runtime_states", return_value=[]), \
             patch("app.main._autostart_services_if_enabled", return_value=None):
            app = create_app()

        app.testing = True
        return app

    def test_setup_http_bootstrap_prepares_local_transport_before_vdb_auth(self):
        app = self._build_app()
        client = app.test_client()

        with patch("app.main._load_normalized_auth_data", return_value={}), \
             patch("app.main._resolve_verun_root", return_value=None), \
             patch("app.main._ensure_vdb_transport_ready", return_value=(True, "started")) as ensure_ready, \
             patch("app.main._verify_vdb_auth", return_value=(True, "Authenticated")) as verify_auth, \
             patch("app.main._save_normalized_auth_data", side_effect=lambda data: data), \
             patch("app.main._initialize_vdb_runtime", return_value=(True, "ok")):
            res = client.post(
                "/auth/signin",
                json={
                    "username": "zulan",
                    "password": "ChangeMeLiwiroPass0!",
                    "vdb_transport": "http",
                    "vdb_server_url": "http://localhost:1957",
                    "vdb_app_username": "Liwiro",
                    "vdb_app_password": "ChangeMeVdbAppPass0!",
                },
            )

        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertTrue(payload["bootstrap"])
        ensure_ready.assert_called_once()
        args = ensure_ready.call_args.args
        self.assertEqual(args[1], "http")
        self.assertEqual(args[2], "http://127.0.0.1:1957")
        verify_args = verify_auth.call_args_list[0].args
        self.assertEqual(verify_args[0], "http://127.0.0.1:1957")

    def test_login_succeeds_when_frontend_credentials_are_valid_but_vdb_runtime_init_fails(self):
        app = self._build_app()
        client = app.test_client()
        auth_data = {
            "users": [
                {
                    "username": "zulan",
                    "password_hash": "pbkdf2:sha256:600000$demo$demo",
                    "role": "admin",
                    "service_access": ["*"],
                    "permissions": [],
                    "liwiro_rbac": {},
                    "is_super_admin": True,
                }
            ],
            "vdb_transport": "unixsocket",
            "vdb_server_url": "http://127.0.0.1:1957",
            "vdb_unix_socket_path": "/tmp/vdb.sock",
            "vdb_named_pipe_path": "",
            "vdb_username": "Liwiro",
            "vdb_password": "ChangeMeVdbAppPass0!",
            "liwiro_domain": "liwiro",
            "liwiro_db": "config",
        }

        with patch("app.main._load_normalized_auth_data", return_value=auth_data), \
             patch("app.main._resolve_verun_root", return_value=Path("/tmp/verun")), \
             patch("app.main._vdb_has_any_user", return_value=True), \
             patch("app.main.check_password_hash", return_value=True), \
             patch("app.main._ensure_vdb_transport_ready", return_value=(True, "ready")), \
             patch("app.main._initialize_vdb_runtime", return_value=(False, "Authentication failed")):
            res = client.post(
                "/auth/signin",
                json={
                    "username": "zulan",
                    "password": "ChangeMeLiwiroPass0!",
                },
            )

        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertTrue(bool(payload.get("token")))
        self.assertEqual(payload["username"], "zulan")
        self.assertFalse(payload["bootstrap"])
        self.assertFalse(payload["vdbRuntimeReady"])
        self.assertEqual(payload["vdbRuntimeError"], "Authentication failed")

        me_res = client.get("/auth/me", headers={"Authorization": f"Bearer {payload['token']}"})
        self.assertEqual(me_res.status_code, 200)
        me_payload = me_res.get_json()
        self.assertFalse(me_payload["vdbRuntimeReady"])
        self.assertEqual(me_payload["vdbRuntimeError"], "Authentication failed")

    def test_bootstrap_signin_returns_concise_vdb_auth_error(self):
        app = self._build_app()
        client = app.test_client()

        with patch("app.main._load_normalized_auth_data", return_value={}), \
             patch("app.main._resolve_verun_root", return_value=Path("/tmp/verun")), \
             patch("app.main._vdb_has_any_user", return_value=False), \
             patch("app.main._vdb_has_user", return_value=False), \
             patch("app.main._vdb_has_super_admin", return_value=False), \
             patch("app.main._ensure_vdb_transport_ready", return_value=(True, "ready")), \
             patch(
                 "app.main._verify_vdb_auth",
                 side_effect=[
                     (False, '{"error": "Invalid credentials"}'),
                     (False, '{"error": "Invalid credentials"}'),
                 ],
             ):
            res = client.post(
                "/auth/signin",
                json={
                    "username": "zulan",
                    "password": "ChangeMeLiwiroPass0!",
                    "vdb_transport": "http",
                    "vdb_server_url": "http://localhost:1957",
                    "vdb_app_username": "liwiro",
                    "vdb_app_password": "ChangeMeVdbAppPass0!",
                },
            )

        self.assertEqual(res.status_code, 400)
        error = res.get_json()["error"]
        self.assertEqual(
            error,
            "Liwiro application user 'liwiro' was not found in VDB. No VDB super admin is configured.",
        )
        self.assertNotIn("Details:", error)
        self.assertNotIn('{"error"', error)
        self.assertNotIn("fallback VDB super-admin", error)

    def test_create_app_skips_vdb_runtime_init_during_first_time_setup(self):
        with patch("app.main._load_normalized_auth_data", return_value={}), \
             patch("app.main._resolve_verun_root", return_value=Path("/tmp/verun")), \
             patch("app.main._vdb_has_any_user", return_value=False), \
             patch("app.main._initialize_vdb_runtime") as initialize_vdb_runtime, \
             patch("app.main._reconcile_service_runtime_states", return_value=[]), \
             patch("app.main._autostart_services_if_enabled", return_value=None):
            app = create_app()

        self.assertIsNotNone(app)
        initialize_vdb_runtime.assert_not_called()

    def test_initialize_vdb_runtime_repairs_app_user_with_super_admin_candidate(self):
        app = Flask(__name__)
        app.config["VDB_TRANSPORT"] = "unixsocket"
        app.config["VDB_SERVER_URL"] = "http://127.0.0.1:1957"
        app.config["VDB_UNIX_SOCKET_PATH"] = "/tmp/vdb.sock"
        app.config["VDB_NAMED_PIPE_PATH"] = ""
        app.config["VDB_USERNAME"] = "liwiro"
        app.config["VDB_PASSWORD"] = "ChangeMeVdbAppPass0!"
        app.config["LIWIRO_DOMAIN"] = "liwiro"
        app.config["LIWIRO_DB"] = "config"
        app.process_manager = MagicMock()

        fake_client = MagicMock()
        fake_client.ensure_workspace.return_value = True
        fake_client.get_context.return_value = {"domain": "liwiro", "database": "config"}

        with patch("app.main._ensure_vdb_transport_ready", return_value=(True, "ready")), \
             patch(
                 "app.main._verify_vdb_auth",
                 side_effect=[
                     (False, "Invalid VDB username or password."),
                     (True, "Authenticated"),
                     (True, "Authenticated"),
                 ],
             ) as verify_vdb_auth, \
             patch("app.main._ensure_vdb_user", return_value=(True, "User repaired")) as ensure_vdb_user, \
             patch("app.main._load_normalized_auth_data", return_value={}), \
             patch("app.main.VDBClient", return_value=fake_client), \
             patch("app.main._initialize_services_collection", return_value=True):
            ok, msg = _initialize_vdb_runtime(
                app,
                repair_admin_candidates=[("zulan", "ChangeMeLiwiroPass0!", "current Liwiro super admin sign-in")],
            )

        self.assertTrue(ok)
        self.assertEqual(msg, "VDB runtime initialized")
        ensure_vdb_user.assert_called_once()
        verify_args = [call.args[1] for call in verify_vdb_auth.call_args_list]
        self.assertEqual(verify_args[:3], ["liwiro", "zulan", "liwiro"])

    def test_initialize_vdb_runtime_prepares_http_transport_before_client_connect(self):
        app = Flask(__name__)
        app.config["VDB_TRANSPORT"] = "http"
        app.config["VDB_SERVER_URL"] = "http://127.0.0.1:2057"
        app.config["VDB_USERNAME"] = "liwiro"
        app.config["VDB_PASSWORD"] = "ChangeMeVdbAppPass0!"
        app.config["LIWIRO_DOMAIN"] = "liwiro"
        app.config["LIWIRO_DB"] = "config"
        app.process_manager = MagicMock()

        fake_client = MagicMock()
        fake_client.ensure_workspace.return_value = True
        fake_client.get_context.return_value = {"domain": "liwiro", "database": "config"}

        with patch("app.main._ensure_vdb_transport_ready", return_value=(True, "started")) as ensure_ready, \
             patch("app.main._verify_vdb_auth", return_value=(True, "Authenticated")), \
             patch("app.main.VDBClient", return_value=fake_client), \
             patch("app.main._initialize_services_collection", return_value=True):
            ok, msg = _initialize_vdb_runtime(app)

        self.assertTrue(ok)
        self.assertEqual(msg, "VDB runtime initialized")
        ensure_ready.assert_called_once_with(app, "http", "http://127.0.0.1:2057", None, None)
        fake_client.ensure_workspace.assert_called_once_with("liwiro", "config")

    def test_initialize_vdb_runtime_falls_back_to_http_when_socket_credentials_are_valid(self):
        app = Flask(__name__)
        app.config["VDB_TRANSPORT"] = "unixsocket"
        app.config["VDB_SERVER_URL"] = "http://127.0.0.1:2057"
        app.config["VDB_UNIX_SOCKET_PATH"] = "/tmp/missing-vdb.sock"
        app.config["VDB_NAMED_PIPE_PATH"] = ""
        app.config["VDB_USERNAME"] = "liwiro"
        app.config["VDB_PASSWORD"] = "ChangeMeVdbAppPass0!"
        app.config["LIWIRO_DOMAIN"] = "liwiro"
        app.config["LIWIRO_DB"] = "config"
        app.process_manager = MagicMock()

        fake_client = MagicMock()
        fake_client.ensure_workspace.return_value = True
        fake_client.get_context.return_value = {"domain": "liwiro", "database": "config"}
        with patch("app.main._ensure_vdb_transport_ready", return_value=(True, "ready")), \
             patch("app.main._verify_vdb_auth", side_effect=[(False, "Unix socket not found"), (True, "Authenticated")]), \
             patch("app.main._autostart_local_vdb_http_if_needed", return_value=(True, "HTTP ready")), \
             patch("app.main._persist_runtime_vdb_env") as persist_env, \
             patch("app.main.VDBClient", return_value=fake_client), \
             patch("app.main._initialize_services_collection", return_value=True):
            ok, msg = _initialize_vdb_runtime(app)

        self.assertTrue(ok)
        self.assertEqual(msg, "VDB runtime initialized")
        self.assertEqual(app.config["VDB_TRANSPORT"], "http")
        persist_env.assert_called_once()

    def test_vdb_connection_status_route_reports_selected_transport_health(self):
        app = self._build_app()
        client = app.test_client()

        with patch(
            "app.main._probe_vdb_transport_status",
            return_value={
                "transport": "http",
                "available": True,
                "status": "available",
                "target": "http://127.0.0.1:1957",
                "detail": "Healthy HTTP response",
            },
        ) as probe_status:
            res = client.get(
                "/auth/vdb-connection-status?vdb_transport=http&vdb_server_url=http://localhost:1957"
            )

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["available"])
        self.assertEqual(data["transport"], "http")
        probe_status.assert_called_once_with(
            transport_mode="http",
            server_url="http://localhost:1957",
            socket_path="/tmp/vdb.sock",
            named_pipe_path="\\\\.\\pipe\\verun_vdb",
        )

    def test_auth_status_reuses_vdb_user_manifest_within_request(self):
        app = self._build_app()
        client = app.test_client()

        with tempfile.TemporaryDirectory() as tmp_dir:
            verun_root = Path(tmp_dir)
            users_dir = verun_root / "vdb" / "__data__" / "sys" / "users"
            users_dir.mkdir(parents=True, exist_ok=True)
            (users_dir / "users.bson").write_bytes(b"stub")

            with patch("app.main._load_normalized_auth_data", return_value={}), \
                 patch("app.main._resolve_verun_root", return_value=verun_root), \
                 patch("app.main.read_bson_value", return_value=[{"username": "alice"}]) as read_bson:
                res = client.get("/auth/status")

        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertTrue(payload["vdbUsersExist"])
        self.assertEqual(payload["vdbUsernames"], ["alice"])
        read_bson.assert_called_once()

    def test_vdb_connection_status_route_can_attempt_http_autostart(self):
        app = self._build_app()
        client = app.test_client()

        with patch(
            "app.main._probe_vdb_transport_status",
            side_effect=[
                {
                    "transport": "http",
                    "available": False,
                    "status": "unavailable",
                    "target": "http://127.0.0.1:1957",
                    "detail": "HTTP server unavailable",
                    "localTarget": True,
                },
                {
                    "transport": "http",
                    "available": True,
                    "status": "available",
                    "target": "http://127.0.0.1:1957",
                    "detail": "HTTP server available",
                    "localTarget": True,
                },
            ],
        ) as probe_status, patch(
            "app.main._autostart_local_vdb_http_if_needed",
            return_value=(True, "Started local VDB HTTP server"),
        ) as autostart_http:
            res = client.get(
                "/auth/vdb-connection-status?vdb_transport=http&vdb_server_url=http://localhost:1957&attempt_autostart=1"
            )

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["available"])
        self.assertTrue(data["autostartAttempted"])
        autostart_http.assert_called_once()
        self.assertEqual(probe_status.call_count, 2)

    def test_vdb_connection_status_route_defers_http_autostart_during_cooldown(self):
        app = self._build_app()
        client = app.test_client()
        app.resilience_state = {
            "vdb_http_autostart": {
                "http|http://localhost:1957": {
                    "pausedUntil": time.time() + 30,
                    "lastError": "Local VDB HTTP auto-start failed",
                }
            }
        }

        with patch(
            "app.main._probe_vdb_transport_status",
            return_value={
                "transport": "http",
                "available": False,
                "status": "unavailable",
                "target": "http://127.0.0.1:1957",
                "detail": "HTTP server unavailable",
                "localTarget": True,
            },
        ) as probe_status, patch(
            "app.main._autostart_local_vdb_http_if_needed",
            return_value=(True, "Started local VDB HTTP server"),
        ) as autostart_http:
            res = client.get(
                "/auth/vdb-connection-status?vdb_transport=http&vdb_server_url=http://localhost:1957&attempt_autostart=1"
            )

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "paused")
        self.assertTrue(data["degraded"])
        self.assertTrue(data["autostartDeferred"])
        self.assertGreater(data["retryAfterMs"], 0)
        self.assertEqual(data["reason"], "Local VDB HTTP auto-start failed")
        autostart_http.assert_not_called()
        probe_status.assert_called_once()

    def test_vdb_connection_status_route_reports_named_pipe_health(self):
        app = self._build_app()
        client = app.test_client()

        with patch(
            "app.main._probe_vdb_transport_status",
            return_value={
                "transport": "namedpipe",
                "available": True,
                "status": "available",
                "target": "\\\\.\\pipe\\verun_vdb",
                "detail": "Named pipe available",
            },
        ) as probe_status:
            res = client.get(
                "/auth/vdb-connection-status?vdb_transport=namedpipe&vdb_named_pipe_path=\\\\.\\pipe\\verun_vdb"
            )

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["available"])
        self.assertEqual(data["transport"], "namedpipe")
        probe_status.assert_called_once_with(
            transport_mode="namedpipe",
            server_url="http://127.0.0.1:1957",
            socket_path="/tmp/vdb.sock",
            named_pipe_path="\\\\.\\pipe\\verun_vdb",
        )

    def test_vdb_connection_status_route_reports_named_pipe_unsupported_state(self):
        app = self._build_app()
        client = app.test_client()

        with patch("app.main.supports_named_pipe_transport", return_value=False):
            res = client.get(
                "/auth/vdb-connection-status?vdb_transport=namedpipe&vdb_named_pipe_path=\\\\.\\pipe\\verun_vdb"
            )

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertFalse(data["available"])
        self.assertEqual(data["transport"], "namedpipe")
        self.assertEqual(data["status"], "unsupported")
        self.assertEqual(data["detail"], "Named pipes are only supported on Windows")
        self.assertFalse(data["localTarget"])

    def test_vdb_connection_status_route_does_not_attempt_named_pipe_autostart(self):
        app = self._build_app()
        client = app.test_client()

        with patch(
            "app.main._probe_vdb_transport_status",
            return_value={
                "transport": "namedpipe",
                "available": False,
                "status": "unavailable",
                "target": "\\\\.\\pipe\\verun_vdb",
                "detail": "Named pipe unavailable",
                "localTarget": True,
            },
        ) as probe_status, patch(
            "app.main._autostart_local_vdb_named_pipe_if_needed",
            return_value=(True, "Started named-pipe interface"),
        ) as autostart_namedpipe:
            res = client.get(
                "/auth/vdb-connection-status?vdb_transport=namedpipe&vdb_named_pipe_path=\\\\.\\pipe\\verun_vdb&attempt_autostart=1"
            )

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertFalse(data["available"])
        self.assertFalse(bool(data.get("autostartAttempted")))
        autostart_namedpipe.assert_not_called()
        probe_status.assert_called_once()

    def test_license_and_health_routes_are_available(self):
        app = self._build_app()
        client = app.test_client()

        health_res = client.get("/health")
        license_res = client.get("/license")

        self.assertEqual(health_res.status_code, 200)
        self.assertEqual(health_res.get_json()["status"], "ok")

        self.assertEqual(license_res.status_code, 200)
        self.assertEqual(license_res.get_json()["license"], "MIT")


if __name__ == "__main__":
    unittest.main()
