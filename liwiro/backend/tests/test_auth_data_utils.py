# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import auth_data as auth_data_module
from app.auth_data import normalize_auth_data
from utils.auth_helpers import MAX_USERNAME_VARIANTS, username_variants


class AuthDataUtilsTests(unittest.TestCase):
    def test_normalize_auth_data_applies_defaults(self):
        normalized = normalize_auth_data(
            {
                "users": [
                    {
                        "username": "alice",
                        "password_hash": "hash-1",
                        "role": "admin",
                    }
                ]
            }
        )
        self.assertIn("settings", normalized)
        self.assertEqual(
            normalized["settings"],
            {
                "productionMode": False,
                "startServicesOnStartup": False,
                "autoRefreshServiceStatus": True,
                "deleteDataWithServiceByDefault": True,
                "startServicesAfterGenerationByDefault": True,
                "retryFailedBatchOpsByDefault": True,
            },
        )
        self.assertTrue(normalized["users"][0]["is_super_admin"])
        self.assertEqual(normalized["users"][0]["service_access"], ["*"])

    def test_username_variants_are_bounded(self):
        variants = username_variants("AbCdEfGhIj")
        self.assertLessEqual(len(variants), MAX_USERNAME_VARIANTS)
        self.assertIn("abcdefghij", variants)
        self.assertTrue(any(item != item.lower() and item != item.upper() for item in variants))

    def test_load_normalized_auth_data_reuses_cached_normalized_payload(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            auth_path = Path(tmp_dir) / "auth.json"
            auth_path.write_text(
                json.dumps(
                    {
                        "users": [
                            {
                                "username": "alice",
                                "password_hash": "hash-1",
                                "role": "admin",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            original_path = auth_data_module.Config.LIWIRO_AUTH_PATH
            original_auth_cache = dict(auth_data_module._AUTH_CACHE)
            original_normalized_cache = dict(auth_data_module._NORMALIZED_AUTH_CACHE)
            auth_data_module.Config.LIWIRO_AUTH_PATH = str(auth_path)
            auth_data_module._AUTH_CACHE.update({"path": None, "mtime_ns": None, "data": None})
            auth_data_module._NORMALIZED_AUTH_CACHE.update({"path": None, "mtime_ns": None, "data": None})
            try:
                original_normalize = auth_data_module.normalize_auth_data
                calls = {"count": 0}

                def wrapped(data):
                    calls["count"] += 1
                    return original_normalize(data)

                with patch("app.auth_data.normalize_auth_data", side_effect=wrapped):
                    first = auth_data_module.load_normalized_auth_data()
                    second = auth_data_module.load_normalized_auth_data()
                    first["settings"]["productionMode"] = True
                    third = auth_data_module.load_normalized_auth_data()

                self.assertEqual(calls["count"], 1)
                self.assertEqual(first["users"][0]["username"], "alice")
                self.assertEqual(second["users"][0]["username"], "alice")
                self.assertIsNot(first, second)
                self.assertFalse(third["settings"]["productionMode"])
            finally:
                auth_data_module.Config.LIWIRO_AUTH_PATH = original_path
                auth_data_module._AUTH_CACHE.clear()
                auth_data_module._AUTH_CACHE.update(original_auth_cache)
                auth_data_module._NORMALIZED_AUTH_CACHE.clear()
                auth_data_module._NORMALIZED_AUTH_CACHE.update(original_normalized_cache)


if __name__ == "__main__":
    unittest.main()
