# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.lapis_repair import collect_lapis_validation_issues, repair_lapis_config_recursively


class LapisRepairTests(unittest.TestCase):
    def _base_config(self):
        return {
            "metadata": {"apiName": "RepairService", "basePath": "/api/v1", "version": "1.0.0"},
            "auth": {"enabled": False},
            "models": {},
            "endpoints": {
                "ep_contact_submit": {
                    "method": "POST",
                    "path": "/contact",
                    "operationType": "script",
                    "versaScript": "return {\n  ok: true\n  preview: doc;\n}",
                }
            },
        }

    def test_collect_lapis_validation_issues_extracts_sandbox_route_issue(self):
        issues = collect_lapis_validation_issues(
            {
                "valid": False,
                "error": "Validation failed",
                "dryRun": {
                    "endpointResults": [
                        {
                            "endpointId": "ep_contact_submit",
                            "route": "/contact",
                            "ok": False,
                            "error": '{"error":"Script error (line 2, column 3): Error at line 2:3\\n preview: preview: doc;\\n ^\\nExpected \',\' after property"}',
                        }
                    ]
                },
            }
        )

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["endpointId"], "ep_contact_submit")
        self.assertTrue(issues[0]["repairable"])
        self.assertEqual(issues[0]["code"], "missing-comma-after-property")
        self.assertEqual(issues[0]["previewText"], "preview: doc;")

    def test_repair_lapis_config_recursively_adds_missing_comma_and_revalidates(self):
        config = self._base_config()
        invalid_detail = {
            "valid": False,
            "error": "Endpoint '/contact' failed dry-run validation in sandbox.",
            "normalized": config,
            "versaIssues": [
                {
                    "endpointId": "ep_contact_submit",
                    "endpointPath": "/contact",
                    "path": "service/contact_submit.versa",
                    "error": "Script error (line 2, column 3): Expected ',' after property",
                }
            ],
        }
        valid_detail = {
            "valid": True,
            "error": "",
            "normalized": {
                **config,
                "endpoints": {
                    **config["endpoints"],
                    "ep_contact_submit": {
                        **config["endpoints"]["ep_contact_submit"],
                        "versaScript": "return {\n  ok: true,\n  preview: doc,\n}",
                    }
                },
            },
            "versaIssues": [],
        }

        with patch("config.Config.validate_lapis_config_detailed", side_effect=[invalid_detail, valid_detail]):
            result = repair_lapis_config_recursively(config)

        self.assertTrue(result["ok"], result)
        self.assertTrue(result["repaired"])
        self.assertEqual(result["finalStatus"], "ready")
        self.assertTrue(any(item.get("code") == "missing-comma-after-property" for item in result["appliedFixes"]))
        repaired_script = result["normalized"]["endpoints"]["ep_contact_submit"]["versaScript"]
        self.assertIn("ok: true,", repaired_script)

    def test_repair_lapis_config_uses_preview_text_to_fix_the_exact_property(self):
        config = self._base_config()
        invalid_detail = {
            "valid": False,
            "error": "Endpoint '/contact' failed dry-run validation in sandbox.",
            "normalized": config,
            "dryRun": {
                "endpointResults": [
                    {
                        "endpointId": "ep_contact_submit",
                        "route": "/contact",
                        "ok": False,
                        "error": '{"error":"Script error (line 130, column 20): Error at line 130:20\\n preview: preview: doc;\\n ^\\nExpected \',\' after property"}',
                    }
                ]
            },
            "versaIssues": [],
        }
        valid_detail = {
            "valid": True,
            "error": "",
            "normalized": {
                **config,
                "endpoints": {
                    **config["endpoints"],
                    "ep_contact_submit": {
                        **config["endpoints"]["ep_contact_submit"],
                        "versaScript": "return {\n  ok: true\n  preview: doc,\n}",
                    }
                },
            },
            "versaIssues": [],
        }

        with patch("config.Config.validate_lapis_config_detailed", side_effect=[invalid_detail, valid_detail]):
            result = repair_lapis_config_recursively(config)

        self.assertTrue(result["ok"], result)
        repaired_script = result["normalized"]["endpoints"]["ep_contact_submit"]["versaScript"]
        self.assertIn("preview: doc,", repaired_script)
        self.assertIn("ok: true", repaired_script)

    def test_repair_lapis_config_recursively_applies_safe_schema_normalization(self):
        config = self._base_config()
        normalized = {
            **config,
            "metadata": {
                **config["metadata"],
                "database": "main",
            },
        }
        invalid_detail = {
            "valid": False,
            "error": "Schema normalization required.",
            "normalized": normalized,
            "versaIssues": [],
        }
        valid_detail = {
            "valid": True,
            "error": "",
            "normalized": normalized,
            "versaIssues": [],
        }

        with patch("config.Config.validate_lapis_config_detailed", side_effect=[invalid_detail, valid_detail]):
            result = repair_lapis_config_recursively(config)

        self.assertTrue(result["ok"], result)
        self.assertTrue(any(item.get("code") == "safe-schema-normalization" for item in result["appliedFixes"]))
        self.assertEqual(result["normalized"]["metadata"]["database"], "main")


if __name__ == "__main__":
    unittest.main()
