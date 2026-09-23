# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import sys
import tempfile
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from generators.api_generator import build_service_preview_bundle


class GeneratedServicePreviewTests(unittest.TestCase):
    def test_preview_bundle_contains_wrapper_and_summary_files(self):
        lapis = {
            "metadata": {
                "apiName": "PreviewService",
                "basePath": "/api/preview",
                "version": "1.0.0",
            },
            "models": {
                "note": {
                    "name": "note",
                    "collection": "notes",
                    "fields": {
                        "title": {"type": "str", "required": True},
                    },
                }
            },
            "endpoints": {
                "listNotes": {
                    "method": "GET",
                    "path": "/notes",
                    "operationType": "crud",
                    "crudOperation": "read",
                    "linkedModel": "note",
                }
            },
        }

        bundle = build_service_preview_bundle(lapis)

        self.assertIn("app.py", bundle)
        self.assertIn("lapis_config.json", bundle)
        self.assertIn("route_summary.json", bundle)
        self.assertIn("README.md", bundle)
        self.assertIn("generate_api_service", bundle["app.py"])
        self.assertIn("listNotes", bundle["route_summary.json"])


if __name__ == "__main__":
    unittest.main()
