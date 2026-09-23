# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import os
import shutil
import socket
import sys
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.dry_run_validation import _summarize_vdb_action, validate_generated_service_dry_run
from app.validation_sandbox import _BCRYPT_HASH_RE, _generate_password_hash


VDB_JAR = REPO_ROOT / "verun" / "vdb" / "target" / "vdb-1.0.0-jar-with-dependencies.jar"
VI_JAR = REPO_ROOT / "verun" / "vi" / "target" / "vi-1.0.0-jar-with-dependencies.jar"


def _local_tcp_bind_available():
    """Return whether this environment permits ephemeral localhost listeners."""
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        return False
    try:
        probe.bind(("127.0.0.1", 0))
        return True
    except OSError:
        return False
    finally:
        probe.close()


LOCAL_TCP_BIND_AVAILABLE = _local_tcp_bind_available()


@unittest.skipUnless(VDB_JAR.is_file(), f"VDB runtime jar missing at {VDB_JAR}")
@unittest.skipUnless(shutil.which("java"), "java is required for validation sandbox auth seeding")
class DryRunValidationTests(unittest.TestCase):
    def test_flat_vdb_actions_have_stable_dry_run_summaries(self):
        self.assertEqual(_summarize_vdb_action({"action": "domain_status", "domain": "engineering"}), ("domain_status", "engineering"))
        self.assertEqual(_summarize_vdb_action({"action": "find", "collection": "users"}), ("find", "users"))

    def _base_config(self):
        return {
            "metadata": {
                "apiName": "DryRunService",
                "basePath": "/api/dry-run",
                "version": "1.0.0",
                "database": "main",
                "rateLimiting": {"enabled": False, "limit": 10, "timeframe": "minute"},
            },
            "auth": {
                "enabled": False,
                "isAuthService": False,
                "keyManagement": "auto",
                "customEndpoints": {"enabled": False, "signIn": "/auth/signin", "signUp": "/auth/signup"},
            },
            "models": {},
            "endpoints": {},
        }

    def test_sandbox_auth_hash_uses_the_vdb_bcrypt_runtime(self):
        password_hash = _generate_password_hash("LiwiroVDBAppPass0!")

        self.assertIsNotNone(_BCRYPT_HASH_RE.fullmatch(password_hash))

    @unittest.skipUnless(LOCAL_TCP_BIND_AVAILABLE, "local TCP binding is unavailable in this environment")
    def test_dry_run_executes_startup_mutations_inside_isolated_sandbox(self):
        cfg = self._base_config()
        cfg["models"] = {
            "notes": {
                "name": "Note",
                "collection": "notes",
                "fields": {
                    "title": {"id": "title", "name": "title", "type": "string", "required": True},
                },
            }
        }
        cfg["endpoints"] = {
            "listNotes": {
                "method": "GET",
                "path": "/notes",
                "operationType": "crud",
                "crudOperation": "read",
                "linkedModel": "Note",
            }
        }

        result = validate_generated_service_dry_run(cfg)

        self.assertTrue(result["ok"], result.get("errors"))
        self.assertTrue(result["vdbAuth"]["ok"], result["vdbAuth"])
        self.assertTrue(any(event.get("action") == "define_domain" for event in result["startupEvents"]))
        self.assertTrue(any(event.get("action") == "create_collection" for event in result["startupEvents"]))
        self.assertTrue(all(not bool(event.get("blocked")) for event in result["startupEvents"]))
        sandbox = result.get("sandbox") or {}
        self.assertTrue(str(sandbox.get("sandboxId") or "").strip())
        self.assertTrue(str(sandbox.get("summaryPath") or "").strip())
        self.assertTrue(Path(str(sandbox["logsPath"])).is_dir())
        self.assertFalse((Path(str(sandbox["logsPath"])) / "runtime-root").exists())

    @unittest.skipUnless(LOCAL_TCP_BIND_AVAILABLE, "local TCP binding is unavailable in this environment")
    def test_dry_run_executes_mutating_custom_vql_in_sandbox_instead_of_skipping(self):
        cfg = self._base_config()
        cfg["models"] = {
            "notes": {
                "name": "Note",
                "collection": "notes",
                "fields": {
                    "title": {"id": "title", "name": "title", "type": "string", "required": True},
                },
            }
        }
        cfg["endpoints"] = {
            "createViaCustomVql": {
                "method": "POST",
                "path": "/notes/custom-create",
                "operationType": "custom",
                "vqlQuery": 'insert notes data title="seeded from validation sandbox"',
            }
        }

        result = validate_generated_service_dry_run(cfg)

        self.assertTrue(result["ok"], result.get("errors"))
        endpoint = next(item for item in result["endpointResults"] if item["endpointId"] == "createViaCustomVql")
        self.assertNotIn("skip", endpoint)
        self.assertTrue(endpoint["ok"], endpoint)

    @unittest.skipUnless(LOCAL_TCP_BIND_AVAILABLE, "local TCP binding is unavailable in this environment")
    @unittest.skipUnless(VI_JAR.is_file(), f"VI runtime jar missing at {VI_JAR}")
    def test_dry_run_mocks_external_http_calls_but_keeps_route_validation_green(self):
        cfg = self._base_config()
        cfg["endpoints"] = {
            "notify": {
                "method": "POST",
                "path": "/notify",
                "operationType": "script",
                "versaScript": (
                    "let res = http.post(\"https://example.com/webhook\", {body: {ok: true}});\n"
                    "return { ok: res.ok, mocked: res.mocked, statusCode: res.status };"
                ),
            }
        }

        result = validate_generated_service_dry_run(cfg)

        self.assertTrue(result["ok"], result.get("errors"))
        endpoint = next(item for item in result["endpointResults"] if item["endpointId"] == "notify")
        self.assertTrue(endpoint["ok"], endpoint)
        self.assertTrue(any(mock.get("kind") == "http" for mock in result["externalMocks"]), result["externalMocks"])
