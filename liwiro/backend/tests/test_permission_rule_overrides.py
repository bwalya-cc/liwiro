# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import sys
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.auth_data import normalize_user_permissions
from app.main import _session_can_access_service, _session_can_modify_service_config


class PermissionRuleOverrideTests(unittest.TestCase):
    def test_normalize_user_permissions_supports_explicit_deny_rules(self):
        normalized = normalize_user_permissions(
            [
                {"effect": "deny", "type": "service_all", "service": "orders"},
                {"type": "service_endpoint", "service": "orders", "endpoint": "/public"},
            ]
        )

        self.assertEqual(
            normalized,
            [
                {"effect": "DENY", "type": "SERVICE_ALL", "service": "orders"},
                {"effect": "ALLOW", "type": "SERVICE_ENDPOINT", "service": "orders", "endpoint": "/public"},
            ],
        )

    def test_service_all_deny_overrides_wildcard_service_access(self):
        session = {
            "role": "viewer",
            "service_access": ["*"],
            "permissions_overrides": [
                {"effect": "DENY", "type": "SERVICE_ALL", "service": "orders"},
            ],
        }
        service_doc = {"apiName": "orders", "processId": "42"}

        self.assertFalse(_session_can_access_service(session, service_doc))

    def test_endpoint_allow_can_grant_service_visibility_without_direct_service_access(self):
        session = {
            "role": "viewer",
            "service_access": [],
            "permissions_overrides": [
                {"effect": "ALLOW", "type": "SERVICE_ENDPOINT", "service": "orders", "endpoint": "/public"},
            ],
        }
        service_doc = {"apiName": "orders", "processId": "42"}

        self.assertTrue(_session_can_access_service(session, service_doc))

    def test_endpoint_deny_does_not_hide_service_but_blocks_denied_endpoint_changes(self):
        session = {
            "role": "viewer",
            "service_access": ["*"],
            "permissions_overrides": [
                {"effect": "DENY", "type": "SERVICE_ENDPOINT", "service": "orders", "endpoint": "/admin"},
            ],
        }
        service_doc = {"apiName": "orders", "processId": "42"}
        old_config = {
            "models": {},
            "endpoints": {
                "admin": {
                    "path": "/admin",
                    "method": "GET",
                    "operationType": "custom",
                    "vqlQuery": "read collection orders",
                },
            },
        }
        new_config = {
            "models": {},
            "endpoints": {
                "admin": {
                    "path": "/admin",
                    "method": "GET",
                    "operationType": "custom",
                    "vqlQuery": "read collection orders limit 1",
                },
            },
        }

        self.assertTrue(_session_can_access_service(session, service_doc))
        self.assertFalse(_session_can_modify_service_config(session, service_doc, old_config, new_config))

    def test_endpoint_deny_does_not_block_other_endpoint_changes_for_wildcard_user(self):
        session = {
            "role": "viewer",
            "service_access": ["*"],
            "permissions_overrides": [
                {"effect": "DENY", "type": "SERVICE_ENDPOINT", "service": "orders", "endpoint": "/admin"},
            ],
        }
        service_doc = {"apiName": "orders", "processId": "42"}
        old_config = {
            "models": {},
            "endpoints": {
                "public": {
                    "path": "/public",
                    "method": "GET",
                    "operationType": "custom",
                    "vqlQuery": "read collection orders",
                },
            },
        }
        new_config = {
            "models": {},
            "endpoints": {
                "public": {
                    "path": "/public",
                    "method": "GET",
                    "operationType": "custom",
                    "vqlQuery": "read collection orders limit 5",
                },
            },
        }

        self.assertTrue(_session_can_modify_service_config(session, service_doc, old_config, new_config))


if __name__ == "__main__":
    unittest.main()
