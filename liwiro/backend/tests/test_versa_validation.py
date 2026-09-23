# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.versa_validation import validate_versa_source


class VersaValidationTests(unittest.TestCase):
    @patch("app.versa_validation._resolve_vi_validation_classpath", return_value="/tmp/vi.jar")
    @patch("app.versa_validation.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="", stderr=""))
    def test_validate_versa_source_blocks_missing_vdb_import(self, _run, _classpath):
        result = validate_versa_source(
            "let status = \"queued\";\n"
            "let rows = vdb.find(\"repairs\", {status: status}, 5);\n",
            path_hint="scratch/repairs.versa",
        )

        self.assertFalse(result["ok"])
        self.assertIn("not imported", result["error"])
        self.assertIn("vdb import *;", result["error"])

    @patch("app.versa_validation._resolve_vi_validation_classpath", return_value="/tmp/vi.jar")
    @patch("app.versa_validation.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="", stderr=""))
    def test_validate_versa_source_blocks_module_import_after_code(self, _run, _classpath):
        result = validate_versa_source(
            "let ready = true;\n"
            "vdb import *;\n"
            "let rows = vdb.find(\"repairs\", {}, 5);\n",
            path_hint="scratch/repairs.versa",
        )

        self.assertFalse(result["ok"])
        self.assertIn("must appear at the top", result["error"])

    @patch("app.versa_validation._resolve_vi_validation_classpath", return_value="/tmp/vi.jar")
    @patch("app.versa_validation.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="", stderr=""))
    def test_validate_versa_source_allows_imported_vdb_namespace_usage(self, _run, _classpath):
        result = validate_versa_source(
            "vdb import *;\n"
            "let rows = vdb.find(\"repairs\", {status: \"queued\"}, 5);\n",
            path_hint="scratch/repairs.versa",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["error"], "")


if __name__ == "__main__":
    unittest.main()
