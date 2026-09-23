# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import _autostart_local_vdb_named_pipe_if_needed


class NamedPipeAutostartTests(unittest.TestCase):
    def test_windows_named_pipe_autostart_uses_bash_launcher(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            verun_root = Path(tmpdir)
            workdir = verun_root / "vdb"
            scripts_dir = workdir / "scripts"
            logs_dir = workdir / "logs"
            scripts_dir.mkdir(parents=True)
            logs_dir.mkdir(parents=True)
            (scripts_dir / "namedpipe.sh").write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")

            app = Flask(__name__)
            app.config["VDB_NAMED_PIPE_PATH"] = r"\\.\pipe\verun_vdb"

            proc = SimpleNamespace(poll=MagicMock(side_effect=[None]), terminate=MagicMock(), wait=MagicMock())

            with app.app_context(), \
                 patch("app.main.supports_named_pipe_transport", return_value=True), \
                 patch("app.main._probe_vdb_named_pipe_status", side_effect=[
                     {"available": False},
                     {"available": True},
                 ]), \
                 patch("app.main._resolve_verun_root", return_value=verun_root), \
                 patch("app.main._resolve_bash_executable", return_value=r"C:\Program Files\Git\bin\bash.exe"), \
                 patch("app.main._launch_background_process", return_value=proc) as launch_process, \
                 patch("app.main.time.sleep", return_value=None):
                ok, message = _autostart_local_vdb_named_pipe_if_needed(
                    app,
                    server_url="http://127.0.0.1:1957",
                    named_pipe_path=r"\\.\pipe\verun_vdb",
                )

        self.assertTrue(ok)
        self.assertIn("Started named-pipe interface", message)
        launch_args = launch_process.call_args.args[0]
        self.assertEqual(launch_args[0], r"C:\Program Files\Git\bin\bash.exe")
        self.assertTrue(launch_args[1].endswith("namedpipe.sh"))


if __name__ == "__main__":
    unittest.main()
