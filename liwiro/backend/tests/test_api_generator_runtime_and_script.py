# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import os
import sys
import unittest
import json
import hashlib
import subprocess
import tempfile
from glob import glob
from pathlib import Path
from unittest.mock import patch
from werkzeug.security import generate_password_hash


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from generators.api_generator import (
    _normalize_vi_script_route_body,
    _strip_vi_import_lines,
    generate_api_service,
)


class _FakeVDBClient:
    def __init__(self):
        self.created_scripts = []
        self.executed_scripts = []
        self.created_indexes = []
        self.workspaces = []
        self._collections = {}

    def create_script(self, name, service, code):
        self.created_scripts.append((name, service, code))
        return True, {"message": "created"}

    def execute_script(self, name, params):
        self.executed_scripts.append((name, params))
        return True, {"name": name, "params": params}

    def execute_vql_query(self, query_obj):
        return True, {"echo": query_obj}

    def create_index(self, collection_name, field_name, unique=False, sparse=False):
        self.created_indexes.append((collection_name, field_name, unique, sparse))
        return True, {"message": "indexed"}

    def ensure_workspace(self, domain_name, db_name):
        self.workspaces.append((domain_name, db_name))
        return True

    def read_documents(self, collection_name, query):
        docs = list(self._collections.get(collection_name, []))
        if not isinstance(query, dict) or not query:
            return True, docs
        filtered = []
        for doc in docs:
            keep = True
            for field, cond in query.items():
                if isinstance(cond, dict) and "$eq" in cond:
                    if doc.get(field) != cond.get("$eq"):
                        keep = False
                        break
                elif doc.get(field) != cond:
                    keep = False
                    break
            if keep:
                filtered.append(doc)
        return True, filtered

    def create_document(self, collection_name, document):
        docs = self._collections.setdefault(collection_name, [])
        docs.append(dict(document or {}))
        return True, {"created": 1}

    def update_document(self, collection_name, query, updates):
        docs = self._collections.get(collection_name, [])
        for idx, doc in enumerate(docs):
            matches = True
            for field, cond in (query or {}).items():
                if isinstance(cond, dict) and "$eq" in cond:
                    if doc.get(field) != cond.get("$eq"):
                        matches = False
                        break
                elif doc.get(field) != cond:
                    matches = False
                    break
            if not matches:
                continue
            merged = dict(doc)
            merged.update(dict(updates or {}))
            docs[idx] = merged
            return True, {"updated": 1}
        return True, {"updated": 0}


class _FakeDomainManager:
    instances = []

    def __init__(self, app):
        self.app = app
        self.vdb_client = _FakeVDBClient()
        self._collections = {}
        self._schemas = {}
        _FakeDomainManager.instances.append(self)

    def ensure_workspace(self, domain_name, db_name):
        return True

    def create_collection(self, collection_name, schema):
        self._schemas[collection_name] = dict(schema or {})
        return True, {}

    def create_document(self, model_name, data):
        docs = self._collections.setdefault(model_name, [])
        docs.append(dict(data or {}))
        return True, {}

    def read_documents(self, model_name, query):
        docs = list(self._collections.get(model_name, []))
        if not isinstance(query, dict) or not query:
            return True, docs
        filtered = []
        for doc in docs:
            keep = True
            for field, cond in query.items():
                if isinstance(cond, dict) and "$eq" in cond:
                    if doc.get(field) != cond.get("$eq"):
                        keep = False
                        break
                elif doc.get(field) != cond:
                    keep = False
                    break
            if keep:
                filtered.append(doc)
        return True, filtered

    def update_document(self, model_name, query, data):
        docs = self._collections.get(model_name, [])
        updates = dict(data or {})
        for idx, doc in enumerate(docs):
            matches = True
            for field, cond in (query or {}).items():
                if isinstance(cond, dict) and "$eq" in cond:
                    if doc.get(field) != cond.get("$eq"):
                        matches = False
                        break
                elif doc.get(field) != cond:
                    matches = False
                    break
            if not matches:
                continue
            merged = dict(doc)
            merged.update(updates)
            docs[idx] = merged
            return True, {"updated": 1}
        return True, {"updated": 0}

    def delete_document(self, model_name, query):
        docs = self._collections.get(model_name, [])
        for idx, doc in enumerate(list(docs)):
            matches = True
            for field, cond in (query or {}).items():
                if isinstance(cond, dict) and "$eq" in cond:
                    if doc.get(field) != cond.get("$eq"):
                        matches = False
                        break
                elif doc.get(field) != cond:
                    matches = False
                    break
            if not matches:
                continue
            docs.pop(idx)
            return True, {"deleted": 1}
        return True, {"deleted": 0}


class _FailingDomainManager(_FakeDomainManager):
    def ensure_workspace(self, domain_name, db_name):
        self.vdb_client.workspace_error = f"Unable to list VDB domains for {domain_name}"
        return False


class ApiGeneratorTests(unittest.TestCase):
    @patch("models.domain.DomainManager", _FailingDomainManager)
    def test_generation_fails_fast_when_service_workspace_cannot_be_prepared(self):
        with self.assertRaisesRegex(
            RuntimeError,
            r"Failed to prepare VDB workspace .*Unable to list VDB domains",
        ):
            generate_api_service(self._lapis_cfg())

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_generated_service_json_provider_serializes_binary_vdb_values(self):
        app = generate_api_service(self._lapis_cfg())
        with app.app_context():
            encoded = app.json.dumps({"text": b"hello", "binary": b"\xff\x00"})
        payload = json.loads(encoded)
        self.assertEqual(payload["text"], "hello")
        self.assertEqual(payload["binary"], {"$binary": "/wA="})

    def setUp(self):
        _FakeDomainManager.instances.clear()

    def _assert_vi_route_body_parses(self, route_body):
        # The backend lives under the inner `liwiro/` package directory while
        # Verun is a sibling of that directory at the workspace root.
        jar_path = BACKEND_ROOT.parent.parent / "verun" / "vi" / "target" / "vi-1.0.0-jar-with-dependencies.jar"
        if not jar_path.is_file():
            self.skipTest(f"VI runtime jar missing at {jar_path}")

        indented = "\n".join(f"  {line}" if line else "" for line in str(route_body or "").splitlines())
        wrapper = (
            "json_xml import *;\n"
            "vdb import *;\n"
            "http import *;\n"
            "email import *;\n"
            "crypto import *;\n"
            "jwt import *;\n"
            "time import *;\n"
            "datetime import *;\n"
            "\n"
            "func __probe(params) {\n"
            f"{indented}\n"
            "}\n"
            "print(\"OK\");\n"
        )

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".versa", delete=False, encoding="utf-8") as handle:
                tmp_path = handle.name
                handle.write(wrapper)
            proc = subprocess.run(
                ["java", "-cp", str(jar_path), "verun.runtime.Main", tmp_path, "--msg-only"],
                cwd=str(BACKEND_ROOT.parent),
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            self.assertEqual(
                proc.returncode,
                0,
                msg=f"VI parser rejected wrapper:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}\nBODY:\n{route_body}",
            )
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    def _lapis_cfg(self):
        return {
            "metadata": {"apiName": "orders", "basePath": "/api/v1", "version": "1.0.0", "database": "main"},
            "models": {
                "m1": {
                    "name": "Order",
                    "collection": "orders",
                    "fields": {"f1": {"name": "sku", "type": "string", "required": True}},
                }
            },
            "endpoints": {
                "script_ep": {
                    "method": "POST",
                    "path": "/run-script",
                    "operationType": "script",
                    "versaScript": "print('ok')",
                }
            },
        }

    def _crud_cfg(self):
        return {
            "metadata": {"apiName": "authcrud", "basePath": "/api/v1", "version": "1.0.0", "database": "main"},
            "models": {
                "m1": {
                    "name": "User",
                    "collection": "users",
                    "fields": {"f1": {"name": "username", "type": "string", "required": True}},
                }
            },
            "endpoints": {
                "read_users": {
                    "method": "GET",
                    "path": "/users",
                    "operationType": "crud",
                    "crudOperation": "read",
                    "linkedModel": "User",
                },
                "update_users": {
                    "method": "PUT",
                    "path": "/users",
                    "operationType": "crud",
                    "crudOperation": "update",
                    "linkedModel": "User",
                },
                "delete_users": {
                    "method": "DELETE",
                    "path": "/users",
                    "operationType": "crud",
                    "crudOperation": "delete",
                    "linkedModel": "User",
                },
            },
        }

    def _custom_vql_cfg(self):
        return {
            "metadata": {"apiName": "customvql", "basePath": "/api/v1", "version": "1.0.0", "database": "main"},
            "models": {},
            "endpoints": {
                "custom_query": {
                    "method": "POST",
                    "path": "/query",
                    "operationType": "custom",
                    "vqlQuery": 'read collection users where status={"$eq":"OPEN"} limit 25',
                }
            },
        }

    def _auth_service_cfg(self):
        return {
            "metadata": {
                "apiName": "AuthCoreService",
                "basePath": "/api/auth",
                "version": "1.0.0",
                "database": "main",
                "documentation": {"enabled": True, "key": "docs-secret"},
            },
            "auth": {
                "enabled": True,
                "isAuthService": True,
                "authModel": "AuthUser",
                "customEndpoints": {
                    "enabled": True,
                    "signIn": "/signin",
                    "signOut": "/signout",
                    "register": "/register",
                    "resetPassword": "/reset-password",
                },
                "passwordResetPage": {
                    "enabled": True,
                    "title": "Reset Your AuthCoreService Password",
                    "description": "Paste the reset token and choose a replacement password.",
                    "submitLabel": "Complete Reset",
                    "loadingMessage": "Resetting password...",
                    "successMessage": "Password reset completed.",
                    "failureMessage": "Password reset failed.",
                },
                "defaultSuperAdmin": {
                    "enabled": False,
                    "username": "jelita.mulenga",
                    "email": "jelita.mulenga@zmail.com",
                    "password": "SystemRoot#ZM1969",
                    "role": "SUPER_ADMIN",
                },
            },
            "models": {
                "m_auth_user": {
                    "name": "AuthUser",
                    "collection": "auth_users",
                    "fields": {"f1": {"name": "username", "type": "string", "required": True}},
                }
            },
            "endpoints": {},
        }

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_runtime_env_overrides_service_config(self):
        with patch.dict(
            os.environ,
            {
                "VDB_TRANSPORT": "namedpipe",
                "VDB_SERVER_URL": "http://127.0.0.1:9999",
                "VDB_UNIX_SOCKET_PATH": "/tmp/runtime-vdb.sock",
                "VDB_NAMED_PIPE_PATH": r"\\.\pipe\runtime_vdb",
                "VDB_USERNAME": "runtime-user",
                "VDB_PASSWORD": "runtime-pass",
                "LIWIRO_DOMAIN": "runtime-domain",
                "LIWIRO_DB": "runtime-db",
            },
            clear=False,
        ):
            app = generate_api_service(self._lapis_cfg())

        self.assertEqual(app.config["VDB_TRANSPORT"], "namedpipe")
        self.assertEqual(app.config["VDB_SERVER_URL"], "http://127.0.0.1:9999")
        self.assertEqual(app.config["VDB_UNIX_SOCKET_PATH"], "/tmp/runtime-vdb.sock")
        self.assertEqual(app.config["VDB_NAMED_PIPE_PATH"], r"\\.\pipe\runtime_vdb")
        self.assertEqual(app.config["VDB_USERNAME"], "runtime-user")
        self.assertEqual(app.config["VDB_PASSWORD"], "runtime-pass")
        self.assertEqual(app.config["LIWIRO_DOMAIN"], "runtime-domain")
        self.assertEqual(app.config["LIWIRO_DB"], "runtime-db")

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_rate_limiting_returns_retry_after_after_limit(self):
        cfg = self._lapis_cfg()
        cfg["metadata"]["rateLimiting"] = {"enabled": True, "limit": 1, "timeframe": "minute"}
        app = generate_api_service(cfg)
        client = app.test_client()
        first = client.post("/api/v1/run-script", json={})
        second = client.post("/api/v1/run-script", json={})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertTrue(second.headers.get("Retry-After"))

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_script_endpoint_merges_query_and_body_params(self):
        app = generate_api_service(self._lapis_cfg())
        client = app.test_client()

        res = client.post("/api/v1/run-script?collection=orders&tenant=blue", json={"limit": 2})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        params = data["params"]

        self.assertEqual(params["collection"], "orders")
        self.assertEqual(params["tenant"], "blue")
        self.assertEqual(params["limit"], 2)
        self.assertEqual(params["query"], {"collection": "orders", "tenant": "blue"})
        self.assertEqual(params["body"], {"limit": 2})
        self.assertIn("__request", params)
        self.assertEqual(params["__request"]["method"], "POST")

        mgr = _FakeDomainManager.instances[0]
        self.assertEqual(len(mgr.vdb_client.created_scripts), 1)
        self.assertEqual(len(mgr.vdb_client.executed_scripts), 1)

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_script_endpoint_exposes_bearer_token_aliases(self):
        app = generate_api_service(self._lapis_cfg())
        client = app.test_client()

        res = client.post(
            "/api/v1/run-script?collection=orders",
            json={"limit": 2},
            headers={"Authorization": "Bearer demo-token"},
        )
        self.assertEqual(res.status_code, 200)
        params = (res.get_json() or {}).get("params", {})

        self.assertEqual(params["bearerToken"], "demo-token")
        self.assertEqual(params["authToken"], "demo-token")
        self.assertEqual(params["token"], "demo-token")

    @patch("models.domain.DomainManager", _FakeDomainManager)
    @patch("generators.api_generator._execute_vi_script")
    def test_auth_script_receives_same_jwt_secret_as_bearer_verifier(self, execute_script):
        cfg = self._auth_service_cfg()
        cfg["metadata"]["setupApiKey"] = "auth-runtime-secret"
        cfg["endpoints"] = {
            "ep_signin": {
                "method": "POST",
                "path": "/signin",
                "operationType": "script",
                "versaScript": "return {authenticated: true, token: jwt.sign({purpose: 'access'}, req.jwtSecret)};",
            }
        }
        execute_script.return_value = (True, {"authenticated": True, "token": "signed-token"})

        app = generate_api_service(cfg)
        response = app.test_client().post("/api/auth/signin", json={"username": "u", "password": "p"})

        self.assertEqual(response.status_code, 200)
        runtime_params = execute_script.call_args.args[1]
        self.assertEqual(runtime_params.get("jwtSecret"), "auth-runtime-secret")

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_script_endpoint_accepts_structured_query_json(self):
        app = generate_api_service(self._lapis_cfg())
        client = app.test_client()

        res = client.post(
            '/api/v1/run-script?__query={"status":{"$eq":"OPEN"},"page":1}',
            json={"limit": 2},
        )
        self.assertEqual(res.status_code, 200)
        params = (res.get_json() or {}).get("params", {})

        self.assertEqual(params["query"], {"status": {"$eq": "OPEN"}, "page": 1})
        self.assertEqual(params["status"], {"$eq": "OPEN"})
        self.assertEqual(params["page"], 1)

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_script_endpoint_exposes_custom_service_env_values(self):
        cfg = self._lapis_cfg()
        cfg["metadata"]["env"] = {
            "CLOUDINARY_CLOUD_NAME": "replace-with-cloudinary-cloud-name",
            "CLOUDINARY_API_KEY": "replace-with-cloudinary-api-key",
        }

        app = generate_api_service(cfg)
        client = app.test_client()
        res = client.post("/api/v1/run-script", json={})

        self.assertEqual(res.status_code, 200)
        runtime_env = ((((res.get_json() or {}).get("params") or {}).get("service") or {}).get("env") or {})
        self.assertEqual(runtime_env.get("CLOUDINARY_CLOUD_NAME"), "replace-with-cloudinary-cloud-name")
        self.assertEqual(runtime_env.get("CLOUDINARY_API_KEY"), "replace-with-cloudinary-api-key")

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_custom_vql_endpoint_merges_request_query_and_body(self):
        app = generate_api_service(self._custom_vql_cfg())
        client = app.test_client()

        res = client.post(
            "/api/v1/query?severity=high&limit=10",
            json={"query": {"tenant": {"$eq": "acme"}}, "args": {"page": 2}},
        )
        self.assertEqual(res.status_code, 200)
        echo = (res.get_json() or {}).get("echo", {})
        from app.vdb_commands import parse_command
        echo = parse_command(echo)

        self.assertEqual(echo.get("action"), "find")
        self.assertEqual(echo.get("collection"), "users")
        self.assertEqual(
            echo.get("where"),
            {
                "status": "OPEN",
                "severity": "high",
                "tenant": "acme",
            },
        )
        self.assertEqual(echo.get("limit"), 10)
        self.assertEqual(echo.get("page"), 2)

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_custom_vql_endpoint_rejects_json_command_at_runtime(self):
        cfg = self._custom_vql_cfg()
        cfg["endpoints"]["custom_query"]["vqlQuery"] = (
            "{action: 'find', collection: 'users', where: {status: {$eq: 'OPEN'}}, limit: 25,}"
        )
        app = generate_api_service(cfg)
        client = app.test_client()

        res = client.post("/api/v1/query")
        self.assertEqual(res.status_code, 400)
        self.assertIn("readable VDB command", (res.get_json() or {}).get("error", ""))

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_custom_vql_endpoint_rejects_json_object(self):
        cfg = self._custom_vql_cfg()
        cfg["endpoints"]["custom_query"]["vqlQuery"] = '{"collection":"users","where":{}}'
        app = generate_api_service(cfg)
        response = app.test_client().post("/api/v1/query")
        self.assertEqual(response.status_code, 400)
        self.assertIn("readable VDB command", (response.get_json() or {}).get("error", ""))

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_custom_vql_endpoint_rejects_nested_request_override(self):
        app = generate_api_service(self._custom_vql_cfg())
        response = app.test_client().post(
            "/api/v1/query",
            json={"read": {"users": {"query": {"status": "OPEN"}}}},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("cannot override", (response.get_json() or {}).get("error", ""))

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_custom_vql_endpoint_rejects_nested_key_with_flat_action(self):
        cfg = self._custom_vql_cfg()
        cfg["endpoints"]["custom_query"]["vqlQuery"] = (
            '{"action":"find","collection":"users","read":{"users":{}}}'
        )
        app = generate_api_service(cfg)
        response = app.test_client().post("/api/v1/query")
        self.assertEqual(response.status_code, 400)
        self.assertIn("readable VDB command", (response.get_json() or {}).get("error", ""))

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_crud_routes_parse_json_query_values(self):
        app = generate_api_service(self._crud_cfg())
        client = app.test_client()
        mgr = _FakeDomainManager.instances[0]
        mgr._collections["users"] = [
            {"username": "alpha.user", "active": True, "role": "VIEWER"},
            {"username": "beta.user", "active": False, "role": "VIEWER"},
        ]

        read_res = client.get(
            "/api/v1/users",
            query_string={"username": json.dumps({"$eq": "alpha.user"}), "active": "true"},
        )
        self.assertEqual(read_res.status_code, 200)
        self.assertEqual(read_res.get_json(), [{"username": "alpha.user", "active": True, "role": "VIEWER"}])

        update_res = client.put(
            "/api/v1/users",
            query_string={"username": json.dumps({"$eq": "alpha.user"})},
            json={"role": "ADMIN"},
        )
        self.assertEqual(update_res.status_code, 200)
        ok, rows = mgr.read_documents("users", {"username": {"$eq": "alpha.user"}})
        self.assertTrue(ok)
        self.assertEqual((rows or [])[0].get("role"), "ADMIN")

        delete_res = client.delete(
            "/api/v1/users",
            query_string={"active": "false"},
        )
        self.assertEqual(delete_res.status_code, 200)
        ok, rows = mgr.read_documents("users", {})
        self.assertTrue(ok)
        self.assertEqual(rows, [{"username": "alpha.user", "active": True, "role": "ADMIN"}])

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_crud_update_and_delete_return_404_when_no_rows_match(self):
        app = generate_api_service(self._crud_cfg())
        client = app.test_client()

        update_res = client.put("/api/v1/users?username=missing.user", json={"role": "USER"})
        self.assertEqual(update_res.status_code, 404)
        self.assertTrue((update_res.get_json() or {}).get("notFound"))

        delete_res = client.delete("/api/v1/users?username=missing.user")
        self.assertEqual(delete_res.status_code, 404)
        self.assertTrue((delete_res.get_json() or {}).get("notFound"))

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_script_endpoint_injects_required_module_imports(self):
        app = generate_api_service(self._lapis_cfg())
        client = app.test_client()

        res = client.post("/api/v1/run-script", json={"k": "v"})
        self.assertEqual(res.status_code, 200)

        mgr = _FakeDomainManager.instances[0]
        self.assertEqual(len(mgr.vdb_client.created_scripts), 1)
        code = mgr.vdb_client.created_scripts[0][2]
        self.assertIn("time import *;", code)
        self.assertIn("jwt import *;", code)
        self.assertIn("crypto import *;", code)
        self.assertIn("email import *;", code)

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_script_endpoint_keeps_existing_module_import_without_duplication(self):
        cfg = self._lapis_cfg()
        cfg["endpoints"]["script_ep"]["versaScript"] = "time import *;\nprint(time.time());"

        app = generate_api_service(cfg)
        client = app.test_client()
        res = client.post("/api/v1/run-script", json={})
        self.assertEqual(res.status_code, 200)

        mgr = _FakeDomainManager.instances[0]
        code = mgr.vdb_client.created_scripts[0][2]
        self.assertEqual([line.strip() for line in code.splitlines()].count("time import *;"), 1)

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_all_lapis_examples_script_endpoints_include_required_imports(self):
        examples = sorted(glob(str(BACKEND_ROOT.parent / "data" / "lapis-examples" / "*.json")))
        self.assertGreater(len(examples), 0)

        required = ("json_xml import *;", "vdb import *;", "http import *;", "email import *;", "crypto import *;", "jwt import *;", "time import *;", "datetime import *;")

        for path in examples:
            with self.subTest(example=Path(path).name):
                _FakeDomainManager.instances.clear()
                with open(path, "r", encoding="utf-8") as handle:
                    cfg = json.load(handle)
                generate_api_service(cfg)
                mgr = _FakeDomainManager.instances[0]
                for _, _, code in mgr.vdb_client.created_scripts:
                    for needed in required:
                        self.assertIn(needed, code)

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_auth_docs_payload_includes_endpoint_documentation_and_admin_register_example(self):
        app = generate_api_service(self._auth_service_cfg())
        client = app.test_client()

        res = client.get("/liwiro/docs.json", headers={"X-Documentation-Key": "docs-secret"})
        self.assertEqual(res.status_code, 200)
        payload = res.get_json() or {}
        endpoints = payload.get("endpoints") or []

        register = next((item for item in endpoints if item.get("id") == "ep_auth_register_auto"), None)
        self.assertIsNotNone(register)
        self.assertEqual((((register or {}).get("exampleParams") or {}).get("body") or {}).get("role"), "ADMIN")
        self.assertTrue(str((((register or {}).get("documentation") or {}).get("summary") or "")).strip())

    @patch("models.domain.DomainManager", _FakeDomainManager)
    @patch("generators.api_generator.requests.post")
    def test_authenticate_resolves_auth_service_by_lapis_metadata_name(self, request_post):
        cfg = self._lapis_cfg()
        cfg["metadata"]["apiName"] = "ConsumerService"
        cfg["auth"] = {
            "enabled": True,
            "isAuthService": False,
            "useAsymmetricJWT": True,
            "authServiceName": "AuthCoreService",
        }
        cfg["endpoints"]["protected"] = {
            "method": "GET",
            "path": "/protected",
            "operationType": "script",
            "requiresAuth": True,
            "versaScript": "return {ok: true};",
        }
        request_post.return_value.status_code = 200
        request_post.return_value.ok = True
        request_post.return_value.headers = {"Content-Type": "application/json"}
        request_post.return_value.json.return_value = {"authenticated": True, "accessToken": "demo-token"}

        app = generate_api_service(cfg)
        manager = _FakeDomainManager.instances[0]
        manager.vdb_client.create_document("services", {
            "status": "RUNNING",
            "port": 5012,
            "vdb_domain": "AuthCoreService",
            "lapis_config": {
                "metadata": {"apiName": "AuthCoreService", "basePath": "/api/auth", "database": "main"},
                "auth": {"customEndpoints": {"enabled": True, "signIn": "/signin"}},
            },
        })

        response = app.test_client().post("/liwiro/setup/authenticate", json={"username": "demo", "password": "secret"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.get_json() or {}).get("accessToken"), "demo-token")
        self.assertTrue(request_post.called)
        self.assertTrue(str(request_post.call_args.args[0]).endswith("/api/auth/signin"))

    @patch("models.domain.DomainManager", _FakeDomainManager)
    @patch("generators.api_generator.requests.post")
    def test_authenticate_uses_saved_authenticator_endpoint_without_registry_lookup(self, request_post):
        cfg = self._lapis_cfg()
        cfg["metadata"]["apiName"] = "ConsumerService"
        cfg["auth"] = {
            "enabled": True,
            "isAuthService": False,
            "useAsymmetricJWT": True,
            "authServiceName": "AuthCoreService",
            "authServiceEndpoint": {
                "baseUrl": "http://127.0.0.1:5012",
                "signInPath": "/api/auth/signin",
                "signOutPath": "/api/auth/signout",
            },
        }
        cfg["endpoints"]["protected"] = {
            "method": "GET", "path": "/protected", "operationType": "script",
            "requiresAuth": True, "versaScript": "return {ok: true};",
        }
        request_post.return_value.status_code = 200
        request_post.return_value.ok = True
        request_post.return_value.headers = {"Content-Type": "application/json"}
        request_post.return_value.json.return_value = {"authenticated": True, "accessToken": "direct-token"}

        response = generate_api_service(cfg).test_client().post(
            "/liwiro/setup/authenticate", json={"username": "demo", "password": "secret"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.get_json() or {}).get("accessToken"), "direct-token")
        self.assertEqual(str(request_post.call_args.args[0]), "http://127.0.0.1:5012/api/auth/signin")

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_media_docs_payload_includes_sanitized_media_capabilities(self):
        example_path = BACKEND_ROOT.parent / "data" / "lapis-examples" / "15-media-storage-bridge-service.json"
        cfg = json.loads(example_path.read_text(encoding="utf-8"))

        app = generate_api_service(cfg)
        client = app.test_client()
        res = client.get("/liwiro/docs.json", headers={"X-Documentation-Key": "liwiroservicepass0!"})

        self.assertEqual(res.status_code, 200)
        payload = res.get_json() or {}
        media = payload.get("mediaCapabilities") or {}
        providers = {item.get("id"): item for item in (media.get("providers") or [])}

        self.assertTrue(media.get("enabled"))
        self.assertEqual(media.get("assetCollection"), "media_assets")
        self.assertEqual(media.get("defaultProvider"), "cloudinary")
        self.assertTrue(media.get("jsonRequestOnly"))
        self.assertIn("sourceUrl", media.get("inputModes") or [])
        self.assertIn("dataBase64", media.get("inputModes") or [])
        self.assertIn("cloudinary", providers)
        self.assertFalse(providers["cloudinary"].get("ready"))
        self.assertIn("CLOUDINARY_API_SECRET", providers["cloudinary"].get("envKeys") or [])
        self.assertEqual(((providers["cloudinary"].get("routes") or [])[0]).get("path"), "/upload/cloudinary")
        self.assertNotIn("replace-with-cloudinary-api-secret", json.dumps(media))

    def test_auth_example_user_scripts_do_not_include_bad_property_semicolons(self):
        example_path = BACKEND_ROOT.parent / "data" / "lapis-examples" / "01-auth-core-service.json"
        example = json.loads(example_path.read_text(encoding="utf-8"))
        read_script = str((((example.get("endpoints") or {}).get("ep_users_read") or {}).get("versaScript") or ""))
        update_script = str((((example.get("endpoints") or {}).get("ep_users_update") or {}).get("versaScript") or ""))

        self.assertIn('updatedAt: row.updatedAt ?? ""', read_script)
        self.assertNotIn('updatedAt: row.updatedAt ?? "";', read_script)
        self.assertIn('updatedBy: updates.updatedBy ?? row.updatedBy ?? ""', update_script)
        self.assertNotIn('updatedBy: updates.updatedBy ?? row.updatedBy ?? "";', update_script)

    def test_normalize_vi_script_route_body_keeps_block_closers_distinct_from_object_closers(self):
        script_body = (
            "let safeUser = {\n"
            "  username: row.username ?? \"\"\n"
            "};\n"
            "if (actor != \"\") {\n"
            "  ownOnly = false\n"
            "}\n"
        )

        normalized = _normalize_vi_script_route_body(script_body)

        self.assertIn("};", normalized)
        self.assertIn("  ownOnly = false;", normalized)
        self.assertTrue(normalized.endswith("}"))
        self.assertNotIn("ownOnly = false;\n};", normalized)

    def test_normalize_vi_script_route_body_keeps_return_object_properties_comma_terminated(self):
        script_body = (
            "return {\n"
            "  mediaCloud: mediacloud.status()\n"
            "  preview: doc\n"
            "}\n"
        )

        normalized = _normalize_vi_script_route_body(script_body)

        self.assertIn("mediaCloud: mediacloud.status(),", normalized)
        self.assertIn("preview: doc,", normalized)
        self.assertIn("\n};", normalized)

    def test_all_lapis_examples_normalized_script_bodies_parse_in_vi_wrapper(self):
        examples = sorted(glob(str(BACKEND_ROOT.parent / "data" / "lapis-examples" / "*.json")))
        self.assertGreater(len(examples), 0)

        checked = 0
        for path in examples:
            with self.subTest(example=Path(path).name):
                with open(path, "r", encoding="utf-8") as handle:
                    cfg = json.load(handle)
                for endpoint_name, endpoint in (cfg.get("endpoints") or {}).items():
                    script = str((endpoint or {}).get("versaScript") or "")
                    if not script.strip():
                        continue
                    checked += 1
                    normalized = _normalize_vi_script_route_body(_strip_vi_import_lines(script))
                    self._assert_vi_route_body_parses(normalized)
        self.assertGreater(checked, 0)

    def test_auth_example_forgot_password_token_insert_is_built_explicitly(self):
        example_path = BACKEND_ROOT.parent / "data" / "lapis-examples" / "01-auth-core-service.json"
        example = json.loads(example_path.read_text(encoding="utf-8"))
        forgot_script = str((((example.get("endpoints") or {}).get("ep_forgot_password") or {}).get("versaScript") or ""))
        reset_script = str((((example.get("endpoints") or {}).get("ep_reset_password") or {}).get("versaScript") or ""))

        self.assertIn("let nowInfo = datetime.now();", forgot_script)
        self.assertIn("let tokenHash = crypto.sha256(resetToken);", forgot_script)
        self.assertIn("let expiresAt = (nowInfo.timestamp ?? 0) + expiresInSeconds;", forgot_script)
        self.assertIn("let tokenDoc = {", forgot_script)
        self.assertIn("let tokenSave = tokenStore.insert(tokenDoc);", forgot_script)
        self.assertIn("let nowInfo = datetime.now();", reset_script)
        self.assertIn("let nowEpoch = nowInfo.timestamp ?? 0;", reset_script)
        self.assertNotIn("time.time()", forgot_script)
        self.assertNotIn("time.time()", reset_script)

    def test_lapis_create_probes_do_not_reuse_seeded_unique_records(self):
        examples = sorted(glob(str(BACKEND_ROOT.parent / "data" / "lapis-examples" / "*.json")))
        for path in examples:
            with self.subTest(example=Path(path).name):
                config = json.loads(Path(path).read_text(encoding="utf-8"))
                seed = ((config.get("metadata") or {}).get("seedData") or {}).get("collections") or {}
                models = config.get("models") or {}
                for endpoint_id, endpoint in (config.get("endpoints") or {}).items():
                    if endpoint.get("operationType") != "crud" or endpoint.get("crudOperation") != "create":
                        continue
                    model = next((item for item in models.values() if item.get("name") == endpoint.get("linkedModel")), {})
                    collection = model.get("collection", model.get("name"))
                    body = ((endpoint.get("exampleParams") or {}).get("body") or {})
                    self.assertFalse(
                        any(isinstance(row, dict) and all(row.get(key) == value for key, value in body.items()) for row in seed.get(collection, [])),
                        f"{Path(path).name}:{endpoint_id} reuses a seeded document",
                    )

    def test_auth_signup_probe_uses_a_new_seed_safe_username(self):
        config = json.loads((BACKEND_ROOT.parent / "data" / "lapis-examples" / "01-auth-core-service.json").read_text(encoding="utf-8"))
        signup = (config.get("endpoints") or {}).get("ep_signup") or {}
        body = ((signup.get("exampleParams") or {}).get("body") or {})
        seeded = ((config.get("metadata") or {}).get("seedData") or {}).get("collections", {}).get("auth_users", [])
        self.assertFalse(any(isinstance(row, dict) and row.get("username") == body.get("username") for row in seeded))

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_auth_seed_password_is_hashed_at_generation_time(self):
        config = json.loads((BACKEND_ROOT.parent / "data" / "lapis-examples" / "01-auth-core-service.json").read_text(encoding="utf-8"))
        app = generate_api_service(config)
        response = app.test_client().post(
            "/liwiro/setup/seed-db",
            json={"collections": {"auth_users": [{"username": "seed-check", "email": "seed-check@example.com", "seedPassword": "AfricaPatriotic#2026", "role": "USER"}]}},
            headers={"X-Liwiro-Setup-Key": "liwiroservicepass0!"},
        )
        self.assertEqual(response.status_code, 200)
        rows_ok, rows = _FakeDomainManager.instances[0].read_documents("auth_users", {"username": {"$eq": "seed-check"}})
        self.assertTrue(rows_ok)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].get("passwordHash"), hashlib.sha256(b"AfricaPatriotic#2026").hexdigest())
        self.assertNotIn("seedPassword", rows[0])
        self.assertNotIn("password", rows[0])

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_auth_service_generation_creates_management_collections_with_real_fields(self):
        config = json.loads((BACKEND_ROOT.parent / "data" / "lapis-examples" / "01-auth-core-service.json").read_text(encoding="utf-8"))
        generate_api_service(config)
        schemas = _FakeDomainManager.instances[0]._schemas
        self.assertIn("username", schemas["auth_session_controls"])
        self.assertIn("jti", schemas["auth_password_reset_tokens"])
        self.assertNotIn("schema", schemas["auth_session_controls"])
        self.assertNotIn("schema", schemas["auth_password_reset_tokens"])

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_service_docs_media_fallback_markup_keeps_javascript_valid(self):
        config = json.loads((BACKEND_ROOT.parent / "data" / "lapis-examples" / "15-media-storage-bridge-service.json").read_text(encoding="utf-8"))
        app = generate_api_service(config)
        response = app.test_client().get("/liwiro/docs?docsKey=liwiroservicepass0%21")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("<span class=\"muted\">No upload routes detected.</span>", html)
        self.assertNotIn('"<span class="muted">No upload routes detected.</span>"', html)

    def test_media_storage_example_keeps_provider_logic_inside_versa_scripts(self):
        example_path = BACKEND_ROOT.parent / "data" / "lapis-examples" / "15-media-storage-bridge-service.json"
        example = json.loads(example_path.read_text(encoding="utf-8"))
        endpoints = example.get("endpoints") or {}

        status_script = str(((endpoints.get("ep_provider_status") or {}).get("versaScript") or ""))
        cloudinary_script = str(((endpoints.get("ep_upload_cloudinary") or {}).get("versaScript") or ""))

        self.assertIn("mediacloud.status()", status_script)
        self.assertIn("service.env.MEDIA_ASSET_COLLECTION", status_script)
        self.assertIn('mediacloud.upload({provider: "cloudinary"', cloudinary_script)
        self.assertIn("assets.insert(record)", cloudinary_script)
        self.assertNotIn("replace-with-cloudinary-cloud-name", cloudinary_script)
        self.assertNotIn("replace-with-cloudinary-api-secret", cloudinary_script)
        self.assertEqual(sorted(endpoints.keys()), ["ep_provider_status", "ep_upload_cloudinary"])

    def test_all_lapis_examples_script_endpoints_touch_runtime_state_or_external_effects(self):
        examples = sorted(glob(str(BACKEND_ROOT.parent / "data" / "lapis-examples" / "*.json")))
        self.assertGreater(len(examples), 0)

        stateful_markers = (
            ".find(",
            ".insert(",
            ".update(",
            ".delete(",
            "email.send(",
            "jwt.sign(",
            "jwt.verify(",
        )

        checked = 0
        for path in examples:
            with self.subTest(example=Path(path).name):
                with open(path, "r", encoding="utf-8") as handle:
                    cfg = json.load(handle)
                for endpoint_name, endpoint in (cfg.get("endpoints") or {}).items():
                    script = str((endpoint or {}).get("versaScript") or "")
                    if not script.strip():
                        continue
                    checked += 1
                    self.assertTrue(
                        any(marker in script for marker in stateful_markers),
                        f"{Path(path).name}:{endpoint_name} should read/write runtime state or invoke a real external effect",
                    )
        self.assertGreater(checked, 0)

    def test_auth_example_me_script_reads_user_and_session_control_state(self):
        example_path = BACKEND_ROOT.parent / "data" / "lapis-examples" / "01-auth-core-service.json"
        example = json.loads(example_path.read_text(encoding="utf-8"))
        me_endpoint = ((example.get("endpoints") or {}).get("ep_me") or {})
        me_script = str((me_endpoint.get("versaScript") or ""))
        me_docs = me_endpoint.get("documentation") or {}
        me_sections = me_docs.get("sections") or []
        combined_docs = " ".join(
            str(part or "")
            for part in [
                me_docs.get("summary"),
                me_docs.get("description"),
                *(section.get("body") for section in me_sections if isinstance(section, dict)),
            ]
        )

        self.assertIn('vdb.collection("auth_users")', me_script)
        self.assertIn('vdb.collection("auth_session_controls")', me_script)
        self.assertIn("sessionControl", me_script)
        self.assertIn("sessionVersion: effectiveSessionVersion", me_script)
        self.assertIn("return {ok: true, user: userPayload};", me_script)
        self.assertNotIn("token:", me_script)
        self.assertNotIn("sessionControl:", me_script)
        self.assertNotIn("tokenClaims: authCtx", me_script)
        self.assertNotIn("decoded token claims", combined_docs)
        self.assertNotIn("bearer token claims", combined_docs)

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_auth_enabled_non_auth_service_gets_default_signout_route(self):
        cfg = {
            "metadata": {
                "apiName": "AuthDependentService",
                "basePath": "/api/dependent",
                "version": "1.0.0",
                "database": "main",
            },
            "auth": {
                "enabled": True,
                "isAuthService": False,
                "keyManagement": "auto",
                "authServiceName": "AuthCoreService",
                "customEndpoints": {
                    "enabled": False,
                    "signIn": "/auth/signin",
                    "signOut": "/auth/signout",
                    "signUp": "/auth/signup",
                },
            },
            "models": {},
            "endpoints": {},
        }

        app = generate_api_service(cfg)
        routes = {rule.rule for rule in app.url_map.iter_rules()}
        self.assertIn("/api/dependent/auth/signout", routes)

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_auth_reset_password_get_route_renders_browser_form(self):
        app = generate_api_service(self._auth_service_cfg())
        client = app.test_client()

        res = client.get("/api/auth/reset-password?token=reset-token-123")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("Reset Your AuthCoreService Password", body)
        self.assertIn("Complete Reset", body)
        self.assertIn("reset-token-123", body)
        self.assertIn("button-dots", body)

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_custom_reset_submission_page_disables_generated_browser_form(self):
        cfg = self._auth_service_cfg()
        cfg["auth"]["passwordResetPage"] = {
            **cfg["auth"]["passwordResetPage"],
            "enabled": False,
            "submissionMode": "custom_page",
            "customPageBaseUrl": "https://app.example.com/reset-password",
        }

        app = generate_api_service(cfg)
        client = app.test_client()

        res = client.get("/api/auth/reset-password?token=reset-token-123")
        self.assertEqual(res.status_code, 404)

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_custom_reset_submission_link_base_is_exposed_to_runtime_service_env(self):
        cfg = {
            "metadata": {
                "apiName": "ResetLinkService",
                "basePath": "/api/reset",
                "version": "1.0.0",
                "database": "main",
            },
            "auth": {
                "enabled": False,
                "isAuthService": False,
                "keyManagement": "auto",
                "customEndpoints": {
                    "enabled": True,
                    "signIn": "/auth/signin",
                    "signUp": "/auth/signup",
                    "resetPassword": "/reset-password",
                },
                "passwordResetPage": {
                    "enabled": False,
                    "submissionMode": "custom_page",
                    "customPageBaseUrl": "https://app.example.com/reset-password",
                },
            },
            "models": {},
            "endpoints": {
                "echo_reset_env": {
                    "method": "POST",
                    "path": "/echo-reset-env",
                    "operationType": "script",
                    "versaScript": "print('ok')",
                }
            },
        }

        with patch.dict(os.environ, {"PORT": "5123"}, clear=False):
            app = generate_api_service(cfg)

        client = app.test_client()
        res = client.post("/api/reset/echo-reset-env", json={})
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        runtime_env = (((payload or {}).get("params") or {}).get("service") or {}).get("env") or {}
        self.assertEqual(runtime_env.get("PASSWORD_RESET_URL"), "https://app.example.com/reset-password")

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_docs_page_try_route_button_includes_loading_animation_markup(self):
        app = generate_api_service(self._auth_service_cfg())
        client = app.test_client()

        res = client.get("/liwiro/docs")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("button-dots", body)
        self.assertIn("button-dot-bounce", body)

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_production_mode_disables_liwiro_management_and_docs_routes(self):
        cfg = self._auth_service_cfg()
        cfg["metadata"]["setupApiKey"] = "setup-secret"
        cfg["auth"]["defaultSuperAdmin"] = {
            "enabled": True,
            "username": "jelita.mulenga",
            "email": "jelita.mulenga@zmail.com",
            "password": "SystemRoot#ZM1969",
            "role": "SUPER_ADMIN",
        }

        app = generate_api_service(cfg)
        client = app.test_client()

        with patch("generators.api_generator.load_normalized_auth_data", return_value={"settings": {"productionMode": True}}):
            liwiro_res = client.get("/liwiro")
            docs_json_res = client.get("/liwiro/docs.json", headers={"X-Docs-Key": "docs-secret"})
            docs_html_res = client.get("/liwiro/docs")
            setup_res = client.post(
                "/liwiro/setup/reset-super-admin",
                headers={"X-Liwiro-Setup-Key": "setup-secret"},
                json={},
            )

        self.assertEqual(liwiro_res.status_code, 404)
        self.assertEqual(docs_json_res.status_code, 404)
        self.assertEqual(docs_html_res.status_code, 404)
        self.assertEqual(setup_res.status_code, 404)

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_disabled_endpoint_returns_403_and_is_marked_disabled_in_docs_payload(self):
        cfg = self._crud_cfg()
        cfg["metadata"]["documentation"] = {"enabled": True, "key": "docs-secret"}
        cfg["endpoints"]["read_users"]["enabled"] = False

        app = generate_api_service(cfg)
        client = app.test_client()

        res = client.get("/api/v1/users")
        self.assertEqual(res.status_code, 403)
        self.assertIn("disabled", res.get_json().get("error", "").lower())

        docs_res = client.get("/liwiro/docs.json", headers={"X-Docs-Key": "docs-secret"})
        self.assertEqual(docs_res.status_code, 200)
        payload = docs_res.get_json()
        route_doc = next((ep for ep in (payload.get("endpoints") or []) if ep.get("id") == "read_users"), None)
        self.assertIsNotNone(route_doc)
        self.assertFalse(route_doc.get("enabled"))
        self.assertTrue(route_doc.get("toggleable"))

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_docs_endpoint_toggle_updates_runtime_and_registry_snapshot(self):
        cfg = self._crud_cfg()
        cfg["metadata"]["documentation"] = {"enabled": True, "key": "docs-secret"}

        app = generate_api_service(cfg)
        domain_manager = _FakeDomainManager.instances[-1]
        domain_manager.vdb_client._collections["services"] = [{
            "apiName": "authcrud",
            "lapis_config": json.loads(json.dumps(cfg)),
        }]
        client = app.test_client()

        toggle_res = client.post(
            "/liwiro/docs/endpoints/read_users/enabled",
            headers={"X-Docs-Key": "docs-secret"},
            json={"enabled": False},
        )
        self.assertEqual(toggle_res.status_code, 200)
        self.assertFalse(toggle_res.get_json().get("enabled"))

        disabled_res = client.get("/api/v1/users")
        self.assertEqual(disabled_res.status_code, 403)

        persisted_cfg = (((domain_manager.vdb_client._collections.get("services") or [])[0]).get("lapis_config") or {})
        self.assertFalse((((persisted_cfg.get("endpoints") or {}).get("read_users") or {}).get("enabled", True)))

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_default_super_admin_setup_uses_sha256_when_signin_script_requires_it(self):
        cfg = {
            "metadata": {
                "apiName": "AuthCoreService",
                "basePath": "/api/auth",
                "version": "1.0.0",
                "database": "main",
                "setupApiKey": "setup-secret",
            },
            "auth": {
                "enabled": True,
                "isAuthService": True,
                "authModel": "AuthUser",
                "customEndpoints": {"enabled": True, "signIn": "/signin"},
                "defaultSuperAdmin": {
                    "enabled": True,
                    "username": "jelita.mulenga",
                    "email": "jelita.mulenga@zmail.com",
                    "password": "SystemRoot#ZM1969",
                    "role": "SUPER_ADMIN",
                },
            },
            "models": {
                "m_auth_user": {
                    "name": "AuthUser",
                    "collection": "auth_users",
                    "fields": {"f1": {"name": "username", "type": "string", "required": True}},
                }
            },
            "endpoints": {
                "ep_signin": {
                    "method": "POST",
                    "path": "/signin",
                    "operationType": "script",
                    "versaScript": "let incomingHash = crypto.sha256(password); let storedHash = user.passwordHash ?? \"\";",
                }
            },
        }

        app = generate_api_service(cfg)
        client = app.test_client()
        payload = {
            "username": "jelita.mulenga",
            "email": "jelita.mulenga@zmail.com",
            "password": "SystemRoot#ZM1969",
            "role": "SUPER_ADMIN",
        }

        res = client.post(
            "/liwiro/setup/reset-super-admin",
            json=payload,
            headers={"X-Liwiro-Setup-Key": "setup-secret"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual((res.get_json() or {}).get("status"), "created")

        mgr = _FakeDomainManager.instances[0]
        ok, rows = mgr.read_documents("auth_users", {"username": {"$eq": "jelita.mulenga"}})
        self.assertTrue(ok)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].get("passwordHash"), hashlib.sha256(payload["password"].encode("utf-8")).hexdigest())

    @patch("models.domain.DomainManager", _FakeDomainManager)
    def test_default_super_admin_setup_refreshes_existing_legacy_hash(self):
        cfg = {
            "metadata": {
                "apiName": "AuthCoreService",
                "basePath": "/api/auth",
                "version": "1.0.0",
                "database": "main",
                "setupApiKey": "setup-secret",
            },
            "auth": {
                "enabled": True,
                "isAuthService": True,
                "authModel": "AuthUser",
                "customEndpoints": {"enabled": True, "signIn": "/signin"},
                "defaultSuperAdmin": {
                    "enabled": True,
                    "username": "jelita.mulenga",
                    "email": "jelita.mulenga@zmail.com",
                    "password": "SystemRoot#ZM1969",
                    "role": "SUPER_ADMIN",
                },
            },
            "models": {
                "m_auth_user": {
                    "name": "AuthUser",
                    "collection": "auth_users",
                    "fields": {"f1": {"name": "username", "type": "string", "required": True}},
                }
            },
            "endpoints": {
                "ep_signin": {
                    "method": "POST",
                    "path": "/signin",
                    "operationType": "script",
                    "versaScript": "let incomingHash = crypto.sha256(password); let storedHash = user.passwordHash ?? \"\";",
                }
            },
        }

        app = generate_api_service(cfg)
        mgr = _FakeDomainManager.instances[0]
        mgr.create_document(
            "auth_users",
            {
                "username": "jelita.mulenga",
                "email": "old@zmail.com",
                "passwordHash": generate_password_hash("old-password"),
                "role": "USER",
                "password": "legacy",
            },
        )
        client = app.test_client()
        payload = {
            "username": "jelita.mulenga",
            "email": "jelita.mulenga@zmail.com",
            "password": "SystemRoot#ZM1969",
            "role": "SUPER_ADMIN",
        }

        res = client.post(
            "/liwiro/setup/reset-super-admin",
            json=payload,
            headers={"X-Liwiro-Setup-Key": "setup-secret"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual((res.get_json() or {}).get("status"), "updated")

        ok, rows = mgr.read_documents("auth_users", {"username": {"$eq": "jelita.mulenga"}})
        self.assertTrue(ok)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.get("email"), "jelita.mulenga@zmail.com")
        self.assertEqual(row.get("role"), "SUPER_ADMIN")
        self.assertEqual(row.get("passwordHash"), hashlib.sha256(payload["password"].encode("utf-8")).hexdigest())
        self.assertEqual(row.get("password"), "")


if __name__ == "__main__":
    unittest.main()
