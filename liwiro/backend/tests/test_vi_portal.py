# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import sys
import threading
import tempfile
import unittest
import signal
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import (
    _count_vi_portal_files,
    _ensure_vi_terminal_session,
    _load_normalized_auth_data,
    _normalize_vi_repl_input,
    _normalize_vi_terminal_size,
    _run_vi_terminal_file,
    _sanitize_vi_repl_stdout,
    _signal_vi_terminal_session,
    _start_vi_terminal_repl_process,
    _submit_vi_repl_input,
    _write_vi_terminal_input,
    _vi_terminal_reader_loop,
    _vi_terminal_poll_payload,
    _vi_terminal_session_metadata,
    _vi_runtime_env,
    _vi_repl_session_key,
    create_app,
)


class VIPortalRoutesTests(unittest.TestCase):
    def test_repl_input_normalizer_appends_statement_terminator_for_single_line_input(self):
        self.assertEqual(_normalize_vi_repl_input('print("hello")', "> "), 'print("hello");')
        self.assertEqual(_normalize_vi_repl_input('print("hello");', "> "), 'print("hello");')
        self.assertEqual(_normalize_vi_repl_input("if (ok) {", "> "), "if (ok) {")

    def test_repl_stdout_sanitizer_removes_prompt_noise(self):
        self.assertEqual(
            _sanitize_vi_repl_stdout("VI REPL. Type 'exit' to quit.\n> > > > > "),
            "VI REPL. Type 'exit' to quit.",
        )
        self.assertEqual(_sanitize_vi_repl_stdout("> > 7\n> "), "7")

    def test_terminal_size_normalizer_clamps_bounds(self):
        self.assertEqual(_normalize_vi_terminal_size(10, 2), (40, 12))
        self.assertEqual(_normalize_vi_terminal_size(400, 200), (240, 120))

    def _build_app(self):
        with patch("app.main._initialize_vdb_runtime", return_value=(True, "ok")), \
             patch("app.main._reconcile_service_runtime_states", return_value=[]), \
             patch("app.main._autostart_services_if_enabled", return_value=None):
            app = create_app()

        app.testing = True
        app.config["LIWIRO_DOMAIN"] = "liwiro"
        app.config["LIWIRO_DB"] = "config"
        app.config["VDB_TRANSPORT"] = "unixsocket"
        app.config["VDB_UNIX_SOCKET_PATH"] = "/tmp/vdb.sock"
        app.config["VDB_SERVER_URL"] = "http://localhost:1957"
        app.config["VDB_USERNAME"] = "liwiro"
        app.config["VDB_PASSWORD"] = "pass"
        source_dir = tempfile.TemporaryDirectory()
        self.addCleanup(source_dir.cleanup)
        app.config["VI_PORTAL_SOURCE_DIR"] = source_dir.name

        app.vdb_client = MagicMock()
        app.vdb_client.async_authorize.return_value = True
        app.vdb_client.use_domain.return_value = True
        app.vdb_client.use_database.return_value = True

        token = "test-token"
        app.auth_sessions[token] = {
            "username": "zulan",
            "role": "admin",
            "is_super_admin": True,
            "service_access": ["*"],
            "permissions_overrides": [],
            "liwiro_rbac": {},
            "permissions": ["VIEW_SERVICES", "MANAGE_SERVICES"],
        }
        return app, token

    def test_vi_connection_reports_runtime_settings(self):
        app, token = self._build_app()
        Path(app.config["VI_PORTAL_SOURCE_DIR"], "hello.versa").write_text("print('hi');", encoding="utf-8")
        with patch("app.main._resolve_verun_root", return_value=Path("/tmp/verun")), \
             patch("app.main._resolve_vi_jar_path", return_value=Path("/tmp/verun/vi.jar")), \
             patch("pathlib.Path.is_file", return_value=True):
            client = app.test_client()
            res = client.get("/platform/vi/connection", headers={"Authorization": f"Bearer {token}"})

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["source_dir"], app.config["VI_PORTAL_SOURCE_DIR"])
        self.assertEqual(data["files_count"], 1)
        self.assertFalse(data["repl_active"])
        self.assertFalse(data["terminal_active"])

    def test_vi_connection_counts_files_without_building_full_metadata_list(self):
        app, token = self._build_app()
        Path(app.config["VI_PORTAL_SOURCE_DIR"], "hello.versa").write_text("print('hi');", encoding="utf-8")
        Path(app.config["VI_PORTAL_SOURCE_DIR"], "notes.txt").write_text("ignore", encoding="utf-8")

        client = app.test_client()
        with patch("app.main._resolve_verun_root", return_value=Path("/tmp/verun")), \
             patch("app.main._resolve_vi_jar_path", return_value=Path("/tmp/verun/vi.jar")), \
             patch("pathlib.Path.is_file", return_value=True), \
             patch("app.main._list_vi_portal_files", side_effect=AssertionError("connection route should not build file metadata")):
            res = client.get("/platform/vi/connection", headers={"Authorization": f"Bearer {token}"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["files_count"], 1)

    def test_vi_terminal_poll_payload_marks_missing_session_degraded(self):
        app, _ = self._build_app()

        with app.app_context():
            payload = _vi_terminal_poll_payload("zulan", None, 0)

        self.assertTrue(payload["degraded"])
        self.assertGreater(payload["retryAfterMs"], 0)
        self.assertEqual(payload["reason"], "VI terminal session is not active")

    def test_vi_connection_can_update_source_directory(self):
        app, token = self._build_app()
        target_root = tempfile.TemporaryDirectory()
        self.addCleanup(target_root.cleanup)
        target_path = Path(target_root.name, "workspace", "versa")

        client = app.test_client()
        res = client.put(
            "/platform/vi/connection",
            json={"source_dir": str(target_path)},
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["source_dir"], str(target_path))
        self.assertTrue(target_path.is_dir())
        self.assertEqual(app.config["VI_PORTAL_SOURCE_DIR"], str(target_path))

    def test_vi_directory_browser_lists_subdirectories(self):
        app, token = self._build_app()
        base_dir = Path(app.config["VI_PORTAL_SOURCE_DIR"])
        Path(base_dir, "examples").mkdir(parents=True, exist_ok=True)
        Path(base_dir, "snippets").mkdir(parents=True, exist_ok=True)
        Path(base_dir, "notes.txt").write_text("ignore me", encoding="utf-8")

        client = app.test_client()
        res = client.get(
            f"/platform/vi/directories?path={base_dir}",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["path"], str(base_dir))
        self.assertEqual(sorted(item["name"] for item in data["directories"]), ["examples", "snippets"])
        self.assertEqual(data["source_dir"], str(base_dir))
        self.assertTrue(any(entry["path"] == str(base_dir) for entry in data["roots"]))

    def test_vi_list_files_returns_local_file_metadata(self):
        app, token = self._build_app()
        Path(app.config["VI_PORTAL_SOURCE_DIR"], "examples").mkdir(parents=True, exist_ok=True)
        Path(app.config["VI_PORTAL_SOURCE_DIR"], "examples", "hello.versa").write_text("print('ok');", encoding="utf-8")

        client = app.test_client()
        res = client.get("/platform/vi/files", headers={"Authorization": f"Bearer {token}"})

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data["files"]), 1)
        self.assertEqual(data["files"][0]["path"], "examples/hello.versa")
        self.assertEqual(data["files"][0]["extension"], ".versa")

    def test_count_vi_portal_files_matches_visible_versa_files(self):
        app, _ = self._build_app()
        Path(app.config["VI_PORTAL_SOURCE_DIR"], "examples").mkdir(parents=True, exist_ok=True)
        Path(app.config["VI_PORTAL_SOURCE_DIR"], "examples", "hello.versa").write_text("print('ok');", encoding="utf-8")
        Path(app.config["VI_PORTAL_SOURCE_DIR"], "examples", "ignore.txt").write_text("ignore", encoding="utf-8")
        Path(app.config["VI_PORTAL_SOURCE_DIR"], "examples", "upper.VERSA").write_text("print('ok');", encoding="utf-8")

        self.assertEqual(_count_vi_portal_files(Path(app.config["VI_PORTAL_SOURCE_DIR"])), 2)

    def test_request_local_auth_data_cache_reuses_loaded_payload_without_sharing_mutations(self):
        app, token = self._build_app()
        calls = {"count": 0}

        def fake_load():
            calls["count"] += 1
            return {"settings": {"productionMode": False}, "users": []}

        with app.app_context():
            with app.test_request_context("/platform/vi/connection", headers={"Authorization": f"Bearer {token}"}):
                with patch("app.main._load_normalized_auth_data_impl", side_effect=fake_load):
                    first = _load_normalized_auth_data()
                    second = _load_normalized_auth_data()
                    first["settings"]["productionMode"] = True
                    third = _load_normalized_auth_data()

        self.assertEqual(calls["count"], 1)
        self.assertIsNot(first, second)
        self.assertFalse(second["settings"]["productionMode"])
        self.assertFalse(third["settings"]["productionMode"])

    def test_vi_repl_input_route_returns_live_prompt_payload(self):
        app, token = self._build_app()
        with patch(
            "app.main._submit_vi_repl_input",
            return_value=(True, {"output": "42", "stderr": "", "prompt": "> ", "active": True}),
        ):
            client = app.test_client()
            res = client.post(
                "/platform/vi/repl/input",
                json={"source": "print(42);"},
                headers={"Authorization": f"Bearer {token}"},
            )

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["output"], "42")
        self.assertEqual(data["prompt"], "> ")
        self.assertTrue(data["active"])

    def test_vi_terminal_status_defaults_inactive(self):
        app, token = self._build_app()
        client = app.test_client()

        res = client.get("/platform/vi/terminal/session", headers={"Authorization": f"Bearer {token}"})

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertFalse(data["active"])
        self.assertEqual(data["sourceDir"], app.config["VI_PORTAL_SOURCE_DIR"])

    def test_vi_terminal_start_route_returns_metadata(self):
        app, token = self._build_app()
        client = app.test_client()
        with patch(
            "app.main._ensure_vi_terminal_session",
            return_value=(True, {"sessionKey": "zulan", "active": True, "prompt": "> ", "cols": 120, "rows": 32}),
        ):
            res = client.post(
                "/platform/vi/terminal/session",
                json={"cols": 120, "rows": 32},
                headers={"Authorization": f"Bearer {token}"},
            )

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["active"])
        self.assertEqual(data["sessionKey"], "zulan")
        self.assertEqual(data["cols"], 120)

    def test_vi_terminal_startup_session_is_reused_while_launch_is_in_progress(self):
        app, token = self._build_app()
        with app.test_request_context("/platform/vi/terminal/session", headers={"Authorization": f"Bearer {token}"}):
            app.vi_terminal_sessions["zulan"] = {
                "process": None,
                "master_fd": None,
                "slave_fd": None,
                "prompt": "> ",
                "createdAt": datetime.now(timezone.utc).isoformat(),
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                "cols": 120,
                "rows": 32,
                "buffer": "",
                "chunks": deque(maxlen=2000),
                "next_seq": 1,
                "active": True,
                "exitCode": None,
                "mode": "repl",
                "cwd": app.config["VI_PORTAL_SOURCE_DIR"],
                "restart_repl_on_exit": False,
                "switchingProcess": True,
                "cleanupPaths": [],
                "lock": threading.Lock(),
            }

            ok, metadata = _ensure_vi_terminal_session(cols=100, rows=30)

        self.assertTrue(ok)
        self.assertTrue(metadata["active"])
        self.assertEqual(metadata["sessionKey"], "zulan")
        self.assertEqual(metadata["cols"], 100)
        self.assertEqual(metadata["rows"], 30)

    def test_vi_terminal_session_can_start_without_pty_backend(self):
        app, token = self._build_app()
        proc = MagicMock()
        proc.poll.return_value = None

        with app.app_context():
            with app.test_request_context("/platform/vi/terminal/session", headers={"Authorization": f"Bearer {token}"}):
                with patch("app.main._resolve_verun_root", return_value=Path("/tmp/verun")), \
                     patch("app.main._resolve_vi_jar_path", return_value=Path("/tmp/verun/vi.jar")), \
                     patch("pathlib.Path.is_file", return_value=True), \
                     patch("app.main._start_vi_terminal_repl_process", return_value=(True, proc)) as start_repl, \
                     patch("app.main._ensure_vi_terminal_reader") as ensure_reader, \
                     patch("app.main._wait_for_vi_terminal_activity", return_value=None):
                    ok, metadata = _ensure_vi_terminal_session(cols=120, rows=32)

        self.assertTrue(ok)
        self.assertTrue(metadata["active"])
        self.assertEqual(metadata["mode"], "repl")
        start_repl.assert_called_once()
        ensure_reader.assert_called_once()

    def test_vi_repl_session_key_accepts_websocket_token_query(self):
        app, token = self._build_app()

        with app.test_request_context(f"/platform/vi/terminal/ws?token={token}"):
            self.assertEqual(_vi_repl_session_key(), "zulan")

    def test_vi_terminal_run_route_returns_metadata(self):
        app, token = self._build_app()
        client = app.test_client()
        with patch(
            "app.main._run_vi_terminal_file",
            return_value=(True, {"sessionKey": "zulan", "active": True, "mode": "file", "path": "scratch/playground.versa"}),
        ):
            res = client.post(
                "/platform/vi/terminal/run",
                json={"path": "playground.versa"},
                headers={"Authorization": f"Bearer {token}"},
            )

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["mode"], "file")
        self.assertEqual(data["path"], "scratch/playground.versa")

    def test_vi_terminal_run_route_accepts_ephemeral_source(self):
        app, token = self._build_app()
        client = app.test_client()
        with patch(
            "app.main._run_vi_terminal_source",
            return_value=(True, {"sessionKey": "zulan", "active": True, "mode": "file", "path": "scratch/draft.versa", "ephemeral": True}),
        ) as run_source:
            res = client.post(
                "/platform/vi/terminal/run",
                json={"path": "scratch/draft.versa", "source": 'print("draft");'},
                headers={"Authorization": f"Bearer {token}"},
            )

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ephemeral"])
        self.assertEqual(data["path"], "scratch/draft.versa")
        run_source.assert_called_once_with("scratch/draft.versa", 'print("draft");')

    def test_signal_vi_terminal_session_targets_process_group(self):
        app, _ = self._build_app()
        proc = MagicMock()
        proc.poll.return_value = None
        proc.pid = 4321

        with app.app_context():
            app.vi_terminal_sessions["zulan"] = {
                "process": proc,
                "prompt": "> ",
                "lock": threading.Lock(),
            }
            with patch("app.main._vi_terminal_session_key", return_value="zulan"):
                ok, result = _signal_vi_terminal_session("SIGINT")

        self.assertTrue(ok)
        self.assertTrue(result["active"])
        proc.send_signal.assert_called()

    def test_run_vi_terminal_file_replaces_running_file_process(self):
        app, _ = self._build_app()
        existing_proc = MagicMock()
        existing_proc.poll.return_value = None
        next_proc = MagicMock()
        next_proc.poll.return_value = None
        session = {
            "process": existing_proc,
            "mode": "file",
            "prompt": "",
            "cols": 120,
            "rows": 32,
            "buffer": "",
            "chunks": [],
            "next_seq": 1,
            "active": True,
            "cwd": app.config["VI_PORTAL_SOURCE_DIR"],
            "restart_repl_on_exit": True,
            "lock": threading.Lock(),
            "master_fd": 11,
            "slave_fd": 12,
        }

        with app.app_context():
            app.vi_terminal_sessions["zulan"] = session
            with patch("app.main._ensure_vi_terminal_session", return_value=(True, {"sessionKey": "zulan"})), \
                 patch("app.main._resolve_verun_root", return_value=Path("/tmp/verun")), \
                 patch("app.main._resolve_vi_jar_path", return_value=Path("/tmp/verun/vi.jar")), \
                 patch("pathlib.Path.is_file", return_value=True), \
                 patch("app.main._resolve_vi_portal_existing_file", return_value=(Path("/tmp/source/scratch/playground.versa"), "scratch/playground.versa")), \
                 patch("app.main._terminate_vi_terminal_process") as terminate_proc, \
                 patch("app.main._launch_vi_terminal_process", return_value=(True, next_proc)) as launch_proc, \
                 patch("app.main._wait_for_vi_terminal_activity", return_value=None):
                ok, result = _run_vi_terminal_file("scratch/playground.versa")

        self.assertTrue(ok)
        self.assertEqual(result["path"], "scratch/playground.versa")
        terminate_proc.assert_called_once_with(session)
        launch_proc.assert_called_once()

    def test_ensure_vi_terminal_session_recovers_dead_file_session_before_replacing_it(self):
        app, token = self._build_app()
        dead_proc = MagicMock()
        dead_proc.poll.return_value = 0
        next_proc = MagicMock()
        next_proc.poll.return_value = None
        session = {
            "process": dead_proc,
            "mode": "file",
            "prompt": "",
            "cols": 120,
            "rows": 32,
            "buffer": "Prompt: ",
            "chunks": [],
            "next_seq": 1,
            "active": True,
            "cwd": app.config["VI_PORTAL_SOURCE_DIR"],
            "restart_repl_on_exit": True,
            "switchingProcess": False,
            "cleanupPaths": [],
            "lock": threading.Lock(),
            "master_fd": 11,
            "slave_fd": 12,
        }

        def fake_restart(target_session):
            with target_session["lock"]:
                target_session["process"] = next_proc
                target_session["mode"] = "repl"
                target_session["prompt"] = "> "
                target_session["cwd"] = app.config["VI_PORTAL_SOURCE_DIR"]
                target_session["restart_repl_on_exit"] = False
                target_session["switchingProcess"] = False
                target_session["active"] = True
                target_session["exitCode"] = None
                target_session["exitNotified"] = False
            return True, next_proc

        with app.app_context():
            app.vi_terminal_sessions["zulan"] = session
            with app.test_request_context("/", headers={"Authorization": f"Bearer {token}"}):
                with patch("app.main._start_vi_terminal_repl_process", side_effect=fake_restart) as restart_proc, \
                     patch("app.main._ensure_vi_terminal_reader") as ensure_reader, \
                     patch("app.main._wait_for_vi_terminal_activity", return_value=None) as wait_activity, \
                     patch("app.main._terminate_vi_terminal_session") as terminate_session:
                    ok, data = _ensure_vi_terminal_session()

        self.assertTrue(ok)
        self.assertTrue(data["active"])
        self.assertEqual(data["mode"], "repl")
        restart_proc.assert_called_once_with(session)
        self.assertEqual(ensure_reader.call_count, 2)
        wait_activity.assert_called_once()
        terminate_session.assert_not_called()

    def test_run_vi_terminal_file_recovers_fast_exit_back_into_repl(self):
        app, _ = self._build_app()
        file_proc = MagicMock()
        file_proc.poll.return_value = 0
        repl_proc = MagicMock()
        repl_proc.poll.return_value = None
        session = {
            "process": None,
            "mode": "repl",
            "prompt": "> ",
            "cols": 120,
            "rows": 32,
            "buffer": "",
            "chunks": [],
            "next_seq": 1,
            "active": True,
            "cwd": app.config["VI_PORTAL_SOURCE_DIR"],
            "restart_repl_on_exit": False,
            "switchingProcess": False,
            "lock": threading.Lock(),
            "master_fd": 11,
            "slave_fd": 12,
        }

        def fake_launch(target_session, *_args, **_kwargs):
            with target_session["lock"]:
                target_session["process"] = file_proc
                target_session["mode"] = "file"
                target_session["prompt"] = ""
                target_session["cwd"] = "/tmp/source/scratch"
                target_session["restart_repl_on_exit"] = True
                target_session["switchingProcess"] = False
                target_session["active"] = True
            return True, file_proc

        def fake_restart(target_session):
            with target_session["lock"]:
                target_session["process"] = repl_proc
                target_session["mode"] = "repl"
                target_session["prompt"] = "> "
                target_session["cwd"] = app.config["VI_PORTAL_SOURCE_DIR"]
                target_session["restart_repl_on_exit"] = False
                target_session["switchingProcess"] = False
                target_session["active"] = True
                target_session["exitCode"] = None
                target_session["exitNotified"] = False
            return True, repl_proc

        with app.app_context():
            app.vi_terminal_sessions["zulan"] = session
            with patch("app.main._ensure_vi_terminal_session", return_value=(True, {"sessionKey": "zulan"})), \
                 patch("app.main._resolve_verun_root", return_value=Path("/tmp/verun")), \
                 patch("app.main._resolve_vi_jar_path", return_value=Path("/tmp/verun/vi.jar")), \
                 patch("pathlib.Path.is_file", return_value=True), \
                 patch("app.main._resolve_vi_portal_existing_file", return_value=(Path("/tmp/source/scratch/zezt.versa"), "scratch/zezt.versa")), \
                 patch("app.main._terminate_vi_terminal_process") as terminate_proc, \
                 patch("app.main._launch_vi_terminal_process", side_effect=fake_launch) as launch_proc, \
                 patch("app.main._start_vi_terminal_repl_process", side_effect=fake_restart) as restart_proc, \
                 patch("app.main._ensure_vi_terminal_reader") as ensure_reader, \
                 patch("app.main._wait_for_vi_terminal_activity", return_value=None) as wait_activity:
                ok, result = _run_vi_terminal_file("scratch/zezt.versa")

        self.assertTrue(ok)
        self.assertTrue(result["active"])
        self.assertEqual(result["mode"], "repl")
        self.assertEqual(result["path"], "scratch/zezt.versa")
        terminate_proc.assert_called_once_with(session)
        launch_proc.assert_called_once()
        restart_proc.assert_called_once_with(session)
        self.assertEqual(ensure_reader.call_count, 3)
        self.assertEqual(wait_activity.call_count, 2)

    def test_run_vi_terminal_file_disables_old_repl_restart_before_replacing_live_file(self):
        app, _ = self._build_app()
        old_file_proc = MagicMock()
        old_file_proc.poll.return_value = None
        new_file_proc = MagicMock()
        new_file_proc.poll.return_value = None
        session = {
            "process": old_file_proc,
            "mode": "file",
            "prompt": "",
            "cols": 120,
            "rows": 32,
            "buffer": "",
            "chunks": [],
            "next_seq": 1,
            "active": True,
            "cwd": app.config["VI_PORTAL_SOURCE_DIR"],
            "restart_repl_on_exit": True,
            "switchingProcess": False,
            "cleanupPaths": [],
            "lock": threading.Lock(),
            "master_fd": 11,
            "slave_fd": 12,
        }

        def fake_terminate(target_session):
            self.assertFalse(target_session["restart_repl_on_exit"])
            self.assertTrue(target_session["switchingProcess"])
            target_session["process"] = None

        def fake_launch(target_session, *_args, **_kwargs):
            with target_session["lock"]:
                target_session["process"] = new_file_proc
                target_session["mode"] = "file"
                target_session["prompt"] = ""
                target_session["cwd"] = "/tmp/source/scratch"
                target_session["restart_repl_on_exit"] = True
                target_session["switchingProcess"] = False
                target_session["active"] = True
                target_session["exitCode"] = None
                target_session["exitNotified"] = False
            return True, new_file_proc

        with app.app_context():
            app.vi_terminal_sessions["zulan"] = session
            with patch("app.main._ensure_vi_terminal_session", return_value=(True, {"sessionKey": "zulan"})), \
                 patch("app.main._resolve_verun_root", return_value=Path("/tmp/verun")), \
                 patch("app.main._resolve_vi_jar_path", return_value=Path("/tmp/verun/vi.jar")), \
                 patch("pathlib.Path.is_file", return_value=True), \
                 patch("app.main._resolve_vi_portal_existing_file", return_value=(Path("/tmp/source/scratch/space.versa"), "scratch/space.versa")), \
                 patch("app.main._terminate_vi_terminal_process", side_effect=fake_terminate) as terminate_proc, \
                 patch("app.main._flush_vi_terminal_buffers") as flush_buffers, \
                 patch("app.main._launch_vi_terminal_process", side_effect=fake_launch) as launch_proc, \
                 patch("app.main._ensure_vi_terminal_reader") as ensure_reader, \
                 patch("app.main._wait_for_vi_terminal_activity", return_value=None) as wait_activity:
                ok, result = _run_vi_terminal_file("scratch/space.versa")

        self.assertTrue(ok)
        self.assertTrue(result["active"])
        self.assertEqual(result["mode"], "file")
        self.assertEqual(result["path"], "scratch/space.versa")
        terminate_proc.assert_called_once_with(session)
        flush_buffers.assert_called_once_with(session)
        launch_proc.assert_called_once()
        self.assertEqual(ensure_reader.call_count, 2)
        wait_activity.assert_called_once()

    def test_vi_terminal_status_recovers_dead_file_session_back_into_repl(self):
        app, _ = self._build_app()
        dead_proc = MagicMock()
        dead_proc.poll.return_value = 0
        next_proc = MagicMock()
        next_proc.poll.return_value = None
        session = {
            "process": dead_proc,
            "mode": "file",
            "prompt": "",
            "cols": 120,
            "rows": 32,
            "buffer": "Hello, what is your name? : \r\nNice to meet you John\r\n",
            "chunks": [],
            "next_seq": 7,
            "active": True,
            "cwd": app.config["VI_PORTAL_SOURCE_DIR"],
            "restart_repl_on_exit": True,
            "switchingProcess": False,
            "lock": threading.Lock(),
            "master_fd": 11,
            "slave_fd": 12,
        }

        def fake_restart(target_session):
            with target_session["lock"]:
                target_session["process"] = next_proc
                target_session["mode"] = "repl"
                target_session["prompt"] = "> "
                target_session["cwd"] = app.config["VI_PORTAL_SOURCE_DIR"]
                target_session["restart_repl_on_exit"] = False
                target_session["switchingProcess"] = False
                target_session["active"] = True
                target_session["exitCode"] = None
                target_session["exitNotified"] = False
            return True, next_proc

        with app.app_context():
            with patch("app.main._start_vi_terminal_repl_process", side_effect=fake_restart) as restart_proc, \
                 patch("app.main._ensure_vi_terminal_reader") as ensure_reader, \
                 patch("app.main._wait_for_vi_terminal_activity", return_value=None) as wait_activity:
                data = _vi_terminal_session_metadata("zulan", session)

        self.assertTrue(data["active"])
        self.assertEqual(data["mode"], "repl")
        self.assertEqual(data["prompt"], "> ")
        self.assertEqual(data["exitCode"], None)
        restart_proc.assert_called_once_with(session)
        ensure_reader.assert_called_once_with("zulan", session)
        wait_activity.assert_called_once()

    def test_vi_terminal_input_reconciles_completed_file_session_before_writing(self):
        app, _ = self._build_app()
        dead_proc = MagicMock()
        dead_proc.poll.return_value = 0
        repl_proc = MagicMock()
        repl_proc.poll.return_value = None
        repl_proc.stdin = MagicMock()
        session = {
            "process": dead_proc,
            "mode": "file",
            "prompt": "",
            "active": True,
            "restart_repl_on_exit": True,
            "lock": threading.Lock(),
        }
        reconciled_session = {
            **session,
            "process": repl_proc,
            "mode": "repl",
            "prompt": "> ",
            "restart_repl_on_exit": False,
        }

        with app.app_context():
            app.vi_terminal_sessions["zulan"] = session
            with patch("app.main._ensure_vi_terminal_session", return_value=(True, {"sessionKey": "zulan"})), \
                 patch("app.main._reconcile_vi_terminal_session", return_value=reconciled_session) as reconcile_session, \
                 patch("app.main._vi_terminal_session_metadata", return_value={"sessionKey": "zulan", "active": True, "mode": "repl"}):
                ok, result = _write_vi_terminal_input("John")

        self.assertTrue(ok)
        self.assertEqual(result["mode"], "repl")
        reconcile_session.assert_called_once_with("zulan", session, wait_timeout=0.05)
        repl_proc.stdin.write.assert_called_once_with(b"John;\n")
        repl_proc.stdin.flush.assert_called_once()

    def test_vi_terminal_input_recovers_when_file_session_closes_during_write(self):
        app, _ = self._build_app()
        file_proc = MagicMock()
        file_proc.poll.return_value = None
        file_proc.stdin = MagicMock()
        file_proc.stdin.write.side_effect = OSError("EIO")
        repl_proc = MagicMock()
        repl_proc.poll.return_value = None
        repl_proc.stdin = MagicMock()
        reconcile_calls = {"count": 0}
        session = {
            "process": file_proc,
            "mode": "file",
            "prompt": "",
            "active": True,
            "restart_repl_on_exit": True,
            "lock": threading.Lock(),
        }

        def fake_reconcile(_session_key, target_session, wait_timeout=0.25):
            reconcile_calls["count"] += 1
            if reconcile_calls["count"] > 1 and target_session["process"] is file_proc:
                target_session["process"] = repl_proc
                target_session["mode"] = "repl"
                target_session["prompt"] = "> "
                target_session["restart_repl_on_exit"] = False
            return target_session

        with app.app_context():
            app.vi_terminal_sessions["zulan"] = session
            with patch("app.main._ensure_vi_terminal_session", return_value=(True, {"sessionKey": "zulan"})), \
                 patch("app.main._reconcile_vi_terminal_session", side_effect=fake_reconcile) as reconcile_session, \
                 patch("app.main._vi_terminal_session_metadata", return_value={"sessionKey": "zulan", "active": True, "mode": "repl"}), \
                 patch("app.main._terminate_vi_terminal_session") as terminate_session:
                ok, result = _write_vi_terminal_input("John")

        self.assertTrue(ok)
        self.assertEqual(result["mode"], "repl")
        self.assertEqual(reconcile_session.call_count, 2)
        file_proc.stdin.write.assert_called_once_with(b"John\n")
        terminate_session.assert_not_called()

    def test_vi_terminal_status_marks_dead_repl_session_inactive_when_reader_misses_exit(self):
        app, _ = self._build_app()
        dead_proc = MagicMock()
        dead_proc.poll.return_value = 0
        session = {
            "process": dead_proc,
            "mode": "repl",
            "prompt": "> ",
            "cols": 120,
            "rows": 32,
            "buffer": "",
            "chunks": [],
            "next_seq": 1,
            "active": True,
            "cwd": app.config["VI_PORTAL_SOURCE_DIR"],
            "restart_repl_on_exit": False,
            "switchingProcess": False,
            "lock": threading.Lock(),
            "master_fd": 11,
            "slave_fd": 12,
        }

        with app.app_context():
            data = _vi_terminal_session_metadata("zulan", session)

        self.assertFalse(data["active"])
        self.assertEqual(data["exitCode"], 0)
        self.assertIsNone(session["process"])
        self.assertIn("VI terminal exited with code 0", session["buffer"])
        self.assertGreater(data["lastSeq"], 0)

    def test_vi_terminal_reader_ignores_expected_exit_while_switching_processes(self):
        app, _ = self._build_app()
        old_proc = MagicMock()
        old_proc.poll.return_value = 0
        session = {
            "process": old_proc,
            "mode": "repl",
            "prompt": "> ",
            "cols": 120,
            "rows": 32,
            "buffer": "",
            "chunks": [],
            "next_seq": 1,
            "active": True,
            "cwd": app.config["VI_PORTAL_SOURCE_DIR"],
            "restart_repl_on_exit": False,
            "switchingProcess": True,
            "lock": threading.Lock(),
            "master_fd": 11,
            "slave_fd": 12,
        }

        def fake_sleep(_seconds):
            app.vi_terminal_sessions.pop("zulan", None)

        with app.app_context():
            app.vi_terminal_sessions["zulan"] = session
            with patch("app.main.select.select", return_value=([], [], [])), \
                 patch("app.main.os.read", return_value=b""), \
                 patch("app.main._mark_vi_terminal_session_inactive") as mark_inactive, \
                 patch("app.main.time.sleep", side_effect=fake_sleep):
                _vi_terminal_reader_loop(app, "zulan")

        mark_inactive.assert_not_called()

    def test_start_vi_terminal_repl_process_uses_stored_auth_session_without_request_context(self):
        app, _ = self._build_app()
        session = {
            "slave_fd": 12,
            "lock": threading.Lock(),
            "auth_session": {
                "username": "zulan",
                "role": "admin",
                "is_super_admin": True,
                "service_access": ["*"],
                "permissions": ["VIEW_SERVICES", "MANAGE_SERVICES"],
            },
            "preferred_module_domain": "liwiro",
        }
        proc = MagicMock()

        with app.app_context():
            with patch("app.main._resolve_verun_root", return_value=Path("/tmp/verun")), \
                 patch("app.main._resolve_vi_jar_path", return_value=Path("/tmp/verun/vi.jar")), \
                 patch("pathlib.Path.is_file", return_value=True), \
                 patch("app.main._resolve_vi_portal_source_dir", return_value=Path("/tmp/source")), \
                 patch("app.main.subprocess.Popen", return_value=proc) as popen:
                ok, started = _start_vi_terminal_repl_process(session)

        self.assertTrue(ok)
        self.assertIs(started, proc)
        self.assertEqual(popen.call_args.kwargs["env"]["LIWIRO_VI_MODULE_DOMAIN"], "liwiro")

    def test_vi_runtime_env_falls_back_to_config_domain_when_request_helper_raises(self):
        app, _ = self._build_app()

        with app.app_context():
            with patch("app.main._preferred_vi_module_domain", side_effect=RuntimeError("Working outside of request context.")):
                env = _vi_runtime_env()

        self.assertEqual(env["LIWIRO_VI_MODULE_DOMAIN"], "liwiro")

    def test_vi_repl_input_reports_exit_error_when_process_dies_without_output(self):
        app, _ = self._build_app()
        proc = MagicMock()
        proc.poll.return_value = None
        proc.stdin.write.return_value = None
        proc.stdin.flush.return_value = None

        with app.app_context():
            app.vi_repl_sessions["zulan"] = {"process": proc, "prompt": "> "}
            with patch("app.main._ensure_vi_repl_session", return_value=(True, {"sessionKey": "zulan", "prompt": "> ", "active": True})), \
                 patch("app.main._drain_vi_repl_output", return_value=("", "", "> ", 1)), \
                 patch("app.main._terminate_vi_repl_session", return_value=None):
                ok, result = _submit_vi_repl_input("bad();")

        self.assertTrue(ok)
        self.assertFalse(result["active"])
        self.assertEqual(result["error"], "VI REPL exited with code 1")

    def test_vi_repl_input_submits_raw_single_line_source(self):
        app, _ = self._build_app()
        proc = MagicMock()
        proc.poll.return_value = None
        proc.stdin.write.return_value = None
        proc.stdin.flush.return_value = None

        with app.app_context():
            app.vi_repl_sessions["zulan"] = {"process": proc, "prompt": "> "}
            with patch("app.main._ensure_vi_repl_session", return_value=(True, {"sessionKey": "zulan", "prompt": "> ", "active": True})), \
                 patch("app.main._drain_vi_repl_output", return_value=("hello", "", "> ", None)):
                ok, result = _submit_vi_repl_input('print("hello")')

        self.assertTrue(ok)
        self.assertEqual(result["output"], "hello")
        self.assertEqual(proc.stdin.write.call_args_list[0].args[0], 'print("hello");')


if __name__ == "__main__":
    unittest.main()
