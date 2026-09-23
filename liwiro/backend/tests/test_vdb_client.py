# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.vdb import VDBClient
from app.vdb_commands import command_text
from app.vdb_transport import VDBTransportRequestError


class _FakeApp:
    def __init__(self):
        self.logger = logging.getLogger("vdb-test")
        self.config = {
            "VDB_SERVER_URL": "http://127.0.0.1:1957",
            "VDB_USERNAME": "ver",
            "VDB_PASSWORD": "pass",
            "LIWIRO_DOMAIN": "liwiro",
            "LIWIRO_DB": "main",
        }


class VDBClientTests(unittest.TestCase):
    def test_define_domain_with_database_serializes_to_atomic_native_command(self):
        self.assertEqual(
            command_text({"action": "define", "domain": "AuthCoreService", "db": "main"}),
            'create domain AuthCoreService = { database: "main" }',
        )

    def test_execute_vql_query_rejects_legacy_nested_operation_before_transport(self):
        transport = MagicMock()
        transport.auth.return_value = {"sessionId": "sid"}
        client = VDBClient(_FakeApp(), transport=transport)
        client.session_id = "sid"

        ok, data = client.execute_vql_query({"action": "find", "collection": "users", "script": {"read": "x"}})

        self.assertFalse(ok)
        self.assertIn("Nested internal VDB operation objects", data["error"])
        transport.vql.assert_not_called()

    def test_warning_response_is_treated_as_non_fatal(self):
        transport = MagicMock()
        transport.auth.return_value = {"sessionId": "sid"}
        transport.vql.return_value = {"status": "warning", "message": "already exists"}
        client = VDBClient(_FakeApp(), transport=transport)
        client.session_id = "sid"
        ok, data = client.execute_vql_query({"action": "define", "resource": "domain", "name": "liwiro"})

        self.assertTrue(ok)
        self.assertIsInstance(data, dict)

    def test_transport_error_includes_server_detail(self):
        transport = MagicMock()
        transport.auth.return_value = {"sessionId": "sid"}
        transport.vql.side_effect = VDBTransportRequestError(
            401,
            "401",
            payload={"status": "error", "message": "bad credentials"},
            raw_body='{"status":"error","message":"bad credentials"}',
        )
        client = VDBClient(_FakeApp(), transport=transport)
        client.session_id = "sid"
        ok, data = client.execute_vql_query({"action": "list", "resource": "domains"})

        self.assertFalse(ok)
        self.assertIn("server:", data["error"])

    def test_ensure_workspace_retries_define_when_existing_domain_is_unusable(self):
        transport = MagicMock()
        transport.auth.return_value = {"sessionId": "sid"}
        client = VDBClient(_FakeApp(), transport=transport)
        client.list_domains = MagicMock(return_value=(True, ["authcoreservice"]))
        client.define_domain = MagicMock(return_value=(True, {}))
        client.use_domain = MagicMock(side_effect=[False, True])
        client.list_databases = MagicMock(return_value=(True, ["main"]))
        client.define_database = MagicMock(return_value=(True, {}))
        client.use_database = MagicMock(return_value=True)

        ok = client.ensure_workspace("authcoreservice", "main")

        self.assertTrue(ok)
        client.define_domain.assert_called_once_with("authcoreservice", "main")
        self.assertEqual(client.use_domain.call_count, 2)
        client.define_database.assert_not_called()

    def test_ensure_workspace_creates_missing_domain_with_requested_database(self):
        transport = MagicMock()
        transport.auth.return_value = {"sessionId": "sid"}
        client = VDBClient(_FakeApp(), transport=transport)
        client.list_domains = MagicMock(return_value=(True, []))
        client.define_domain = MagicMock(return_value=(True, {}))
        client.use_domain = MagicMock(return_value=True)
        client.list_databases = MagicMock(return_value=(True, ["main"]))
        client.use_database = MagicMock(return_value=True)

        self.assertTrue(client.ensure_workspace("AuthCoreService", "main"))
        client.define_domain.assert_called_once_with("AuthCoreService", "main")

    def test_ensure_workspace_repairs_stale_current_database_before_listing_domains(self):
        transport = MagicMock()
        transport.auth.return_value = {"sessionId": "sid"}
        client = VDBClient(_FakeApp(), transport=transport)
        client.list_domains = MagicMock(side_effect=[
            (False, {"error": "Server error: Database does not exist in domain authcoreservice: config"}),
            (False, {"error": "Server error: Database does not exist in domain authcoreservice: config"}),
            (True, ["authcoreservice"]),
        ])
        client.authenticate = MagicMock(return_value=True)
        client.define_domain = MagicMock(return_value=(True, {}))
        client.use_domain = MagicMock(return_value=True)
        client.list_databases = MagicMock(return_value=(True, ["main"]))
        client.use_database = MagicMock(return_value=True)

        self.assertTrue(client.ensure_workspace("AuthCoreService", "main"))
        client.authenticate.assert_called_once_with()
        client.define_domain.assert_called_once_with("AuthCoreService", "main")
        self.assertEqual(client.list_domains.call_count, 3)

    def test_ensure_workspace_recovers_when_a_fresh_session_clears_stale_context(self):
        transport = MagicMock()
        transport.auth.return_value = {"sessionId": "sid"}
        client = VDBClient(_FakeApp(), transport=transport)
        client.list_domains = MagicMock(side_effect=[
            (False, {"error": "Server error: Database does not exist in domain authcoreservice: config"}),
            (True, ["authcoreservice"]),
        ])
        client.authenticate = MagicMock(return_value=True)
        client.define_domain = MagicMock(return_value=(True, {}))
        client.use_domain = MagicMock(return_value=True)
        client.list_databases = MagicMock(return_value=(True, ["main"]))
        client.use_database = MagicMock(return_value=True)

        self.assertTrue(client.ensure_workspace("AuthCoreService", "main"))
        client.authenticate.assert_called_once_with()
        client.define_domain.assert_not_called()

    def test_ensure_workspace_does_not_mask_unrelated_domain_listing_failures(self):
        transport = MagicMock()
        transport.auth.return_value = {"sessionId": "sid"}
        client = VDBClient(_FakeApp(), transport=transport)
        client.list_domains = MagicMock(return_value=(False, {"error": "VDB communication failed"}))
        client.define_domain = MagicMock(return_value=(True, {}))

        self.assertFalse(client.ensure_workspace("AuthCoreService", "main"))
        self.assertIn("Unable to list VDB domains", client.workspace_error)
        client.define_domain.assert_not_called()

    def test_ensure_workspace_accepts_named_domain_and_database_rows(self):
        transport = MagicMock()
        transport.auth.return_value = {"sessionId": "sid"}
        client = VDBClient(_FakeApp(), transport=transport)
        client.list_domains = MagicMock(return_value=(True, [{"name": "AuthCoreService"}]))
        client.define_domain = MagicMock(return_value=(True, {}))
        client.use_domain = MagicMock(return_value=True)
        client.list_databases = MagicMock(return_value=(True, [{"name": "MAIN"}]))
        client.define_database = MagicMock(return_value=(True, {}))
        client.use_database = MagicMock(return_value=True)

        self.assertTrue(client.ensure_workspace("authcoreservice", "main"))
        client.define_domain.assert_not_called()
        client.define_database.assert_not_called()

    def test_ensure_workspace_accepts_nested_transport_envelopes(self):
        transport = MagicMock()
        transport.auth.return_value = {"sessionId": "sid"}
        client = VDBClient(_FakeApp(), transport=transport)
        client.list_domains = MagicMock(return_value=(True, {"data": {"domains": [{"name": "AuthCoreService"}]}}))
        client.define_domain = MagicMock(return_value=(True, {}))
        client.use_domain = MagicMock(return_value=True)
        client.list_databases = MagicMock(return_value=(True, {"data": {"databases": [{"name": "main"}]}}))
        client.define_database = MagicMock(return_value=(True, {}))
        client.use_database = MagicMock(return_value=True)

        self.assertTrue(client.ensure_workspace("authcoreservice", "main"))
        client.define_domain.assert_not_called()
        client.define_database.assert_not_called()

    def test_ensure_workspace_repairs_stale_database_context(self):
        transport = MagicMock()
        transport.auth.return_value = {"sessionId": "sid"}
        client = VDBClient(_FakeApp(), transport=transport)
        client.list_domains = MagicMock(return_value=(True, ["authcoreservice"]))
        client.use_domain = MagicMock(return_value=True)
        client.list_databases = MagicMock(return_value=(False, {"error": "stale database"}))
        client.define_database = MagicMock(return_value=(True, {}))
        client.use_database = MagicMock(return_value=True)

        self.assertTrue(client.ensure_workspace("authcoreservice", "main"))
        client.define_database.assert_called_once_with("main")
        client.use_database.assert_called_once_with("main")

    def test_define_domain_with_database_uses_repairable_structured_operation(self):
        transport = MagicMock()
        transport.auth.return_value = {"sessionId": "sid"}
        transport.vql.return_value = {"status": "success", "data": {}}
        client = VDBClient(_FakeApp(), transport=transport)

        ok, _ = client.define_domain("AuthCoreService", "main")

        self.assertTrue(ok)
        self.assertEqual(transport.vql.call_args.args[1], {"action": "define", "domain": "AuthCoreService", "db": "main"})

    def test_create_collection_orders_defaults_before_annotations(self):
        transport = MagicMock()
        transport.auth.return_value = {"sessionId": "sid"}
        transport.vql.return_value = {"status": "success", "data": {}}
        client = VDBClient(_FakeApp(), transport=transport)
        client.list_collections = MagicMock(return_value=(True, []))

        ok, _ = client.create_collection(
            "auth_users",
            {
                "profile": {
                    "type": "object",
                    "properties": {"fullName": {"type": "string"}},
                }
                ,"role": {"type": "string", "default": "USER", "required": True}
            },
        )

        self.assertTrue(ok)
        command = transport.vql.call_args.args[1]
        self.assertIn("create collection auth_users =", command)
        self.assertIn("profile: object", command)
        self.assertIn('role: string = "USER" @required', command)


if __name__ == "__main__":
    unittest.main()
