# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch


CLI_PATH = Path(__file__).resolve().parents[1] / "cli" / "liwiro.py"
SPEC = importlib.util.spec_from_file_location("liwiro_cli", CLI_PATH)
liwiro_cli = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = liwiro_cli
SPEC.loader.exec_module(liwiro_cli)


class LiwiroCliTests(unittest.TestCase):
    def setUp(self):
        self.state_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.state_dir.cleanup)
        self.runtime_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.runtime_dir.cleanup)

        self.state_path = Path(self.state_dir.name) / "liwiro-cli.json"
        self.fallback_state_path = Path(self.state_dir.name) / "fallback-liwiro-cli.json"
        self.runtime_root = Path(self.runtime_dir.name) / "runtime"
        self.fallback_runtime_root = Path(self.runtime_dir.name) / "fallback-runtime"
        self.log_dir = self.runtime_root / "logs"
        self.fallback_log_dir = self.fallback_runtime_root / "logs"

        self.state_patch = patch.object(liwiro_cli, "STATE_PATH", self.state_path)
        self.fallback_state_patch = patch.object(liwiro_cli, "FALLBACK_STATE_PATH", self.fallback_state_path)
        self.runtime_patch = patch.object(liwiro_cli, "LOCAL_RUNTIME_ROOT", self.runtime_root)
        self.fallback_runtime_patch = patch.object(liwiro_cli, "FALLBACK_RUNTIME_ROOT", self.fallback_runtime_root)
        self.log_patch = patch.object(liwiro_cli, "LOCAL_LOG_DIR", self.log_dir)
        self.fallback_log_patch = patch.object(liwiro_cli, "FALLBACK_LOG_DIR", self.fallback_log_dir)

        self.state_patch.start()
        self.fallback_state_patch.start()
        self.runtime_patch.start()
        self.fallback_runtime_patch.start()
        self.log_patch.start()
        self.fallback_log_patch.start()
        self.addCleanup(self.state_patch.stop)
        self.addCleanup(self.fallback_state_patch.stop)
        self.addCleanup(self.runtime_patch.stop)
        self.addCleanup(self.fallback_runtime_patch.stop)
        self.addCleanup(self.log_patch.stop)
        self.addCleanup(self.fallback_log_patch.stop)

    def write_state(self, payload: dict) -> None:
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def read_state(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def test_load_state_migrates_legacy_shape(self):
        self.write_state(
            {
                "backend": "http://legacy.example",
                "token": "legacy-token",
                "username": "legacy-user",
                "vdb_portal_token": "portal-1",
            }
        )

        state = liwiro_cli.load_state()

        self.assertEqual(state["current_profile"], "default")
        self.assertIn("default", state["profiles"])
        self.assertEqual(state["profiles"]["default"]["backend"], "http://legacy.example")
        self.assertEqual(state["profiles"]["default"]["token"], "legacy-token")
        self.assertEqual(state["profiles"]["default"]["vdb_portal_token"], "portal-1")

    def test_vdb_connect_stores_portal_token_in_profile(self):
        self.write_state(
            {
                "version": 2,
                "current_profile": "default",
                "profiles": {
                    "default": {
                        "backend": "http://127.0.0.1:5000",
                        "token": "frontend-token",
                        "username": "zulan",
                        "vdb_portal_token": "",
                    }
                },
                "local": {"processes": {}},
            }
        )

        with patch.object(
            liwiro_cli.LiwiroClient,
            "request",
            return_value={
                "portalToken": "portal-123",
                "mode": "app",
                "username": "liwiro",
                "vdb_transport": "unixsocket",
                "context": {"data": {"domain": "liwiro", "database": "config"}},
            },
        ) as request_mock, redirect_stdout(io.StringIO()):
            exit_code = liwiro_cli.main(["vdb", "connect"])

        self.assertEqual(exit_code, 0)
        request_mock.assert_called_once()
        self.assertEqual(self.read_state()["profiles"]["default"]["vdb_portal_token"], "portal-123")

    def test_auth_login_prompts_for_vdb_repair_and_retries(self):
        stdin_mock = MagicMock()
        stdin_mock.isatty.return_value = True
        self.write_state(
            {
                "version": 2,
                "current_profile": "default",
                "profiles": {
                    "default": {
                        "backend": "http://127.0.0.1:5000",
                        "token": "",
                        "username": "",
                        "vdb_portal_token": "",
                    }
                },
                "local": {"processes": {}},
            }
        )

        responses = [
            {
                "token": "frontend-token-1",
                "username": "zulan",
                "role": "admin",
                "bootstrap": False,
                "bootstrapNotices": [],
                "vdbRuntimeReady": False,
                "vdbRuntimeError": "Authentication failed",
            },
            {
                "configured": True,
                "vdbTransport": "unixsocket",
                "vdbUnixSocketPath": "/tmp/vdb.sock",
                "defaultVdbTransport": "unixsocket",
                "defaultVdbServerUrl": "http://127.0.0.1:1957",
                "defaultVdbUnixSocketPath": "/tmp/vdb.sock",
                "defaultVdbNamedPipePath": "\\\\.\\pipe\\verun_vdb",
            },
            {
                "token": "frontend-token-2",
                "username": "zulan",
                "role": "admin",
                "bootstrap": False,
                "bootstrapNotices": [],
                "vdbRuntimeReady": True,
                "vdbRuntimeError": "",
            },
        ]

        with patch.object(
            liwiro_cli.LiwiroClient,
            "request",
            side_effect=responses,
        ) as request_mock, patch.object(
            liwiro_cli.sys,
            "stdin",
            stdin_mock,
        ), patch(
            "builtins.input",
            side_effect=["y", "", "", ""],
        ), patch.object(
            liwiro_cli.getpass,
            "getpass",
            return_value="RepairedVdbPass0!",
        ), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            exit_code = liwiro_cli.main(["auth", "login", "--username", "zulan", "--password", "ChangeMeLiwiroPass0!"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(request_mock.call_count, 3)
        retry_payload = request_mock.call_args_list[2].kwargs["body"]
        self.assertEqual(retry_payload["vdb_transport"], "unixsocket")
        self.assertEqual(retry_payload["vdb_unix_socket_path"], "/tmp/vdb.sock")
        self.assertEqual(retry_payload["vdb_app_username"], "Liwiro")
        self.assertEqual(retry_payload["vdb_app_password"], "RepairedVdbPass0!")
        self.assertEqual(self.read_state()["profiles"]["default"]["token"], "frontend-token-2")

    def test_client_request_autostarts_local_backend_and_retries(self):
        client = liwiro_cli.LiwiroClient("http://127.0.0.1:5000", timeout=5)
        response = MagicMock()
        response.read.return_value = b'{"configured": true}'
        context_manager = MagicMock()
        context_manager.__enter__.return_value = response
        context_manager.__exit__.return_value = False

        with patch.object(liwiro_cli, "maybe_autostart_local_backend", return_value=True) as autostart_mock, patch.object(
            liwiro_cli.request,
            "urlopen",
            side_effect=[liwiro_cli.error.URLError("connection refused"), context_manager],
        ) as urlopen_mock:
            payload = client.request("GET", "/auth/status")

        self.assertEqual(payload["configured"], True)
        autostart_mock.assert_called_once_with("http://127.0.0.1:5000")
        self.assertEqual(urlopen_mock.call_count, 2)

    def test_client_request_recovers_local_vdb_after_rbac_failure_and_retries(self):
        client = liwiro_cli.LiwiroClient("http://127.0.0.1:5000", token="frontend-token", timeout=5)
        response = MagicMock()
        response.read.return_value = b'[{"processId":"1234","apiName":"auth-api"}]'
        context_manager = MagicMock()
        context_manager.__enter__.return_value = response
        context_manager.__exit__.return_value = False
        http_error = liwiro_cli.error.HTTPError(
            "http://127.0.0.1:5000/services?summary=1",
            403,
            "Forbidden",
            hdrs=None,
            fp=io.BytesIO(b'{"error":"RBAC authorization failed"}'),
        )

        with patch.object(
            liwiro_cli,
            "maybe_autostart_local_vdb_runtime",
            return_value=True,
        ) as recover_mock, patch.object(
            liwiro_cli.request,
            "urlopen",
            side_effect=[http_error, context_manager],
        ) as urlopen_mock:
            payload = client.request("GET", "/services?summary=1", require_auth=True)

        self.assertEqual(payload[0]["processId"], "1234")
        recover_mock.assert_called_once_with("http://127.0.0.1:5000")
        self.assertEqual(urlopen_mock.call_count, 2)

    def test_maybe_autostart_local_vdb_runtime_starts_unixsocket_target(self):
        state = {"version": 2, "current_profile": "default", "profiles": {}, "local": {"processes": {}}}

        with patch.object(
            liwiro_cli,
            "maybe_autostart_local_backend",
            return_value=False,
        ) as backend_mock, patch.object(
            liwiro_cli,
            "auth_status_snapshot",
            return_value={
                "vdbTransport": "unixsocket",
                "vdbUnixSocketPath": "/tmp/vdb.sock",
                "defaultVdbServerUrl": "http://127.0.0.1:1957",
            },
        ), patch.object(
            liwiro_cli,
            "socket_ok",
            return_value=False,
        ), patch.object(
            liwiro_cli,
            "load_state",
            return_value=state,
        ), patch.object(
            liwiro_cli,
            "start_local_target_in_background",
            return_value={"target": "vdb", "healthy": True},
        ) as start_mock:
            recovered = liwiro_cli.maybe_autostart_local_vdb_runtime("http://127.0.0.1:5000")

        self.assertTrue(recovered)
        backend_mock.assert_called_once_with("http://127.0.0.1:5000")
        start_mock.assert_called_once_with(
            state,
            "vdb",
            vdb_transport="unixsocket",
            vdb_http_url="http://127.0.0.1:1957",
            vdb_socket_path="/tmp/vdb.sock",
        )

    def test_services_generate_requires_explicit_input(self):
        self.write_state(
            {
                "version": 2,
                "current_profile": "default",
                "profiles": {
                    "default": {
                        "backend": "http://127.0.0.1:5000",
                        "token": "frontend-token",
                        "username": "zulan",
                        "vdb_portal_token": "",
                    }
                },
                "local": {"processes": {}},
            }
        )

        with self.assertRaises(liwiro_cli.CliError):
            liwiro_cli.main(["services", "generate"])

    def test_vi_files_write_creates_when_file_is_missing(self):
        self.write_state(
            {
                "version": 2,
                "current_profile": "default",
                "profiles": {
                    "default": {
                        "backend": "http://127.0.0.1:5000",
                        "token": "frontend-token",
                        "username": "zulan",
                        "vdb_portal_token": "",
                    }
                },
                "local": {"processes": {}},
            }
        )

        with patch.object(
            liwiro_cli.LiwiroClient,
            "request",
            side_effect=[
                liwiro_cli.CliHttpError("not found", 404, {"error": "not found"}),
                {"path": "demo.versa", "size": 9},
            ],
        ) as request_mock, redirect_stdout(io.StringIO()):
            exit_code = liwiro_cli.main(["vi", "files", "write", "demo.versa", "--text", "print(1);"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(request_mock.call_args_list[1].args[:2], ("POST", "/platform/vi/files"))
        self.assertEqual(request_mock.call_args_list[1].kwargs["body"]["path"], "demo.versa")
        self.assertEqual(request_mock.call_args_list[1].kwargs["body"]["content"], "print(1);")

    def test_local_start_tracks_background_process(self):
        self.write_state(
            {
                "version": 2,
                "current_profile": "default",
                "profiles": {
                    "default": {
                        "backend": "http://127.0.0.1:5000",
                        "token": "frontend-token",
                        "username": "zulan",
                        "vdb_portal_token": "",
                    }
                },
                "local": {"processes": {}},
            }
        )

        fake_proc = MagicMock()
        fake_proc.pid = 4321

        with patch.object(liwiro_cli, "wait_for_local_health", return_value=(True, "healthy")), patch.object(
            liwiro_cli,
            "find_pids_by_port",
            return_value=[],
        ), patch.object(
            liwiro_cli.subprocess,
            "Popen",
            return_value=fake_proc,
        ), redirect_stdout(io.StringIO()):
            exit_code = liwiro_cli.main(["local", "start", "backend"])

        self.assertEqual(exit_code, 0)
        state = self.read_state()
        entry = state["local"]["processes"]["backend"]
        self.assertEqual(entry["pid"], 4321)
        self.assertTrue(entry["log_file"].endswith(".log"))
        self.assertEqual(entry["backend_url"], "http://127.0.0.1:5000")

    def test_build_local_command_backend_uses_next_free_port_when_default_is_occupied(self):
        args = liwiro_cli.local_start_namespace("backend")

        def fake_can_bind(port: int, host: str = "0.0.0.0") -> bool:
            return port != 5000

        with patch.object(liwiro_cli, "can_bind_tcp_port", side_effect=fake_can_bind):
            command, cwd, env, transport, backend_url, frontend_url, vdb_target = liwiro_cli.build_local_command(args)

        self.assertEqual(command, [str(liwiro_cli.LIWIRO_ROOT / "backend" / "scripts" / "backend-start.sh")])
        self.assertEqual(cwd, liwiro_cli.LIWIRO_ROOT / "backend")
        self.assertEqual(transport, "unixsocket")
        self.assertEqual(backend_url, "http://127.0.0.1:5001")
        self.assertEqual(frontend_url, "http://127.0.0.1:3000")
        self.assertEqual(vdb_target, liwiro_cli.resolve_default_vdb_socket_path())
        self.assertEqual(env["FLASK_PORT"], "5001")
        self.assertEqual(env["LIWIRO_BACKEND_PORT"], "5001")
        self.assertEqual(env["LIWIRO_BACKEND_URL"], "http://127.0.0.1:5001")

    def test_build_local_command_all_uses_next_free_ports_when_defaults_are_occupied(self):
        args = liwiro_cli.local_start_namespace("all")

        def fake_can_bind(port: int, host: str = "0.0.0.0") -> bool:
            return port not in {5000, 3000}

        with patch.object(liwiro_cli, "can_bind_tcp_port", side_effect=fake_can_bind):
            command, cwd, env, transport, backend_url, frontend_url, vdb_target = liwiro_cli.build_local_command(args)

        self.assertEqual(command, [str(liwiro_cli.LIWIRO_ROOT / "scripts" / "start_all.sh")])
        self.assertEqual(cwd, liwiro_cli.REPO_ROOT)
        self.assertEqual(transport, "unixsocket")
        self.assertEqual(backend_url, "http://127.0.0.1:5001")
        self.assertEqual(frontend_url, "http://127.0.0.1:3001")
        self.assertEqual(vdb_target, liwiro_cli.resolve_default_vdb_socket_path())
        self.assertEqual(env["FLASK_PORT"], "5001")
        self.assertEqual(env["LIWIRO_BACKEND_PORT"], "5001")
        self.assertEqual(env["LIWIRO_BACKEND_URL"], "http://127.0.0.1:5001")
        self.assertEqual(env["PORT"], "3001")
        self.assertEqual(env["LIWIRO_FRONTEND_PORT"], "3001")
        self.assertEqual(env["NEXT_PUBLIC_LIWIRO_BACKEND"], "http://127.0.0.1:5001")

    def test_build_local_command_frontend_only_resolves_frontend_port(self):
        args = liwiro_cli.local_start_namespace("frontend")

        def fake_can_bind(port: int, host: str = "0.0.0.0") -> bool:
            return port != 3000

        with patch.object(liwiro_cli, "can_bind_tcp_port", side_effect=fake_can_bind):
            _, _, env, _, backend_url, frontend_url, _ = liwiro_cli.build_local_command(args)

        self.assertEqual(frontend_url, "http://127.0.0.1:3001")
        self.assertEqual(backend_url, "http://127.0.0.1:5000")
        self.assertEqual(env["PORT"], "3001")
        self.assertEqual(env["LIWIRO_FRONTEND_PORT"], "3001")
        self.assertEqual(env["NEXT_PUBLIC_LIWIRO_BACKEND"], "http://127.0.0.1:5000")

    def test_stop_local_target_uses_tracked_dynamic_port_when_pid_is_stale(self):
        self.write_state(
            {
                "version": 2,
                "current_profile": "default",
                "profiles": {
                    "default": {
                        "backend": "http://127.0.0.1:5000",
                        "token": "frontend-token",
                        "username": "zulan",
                        "vdb_portal_token": "",
                    }
                },
                "local": {
                    "processes": {
                        "backend": {
                            "pid": 0,
                            "backend_url": "http://127.0.0.1:5007",
                            "frontend_url": "http://127.0.0.1:3000",
                            "vdb_http_url": liwiro_cli.DEFAULT_VDB_HTTP_URL,
                            "vdb_socket_path": liwiro_cli.resolve_default_vdb_socket_path(),
                        }
                    }
                },
            }
        )
        ctx = liwiro_cli.CliContext(
            args=liwiro_cli.argparse.Namespace(json=False, target="backend"),
            state=liwiro_cli.load_state(),
            profile_name="default",
            profile=liwiro_cli.load_state()["profiles"]["default"],
            client=MagicMock(),
        )

        with patch.object(liwiro_cli, "find_pids_by_port", return_value=[7007]) as find_mock, patch.object(
            liwiro_cli,
            "terminate_pid",
            return_value=True,
        ) as terminate_mock:
            result = liwiro_cli.stop_local_target(ctx, "backend")

        find_mock.assert_called_once_with(5007)
        terminate_mock.assert_called_once_with(7007)
        self.assertTrue(result["stopped"])
        self.assertEqual(result["target"], "backend")
        self.assertNotIn("backend", self.read_state()["local"]["processes"])

    def test_shell_prompt_formats_root_area_and_service_contexts(self):
        session = liwiro_cli.ShellSession(profile_name="default", backend="http://127.0.0.1:5000", timeout=30)
        self.assertEqual(session.prompt(), "liwiro!> ")

        session.area = "vdb"
        self.assertEqual(session.prompt(), "liwiro:vdb> ")

        session.area = "service"
        session.service_id = "295465"
        session.service_name = "auth-api"
        self.assertEqual(session.prompt(), "liwiro:[auth-api]> ")

    def test_translate_service_context_command_injects_service_id(self):
        session = liwiro_cli.ShellSession(
            profile_name="default",
            backend="http://127.0.0.1:5000",
            timeout=30,
            area="service",
            service_id="295465",
            service_name="auth-api",
        )

        with patch.object(liwiro_cli, "ensure_service_context_valid", return_value=None):
            argv = liwiro_cli.translate_service_context_command(session, ["show", "--out-file", "/tmp/service.json"])

        self.assertEqual(argv, ["services", "show", "295465", "--out-file", "/tmp/service.json"])

    def test_translate_services_area_use_command_switches_to_service_context(self):
        session = liwiro_cli.ShellSession(profile_name="default", backend="http://127.0.0.1:5000", timeout=30, area="services")

        action, payload = liwiro_cli.translate_shell_command(session, ["use", "auth-api"])

        self.assertEqual(action, "use-service")
        self.assertEqual(payload, "auth-api")

    def test_services_list_requires_sign_in(self):
        with self.assertRaisesRegex(liwiro_cli.CliError, "Sign in required"):
            liwiro_cli.main(["services", "list"])

    def test_local_start_requires_sign_in(self):
        with patch.object(liwiro_cli.subprocess, "Popen") as popen_mock:
            with self.assertRaisesRegex(liwiro_cli.CliError, "Sign in required"):
                liwiro_cli.main(["local", "start", "backend"])
        popen_mock.assert_not_called()

    def test_ensure_log_dir_falls_back_when_primary_is_not_writable(self):
        def fake_named_tempfile(*args, **kwargs):
            if kwargs.get("dir") == str(self.log_dir):
                raise PermissionError("primary log dir not writable")
            handle = MagicMock()
            handle.__enter__.return_value = handle
            handle.__exit__.return_value = False
            return handle

        with patch.object(liwiro_cli.tempfile, "NamedTemporaryFile", side_effect=fake_named_tempfile):
            selected = liwiro_cli.ensure_log_dir()

        self.assertEqual(selected, self.fallback_log_dir)

    def test_shell_help_mentions_exit_and_stdin(self):
        session = liwiro_cli.ShellSession(profile_name="default", backend="http://127.0.0.1:5000", timeout=30, area="services")

        with patch.object(liwiro_cli, "shell_is_signed_in", return_value=False), redirect_stdout(io.StringIO()) as output:
            liwiro_cli.render_shell_help(session, [])

        rendered = output.getvalue()
        self.assertIn("exit", rendered)
        self.assertIn("Ctrl-D", rendered)
        self.assertIn("--stdin", rendered)
        self.assertIn("back", rendered)

    def test_shell_enter_protected_area_requires_sign_in(self):
        session = liwiro_cli.ShellSession(profile_name="default", backend="http://127.0.0.1:5000", timeout=30)

        with patch.object(liwiro_cli, "shell_is_signed_in", return_value=False), self.assertRaisesRegex(liwiro_cli.CliError, "Sign in required"):
            liwiro_cli.enforce_shell_area_access(session, "services")

    def test_shell_public_areas_are_available_before_sign_in(self):
        session = liwiro_cli.ShellSession(profile_name="default", backend="http://127.0.0.1:5000", timeout=30)

        liwiro_cli.enforce_shell_area_access(session, "auth")
        liwiro_cli.enforce_shell_area_access(session, "profiles")

    def test_invalid_saved_shell_token_is_cleared(self):
        self.write_state(
            {
                "version": 2,
                "current_profile": "default",
                "profiles": {
                    "default": {
                        "backend": "http://127.0.0.1:5000",
                        "token": "stale-token",
                        "username": "zulan",
                        "vdb_portal_token": "portal-123",
                    }
                },
                "local": {"processes": {}},
            }
        )
        session = liwiro_cli.ShellSession(profile_name="default", backend="http://127.0.0.1:5000", timeout=30)

        with patch.object(
            liwiro_cli.LiwiroClient,
            "request",
            side_effect=[
                {"configured": True},
                liwiro_cli.CliHttpError("unauthorized", 401, {"error": "unauthorized"}),
            ],
        ):
            signed_in = liwiro_cli.shell_is_signed_in(session)

        self.assertFalse(signed_in)
        state = self.read_state()
        profile = state["profiles"]["default"]
        self.assertEqual(profile["token"], "")
        self.assertEqual(profile["username"], "")
        self.assertEqual(profile["vdb_portal_token"], "")

    def test_root_help_mentions_shell_exit_and_sign_in(self):
        parser = liwiro_cli.build_parser()

        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()) as output:
            parser.parse_args(["--help"])

        rendered = output.getvalue()
        self.assertIn("Ctrl-D", rendered)
        self.assertIn("auth login", rendered)
        self.assertIn("help --stdin", rendered)

    def test_services_generate_help_mentions_stdin_example(self):
        parser = liwiro_cli.build_parser()

        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()) as output:
            parser.parse_args(["services", "generate", "--help"])

        rendered = output.getvalue()
        self.assertIn("--stdin", rendered)
        self.assertIn("cat ./examples/auth-service.json", rendered)
        self.assertIn("$EDITOR", rendered)

    def test_prompt_uses_color_when_forced(self):
        session = liwiro_cli.ShellSession(profile_name="default", backend="http://127.0.0.1:5000", timeout=30, area="vdb")

        with patch.object(liwiro_cli, "supports_color", return_value=True):
            prompt = session.prompt()

        self.assertIn("\033[", prompt)
        self.assertIn("vdb", prompt)

    def test_no_arg_tty_starts_shell(self):
        stdin_mock = MagicMock()
        stdin_mock.isatty.return_value = True

        with patch.object(liwiro_cli, "run_cli_command", return_value=0) as run_mock, patch.object(
            liwiro_cli.sys,
            "stdin",
            stdin_mock,
        ):
            exit_code = liwiro_cli.main([])

        self.assertEqual(exit_code, 0)
        run_mock.assert_called_once_with(["shell"])


if __name__ == "__main__":
    unittest.main()
