# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import json
import sys
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from config import Config, normalize_lapis_config_contract
from app.lapis_repair import repair_lapis_config_recursively


class ConfigSchemaTests(unittest.TestCase):
    def test_all_lapis_examples_are_valid(self):
        example_dir = BACKEND_ROOT.parent / "data" / "lapis-examples"
        examples = sorted(example_dir.glob("*.json"))
        self.assertGreater(len(examples), 0)

        for example_path in examples:
            with self.subTest(example=example_path.name):
                cfg = json.loads(example_path.read_text(encoding="utf-8"))
                ok, err = Config.validate_lapis_config(cfg)
                self.assertTrue(ok, err)

    def test_all_lapis_examples_need_no_deterministic_repair(self):
        example_dir = BACKEND_ROOT.parent / "data" / "lapis-examples"
        for example_path in sorted(example_dir.glob("*.json")):
            with self.subTest(example=example_path.name):
                cfg = json.loads(example_path.read_text(encoding="utf-8"))
                result = repair_lapis_config_recursively(cfg, include_dry_run=False)
                self.assertTrue(result.get("ok"), result.get("error"))
                self.assertFalse(result.get("repaired"), result.get("appliedFixes"))

    def test_lapis_example_catalog_covers_supported_endpoint_operation_types(self):
        example_dir = BACKEND_ROOT.parent / "data" / "lapis-examples"
        examples = sorted(example_dir.glob("*.json"))
        self.assertGreater(len(examples), 0)

        crud_examples = []
        custom_examples = []
        script_examples = []
        all_mode_examples = []
        full_crud_examples = []

        for example_path in examples:
            cfg = json.loads(example_path.read_text(encoding="utf-8"))
            endpoint_map = cfg.get("endpoints") or {}
            ops = {str((endpoint or {}).get("operationType") or "").strip().lower() for endpoint in endpoint_map.values()}
            crud_ops = {
                str((endpoint or {}).get("crudOperation") or "").strip().lower()
                for endpoint in endpoint_map.values()
                if str((endpoint or {}).get("operationType") or "").strip().lower() == "crud"
            }

            if "crud" in ops:
                crud_examples.append(example_path.name)
            if "custom" in ops:
                custom_examples.append(example_path.name)
            if "script" in ops:
                script_examples.append(example_path.name)
            if {"crud", "custom", "script"}.issubset(ops):
                all_mode_examples.append(example_path.name)
            if {"create", "read", "update", "delete"}.issubset(crud_ops):
                full_crud_examples.append(example_path.name)

        self.assertTrue(crud_examples, "Expected at least one CRUD LAPIS example")
        self.assertTrue(custom_examples, "Expected at least one custom VQL LAPIS example")
        self.assertTrue(script_examples, "Expected at least one Versa script LAPIS example")
        self.assertTrue(all_mode_examples, "Expected at least one LAPIS example covering CRUD, custom VQL, and script endpoints together")
        self.assertTrue(full_crud_examples, "Expected at least one LAPIS example exposing full create/read/update/delete coverage")

    def test_auth_core_example_demo_user_roles_match_expected_hierarchy(self):
        example_path = BACKEND_ROOT.parent / "data" / "lapis-examples" / "01-auth-core-service.json"
        cfg = json.loads(example_path.read_text(encoding="utf-8"))
        auth_users = ((((cfg.get("metadata") or {}).get("seedData") or {}).get("collections") or {}).get("auth_users") or [])
        by_name = {
            str((((user or {}).get("profile") or {}).get("fullName") or "").strip()): str((user or {}).get("role") or "").strip()
            for user in auth_users
        }

        self.assertEqual(by_name.get("Kalulu Kaumba"), "SUPER_ADMIN")
        self.assertEqual(by_name.get("Jelita Mulenga"), "ADMIN")
        self.assertEqual(by_name.get("Kalumbi Banda"), "USER")

        default_super_admin = ((cfg.get("auth") or {}).get("defaultSuperAdmin") or {})
        self.assertEqual(default_super_admin.get("username"), "kalulu.kaumba")
        self.assertEqual(default_super_admin.get("role"), "SUPER_ADMIN")

    def test_uuid_style_keys_are_valid(self):
        cfg = {
            "metadata": {
                "apiName": "svc",
                "basePath": "/api",
                "version": "1.0.0",
                "database": "main",
                "rateLimiting": {"enabled": False, "limit": 100, "timeframe": "minute"},
            },
            "auth": {
                "enabled": False,
                "isAuthService": False,
                "keyManagement": "auto",
                "customEndpoints": {"enabled": False, "signIn": "/auth/signin", "signUp": "/auth/signup"},
            },
            "models": {
                "b4d7f0d1-00a4-4f62-a037-2dfed97c5531": {
                    "name": "User",
                    "collection": "users",
                    "fields": {
                        "fd_abc-123": {
                            "id": "fd_abc-123",
                            "name": "username",
                            "type": "string",
                            "required": True,
                        }
                    },
                }
            },
            "endpoints": {
                "ep-9ed6df6a_1": {
                    "method": "GET",
                    "path": "/users",
                    "operationType": "crud",
                    "crudOperation": "read",
                    "linkedModel": "User",
                }
            },
        }
        ok, err = Config.validate_lapis_config(cfg)
        self.assertTrue(ok, err)

    def test_typed_field_default_values_are_valid(self):
        cfg = {
            "metadata": {
                "apiName": "svc-defaults",
                "basePath": "/api",
                "version": "1.0.0",
                "database": "main",
                "rateLimiting": {"enabled": False, "limit": 100, "timeframe": "minute"},
            },
            "auth": {
                "enabled": False,
                "isAuthService": False,
                "keyManagement": "auto",
                "customEndpoints": {"enabled": False, "signIn": "/auth/signin", "signUp": "/auth/signup"},
            },
            "models": {
                "model_defaults": {
                    "name": "FeatureFlags",
                    "collection": "feature_flags",
                    "fields": {
                        "field_version": {
                            "id": "field_version",
                            "name": "version",
                            "type": "number",
                            "required": True,
                            "default": True,
                            "defaultValue": 1,
                        },
                        "field_enabled": {
                            "id": "field_enabled",
                            "name": "enabled",
                            "type": "boolean",
                            "required": True,
                            "default": True,
                            "defaultValue": False,
                        },
                    },
                }
            },
            "endpoints": {
                "ep_defaults": {
                    "method": "GET",
                    "path": "/flags",
                    "operationType": "crud",
                    "crudOperation": "read",
                    "linkedModel": "FeatureFlags",
                }
            },
        }

        ok, err = Config.validate_lapis_config(cfg)
        self.assertTrue(ok, err)

    def test_auth_core_example_is_valid(self):
        cfg = json.loads(
            (BACKEND_ROOT.parent / "data" / "lapis-examples" / "01-auth-core-service.json").read_text(encoding="utf-8")
        )

        ok, err = Config.validate_lapis_config(cfg)
        self.assertTrue(ok, err)

    def test_endpoint_enablement_and_custom_reset_page_fields_are_valid(self):
        cfg = {
            "metadata": {
                "apiName": "svc-reset",
                "basePath": "/api/reset",
                "version": "1.0.0",
                "database": "main",
                "rateLimiting": {"enabled": False, "limit": 100, "timeframe": "minute"},
            },
            "auth": {
                "enabled": True,
                "isAuthService": True,
                "keyManagement": "auto",
                "customEndpoints": {
                    "enabled": True,
                    "signIn": "/auth/signin",
                    "signUp": "/auth/signup",
                    "resetPassword": "/auth/reset-password",
                },
                "passwordResetPage": {
                    "enabled": False,
                    "submissionMode": "custom_page",
                    "customPageBaseUrl": "https://app.example.com/reset-password",
                },
            },
            "models": {},
            "endpoints": {
                "ep_reset": {
                    "enabled": False,
                    "method": "POST",
                    "path": "/auth/reset-password",
                    "operationType": "script",
                    "versaScript": "print('ok')",
                }
            },
        }

        ok, err = Config.validate_lapis_config(cfg)
        self.assertTrue(ok, err)

    def test_custom_vql_endpoint_requires_valid_json_object(self):
        cfg = {
            "metadata": {
                "apiName": "svc-custom",
                "basePath": "/api/custom",
                "version": "1.0.0",
                "database": "main",
            },
            "auth": {
                "enabled": False,
                "isAuthService": False,
                "keyManagement": "auto",
                "customEndpoints": {"enabled": False, "signIn": "/auth/signin", "signUp": "/auth/signup"},
            },
            "models": {},
            "endpoints": {
                "ep_custom": {
                    "method": "POST",
                    "path": "/query",
                    "operationType": "custom",
                    "vqlQuery": "[]",
                }
            },
        }

        ok, err = Config.validate_lapis_config(cfg)
        self.assertFalse(ok)
        self.assertIn("vqlQuery", str(err))

    def test_endpoint_rejects_unknown_operation_type(self):
        cfg = {
            "metadata": {"apiName": "svc-invalid-op", "basePath": "/api/invalid", "version": "1.0.0", "database": "main"},
            "auth": {"enabled": False, "isAuthService": False, "keyManagement": "auto", "customEndpoints": {"enabled": False, "signIn": "/auth/signin", "signUp": "/auth/signup"}},
            "models": {},
            "endpoints": {"ep": {"method": "GET", "path": "/x", "operationType": "future-operation"}},
        }
        ok, err = Config.validate_lapis_config(cfg)
        self.assertFalse(ok)
        self.assertIn("future_operation", str(err))

    def test_custom_vql_endpoint_rejects_relaxed_vql_object_syntax(self):
        cfg = {
            "metadata": {
                "apiName": "svc-custom-relaxed",
                "basePath": "/api/custom",
                "version": "1.0.0",
                "database": "main",
            },
            "auth": {
                "enabled": False,
                "isAuthService": False,
                "keyManagement": "auto",
                "customEndpoints": {"enabled": False, "signIn": "/auth/signin", "signUp": "/auth/signup"},
            },
            "models": {},
            "endpoints": {
                "ep_custom": {
                    "method": "POST",
                    "path": "/query",
                    "operationType": "custom",
                    "vqlQuery": "{action: 'find', collection: 'users', where: {status: {$eq: 'OPEN'}}, limit: 25,}",
                }
            },
        }

        ok, err = Config.validate_lapis_config(cfg)
        self.assertFalse(ok)
        self.assertIn("readable VDB command", str(err))

    def test_custom_vql_endpoint_rejects_nested_operation_object(self):
        cfg = json.loads((BACKEND_ROOT.parent / "data" / "lapis-examples" / "06-analytics-custom-vql-service.json").read_text(encoding="utf-8"))
        cfg["endpoints"] = {
            "ep_custom": {
                "method": "POST", "path": "/query", "operationType": "custom",
                "vqlQuery": '{"read":"users","query":{}}',
            }
        }
        ok, err = Config.validate_lapis_config(cfg)
        self.assertFalse(ok)
        self.assertIn("readable VDB command", str(err))

    def test_custom_vql_endpoint_rejects_nested_key_with_flat_action(self):
        cfg = json.loads((BACKEND_ROOT.parent / "data" / "lapis-examples" / "06-analytics-custom-vql-service.json").read_text(encoding="utf-8"))
        cfg["endpoints"] = {
            "ep_custom": {
                "method": "POST", "path": "/query", "operationType": "custom",
                "vqlQuery": '{"action":"find","collection":"users","read":{"users":{}}}',
            }
        }
        ok, err = Config.validate_lapis_config(cfg)
        self.assertFalse(ok)
        self.assertIn("readable VDB command", str(err))

    def test_custom_vql_endpoint_rejects_nested_lifecycle_key(self):
        cfg = json.loads((BACKEND_ROOT.parent / "data" / "lapis-examples" / "06-analytics-custom-vql-service.json").read_text(encoding="utf-8"))
        cfg["endpoints"] = {
            "ep_custom": {
                "method": "POST", "path": "/query", "operationType": "custom",
                "vqlQuery": '{"action":"echo","domain_status":{"domain":"engineering"}}',
            }
        }
        ok, err = Config.validate_lapis_config(cfg)
        self.assertFalse(ok)
        self.assertIn("readable VDB command", str(err))

    def test_custom_vql_endpoint_rejects_unknown_action(self):
        cfg = json.loads((BACKEND_ROOT.parent / "data" / "lapis-examples" / "06-analytics-custom-vql-service.json").read_text(encoding="utf-8"))
        cfg["endpoints"] = {
            "ep_custom": {
                "method": "POST", "path": "/query", "operationType": "custom",
                "vqlQuery": "teleport users",
            }
        }
        ok, err = Config.validate_lapis_config(cfg)
        self.assertFalse(ok)
        self.assertIn("Unknown VDB command", str(err))

    def test_custom_vql_endpoint_allows_domain_targeted_drop(self):
        cfg = json.loads((BACKEND_ROOT.parent / "data" / "lapis-examples" / "06-analytics-custom-vql-service.json").read_text(encoding="utf-8"))
        cfg["endpoints"] = {
            "ep_custom": {
                "method": "POST", "path": "/drop", "operationType": "custom",
                "vqlQuery": "drop domain temporary",
            }
        }
        ok, err = Config.validate_lapis_config(cfg)
        self.assertTrue(ok, err)

    def test_custom_vql_endpoint_allows_domain_lifecycle_actions(self):
        cfg = json.loads((BACKEND_ROOT.parent / "data" / "lapis-examples" / "06-analytics-custom-vql-service.json").read_text(encoding="utf-8"))
        for action in ("status", "suspend", "resume"):
            cfg["endpoints"] = {
                "ep_custom": {
                    "method": "POST", "path": "/domain", "operationType": "custom",
                    "vqlQuery": f"{action} domain engineering",
                }
            }
            ok, err = Config.validate_lapis_config(cfg)
            self.assertTrue(ok, (action, err))

    def test_custom_vql_endpoint_requires_domain_for_lifecycle_actions(self):
        cfg = json.loads((BACKEND_ROOT.parent / "data" / "lapis-examples" / "06-analytics-custom-vql-service.json").read_text(encoding="utf-8"))
        cfg["endpoints"] = {
            "ep_custom": {
                "method": "POST", "path": "/domain", "operationType": "custom",
                "vqlQuery": "status domain",
            }
        }
        ok, err = Config.validate_lapis_config(cfg)
        self.assertFalse(ok)
        self.assertIn("Incomplete readable VDB command", str(err))

    def test_script_endpoint_requires_source(self):
        cfg = {
            "metadata": {
                "apiName": "svc-script",
                "basePath": "/api/script",
                "version": "1.0.0",
                "database": "main",
            },
            "auth": {
                "enabled": False,
                "isAuthService": False,
                "keyManagement": "auto",
                "customEndpoints": {"enabled": False, "signIn": "/auth/signin", "signUp": "/auth/signup"},
            },
            "models": {},
            "endpoints": {
                "ep_script": {
                    "method": "POST",
                    "path": "/run",
                    "operationType": "script",
                    "versaScript": "",
                }
            },
        }

        ok, err = Config.validate_lapis_config(cfg)
        self.assertFalse(ok)
        self.assertIn("versaScript", str(err))

    def test_crud_endpoint_requires_known_linked_model(self):
        cfg = {
            "metadata": {
                "apiName": "svc-crud",
                "basePath": "/api/crud",
                "version": "1.0.0",
                "database": "main",
            },
            "auth": {
                "enabled": False,
                "isAuthService": False,
                "keyManagement": "auto",
                "customEndpoints": {"enabled": False, "signIn": "/auth/signin", "signUp": "/auth/signup"},
            },
            "models": {
                "model_one": {
                    "name": "User",
                    "collection": "users",
                    "fields": {
                        "field_username": {
                            "id": "field_username",
                            "name": "username",
                            "type": "string",
                            "required": True,
                        }
                    },
                }
            },
            "endpoints": {
                "ep_crud": {
                    "method": "GET",
                    "path": "/users",
                    "operationType": "crud",
                    "crudOperation": "read",
                    "linkedModel": "MissingModel",
                }
            },
        }

        ok, err = Config.validate_lapis_config(cfg)
        self.assertFalse(ok)
        self.assertIn("linkedModel", str(err))

    def test_lapis_validation_normalizes_alias_operation_tokens(self):
        cfg = {
            "metadata": {
                "apiName": "svc-alias",
                "basePath": "/api/alias",
                "version": "1.0.0",
                "database": "main",
            },
            "auth": {
                "enabled": False,
                "isAuthService": False,
                "keyManagement": "auto",
                "customEndpoints": {"enabled": False, "signIn": "/auth/signin", "signUp": "/auth/signup"},
            },
            "models": {
                "model_one": {
                    "name": "User",
                    "collection": "users",
                    "fields": {
                        "field_username": {
                            "id": "field_username",
                            "name": "username",
                            "type": "string",
                            "required": True,
                        }
                    },
                }
            },
            "endpoints": {
                "ep_crud": {
                    "method": "GET",
                    "path": "/users",
                    "operationType": "RESOURCE",
                    "crudOperation": "READ_MANY",
                    "linkedModel": "User",
                }
            },
        }

        ok, err = Config.validate_lapis_config(cfg)
        self.assertTrue(ok, err)

        normalized = normalize_lapis_config_contract(cfg)
        self.assertEqual(normalized["endpoints"]["ep_crud"]["operationType"], "crud")
        self.assertEqual(normalized["endpoints"]["ep_crud"]["crudOperation"], "read")


if __name__ == "__main__":
    unittest.main()
