# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import _sync_lapis_service_modules, create_app
from app.vi_modules import load_module_record


class VIModuleRoutesTests(unittest.TestCase):
    @staticmethod
    def _unique_module_name(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:8]}"

    def _build_app(self):
        with patch("app.main._initialize_vdb_runtime", return_value=(True, "ok")), \
             patch("app.main._reconcile_service_runtime_states", return_value=[]), \
             patch("app.main._autostart_services_if_enabled", return_value=None):
            app = create_app()

        app.testing = True
        app.config["LIWIRO_DOMAIN"] = "liwiro"
        app.config["LIWIRO_DB"] = "config"
        app.config["VDB_TRANSPORT"] = "unixsocket"
        app.config["VDB_UNIX_SOCKET_PATH"] = "/tmp/vdb.sock"
        app.config["VDB_SERVER_URL"] = "http://localhost:1957"
        app.config["VDB_USERNAME"] = "liwiro"
        app.config["VDB_PASSWORD"] = "pass"
        source_dir = tempfile.TemporaryDirectory()
        modules_dir = tempfile.TemporaryDirectory()
        self.addCleanup(source_dir.cleanup)
        self.addCleanup(modules_dir.cleanup)
        app.config["VI_PORTAL_SOURCE_DIR"] = source_dir.name
        app.config["VI_CUSTOM_MODULES_DIR"] = modules_dir.name

        app.vdb_client = MagicMock()
        app.vdb_client.async_authorize.return_value = True
        app.vdb_client.use_domain.return_value = True
        app.vdb_client.use_database.return_value = True
        app.vdb_client.list_domains.return_value = (True, ["liwiro", "media", "portal"])

        token = "test-token"
        app.auth_sessions[token] = {
            "username": "zulan",
            "role": "admin",
            "is_super_admin": False,
            "service_access": ["*"],
            "permissions_overrides": [],
            "liwiro_rbac": {},
            "permissions": ["VIEW_SERVICES", "MANAGE_SERVICES"],
        }
        super_token = "super-token"
        app.auth_sessions[super_token] = {
            "username": "root",
            "role": "admin",
            "is_super_admin": True,
            "service_access": ["*"],
            "permissions_overrides": [],
            "liwiro_rbac": {},
            "permissions": ["VIEW_SERVICES", "MANAGE_SERVICES"],
        }
        return app, token, super_token

    def test_modules_catalog_returns_seeded_mediacloud(self):
        app, token, _ = self._build_app()
        client = app.test_client()

        res = client.get("/platform/vi/modules/catalog", headers={"Authorization": f"Bearer {token}"})

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("mediacloud", [item["name"] for item in data["modules"]])
        self.assertIn("media", data["available_domains"])

    def test_non_super_admin_cannot_create_global_module(self):
        app, token, _ = self._build_app()
        client = app.test_client()
        module_name = self._unique_module_name("domain_media")

        res = client.post(
            "/platform/vi/modules",
            json={
                "name": module_name,
                "title": "Domain Media",
                "scope": "global",
                "source": 'func hello() {\n  return "ok";\n}',
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(res.status_code, 400)
        self.assertIn("super admin", res.get_json()["error"].lower())

    def test_non_super_admin_can_assign_multiple_accessible_domains(self):
        app, token, _ = self._build_app()
        client = app.test_client()
        module_name = self._unique_module_name("domain_bundle")

        res = client.post(
            "/platform/vi/modules",
            json={
                "name": module_name,
                "title": "Domain Bundle",
                "scope": "domain",
                "assigned_domains": ["media", "portal", "unknown"],
                "source": 'func hello() {\n  return "ok";\n}',
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(res.status_code, 201)
        module = res.get_json()["module"]
        self.assertEqual(module["assigned_domains"], ["media", "portal"])
        self.assertEqual(module["owner_domains"], ["media", "portal"])

    def test_service_module_sync_adds_current_service_domain(self):
        app, token, _ = self._build_app()
        client = app.test_client()
        module_name = self._unique_module_name("domain_media")
        create_res = client.post(
            "/platform/vi/modules",
            json={
                "name": module_name,
                "title": "Domain Media",
                "scope": "domain",
                "assigned_domains": ["media"],
                "source": 'func hello(name) {\n  return "hello " + name;\n}',
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(create_res.status_code, 201)

        with app.test_request_context(headers={"Authorization": f"Bearer {token}"}), app.app_context():
            synced = _sync_lapis_service_modules(
                {
                    "metadata": {"apiName": "portal"},
                    "auth": {},
                    "models": {},
                    "endpoints": {},
                    "modules": [{"name": module_name, "config": {"greeting": "hello"}}],
                },
                app.auth_sessions[token],
            )

            module = load_module_record(module_name, include_source=False, app_config=app.config)

        self.assertEqual(synced["modules"][0]["name"], module_name)
        self.assertIn("portal", module["assigned_domains"])


if __name__ == "__main__":
    unittest.main()
