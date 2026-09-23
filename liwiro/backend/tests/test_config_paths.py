# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import config


class ConfigPathResolutionTests(unittest.TestCase):
    def test_root_style_relative_verse_path_resolves_to_project_verse_dir(self):
        resolved = Path(config._resolve_project_path("liwiro/verse"))
        self.assertEqual(resolved, (BACKEND_ROOT.parent / "verse").resolve())

    def test_project_relative_verse_path_resolves_to_project_verse_dir(self):
        resolved = Path(config._resolve_project_path("verse"))
        self.assertEqual(resolved, (BACKEND_ROOT.parent / "verse").resolve())

    def test_root_style_auth_config_path_resolves_to_backend_runtime_file(self):
        resolved = Path(config._resolve_project_path("liwiro/backend/.runtime/liwiro.vdb.auth.json"))
        self.assertEqual(resolved, (BACKEND_ROOT / ".runtime" / "liwiro.vdb.auth.json").resolve())

    def test_explicit_missing_auth_config_path_remains_the_selected_path(self):
        with patch.dict(os.environ, {"LIWIRO_VDB_AUTH_CONFIG": "missing/liwiro.vdb.auth.json"}):
            data, path = config._load_liwiro_auth_config()
        self.assertEqual(Path(path).resolve(), (BACKEND_ROOT.parent / "missing/liwiro.vdb.auth.json").resolve())
        self.assertEqual(data, {})

    def test_platform_detection_prefers_windows_runtime_over_unix_like_shell(self):
        detected = config._classify_host_platform("Linux", "nt", "win32")
        self.assertEqual(detected, "windows")

    def test_platform_runtime_info_uses_cache_path_without_writing_file(self):
        with TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "platform-runtime.json"
            config.platform_runtime_info.cache_clear()
            with patch.object(config, "_PLATFORM_CACHE_PATH", cache_path):
                details = config.platform_runtime_info()
            config.platform_runtime_info.cache_clear()

            self.assertFalse(cache_path.exists())
            self.assertEqual(details["cache_path"], str(cache_path))
            self.assertIn(details["platform"], {"windows", "linux", "macos"})

    def test_named_pipe_path_normalization_removes_duplicate_prefix_and_control_chars(self):
        normalized = config.normalize_vdb_named_pipe_path("\\\\.\\pipe\\.\\pipe\verun_vdb")
        self.assertEqual(normalized, r"\\.\pipe\verun_vdb")


if __name__ == "__main__":
    unittest.main()
