# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import create_app, _canonicalize_vdb_query
from app.vdb_transport import VDBTransportRequestError


class _FakeTransport:
    def auth(self, username, password, timeout=30):
        return {"sessionId": "portal-session-1"}

    def vql(self, session_id, payload, timeout=30):
        if payload == {"action": "whoami"}:
            return {"status": "success", "data": {"username": "liwiro"}}
        if payload == {"action": "context"}:
            return {"status": "success", "data": {"domain": "liwiro", "database": "config"}}
        if payload == {"action": "tumi", "operation": "list", "resource": "users"}:
            return {"status": "success", "data": ["alice", "bob"]}
        if payload == {"action": "tumi", "operation": "list", "resource": "roles"}:
            return {
                "status": "success",
                "data": {
                    "system_roles": [{"name": "SUPER_ADMIN"}, {"name": "ADMIN"}],
                    "custom_roles": [{"name": "DOMAIN_EDITOR", "permissions": ["READ", "WRITE"]}],
                },
            }
        if payload == {"action": "tumi", "operation": "list", "resource": "permissions"}:
            return {"status": "success", "data": ["READ", "WRITE", "DATA_EXPORT"]}
        if payload == {"action": "tumi", "operation": "list", "domains_and_owners": True}:
            return {"status": "success", "data": [{"domain": "default", "owners": ["alice"]}]}
        if payload == {"action": "tumi", "operation": "list", "permissions": "alice"}:
            return {
                "status": "success",
                "data": {
                    "username": "alice",
                    "owned_domains": ["default"],
                    "db_permissions": {"default": {"main": ["READ", "WRITE"]}},
                    "collection_permissions": {},
                },
            }
        if payload == {"action": "tumi", "operation": "list", "permissions": "bob"}:
            return {
                "status": "success",
                "data": {
                    "username": "bob",
                    "owned_domains": [],
                    "db_permissions": {"default": {"main": ["READ"]}},
                    "collection_permissions": {},
                },
            }
        if payload == {"action": "tumi", "operation": "grant", "username": "alice", "domain": "default", "permissions": ["READ"]}:
            return {"status": "success", "data": {"message": "Permissions granted"}}
        if payload == 'export domains ["default"] out_dir "/tmp/vdb-exports"':
            return {
                "status": "success",
                "data": {
                    "zip_file": "/tmp/vdb-exports/default-export.zip",
                    "out_dir": "/tmp/vdb-exports",
                    "exported_domains": ["default"],
                    "skipped_domains": {},
                },
            }
        return {"status": "success", "data": {}}


class _FailingAuthTransport:
    def auth(self, username, password, timeout=30):
        raise VDBTransportRequestError(
            401,
            "Invalid credentials",
            payload={"error": "Invalid credentials"},
            raw_body='{"error": "Invalid credentials"}',
        )


class VdbPortalTests(unittest.TestCase):
    def test_portal_requires_readable_command_text(self):
        command = "grant alice domain default"
        self.assertEqual(_canonicalize_vdb_query(command), command)
        with self.assertRaisesRegex(ValueError, "readable VDB command"):
            _canonicalize_vdb_query({"tumi": {"grant": {"username": "alice", "domain": "default"}}})

    def test_portal_accepts_readable_batches(self):
        batch = 'echo "hello"; context'
        self.assertEqual(_canonicalize_vdb_query(batch), batch)

    def _build_app(self):
        with patch("app.main._initialize_vdb_runtime", return_value=(True, "ok")), \
             patch("app.main._reconcile_service_runtime_states", return_value=[]), \
             patch("app.main._autostart_services_if_enabled", return_value=None):
            app = create_app()
        app.testing = True
        token = "frontend-session-token"
        app.auth_sessions[token] = {
            "username": "zulan",
            "role": "ADMIN",
            "is_super_admin": True,
            "service_access": ["*"],
            "permissions": ["MANAGE_SERVICES", "DATA_ACCESS", "DATA_EXPORT", "WRITE"],
        }
        return app, token

    def test_connection_includes_default_export_directory(self):
        app, token = self._build_app()
        client = app.test_client()

        with patch("app.main._load_normalized_auth_data", return_value={}):
            res = client.get(
                "/platform/vdb/connection",
                headers={"Authorization": f"Bearer {token}"},
            )

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(str(data["defaultVdbExportOutDir"]).endswith("vdb-exports"))

    def test_options_include_models_list(self):
        app, token = self._build_app()
        portal_token = "portal-token"
        app.vdb_portal_sessions[portal_token] = {
            "mode": "app",
            "username": "liwiro",
            "owner_username": "zulan",
            "vdb_transport": "http",
            "vdb_server_url": "http://127.0.0.1:1957",
            "session_id": "portal-session-1",
            "issued_at": "2026-03-13T00:00:00",
        }
        client = app.test_client()

        with patch(
            "app.main._vdb_portal_query",
            side_effect=[
                (True, ["default"]),
                (True, ["main"]),
                (True, ["users"]),
                (True, ["users"]),
                (True, ["bootstrap"]),
                (True, ["liwiro"]),
                (True, ["ADMIN"]),
                (True, ["DATA_EXPORT"]),
            ],
        ):
            res = client.get(
                "/platform/vdb/options",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-VDB-Portal-Token": portal_token,
                },
            )

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["models"], ["users"])

    def test_portal_session_can_execute_export_query(self):
        app, token = self._build_app()
        client = app.test_client()

        with patch(
            "app.main._load_normalized_auth_data",
            return_value={
                "vdb_transport": "http",
                "vdb_server_url": "http://127.0.0.1:1957",
                "vdb_username": "liwiro",
                "vdb_password": "ChangeMeVdbAppPass0!",
            },
        ), patch(
            "app.main._ensure_vdb_transport_ready",
            return_value=(True, "ready"),
        ), patch(
            "app.main.build_vdb_transport",
            return_value=_FakeTransport(),
        ):
            session_res = client.post(
                "/platform/vdb/session",
                headers={"Authorization": f"Bearer {token}"},
                json={"mode": "app"},
            )

            self.assertEqual(session_res.status_code, 200)
            portal_token = session_res.get_json()["portalToken"]

            export_res = client.post(
                "/platform/vdb/query",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-VDB-Portal-Token": portal_token,
                },
                json={"query": 'export domains ["default"] out_dir "/tmp/vdb-exports"'},
            )

        self.assertEqual(export_res.status_code, 200)
        data = export_res.get_json()
        self.assertEqual(data["data"]["zip_file"], "/tmp/vdb-exports/default-export.zip")
        self.assertEqual(data["data"]["exported_domains"], ["default"])

    def test_portal_query_rejects_nested_vdb_envelope(self):
        app, token = self._build_app()
        client = app.test_client()
        portal_token = "nested-contract-token"
        app.vdb_portal_sessions[portal_token] = {"owner_username": "zulan", "session_id": "saved-super-admin-session"}
        response = client.post(
            "/platform/vdb/query",
            headers={"Authorization": f"Bearer {token}", "X-VDB-Portal-Token": portal_token},
            json={"query": {"read": {"users": {"query": {}}}}},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("readable VDB command", response.get_json()["error"])

    def test_portal_query_accepts_readable_batch(self):
        app, token = self._build_app()
        client = app.test_client()
        portal_token = "batch-contract-token"
        app.vdb_portal_sessions[portal_token] = {"owner_username": "zulan", "session_id": "saved-session"}
        with patch("app.main._vdb_portal_query", return_value=(True, {"status": "success", "data": []})) as query:
            response = client.post(
                "/platform/vdb/query",
                headers={"Authorization": f"Bearer {token}", "X-VDB-Portal-Token": portal_token},
                json={"query": 'echo "hello"; context'},
            )
        self.assertEqual(response.status_code, 200)
        sent_query = query.call_args.args[1]
        self.assertEqual(sent_query, 'echo "hello"; context')

    def test_settings_can_repair_vdb_runtime_without_login_form(self):
        app, token = self._build_app()
        client = app.test_client()
        with patch("app.main._ensure_vdb_transport_ready", return_value=(True, "ready")), \
             patch("app.main._persist_runtime_vdb_env"), \
             patch("app.main._save_normalized_auth_data"), \
             patch("app.main._initialize_vdb_runtime", return_value=(True, "ready")):
            response = client.put(
                "/platform/vdb/connection",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "vdb_transport": "http",
                    "vdb_server_url": "http://127.0.0.1:1957",
                    "vdb_app_username": "runtime-user",
                    "vdb_app_password": "runtime-pass",
                    "liwiro_domain": "default",
                    "liwiro_db": "main",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["vdbRuntimeReady"])

    def test_portal_session_returns_concise_auth_error(self):
        app, token = self._build_app()
        client = app.test_client()

        with patch(
            "app.main._load_normalized_auth_data",
            return_value={
                "vdb_transport": "http",
                "vdb_server_url": "http://127.0.0.1:1957",
                "vdb_username": "liwiro",
                "vdb_password": "ChangeMeVdbAppPass0!",
            },
        ), patch(
            "app.main._ensure_vdb_transport_ready",
            return_value=(True, "ready"),
        ), patch(
            "app.main.build_vdb_transport",
            return_value=_FailingAuthTransport(),
        ):
            res = client.post(
                "/platform/vdb/session",
                headers={"Authorization": f"Bearer {token}"},
                json={"mode": "app"},
            )

        self.assertEqual(res.status_code, 401)
        error = res.get_json()["error"]
        self.assertEqual(error, "Invalid VDB username or password.")
        self.assertNotIn('{"error"', error)

    def test_rbac_overview_uses_saved_super_admin_when_no_portal_session_exists(self):
        app, token = self._build_app()
        client = app.test_client()

        with patch(
            "app.main._create_saved_vdb_super_admin_session",
            return_value=(True, {"session_id": "saved-super-admin-session"}),
        ), patch(
            "app.main._vdb_portal_query",
            side_effect=[
                (True, ["alice", "bob"]),
                (True, {"data": {"system_roles": [], "custom_roles": [{"name": "DOMAIN_EDITOR"}]}}),
                (True, ["READ", "WRITE"]),
                (True, [{"domain": "default", "owners": ["alice"]}]),
                (True, {"data": {"username": "alice", "owned_domains": ["default"], "db_permissions": {"default": {"main": ["READ"]}}, "collection_permissions": {}}}),
                (True, {"data": {"username": "bob", "owned_domains": [], "db_permissions": {"default": {"main": ["WRITE"]}}, "collection_permissions": {}}}),
            ],
        ):
            res = client.get(
                "/platform/vdb/rbac/overview",
                headers={"Authorization": f"Bearer {token}"},
            )

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["users"], ["alice", "bob"])
        self.assertEqual(len(data["user_permissions"]), 2)
        self.assertEqual(data["user_permissions"][0]["username"], "alice")

    def test_rbac_command_passes_through_tumi_payload(self):
        app, token = self._build_app()
        client = app.test_client()

        with patch(
            "app.main._create_saved_vdb_super_admin_session",
            return_value=(True, {"session_id": "saved-super-admin-session"}),
        ), patch(
            "app.main._vdb_portal_query",
            return_value=(True, {"status": "success", "data": {"message": "Permissions granted"}}),
        ) as portal_query:
            res = client.post(
                "/platform/vdb/rbac/command",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "text/plain"},
                data='grant alice domain default permissions ["READ"]',
            )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["data"]["message"], "Permissions granted")
        portal_query.assert_called_once_with(
            {"session_id": "saved-super-admin-session"},
            'grant alice domain default permissions ["READ"]',
        )

    def test_rbac_command_rejects_json_payload(self):
        app, token = self._build_app()
        response = app.test_client().post(
            "/platform/vdb/rbac/command",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "text/plain"},
            data='{"tumi":{"grant":{"username":"alice","domain":"default"}}}',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("readable VDB command", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
