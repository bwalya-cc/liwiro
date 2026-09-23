#!/usr/bin/env python3
# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

from __future__ import annotations

import argparse
import getpass
import json
import os
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, parse, request

try:
    import readline  # type: ignore
except ImportError:  # pragma: no cover
    readline = None


REPO_ROOT = Path(__file__).resolve().parents[2]
LIWIRO_ROOT = REPO_ROOT / "liwiro"
VERUN_ROOT = REPO_ROOT / "verun"
DEFAULT_BACKEND = (
    os.environ.get("LIWIRO_BACKEND_URL")
    or os.environ.get("NEXT_PUBLIC_LIWIRO_BACKEND")
    or "http://127.0.0.1:5000"
)
DEFAULT_FRONTEND_URL = "http://127.0.0.1:3000"
DEFAULT_VDB_HTTP_URL = "http://127.0.0.1:1957"
DEFAULT_PROFILE = "default"
STATE_PATH = Path.home() / ".liwiro_cli.json"
LOCAL_RUNTIME_ROOT = Path.home() / ".liwiro_cli_runtime"
LOCAL_LOG_DIR = LOCAL_RUNTIME_ROOT / "logs"
FALLBACK_STATE_PATH = REPO_ROOT / "tmp" / ".liwiro_cli.json"
FALLBACK_RUNTIME_ROOT = REPO_ROOT / "tmp" / "liwiro_cli_runtime"
FALLBACK_LOG_DIR = FALLBACK_RUNTIME_ROOT / "logs"
LOCAL_VDB_LICENSE_FILE = VERUN_ROOT / "vdb" / "__data__" / "sys" / "mit-license-acceptance.json"
ANSI_RESET = "\033[0m"
ANSI_STYLES = {
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
}
LOCAL_BACKEND_HOSTS = {"127.0.0.1", "localhost", "0.0.0.0", "::1"}

SETTING_KEYS = {
    "productionMode": False,
    "startServicesOnStartup": False,
    "autoRefreshServiceStatus": True,
    "deleteDataWithServiceByDefault": True,
    "startServicesAfterGenerationByDefault": True,
    "retryFailedBatchOpsByDefault": True,
}
SETTING_ALIASES = {
    "productionmode": "productionMode",
    "production-mode": "productionMode",
    "startservicesonstartup": "startServicesOnStartup",
    "start-services-on-startup": "startServicesOnStartup",
    "autorefreshservicestatus": "autoRefreshServiceStatus",
    "auto-refresh-service-status": "autoRefreshServiceStatus",
    "deletedatawithservicebydefault": "deleteDataWithServiceByDefault",
    "delete-data-with-service-by-default": "deleteDataWithServiceByDefault",
    "startservicesaftergenerationbydefault": "startServicesAfterGenerationByDefault",
    "start-services-after-generation-by-default": "startServicesAfterGenerationByDefault",
    "retryfailedbatchopsbydefault": "retryFailedBatchOpsByDefault",
    "retry-failed-batch-ops-by-default": "retryFailedBatchOpsByDefault",
}


class CliError(RuntimeError):
    pass


class CliHttpError(CliError):
    def __init__(self, message: str, status_code: int, payload: Any = None):
        super().__init__(message)
        self.status_code = int(status_code)
        self.payload = payload


@dataclass
class CliContext:
    args: argparse.Namespace
    state: dict
    profile_name: str
    profile: dict
    client: "LiwiroClient"


@dataclass
class ShellSession:
    profile_name: str
    backend: str
    timeout: int
    area: str = "root"
    service_id: str = ""
    service_name: str = ""
    running: bool = True
    auth_valid: bool = False
    auth_checked_at: float = 0.0
    auth_configured: bool | None = None

    def prompt(self) -> str:
        if self.area == "service":
            label = self.service_name or self.service_id or "service"
            return f"{colorize('liwiro', 'bold', 'cyan')}:{colorize(f'[{label}]', 'bold', 'yellow')}> "
        if self.area == "root":
            return f"{colorize('liwiro!>', 'bold', 'cyan')} "
        return f"{colorize('liwiro', 'bold', 'cyan')}:{colorize(self.area, 'bold', 'magenta')}> "


TOP_LEVEL_AREAS = {
    "auth",
    "capabilities",
    "health",
    "license",
    "profiles",
    "settings",
    "users",
    "services",
    "vdb",
    "vi",
    "modules",
    "local",
    "shell",
}
SHELL_AREA_CONTEXTS = {
    "auth",
    "capabilities",
    "health",
    "license",
    "profiles",
    "settings",
    "users",
    "services",
    "vdb",
    "vi",
    "modules",
    "local",
}
SHELL_CONTEXT_COMMANDS = {
    "root": [
        ("menu", "Show the root command menu"),
        ("help [command]", "Show contextual help"),
        ("enter <area>", "Switch to an area prompt"),
        ("use service <id|apiName>", "Enter a service management prompt"),
        ("whereami", "Show current profile, backend, and prompt context"),
        ("capabilities ...", "Inspect the shared platform capability catalog"),
        ("auth ...", "Run auth commands"),
        ("services ...", "Run service commands"),
        ("vdb ...", "Run VDB commands"),
        ("vi ...", "Run VI commands"),
        ("modules ...", "Run VI module commands"),
        ("users ...", "Run platform user commands"),
        ("local ...", "Run local operator commands"),
        ("exit", "Exit the shell"),
    ],
    "services": [
        ("list [--full]", "List services"),
        ("show <service_id>", "Show one service"),
        ("use <service_id|apiName>", "Enter that service's prompt"),
        ("generate <file>|--edit|--stdin", "Generate a service"),
        ("update <service_id> ...", "Update a service"),
        ("start <service_id>", "Start a service"),
        ("stop <service_id>", "Stop a service"),
        ("delete <service_id> [--yes]", "Delete a service"),
        ("auth-keys <service_id> [--out-dir DIR]", "Export auth-service keys"),
        ("back", "Return to liwiro!>"),
    ],
    "service": [
        ("show", "Show the current service"),
        ("start", "Start the current service"),
        ("stop", "Stop the current service"),
        ("update ...", "Update the current service"),
        ("delete [--yes]", "Delete the current service"),
        ("auth-keys [--out-dir DIR]", "Export auth keys for the current service"),
        ("manager-state --edit|--file PATH|--stdin", "Update only manager_state for the current service"),
        ("use <service_id|apiName>", "Switch to another service prompt"),
        ("back", "Return to liwiro:services>"),
    ],
    "vdb": [
        ("status", "Show VDB connection and portal session state"),
        ("connect [--mode app|super_admin]", "Create a VDB portal session"),
        ("disconnect", "Clear the stored VDB portal session"),
        ("whoami", "Run VDB whoami"),
        ("context", "Show VDB context"),
        ("query <json>|--from-file|--stdin|--edit", "Submit a raw VDB query"),
        ("export --domain NAME|--all-domains", "Export VDB domains"),
        ("options", "List VDB options"),
        ("domains list|create", "Manage VDB domains"),
        ("back", "Return to liwiro!>"),
    ],
    "vi": [
        ("status", "Show VI connection status"),
        ("config get|set", "Read or update VI config"),
        ("dirs list [path]", "Browse VI directories"),
        ("files list|read|write|move|delete", "Manage VI files"),
        ("run <path>", "Execute a VI file"),
        ("repl start|send|stop", "Use the VI REPL"),
        ("back", "Return to liwiro!>"),
    ],
    "modules": [
        ("catalog", "Show visible modules and reserved names"),
        ("list", "List visible modules"),
        ("show <name>", "Show one module"),
        ("create <name> ...", "Create a module"),
        ("update <name> ...", "Update a module"),
        ("delete <name> [--yes]", "Delete a module"),
        ("assign-domain <name> <domain...>", "Assign domains to a module"),
        ("back", "Return to liwiro!>"),
    ],
    "users": [
        ("list", "List users"),
        ("show <username>", "Show one user"),
        ("create <username> ...", "Create a user"),
        ("update <username> ...", "Update a user"),
        ("delete <username> [--yes]", "Delete a user"),
        ("back", "Return to liwiro!>"),
    ],
    "local": [
        ("status [target]", "Show local process and health status"),
        ("start <target>", "Start local services"),
        ("stop <target>", "Stop local services"),
        ("restart <target>", "Restart local services"),
        ("logs <target> [--lines N]", "Show tracked logs"),
        ("back", "Return to liwiro!>"),
    ],
    "auth": [
        ("status", "Show setup/auth status"),
        ("vdb-status", "Probe VDB connection status"),
        ("login", "Authenticate or bootstrap"),
        ("me", "Show the current Liwiro session"),
        ("logout", "Clear the auth session"),
        ("back", "Return to liwiro!>"),
    ],
    "capabilities": [
        ("list [--client verse|cli|ui]", "List platform capabilities from the shared catalog"),
        ("show <capability_id>", "Show one capability definition"),
        ("back", "Return to liwiro!>"),
    ],
    "profiles": [
        ("list", "List saved profiles"),
        ("show [name]", "Show one profile"),
        ("use <name>", "Switch active profile"),
        ("set-backend <name> <url>", "Create or update a backend profile"),
        ("delete <name> [--yes]", "Delete a profile"),
        ("back", "Return to liwiro!>"),
    ],
    "settings": [
        ("show", "Show platform settings"),
        ("set KEY=VALUE ...", "Update platform settings"),
        ("back", "Return to liwiro!>"),
    ],
    "health": [
        ("check", "Run a control-plane health check"),
        ("back", "Return to liwiro!>"),
    ],
    "license": [
        ("show", "Show license disclosure"),
        ("back", "Return to liwiro!>"),
    ],
}
SHELL_CONTEXT_DETAILS = {
    "root": {
        "help": "Syntax: help [command]\nExamples:\n  help\n  help exit\n  help --stdin\nShows contextual shell help for the current prompt.",
        "menu": "Syntax: menu\nShows a menu-style command list for the current prompt.",
        "enter": "Syntax: enter <area>\nExamples:\n  enter services\n  enter vdb\nSwitches the prompt into an area context so commands can be shorter.",
        "use service": "Syntax: use service <process_id|apiName>\nExample:\n  use service auth-api\nResolves the service and enters liwiro:[service_name]>.",
        "whereami": "Syntax: whereami\nShows the current profile, backend, prompt context, and selected service if any.",
        "exit": "Syntax: exit\nAliases: quit\nAlso works with Ctrl-D at the prompt.\nCloses the interactive shell.",
        "back": "Syntax: back\nIn a service prompt it returns to liwiro:services>.\nIn an area prompt it returns to liwiro!>.",
        "stdin": "Syntax: --stdin\nMany create, update, query, and write commands can read JSON or source from standard input.\nExamples:\n  cat service.json | ./liwiro.sh services generate --stdin\n  cat query.json | ./liwiro.sh vdb query --stdin\n  printf 'print(\"ok\")' | ./liwiro.sh vi repl send --stdin\nInside the interactive shell, run the command first, paste the payload, then press Ctrl-D to finish stdin.",
        "--stdin": "Syntax: --stdin\nMany create, update, query, and write commands can read JSON or source from standard input.\nExamples:\n  cat service.json | ./liwiro.sh services generate --stdin\n  cat query.json | ./liwiro.sh vdb query --stdin\n  printf 'print(\"ok\")' | ./liwiro.sh vi repl send --stdin\nInside the interactive shell, run the command first, paste the payload, then press Ctrl-D to finish stdin.",
    },
    "services": {
        "use": "Syntax: use <process_id|apiName>\nExample:\n  use 295465\nEnters liwiro:[service_name]> for the selected service.",
        "generate": "Syntax: generate <lapis_file>\n   or: generate --edit\n   or: generate --stdin\nRuns the existing services generate flow from the services prompt.\nUse --stdin to pipe LAPIS JSON from another command or file.",
        "auth-keys": "Syntax: auth-keys <service_id> [--out-dir DIR]\nExports auth-service signing material.",
    },
    "service": {
        "update": "Syntax: update [lapis_file] [--edit] [--stdin] [--no-restart]\nRuns services update for the current service without requiring the service id.\nUse --stdin to pipe LAPIS JSON directly into the current service update.",
        "manager-state": "Syntax: manager-state --edit\n   or: manager-state --file PATH\n   or: manager-state --stdin\nUpdates only manager_state for the current service.\nUse --stdin when piping manager_state JSON into the shell command.",
        "auth-keys": "Syntax: auth-keys [--out-dir DIR]\nRuns services download-auth-keys for the selected service.",
    },
    "vdb": {
        "query": "Syntax: query <json>\n   or: query --from-file PATH\n   or: query --stdin\n   or: query --edit\nSubmits a raw VDB query using the active portal session.",
        "export": "Syntax: export --domain NAME [--domain NAME2] [--out-dir DIR]\n   or: export --all-domains\nRuns the VDB export flow.",
    },
    "vi": {
        "files": "Syntax: files list|read|write|move|delete ...\nExamples:\n  files list\n  files write examples/demo.versa --edit\n  files move old.versa new.versa",
        "repl": "Syntax: repl start|send|stop\nExamples:\n  repl start\n  repl send 'print(\"hello\")'",
    },
    "modules": {
        "create": "Syntax: create <name> [--edit|--from-file PATH|other flags]\nCreates a VI module from the modules prompt.",
        "assign-domain": "Syntax: assign-domain <name> <domain...>\nAssigns one or more domains to a module.",
    },
    "capabilities": {
        "list": "Syntax: list [--client verse|cli|ui] [--surface-id ID] [--executable-only]\nLists shared platform capabilities from the backend registry.",
        "show": "Syntax: show <capability_id>\nDisplays one capability definition from the backend registry.",
    },
}
CRITICAL_SHELL_AREAS = {"settings", "users", "services", "vdb", "vi", "modules", "local"}
SHELL_PUBLIC_AREAS = {"auth", "capabilities", "profiles"}
CLI_ROOT_EPILOG = """Quick start:
  liwiro_cli auth login --username zulan
  liwiro_cli capabilities list --client cli
  liwiro_cli shell
  liwiro_cli services list

Shell notes:
  Run `liwiro_cli shell` or just `./liwiro.sh` from a TTY.
  Exit the shell with `exit`, `quit`, or Ctrl-D.
  Inside the shell, `help --stdin` explains how to finish piped/typed stdin payloads.

Auth notes:
  Management commands for settings, users, services, VDB, VI, modules, and mutating local operations
  require a signed-in Liwiro profile.
"""
SHELL_HELP_EPILOG = """Examples:
  liwiro_cli shell
  liwiro!> help exit
  liwiro!> enter services
  liwiro:services> help generate

Exit with `exit`, `quit`, or Ctrl-D.
Use `help --stdin` for stdin-driven workflows.
"""
SERVICES_GENERATE_HELP = """Generate a service from LAPIS JSON.

Input sources:
  - positional LAPIS JSON file path
  - `--stdin` to read JSON from standard input
  - `--edit` to open a temp JSON file in $EDITOR
"""
SERVICES_GENERATE_EPILOG = """Examples:
  liwiro_cli services generate ./examples/auth-service.json
  cat ./examples/auth-service.json | liwiro_cli services generate --stdin
  liwiro_cli services generate --edit --no-start
"""
SERVICES_UPDATE_HELP = """Update an existing service using LAPIS JSON and optional manager_state JSON.

You may provide LAPIS config with a file path, `--stdin`, or `--edit`.
Manager state can be supplied separately with `--manager-state-file`, `--manager-state-stdin`, or `--manager-state-edit`.
"""
SERVICES_UPDATE_EPILOG = """Examples:
  liwiro_cli services update 295465 ./examples/auth-service.json
  cat ./examples/auth-service.json | liwiro_cli services update 295465 --stdin
  liwiro_cli services update 295465 --edit --manager-state-edit
  cat ./tmp/manager-state.json | liwiro_cli services update 295465 --manager-state-stdin
"""
VDB_QUERY_HELP = """Submit a readable VDB command through the active portal session.

Command input can come inline, from `--from-file`, `--stdin`, or `--edit`.
"""
VDB_QUERY_EPILOG = """Examples:
  liwiro_cli vdb query 'read users'
  cat ./tmp/query.vql | liwiro_cli vdb query --stdin
  liwiro_cli vdb query --edit
"""
VI_FILES_WRITE_HELP = """Create or update a VI portal file.

Content can come from `--from-file`, `--stdin`, `--edit`, or `--text`.
"""
VI_FILES_WRITE_EPILOG = """Examples:
  liwiro_cli vi files write demo/hello.versa --text 'print("hello")'
  cat ./demo/hello.versa | liwiro_cli vi files write demo/hello.versa --stdin
  liwiro_cli vi files write demo/hello.versa --edit
"""
VI_REPL_SEND_HELP = """Send source to the active VI REPL session.

REPL input can come from inline source, `--from-file`, `--stdin`, or `--edit`.
"""
VI_REPL_SEND_EPILOG = """Examples:
  liwiro_cli vi repl send 'print("hello")'
  printf 'print("hello")' | liwiro_cli vi repl send --stdin
  liwiro_cli vi repl send --edit
"""


def supports_color(stream=None) -> bool:
    handle = stream or sys.stdout
    if str(os.environ.get("NO_COLOR") or "").strip():
        return False
    forced = str(os.environ.get("LIWIRO_CLI_COLOR") or "").strip().lower()
    if forced in {"1", "true", "yes", "on"}:
        return True
    return bool(getattr(handle, "isatty", lambda: False)())


def colorize(text: Any, *styles: str, stream=None) -> str:
    output = str(text)
    if not supports_color(stream):
        return output
    prefix = "".join(ANSI_STYLES.get(style, "") for style in styles)
    return f"{prefix}{output}{ANSI_RESET}" if prefix else output


def print_heading(text: str) -> None:
    print(colorize(text, "bold", "cyan"))


def print_info(text: str) -> None:
    print(colorize(text, "cyan"))


def print_success(text: str) -> None:
    print(colorize(text, "green"))


def print_warning(text: str) -> None:
    print(colorize(text, "yellow"), file=sys.stderr)


def print_error_line(text: str) -> None:
    print(colorize(text, "red", "bold", stream=sys.stderr), file=sys.stderr)


def format_label(label: str) -> str:
    return colorize(label, "bold", "blue")


def parse_json_bytes(raw_bytes: bytes):
    text = raw_bytes.decode("utf-8", errors="replace")
    if not text.strip():
        return {}
    try:
        return json.loads(text)
    except Exception:
        return {"raw": text}


def parse_json_text(text: str, label: str = "JSON", expected_type: type | tuple[type, ...] | None = None):
    try:
        data = json.loads(str(text or ""))
    except json.JSONDecodeError as exc:
        raise CliError(f"Invalid {label}: {exc}") from exc
    if expected_type is not None and not isinstance(data, expected_type):
        if isinstance(expected_type, tuple):
            names = ", ".join(item.__name__ for item in expected_type)
        else:
            names = expected_type.__name__
        raise CliError(f"{label} must decode to {names}")
    return data


def _normalize_profile(profile: dict | None) -> dict:
    data = dict(profile or {})
    return {
        "backend": str(data.get("backend") or DEFAULT_BACKEND).strip() or DEFAULT_BACKEND,
        "token": str(data.get("token") or "").strip(),
        "username": str(data.get("username") or "").strip(),
        "vdb_portal_token": str(data.get("vdb_portal_token") or data.get("vdbPortalToken") or "").strip(),
    }


def _normalize_local_processes(raw: dict | None) -> dict:
    entries = {}
    if not isinstance(raw, dict):
        return entries
    for key, value in raw.items():
        if not isinstance(value, dict):
            continue
        try:
            pid = int(value.get("pid"))
        except Exception:
            pid = 0
        entries[str(key)] = {
            "pid": pid,
            "log_file": str(value.get("log_file") or "").strip(),
            "command": list(value.get("command") or []),
            "cwd": str(value.get("cwd") or "").strip(),
            "started_at": str(value.get("started_at") or "").strip(),
            "transport": str(value.get("transport") or "").strip(),
            "backend_url": str(value.get("backend_url") or "").strip(),
            "frontend_url": str(value.get("frontend_url") or "").strip(),
            "vdb_http_url": str(value.get("vdb_http_url") or "").strip(),
            "vdb_socket_path": str(value.get("vdb_socket_path") or "").strip(),
        }
    return entries


def _default_state() -> dict:
    return {
        "version": 2,
        "current_profile": DEFAULT_PROFILE,
        "profiles": {DEFAULT_PROFILE: _normalize_profile({})},
        "local": {"processes": {}},
    }


def _candidate_state_paths() -> list[Path]:
    paths = []
    for item in [STATE_PATH, FALLBACK_STATE_PATH]:
        if item not in paths:
            paths.append(item)
    return paths


def _candidate_log_dirs() -> list[Path]:
    paths = []
    for item in [LOCAL_LOG_DIR, FALLBACK_LOG_DIR]:
        if item not in paths:
            paths.append(item)
    return paths


def _normalize_state(data: dict | None) -> dict:
    if not isinstance(data, dict):
        return _default_state()

    state = _default_state()
    raw_profiles = data.get("profiles")
    if isinstance(raw_profiles, dict) and raw_profiles:
        profiles = {}
        for name, value in raw_profiles.items():
            normalized_name = str(name or "").strip() or DEFAULT_PROFILE
            profiles[normalized_name] = _normalize_profile(value if isinstance(value, dict) else {})
        state["profiles"] = profiles or {DEFAULT_PROFILE: _normalize_profile({})}
        current_profile = str(data.get("current_profile") or data.get("currentProfile") or "").strip()
        state["current_profile"] = current_profile if current_profile in state["profiles"] else next(iter(state["profiles"]))
    else:
        legacy_profile = _normalize_profile(data)
        legacy_portal_token = str(data.get("vdb_portal_token") or data.get("vdbPortalToken") or "").strip()
        legacy_profile["vdb_portal_token"] = legacy_portal_token
        state["profiles"] = {DEFAULT_PROFILE: legacy_profile}
        state["current_profile"] = DEFAULT_PROFILE

    raw_local = data.get("local") if isinstance(data.get("local"), dict) else {}
    raw_processes = raw_local.get("processes") if isinstance(raw_local.get("processes"), dict) else data.get("local_processes")
    state["local"] = {"processes": _normalize_local_processes(raw_processes)}
    return state


def load_state() -> dict:
    for path in _candidate_state_paths():
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return _default_state()
        return _normalize_state(data)
    return _default_state()


def save_state(state: dict) -> None:
    payload = json.dumps(_normalize_state(state), indent=2)
    last_error = None
    for path in _candidate_state_paths():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload, encoding="utf-8")
            return
        except PermissionError as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error


def ensure_log_dir() -> Path:
    last_error = None
    for path in _candidate_log_dirs():
        try:
            path.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=str(path), prefix=".liwiro-log-probe-", delete=True):
                pass
            return path
        except (PermissionError, OSError) as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    raise CliError("Unable to create a writable local log directory")


def get_profile(state: dict, name: str, create: bool = True) -> tuple[str, dict]:
    profiles = state.setdefault("profiles", {})
    profile_name = str(name or state.get("current_profile") or DEFAULT_PROFILE).strip() or DEFAULT_PROFILE
    if profile_name not in profiles:
        if not create:
            raise CliError(f"Profile '{profile_name}' does not exist")
        profiles[profile_name] = _normalize_profile({})
    state["current_profile"] = profile_name if state.get("current_profile") in profiles else profile_name
    return profile_name, profiles[profile_name]


def load_text_file(path: str, label: str = "file") -> str:
    file_path = Path(path).expanduser().resolve()
    try:
        return file_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise CliError(f"{label.capitalize()} not found: {file_path}") from exc


def load_json_file(path: str, label: str = "JSON", expected_type: type | tuple[type, ...] | None = dict):
    return parse_json_text(load_text_file(path, label=label), label=label, expected_type=expected_type)


def parse_json_option(value: str, label: str, expected_type: type | tuple[type, ...] | None = None):
    raw = str(value or "").strip()
    if not raw:
        raise CliError(f"{label} is required")
    candidate = Path(raw).expanduser()
    if candidate.exists() and candidate.is_file():
        return load_json_file(str(candidate), label=label, expected_type=expected_type)
    return parse_json_text(raw, label=label, expected_type=expected_type)


def read_stdin_text() -> str:
    return sys.stdin.read()


def editor_command() -> list[str]:
    value = str(os.environ.get("VISUAL") or os.environ.get("EDITOR") or "").strip()
    if not value:
        raise CliError("No editor configured. Set $EDITOR or use --from-file/--stdin.")
    return shlex.split(value)


def edit_text(initial_text: str, suffix: str = ".txt") -> str:
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=suffix, delete=False) as handle:
            temp_path = Path(handle.name)
            handle.write(str(initial_text or ""))
        command = editor_command() + [str(temp_path)]
        result = subprocess.run(command, check=False)
        if result.returncode != 0:
            raise CliError(f"Editor exited with status {result.returncode}")
        return temp_path.read_text(encoding="utf-8")
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def edit_json_object(initial_data: dict, label: str) -> dict:
    initial_text = json.dumps(initial_data, indent=2) + "\n"
    return parse_json_text(edit_text(initial_text, suffix=".json"), label=label, expected_type=dict)


def coerce_bool(value: str) -> bool:
    lowered = str(value or "").strip().lower()
    if lowered in {"1", "true", "yes", "on", "enable", "enabled"}:
        return True
    if lowered in {"0", "false", "no", "off", "disable", "disabled"}:
        return False
    raise CliError(f"Expected boolean value, got '{value}'")


def canonical_setting_name(name: str) -> str:
    raw = str(name or "").strip()
    if raw in SETTING_KEYS:
        return raw
    lowered = raw.lower()
    if lowered in SETTING_ALIASES:
        return SETTING_ALIASES[lowered]
    squashed = lowered.replace("_", "").replace("-", "")
    for candidate in SETTING_KEYS:
        if candidate.lower() == squashed:
            return candidate
    raise CliError(f"Unknown setting '{name}'")


def safe_filename_segment(value: str, fallback: str = "service") -> str:
    text = str(value or "").strip().lower()
    chars = []
    for char in text:
        if char.isalnum() or char in {"-", "_", "."}:
            chars.append(char)
        else:
            chars.append("-")
    normalized = "".join(chars).strip("-_.")
    return normalized or fallback


def normalize_service_access(values: list[str] | None) -> list[str]:
    if values is None:
        return []
    seen = set()
    output = []
    for item in values:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def is_local_backend_url(url: str) -> bool:
    parsed = parse.urlparse(str(url or "").strip())
    if parsed.scheme != "http":
        return False
    host = str(parsed.hostname or "").strip().lower()
    return host in LOCAL_BACKEND_HOSTS


def backend_health_url(backend_url: str) -> str:
    return f"{str(backend_url or DEFAULT_BACKEND).rstrip('/')}/auth/status"


def cleanup_stale_local_entries_in_state(state: dict) -> None:
    processes = state_local_processes(state)
    stale = [name for name, item in processes.items() if not is_pid_running(int(item.get("pid") or 0))]
    changed = False
    for name in stale:
        del processes[name]
        changed = True
    if changed:
        save_state(state)


def local_process_entry_for_state(state: dict, target: str) -> dict | None:
    cleanup_stale_local_entries_in_state(state)
    return state_local_processes(state).get(target)


def save_local_process_for_state(state: dict, target: str, entry: dict) -> None:
    processes = state_local_processes(state)
    processes[target] = entry
    save_state(state)


def local_start_namespace(
    target: str,
    *,
    backend_port: int = 5000,
    frontend_port: int = 3000,
    vdb_transport: str = "unixsocket",
    vdb_http_url: str = DEFAULT_VDB_HTTP_URL,
    vdb_socket_path: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        target=target,
        backend_port=int(backend_port or 5000),
        frontend_port=int(frontend_port or 3000),
        vdb_transport=str(vdb_transport or "unixsocket").strip().lower() or "unixsocket",
        vdb_http_url=str(vdb_http_url or DEFAULT_VDB_HTTP_URL).strip() or DEFAULT_VDB_HTTP_URL,
        vdb_socket_path=str(vdb_socket_path or resolve_default_vdb_socket_path()).strip() or resolve_default_vdb_socket_path(),
        foreground=False,
    )


def start_local_target_in_background(
    state: dict,
    target: str,
    *,
    backend_port: int = 5000,
    frontend_port: int = 3000,
    vdb_transport: str = "unixsocket",
    vdb_http_url: str = DEFAULT_VDB_HTTP_URL,
    vdb_socket_path: str | None = None,
) -> dict:
    args = local_start_namespace(
        target,
        backend_port=backend_port,
        frontend_port=frontend_port,
        vdb_transport=vdb_transport,
        vdb_http_url=vdb_http_url,
        vdb_socket_path=vdb_socket_path,
    )
    existing = local_process_entry_for_state(state, target)
    if existing and is_pid_running(int(existing.get("pid") or 0)):
        return {
            "target": target,
            "pid": existing.get("pid"),
            "log_file": existing.get("log_file"),
            "healthy": True,
            "backend_url": str(existing.get("backend_url") or ""),
            "frontend_url": str(existing.get("frontend_url") or ""),
            "vdb_target": str(existing.get("vdb_http_url") or existing.get("vdb_socket_path") or ""),
            "already_running": True,
        }

    if target in {"vdb", "all"}:
        ensure_vdb_mit_acceptance()

    command, cwd, env, transport, backend_url, frontend_url, vdb_target = build_local_command(args)
    if target == "backend" and http_ok(backend_health_url(backend_url), timeout=2):
        return {
            "target": target,
            "pid": "",
            "log_file": "",
            "healthy": True,
            "backend_url": backend_url,
            "frontend_url": frontend_url,
            "vdb_target": vdb_target,
            "already_running": True,
        }

    port = parse.urlparse(backend_url).port or 5000
    if target == "backend":
        fallback = find_pids_by_port(int(port))
        if fallback:
            ok, message = wait_for_local_health(
                target=target,
                transport=transport,
                backend_url=backend_url,
                frontend_url=frontend_url,
                vdb_http_url=vdb_target if transport == "http" else DEFAULT_VDB_HTTP_URL,
                vdb_socket_path=vdb_target if transport != "http" else resolve_default_vdb_socket_path(),
            )
            if ok:
                return {
                    "target": target,
                    "pid": fallback[0],
                    "log_file": "",
                    "healthy": True,
                    "backend_url": backend_url,
                    "frontend_url": frontend_url,
                    "vdb_target": vdb_target,
                    "already_running": True,
                }
            raise CliError(f"Backend appears to be starting already, but did not become healthy: {message}")

    log_dir = ensure_log_dir()
    timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    log_file = log_dir / f"{target}-{timestamp}.log"
    with log_file.open("a", encoding="utf-8") as stream:
        proc = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    ok, message = wait_for_local_health(
        target=target,
        transport=transport,
        backend_url=backend_url,
        frontend_url=frontend_url,
        vdb_http_url=vdb_target if transport == "http" else DEFAULT_VDB_HTTP_URL,
        vdb_socket_path=vdb_target if transport != "http" else resolve_default_vdb_socket_path(),
    )
    entry = {
        "pid": proc.pid,
        "log_file": str(log_file),
        "command": command,
        "cwd": str(cwd),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "transport": transport,
        "backend_url": backend_url,
        "frontend_url": frontend_url,
        "vdb_http_url": vdb_target if transport == "http" else DEFAULT_VDB_HTTP_URL,
        "vdb_socket_path": vdb_target if transport != "http" else resolve_default_vdb_socket_path(),
    }
    save_local_process_for_state(state, target, entry)
    if not ok:
        raise CliError(f"{target} started with pid {proc.pid}, but health checks failed: {message}. See {log_file}")
    return {
        "target": target,
        "pid": proc.pid,
        "log_file": str(log_file),
        "healthy": True,
        "backend_url": backend_url,
        "frontend_url": frontend_url,
        "vdb_target": vdb_target,
        "already_running": False,
    }


def maybe_autostart_local_backend(backend_url: str) -> bool:
    target_backend = str(backend_url or DEFAULT_BACKEND).strip() or DEFAULT_BACKEND
    if not is_local_backend_url(target_backend):
        return False
    if http_ok(backend_health_url(target_backend), timeout=2):
        return False
    parsed = parse.urlparse(target_backend)
    port = int(parsed.port or 5000)
    state = load_state()
    start_local_target_in_background(state, "backend", backend_port=port)
    return True


def path_requires_local_vdb_runtime(path: str) -> bool:
    normalized = "/" + str(path or "").split("?", 1)[0].lstrip("/")
    return (
        normalized == "/generate"
        or normalized.startswith("/services")
        or normalized.startswith("/platform/vdb/")
    )


def auth_status_snapshot(backend_url: str, timeout: int = 3) -> dict:
    ok, payload = read_http_json(backend_health_url(backend_url), timeout=timeout)
    if ok and isinstance(payload, dict):
        return payload
    return {}


def maybe_autostart_local_vdb_runtime(backend_url: str) -> bool:
    target_backend = str(backend_url or DEFAULT_BACKEND).strip() or DEFAULT_BACKEND
    if not is_local_backend_url(target_backend):
        return False

    recovered = maybe_autostart_local_backend(target_backend)
    status_payload = auth_status_snapshot(target_backend, timeout=3)
    if not status_payload:
        return recovered

    transport = _normalize_cli_vdb_transport(
        status_payload.get("vdbTransport") or status_payload.get("defaultVdbTransport") or "unixsocket"
    )
    vdb_server_url = str(
        status_payload.get("vdbServerUrl")
        or status_payload.get("defaultVdbServerUrl")
        or DEFAULT_VDB_HTTP_URL
    ).strip() or DEFAULT_VDB_HTTP_URL
    vdb_socket_path = str(
        status_payload.get("vdbUnixSocketPath")
        or status_payload.get("defaultVdbUnixSocketPath")
        or resolve_default_vdb_socket_path()
    ).strip() or resolve_default_vdb_socket_path()
    vdb_named_pipe_path = str(
        status_payload.get("vdbNamedPipePath")
        or status_payload.get("defaultVdbNamedPipePath")
        or r"\\.\pipe\verun_vdb"
    ).strip() or r"\\.\pipe\verun_vdb"

    if transport == "http":
        health_url = f"{vdb_server_url.rstrip('/')}/health"
        if http_ok(health_url, timeout=2):
            return recovered
        state = load_state()
        start_local_target_in_background(
            state,
            "vdb",
            vdb_transport="http",
            vdb_http_url=vdb_server_url,
            vdb_socket_path=vdb_socket_path,
        )
        return True

    if transport == "namedpipe":
        query_string = parse.urlencode(
            {
                "vdb_transport": transport,
                "vdb_server_url": vdb_server_url,
                "vdb_named_pipe_path": vdb_named_pipe_path,
                "attempt_autostart": "1",
            }
        )
        ok, payload = read_http_json(
            f"{target_backend.rstrip('/')}/auth/vdb-connection-status?{query_string}",
            timeout=5,
        )
        if ok and isinstance(payload, dict) and bool(payload.get("available")):
            return True
        return recovered

    if socket_ok(vdb_socket_path):
        return recovered

    state = load_state()
    start_local_target_in_background(
        state,
        "vdb",
        vdb_transport="unixsocket",
        vdb_http_url=vdb_server_url,
        vdb_socket_path=vdb_socket_path,
    )
    return True


def should_retry_after_local_runtime_recovery(backend_url: str, path: str, status_code: int, message: str) -> bool:
    if not is_local_backend_url(backend_url):
        return False
    if not path_requires_local_vdb_runtime(path):
        return False
    text = str(message or "").strip().lower()
    if status_code == 403 and text == "rbac authorization failed":
        return True
    if "vdb runtime is not ready" in text:
        return True
    if "vdb communication failed" in text:
        return True
    return False


class LiwiroClient:
    def __init__(self, backend: str, token: str = "", timeout: int = 30):
        self.backend = str(backend or DEFAULT_BACKEND).rstrip("/")
        self.token = str(token or "").strip()
        self.timeout = int(timeout)

    def request(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        require_auth: bool = False,
        headers: dict[str, str] | None = None,
        query: dict[str, Any] | None = None,
    ):
        if require_auth and not self.token:
            raise CliError("Not authenticated. Run './liwiro.sh auth login' first.")

        url = path if str(path).startswith("http") else f"{self.backend}{path}"
        if query:
            query_string = parse.urlencode(query, doseq=True)
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{query_string}"

        final_headers = {"Accept": "application/json"}
        if body is not None:
            final_headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        else:
            data = None
        if self.token:
            final_headers["Authorization"] = f"Bearer {self.token}"
        for key, value in (headers or {}).items():
            final_headers[str(key)] = str(value)

        req = request.Request(url, data=data, headers=final_headers, method=method.upper())

        def perform_request():
            with request.urlopen(req, timeout=self.timeout) as response:
                return parse_json_bytes(response.read())

        def extract_http_error(exc: error.HTTPError) -> tuple[Any, str]:
            payload = parse_json_bytes(exc.read())
            message = ""
            if isinstance(payload, dict):
                message = str(payload.get("error") or payload.get("message") or payload.get("raw") or "").strip()
            if not message:
                message = f"HTTP {exc.code}"
            return payload, message

        try:
            return perform_request()
        except error.HTTPError as exc:
            payload, message = extract_http_error(exc)
            if should_retry_after_local_runtime_recovery(self.backend, path, exc.code, message):
                recovered = maybe_autostart_local_vdb_runtime(self.backend)
                if recovered:
                    try:
                        return perform_request()
                    except error.HTTPError as retry_exc:
                        retry_payload, retry_message = extract_http_error(retry_exc)
                        raise CliHttpError(retry_message, retry_exc.code, retry_payload) from retry_exc
                    except error.URLError as retry_exc:
                        raise CliError(f"Could not reach Liwiro backend at {self.backend}: {retry_exc.reason}") from retry_exc
            raise CliHttpError(message, exc.code, payload) from exc
        except error.URLError as exc:
            autostarted = maybe_autostart_local_backend(self.backend)
            if autostarted:
                try:
                    return perform_request()
                except error.HTTPError as retry_exc:
                    retry_payload, retry_message = extract_http_error(retry_exc)
                    raise CliHttpError(retry_message, retry_exc.code, retry_payload) from retry_exc
                except error.URLError as retry_exc:
                    raise CliError(f"Could not reach Liwiro backend at {self.backend}: {retry_exc.reason}") from retry_exc
            raise CliError(f"Could not reach Liwiro backend at {self.backend}: {exc.reason}") from exc


def print_json(data) -> None:
    print(json.dumps(data, indent=2))


def print_kv(data: dict, keys: list[str]) -> None:
    for key in keys:
        print(f"{format_label(key)}: {data.get(key)}")


def print_table(headers: list[str], rows: list[list[Any]]) -> None:
    if not rows:
        print(colorize("(no results)", "dim"))
        return
    normalized_rows = [[str(cell if cell is not None else "") for cell in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in normalized_rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    print(
        "  ".join(
            colorize(header.ljust(widths[index]), "bold", "blue")
            for index, header in enumerate(headers)
        )
    )
    print(colorize("  ".join("-" * widths[index] for index in range(len(headers))), "dim"))
    for row in normalized_rows:
        print("  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)))


def emit(ctx: CliContext, data, renderer=None) -> None:
    if ctx.args.json or renderer is None:
        print_json(data)
    else:
        renderer(data)


def portal_headers(ctx: CliContext) -> dict[str, str]:
    token = str(ctx.profile.get("vdb_portal_token") or "").strip()
    if not token:
        raise CliError("No active VDB portal session. Run './liwiro.sh vdb connect' first.")
    return {"X-VDB-Portal-Token": token}


def set_profile_values(ctx: CliContext, **updates: Any) -> None:
    for key, value in updates.items():
        ctx.profile[key] = value
    ctx.state["profiles"][ctx.profile_name] = ctx.profile
    save_state(ctx.state)


def is_signed_in_profile(profile: dict | None) -> bool:
    return bool(str((profile or {}).get("token") or "").strip())


def shell_is_signed_in(session: ShellSession) -> bool:
    return refresh_shell_auth_state(session)


def sign_in_required_message() -> str:
    return "Sign in required. Run './liwiro.sh auth login' first or complete setup from the auth prompt."


def command_requires_sign_in(args: argparse.Namespace) -> bool:
    area = str(getattr(args, "area", "") or "").strip().lower()
    action = str(getattr(args, "action", "") or "").strip().lower()
    if area in {"settings", "users", "services", "vdb", "vi", "modules"}:
        return True
    if area == "local" and action != "status":
        return True
    if area == "auth" and action in {"me"}:
        return True
    return False


def enforce_sign_in(args: argparse.Namespace, profile: dict) -> None:
    if command_requires_sign_in(args) and not is_signed_in_profile(profile):
        raise CliError(sign_in_required_message())


def enforce_shell_area_access(session: ShellSession, area: str) -> None:
    if area in SHELL_PUBLIC_AREAS:
        return
    if not shell_is_signed_in(session):
        raise CliError(sign_in_required_message())


def state_local_processes(state: dict) -> dict:
    local = state.setdefault("local", {})
    if not isinstance(local, dict):
        local = {}
        state["local"] = local
    processes = local.setdefault("processes", {})
    if not isinstance(processes, dict):
        processes = {}
        local["processes"] = processes
    return processes


def confirm_action(prompt: str, assume_yes: bool = False) -> bool:
    if assume_yes or not sys.stdin.isatty():
        return True
    answer = input(colorize(f"{prompt} [y/N]: ", "bold", "yellow")).strip().lower()
    return answer in {"y", "yes"}


def read_json_payload_for_services(
    *,
    file_path: str | None,
    stdin_flag: bool,
    edit_flag: bool,
    initial_data: dict,
    label: str,
    allow_default: bool = False,
) -> dict:
    chosen = sum(bool(item) for item in [file_path, stdin_flag, edit_flag])
    if chosen > 1:
        raise CliError(f"Choose only one of file, stdin, or edit for {label}")
    if file_path:
        return load_json_file(file_path, label=label, expected_type=dict)
    if stdin_flag:
        return parse_json_text(read_stdin_text(), label=label, expected_type=dict)
    if edit_flag:
        return edit_json_object(initial_data, label=label)
    if allow_default:
        return initial_data
    raise CliError(f"{label} is required")


def read_optional_json_payload(
    *,
    file_path: str | None,
    stdin_flag: bool,
    edit_flag: bool,
    initial_data: dict,
    label: str,
) -> dict | None:
    chosen = sum(bool(item) for item in [file_path, stdin_flag, edit_flag])
    if chosen > 1:
        raise CliError(f"Choose only one of file, stdin, or edit for {label}")
    if chosen == 0:
        return None
    return read_json_payload_for_services(
        file_path=file_path,
        stdin_flag=stdin_flag,
        edit_flag=edit_flag,
        initial_data=initial_data,
        label=label,
    )


def read_text_payload(
    *,
    file_path: str | None,
    stdin_flag: bool,
    edit_flag: bool,
    inline_text: str | None,
    initial_text: str,
    label: str,
    suffix: str,
) -> str:
    chosen = sum(bool(item) for item in [file_path, stdin_flag, edit_flag, inline_text])
    if chosen > 1:
        raise CliError(f"Choose only one content source for {label}")
    if file_path:
        return load_text_file(file_path, label=label)
    if stdin_flag:
        return read_stdin_text()
    if edit_flag:
        return edit_text(initial_text, suffix=suffix)
    if inline_text is not None:
        return inline_text
    return initial_text


def read_http_json(url: str, timeout: int = 3) -> tuple[bool, Any]:
    req = request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return True, parse_json_bytes(response.read())
    except Exception as exc:
        return False, str(exc)


def is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def wait_for_pid_exit(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not is_pid_running(pid):
            return True
        time.sleep(0.15)
    return not is_pid_running(pid)


def terminate_pid(pid: int, timeout: float = 5.0) -> bool:
    if pid <= 0 or not is_pid_running(pid):
        return True
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return True
    if wait_for_pid_exit(pid, timeout=timeout):
        return True
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        return True
    return wait_for_pid_exit(pid, timeout=1.5)


def run_capture(command: list[str], cwd: Path | None = None) -> str:
    try:
        proc = subprocess.run(command, cwd=str(cwd) if cwd else None, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return ""
    if proc.returncode != 0 and not proc.stdout and not proc.stderr:
        return ""
    return f"{proc.stdout}\n{proc.stderr}".strip()


def find_pids_by_port(port: int) -> list[int]:
    if port <= 0:
        return []
    if shutil.which("lsof"):
        output = run_capture(["lsof", f"-tiTCP:{port}", "-sTCP:LISTEN"])
        return sorted({int(line.strip()) for line in output.splitlines() if line.strip().isdigit()})
    if shutil.which("fuser"):
        output = run_capture(["fuser", "-n", "tcp", str(port)])
        return sorted({int(part) for part in output.replace("\n", " ").split() if part.isdigit()})
    if shutil.which("ss"):
        output = run_capture(["ss", "-ltnp"])
        result = set()
        for line in output.splitlines():
            if f":{port} " not in line and not line.rstrip().endswith(f":{port}"):
                continue
            if "pid=" not in line:
                continue
            fragment = line.split("pid=", 1)[1].split(",", 1)[0].strip()
            if fragment.isdigit():
                result.add(int(fragment))
        return sorted(result)
    return []


def can_bind_tcp_port(port: int, host: str = "0.0.0.0") -> bool:
    try:
        port_value = int(port or 0)
    except (TypeError, ValueError):
        return False
    if port_value <= 0 or port_value > 65535:
        return False
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        return not find_pids_by_port(port_value)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((str(host or "0.0.0.0"), port_value))
    except PermissionError:
        return not find_pids_by_port(port_value)
    except OSError:
        return False
    finally:
        sock.close()
    return True


def find_next_free_port(start_port: int) -> int:
    port = max(int(start_port or 0), 1)
    while port <= 65535:
        if can_bind_tcp_port(port):
            return port
        port += 1
    raise CliError(f"No free TCP port available at or above {start_port}")


def resolve_available_local_port(preferred_port: int) -> int:
    port = int(preferred_port or 0)
    if port <= 0:
        raise CliError(f"Invalid local port: {preferred_port}")
    if can_bind_tcp_port(port):
        return port
    return find_next_free_port(port)


def find_pids_by_socket(path_value: str) -> list[int]:
    socket_path = str(path_value or "").strip()
    if not socket_path or not shutil.which("lsof"):
        return []
    output = run_capture(["lsof", "-t", socket_path])
    return sorted({int(line.strip()) for line in output.splitlines() if line.strip().isdigit()})


def http_ok(url: str, timeout: int = 3) -> bool:
    ok, _ = read_http_json(url, timeout=timeout)
    return ok


def socket_ok(socket_path: str, timeout: float = 1.0) -> bool:
    target = str(socket_path or "").strip()
    if not target:
        return False
    path = Path(target)
    if not path.exists() or not path.is_socket():
        return False
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(target)
        return True
    except OSError:
        return False
    finally:
        sock.close()


def wait_for_local_health(target: str, transport: str, backend_url: str, frontend_url: str, vdb_http_url: str, vdb_socket_path: str) -> tuple[bool, str]:
    checks = []
    if target == "backend":
        checks.append(("backend", f"{backend_url.rstrip('/')}/auth/status", "http"))
    elif target == "frontend":
        checks.append(("frontend", f"{frontend_url.rstrip('/')}/login", "http"))
    elif target == "vdb":
        if transport == "http":
            checks.append(("vdb", f"{vdb_http_url.rstrip('/')}/health", "http"))
        else:
            checks.append(("vdb", vdb_socket_path, "socket"))
    else:
        if transport == "http":
            checks.append(("vdb", f"{vdb_http_url.rstrip('/')}/health", "http"))
        else:
            checks.append(("vdb", vdb_socket_path, "socket"))
        checks.append(("backend", f"{backend_url.rstrip('/')}/auth/status", "http"))
        checks.append(("frontend", f"{frontend_url.rstrip('/')}/login", "http"))

    deadline = time.time() + 90
    while time.time() < deadline:
        all_ok = True
        for _, value, kind in checks:
            if kind == "http" and not http_ok(value, timeout=2):
                all_ok = False
                break
            if kind == "socket" and not socket_ok(value):
                all_ok = False
                break
        if all_ok:
            return True, "healthy"
        time.sleep(1.0)
    return False, "Timed out waiting for local services to become healthy"


def ensure_vdb_mit_acceptance() -> None:
    if LOCAL_VDB_LICENSE_FILE.exists():
        return
    command = [str(VERUN_ROOT / "vdb" / "scripts" / "ensure_mit_acceptance.sh"), "liwiro_cli"]
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise CliError("MIT license acceptance is required before starting VDB locally")


def resolve_default_vdb_socket_path() -> str:
    env_path = str(
        os.environ.get("VDB_UNIX_SOCKET_PATH")
        or os.environ.get("VDB_INTERFACE_UNIXSOCKET_PATH")
        or ""
    ).strip()
    if env_path:
        return env_path
    if Path("/run").is_dir() and os.access("/run", os.W_OK):
        return "/run/vdb.sock"
    return "/tmp/vdb.sock"


def resolve_vdb_http_port(server_url: str) -> int:
    parsed = parse.urlparse(str(server_url or DEFAULT_VDB_HTTP_URL))
    return int(parsed.port or 1957)


def render_service_table(rows: list[dict]) -> None:
    headers = ["PID", "Status", "Port", "API", "Mgmt", "Docs", "Base Path"]
    body = []
    for item in rows:
        body.append(
            [
                item.get("processId") or "",
                item.get("status") or "",
                item.get("port") or "-",
                item.get("apiName") or "",
                "on" if item.get("managementRoutesEnabled", True) else "off",
                "on" if item.get("liwiroDocsUrl") else "off",
                item.get("basePath") or "/",
            ]
        )
    print_table(headers, body)


def render_users_table(rows: list[dict]) -> None:
    headers = ["Username", "Role", "Super", "Access", "Created"]
    body = []
    for item in rows:
        access = item.get("service_access") or []
        if access == ["*"]:
            access_text = "*"
        else:
            access_text = str(len(access))
        body.append(
            [
                item.get("username") or "",
                item.get("role") or "",
                "yes" if item.get("is_super_admin") else "no",
                access_text,
                item.get("created_at") or "",
            ]
        )
    print_table(headers, body)


def render_modules_table(rows: list[dict]) -> None:
    headers = ["Name", "Scope", "Owner", "Domains", "Title"]
    body = []
    for item in rows:
        domains = ",".join(item.get("assigned_domains") or []) or "-"
        body.append(
            [
                item.get("name") or "",
                item.get("scope") or "",
                item.get("owner_username") or "",
                domains,
                item.get("title") or "",
            ]
        )
    print_table(headers, body)


def render_vi_files_table(rows: list[dict]) -> None:
    headers = ["Path", "Ext", "Size", "Modified"]
    body = []
    for item in rows:
        body.append(
            [
                item.get("path") or "",
                item.get("extension") or "",
                item.get("size") or 0,
                item.get("modifiedAt") or "",
            ]
        )
    print_table(headers, body)


def cleanup_stale_local_entries(ctx: CliContext) -> None:
    cleanup_stale_local_entries_in_state(ctx.state)


def local_process_entry(ctx: CliContext, target: str) -> dict | None:
    return local_process_entry_for_state(ctx.state, target)


def save_local_process(ctx: CliContext, target: str, entry: dict) -> None:
    save_local_process_for_state(ctx.state, target, entry)


def remove_local_process(ctx: CliContext, target: str) -> None:
    processes = state_local_processes(ctx.state)
    if target in processes:
        del processes[target]
        save_state(ctx.state)


def backend_and_frontend_urls(args: argparse.Namespace) -> tuple[str, str]:
    backend_port = int(args.backend_port or 5000)
    frontend_port = int(args.frontend_port or 3000)
    return f"http://127.0.0.1:{backend_port}", f"http://127.0.0.1:{frontend_port}"


def build_local_command(args: argparse.Namespace) -> tuple[list[str], Path, dict[str, str], str, str, str, str]:
    target = args.target
    requested_backend_port = int(args.backend_port or 5000)
    requested_frontend_port = int(args.frontend_port or 3000)
    backend_port = resolve_available_local_port(requested_backend_port) if target in {"backend", "all"} else requested_backend_port
    frontend_port = resolve_available_local_port(requested_frontend_port) if target in {"frontend", "all"} else requested_frontend_port
    backend_url = f"http://127.0.0.1:{backend_port}"
    frontend_url = f"http://127.0.0.1:{frontend_port}"
    transport = str(args.vdb_transport or "unixsocket").strip().lower()
    vdb_http_url = str(args.vdb_http_url or DEFAULT_VDB_HTTP_URL).strip()
    vdb_socket_path = str(args.vdb_socket_path or resolve_default_vdb_socket_path()).strip()

    env = dict(os.environ)
    env["VI_CUSTOM_MODULES_DIR"] = env.get("VI_CUSTOM_MODULES_DIR") or str(VERUN_ROOT / "vi" / "custom_modules")

    if target == "all":
        env["FLASK_PORT"] = str(int(backend_port))
        env["LIWIRO_BACKEND_PORT"] = str(int(backend_port))
        env["LIWIRO_BACKEND_URL"] = backend_url
        env["PORT"] = str(int(frontend_port))
        env["LIWIRO_FRONTEND_PORT"] = str(int(frontend_port))
        env["NEXT_PUBLIC_LIWIRO_BACKEND"] = backend_url
        env["VDB_TRANSPORT"] = transport
        env["VDB_SERVER_URL"] = vdb_http_url
        env["VDB_UNIX_SOCKET_PATH"] = vdb_socket_path
        return ([str(LIWIRO_ROOT / "scripts" / "start_all.sh")], REPO_ROOT, env, transport, backend_url, frontend_url, vdb_http_url if transport == "http" else vdb_socket_path)

    if target == "backend":
        env["LIWIRO_MANAGED_STARTUP"] = "1"
        env["FLASK_HOST"] = "0.0.0.0"
        env["FLASK_PORT"] = str(int(backend_port))
        env["LIWIRO_BACKEND_PORT"] = str(int(backend_port))
        env["LIWIRO_BACKEND_URL"] = backend_url
        env["VDB_TRANSPORT"] = transport
        env["VDB_SERVER_URL"] = vdb_http_url
        env["VDB_UNIX_SOCKET_PATH"] = vdb_socket_path
        return ([str(LIWIRO_ROOT / "backend" / "scripts" / "backend-start.sh")], LIWIRO_ROOT / "backend", env, transport, backend_url, frontend_url, vdb_http_url if transport == "http" else vdb_socket_path)

    if target == "frontend":
        env["PORT"] = str(int(frontend_port))
        env["LIWIRO_FRONTEND_PORT"] = str(int(frontend_port))
        env["NEXT_PUBLIC_LIWIRO_BACKEND"] = backend_url
        return (
            [
                "npm",
                "run",
                "dev",
                "--",
                "--hostname",
                "127.0.0.1",
                "--port",
                str(int(frontend_port)),
            ],
            LIWIRO_ROOT / "frontend",
            env,
            transport,
            backend_url,
            frontend_url,
            vdb_http_url if transport == "http" else vdb_socket_path,
        )

    if target == "vdb":
        if transport == "http":
            env["VDB_HTTP_PORT"] = str(resolve_vdb_http_port(vdb_http_url))
            return ([str(VERUN_ROOT / "vdb" / "scripts" / "serve.sh")], VERUN_ROOT / "vdb", env, transport, backend_url, frontend_url, vdb_http_url)
        env["VDB_UNIX_SOCKET_PATH"] = vdb_socket_path
        return ([str(VERUN_ROOT / "vdb" / "scripts" / "socket.sh")], VERUN_ROOT / "vdb", env, transport, backend_url, frontend_url, vdb_socket_path)

    raise CliError(f"Unsupported local target '{target}'")


def collect_local_status(ctx: CliContext, target: str | None = None) -> list[dict]:
    target_name = str(target or "all").strip().lower()
    processes = state_local_processes(ctx.state)
    tracked_all = processes.get("all") or {}
    transport = str((processes.get("vdb") or tracked_all).get("transport") or "unixsocket").strip().lower() or "unixsocket"
    backend_url = str((processes.get("backend") or tracked_all).get("backend_url") or DEFAULT_BACKEND).strip() or DEFAULT_BACKEND
    frontend_url = str((processes.get("frontend") or tracked_all).get("frontend_url") or DEFAULT_FRONTEND_URL).strip() or DEFAULT_FRONTEND_URL
    vdb_http_url = str((processes.get("vdb") or tracked_all).get("vdb_http_url") or DEFAULT_VDB_HTTP_URL).strip() or DEFAULT_VDB_HTTP_URL
    vdb_socket_path = str((processes.get("vdb") or tracked_all).get("vdb_socket_path") or resolve_default_vdb_socket_path()).strip()

    statuses = []
    names = ["vdb", "backend", "frontend"] if target_name == "all" else [target_name]
    for name in names:
        tracked = processes.get(name) or (tracked_all if target_name == "all" else {})
        pid = int(tracked.get("pid") or 0)
        running = is_pid_running(pid)
        healthy = False
        detail = ""
        if name == "backend":
            url = f"{backend_url.rstrip('/')}/auth/status"
            healthy = http_ok(url, timeout=2)
            detail = url
            if not running and not healthy:
                port = parse.urlparse(backend_url).port or 5000
                fallback = find_pids_by_port(int(port))
                if fallback:
                    running = True
                    pid = fallback[0]
        elif name == "frontend":
            url = f"{frontend_url.rstrip('/')}/login"
            healthy = http_ok(url, timeout=2)
            detail = url
            if not running and not healthy:
                port = parse.urlparse(frontend_url).port or 3000
                fallback = find_pids_by_port(int(port))
                if fallback:
                    running = True
                    pid = fallback[0]
        elif name == "vdb":
            if transport == "http":
                url = f"{vdb_http_url.rstrip('/')}/health"
                healthy = http_ok(url, timeout=2)
                detail = url
                if not running and not healthy:
                    fallback = find_pids_by_port(resolve_vdb_http_port(vdb_http_url))
                    if fallback:
                        running = True
                        pid = fallback[0]
            else:
                healthy = socket_ok(vdb_socket_path)
                detail = vdb_socket_path
                if not running and not healthy:
                    fallback = find_pids_by_socket(vdb_socket_path)
                    if fallback:
                        running = True
                        pid = fallback[0]
        statuses.append(
            {
                "target": name,
                "tracked": bool(tracked),
                "pid": pid or "",
                "running": running,
                "healthy": healthy,
                "detail": detail,
                "transport": transport if name == "vdb" else "",
                "log_file": str(tracked.get("log_file") or "").strip(),
            }
        )
    return statuses


def build_user_body(ctx: CliContext, args: argparse.Namespace, existing: dict | None = None) -> dict:
    body = {}
    if args.from_file:
        body = load_json_file(args.from_file, label="user payload", expected_type=dict)
    if args.edit:
        template = body or existing or {
            "username": str(getattr(args, "username", "") or "").strip(),
            "role": "viewer",
            "service_access": ["*"],
            "permissions": [],
            "liwiro_rbac": {},
        }
        body = edit_json_object(template, "user payload")

    if getattr(args, "role", None):
        body["role"] = args.role
    if getattr(args, "service_access", None) is not None:
        body["service_access"] = normalize_service_access(args.service_access)
    if getattr(args, "permissions_json", None):
        body["permissions"] = parse_json_option(args.permissions_json, "permissions", expected_type=(list, dict))
    elif getattr(args, "permissions_file", None):
        body["permissions"] = load_json_file(args.permissions_file, label="permissions", expected_type=(list, dict))
    if getattr(args, "rbac_json", None):
        body["liwiro_rbac"] = parse_json_option(args.rbac_json, "liwiro_rbac", expected_type=dict)
    elif getattr(args, "rbac_file", None):
        body["liwiro_rbac"] = load_json_file(args.rbac_file, label="liwiro_rbac", expected_type=dict)

    password = str(getattr(args, "password", "") or "").strip()
    if password:
        body["password"] = password
    return body


def build_module_body(args: argparse.Namespace, existing: dict | None = None) -> dict:
    body = {}
    if args.from_file:
        body = load_json_file(args.from_file, label="module payload", expected_type=dict)
    if args.edit:
        template = body or existing or {
            "name": str(getattr(args, "name", "") or "").strip(),
            "title": str(getattr(args, "name", "") or "").strip(),
            "description": "",
            "scope": "domain",
            "assigned_domains": [],
            "config_schema": {},
            "config_defaults": {},
            "source": 'func hello() {\n  return "ok";\n}\n',
        }
        body = edit_json_object(template, "module payload")

    name_value = str(getattr(args, "name", "") or "").strip()
    if name_value and "name" not in body:
        body["name"] = name_value
    if getattr(args, "title", None):
        body["title"] = args.title
    if getattr(args, "description", None) is not None:
        body["description"] = args.description
    if getattr(args, "scope", None):
        body["scope"] = args.scope
    if getattr(args, "assigned_domain", None) is not None:
        body["assigned_domains"] = normalize_service_access(args.assigned_domain)
    if getattr(args, "source_file", None):
        body["source"] = load_text_file(args.source_file, label="module source")
    elif getattr(args, "source_text", None) is not None:
        body["source"] = args.source_text
    if getattr(args, "config_schema_json", None):
        body["config_schema"] = parse_json_option(args.config_schema_json, "config_schema", expected_type=dict)
    elif getattr(args, "config_schema_file", None):
        body["config_schema"] = load_json_file(args.config_schema_file, label="config_schema", expected_type=dict)
    if getattr(args, "config_defaults_json", None):
        body["config_defaults"] = parse_json_option(args.config_defaults_json, "config_defaults", expected_type=dict)
    elif getattr(args, "config_defaults_file", None):
        body["config_defaults"] = load_json_file(args.config_defaults_file, label="config_defaults", expected_type=dict)
    return body


def current_profile_snapshot(profile_name: str = "") -> tuple[dict, str, dict]:
    state = load_state()
    requested = str(profile_name or state.get("current_profile") or DEFAULT_PROFILE).strip() or DEFAULT_PROFILE
    resolved_name, profile = get_profile(state, requested, create=True)
    return state, resolved_name, profile


def refresh_shell_session(session: ShellSession) -> None:
    _, profile_name, profile = current_profile_snapshot(session.profile_name)
    session.profile_name = profile_name
    session.backend = str(profile.get("backend") or DEFAULT_BACKEND).strip() or DEFAULT_BACKEND


def refresh_shell_auth_state(session: ShellSession, force: bool = False) -> bool:
    now = time.time()
    if not force and session.auth_checked_at and (now - session.auth_checked_at) < 2.0:
        return session.auth_valid

    state, profile_name, profile = current_profile_snapshot(session.profile_name)
    session.profile_name = profile_name
    session.backend = str(profile.get("backend") or DEFAULT_BACKEND).strip() or DEFAULT_BACKEND
    session.auth_checked_at = now
    session.auth_valid = False
    session.auth_configured = None

    probe_client = LiwiroClient(backend=session.backend, token="", timeout=session.timeout)
    try:
        auth_status = probe_client.request("GET", "/auth/status")
        if isinstance(auth_status, dict):
            session.auth_configured = bool(auth_status.get("configured"))
    except CliError:
        session.auth_configured = None

    if not is_signed_in_profile(profile):
        return False

    auth_client = LiwiroClient(backend=session.backend, token=str(profile.get("token") or ""), timeout=session.timeout)
    try:
        auth_client.request("GET", "/auth/me", require_auth=True)
        session.auth_valid = True
        return True
    except CliHttpError as exc:
        if exc.status_code in {401, 403}:
            profile["token"] = ""
            profile["username"] = ""
            profile["vdb_portal_token"] = ""
            state["profiles"][profile_name] = profile
            save_state(state)
            session.auth_valid = False
            return False
        raise
    except CliError:
        session.auth_valid = False
        return False


def shell_client(session: ShellSession) -> LiwiroClient:
    _, _, profile = current_profile_snapshot(session.profile_name)
    backend = str(profile.get("backend") or DEFAULT_BACKEND).strip() or DEFAULT_BACKEND
    token = str(profile.get("token") or "").strip()
    return LiwiroClient(backend=backend, token=token, timeout=session.timeout)


def clear_service_context(session: ShellSession, area: str = "services") -> None:
    session.area = area
    session.service_id = ""
    session.service_name = ""


def resolve_service_reference(session: ShellSession, reference: str) -> tuple[str, str]:
    value = str(reference or "").strip()
    if not value:
        raise CliError("Service reference is required")
    client = shell_client(session)
    rows = client.request("GET", "/services?summary=1", require_auth=True)
    services = rows if isinstance(rows, list) else []
    lowered = value.lower()
    for item in services:
        process_id = str(item.get("processId") or "").strip()
        api_name = str(item.get("apiName") or "").strip()
        if lowered in {process_id.lower(), api_name.lower()}:
            return process_id or value, api_name or process_id or value
    raise CliError(f"Service '{value}' not found")


def ensure_service_context_valid(session: ShellSession) -> None:
    if session.area != "service" or not session.service_id:
        raise CliError("No active service context")
    client = shell_client(session)
    try:
        payload = client.request("GET", f"/services/{session.service_id}", require_auth=True)
    except CliHttpError as exc:
        if exc.status_code in {403, 404}:
            clear_service_context(session, area="services")
            raise CliError("Active service is no longer available. Returned to liwiro:services>.") from exc
        raise
    session.service_name = str(payload.get("apiName") or session.service_name or session.service_id).strip() or session.service_id


def set_service_context(session: ShellSession, reference: str) -> None:
    if not shell_is_signed_in(session):
        raise CliError(sign_in_required_message())
    process_id, api_name = resolve_service_reference(session, reference)
    session.area = "service"
    session.service_id = process_id
    session.service_name = api_name


def shell_whereami(session: ShellSession) -> None:
    signed_in = shell_is_signed_in(session)
    print_heading("Current Context")
    print(f"{format_label('profile')}: {session.profile_name}")
    print(f"{format_label('backend')}: {session.backend}")
    print(f"{format_label('context')}: {session.area}")
    if session.area == "service":
        print(f"{format_label('service_id')}: {session.service_id}")
        print(f"{format_label('service_name')}: {session.service_name}")
    if session.auth_configured is not None:
        print(f"{format_label('configured')}: {'yes' if session.auth_configured else 'no'}")
    print(f"{format_label('signed_in')}: {'yes' if signed_in else 'no'}")
    print(f"{format_label('prompt')}: {session.prompt().strip()}")


def shell_context_key(session: ShellSession) -> str:
    return "service" if session.area == "service" else session.area


def render_shell_menu(session: ShellSession) -> None:
    context_key = shell_context_key(session)
    signed_in = shell_is_signed_in(session)
    print_heading("Shell Menu")
    print(f"{format_label('prompt')}: {session.prompt().strip()}")
    print(f"{format_label('context')}: {context_key}")
    if context_key == "service":
        print(f"{format_label('service')}: {session.service_name or session.service_id}")
    if context_key == "root" and not signed_in:
        print(colorize("Only auth and profiles prompts are available until you sign in or complete setup.", "yellow"))
    elif context_key not in SHELL_PUBLIC_AREAS.union({"root"}) and not signed_in:
        print(colorize("Sign in required for this context. Run: auth login", "yellow"))
    print("")
    print_heading("Commands")
    for command, description in SHELL_CONTEXT_COMMANDS.get(context_key, []):
        print(f"- {colorize(command, 'bold', 'green')}: {description}")


def normalize_help_topic(tokens: list[str]) -> str:
    if not tokens:
        return ""
    joined_two = " ".join(tokens[:2]).strip().lower()
    if joined_two in {"use service"}:
        return joined_two
    return str(tokens[0] or "").strip().lower()


def render_shell_help(session: ShellSession, tokens: list[str]) -> None:
    context_key = shell_context_key(session)
    if not tokens:
        render_shell_menu(session)
        print("")
        print_heading("Help Notes")
        print(f"- {colorize('exit', 'bold', 'green')} or {colorize('quit', 'bold', 'green')} closes the shell.")
        print("- Press Ctrl-D at any prompt to exit immediately.")
        print("- Arrow keys navigate history; Home/End and Ctrl-A/E move the cursor; Ctrl-L or 'clear' clears the screen.")
        print(f"- {colorize('back', 'bold', 'green')} leaves the current service or area context.")
        print(f"- Use {colorize('help <command>', 'bold', 'green')} for detailed syntax.")
        print(f"- Many create/update/query commands accept {colorize('--stdin', 'bold', 'green')} for piped input.")
        return

    topic = normalize_help_topic(tokens)
    detail_sets = [SHELL_CONTEXT_DETAILS.get(context_key, {}), SHELL_CONTEXT_DETAILS.get("root", {})]
    for details in detail_sets:
        if topic in details:
            print_heading(f"Help: {' '.join(tokens)}")
            print(details[topic])
            return

    for command, description in SHELL_CONTEXT_COMMANDS.get(context_key, []):
        normalized_command = command.split(" ", 1)[0].lower()
        if topic == normalized_command or topic == command.lower():
            print_heading(f"Help: {command}")
            print(f"{command}: {description}")
            return

    if topic in SHELL_AREA_CONTEXTS:
        print_heading(f"Help: enter {topic}")
        print(f"enter {topic}\nSwitch to the {topic} prompt. Example: enter {topic}")
        return

    raise CliError(f"No shell help found for '{' '.join(tokens)}'")


def translate_service_manager_state_command(session: ShellSession, tokens: list[str]) -> list[str]:
    argv = ["services", "update", session.service_id]
    rest = tokens[1:]
    if not rest:
        return argv + ["--manager-state-edit"]

    index = 0
    while index < len(rest):
        token = rest[index]
        lowered = token.lower()
        if lowered in {"edit", "--edit", "--manager-state-edit"}:
            argv.append("--manager-state-edit")
        elif lowered in {"stdin", "--stdin", "--manager-state-stdin"}:
            argv.append("--manager-state-stdin")
        elif lowered in {"file", "--file", "--from-file", "--manager-state-file"}:
            if index + 1 >= len(rest):
                raise CliError("manager-state file path is required")
            argv.extend(["--manager-state-file", rest[index + 1]])
            index += 1
        else:
            raise CliError(f"Unsupported manager-state option '{token}'")
        index += 1
    return argv


def translate_service_context_command(session: ShellSession, tokens: list[str]) -> list[str]:
    ensure_service_context_valid(session)
    first = str(tokens[0] or "").strip().lower()
    if first == "show":
        return ["services", "show", session.service_id] + tokens[1:]
    if first == "start":
        return ["services", "start", session.service_id] + tokens[1:]
    if first == "stop":
        return ["services", "stop", session.service_id] + tokens[1:]
    if first == "update":
        return ["services", "update", session.service_id] + tokens[1:]
    if first == "delete":
        return ["services", "delete", session.service_id] + tokens[1:]
    if first in {"auth-keys", "auth_keys"}:
        return ["services", "download-auth-keys", session.service_id] + tokens[1:]
    if first == "manager-state":
        return translate_service_manager_state_command(session, tokens)
    raise CliError(f"Unknown service-context command '{tokens[0]}'")


def translate_area_context_command(session: ShellSession, tokens: list[str]) -> list[str]:
    if session.area == "services" and str(tokens[0] or "").strip().lower() in {"auth-keys", "auth_keys"}:
        return ["services", "download-auth-keys"] + tokens[1:]
    return [session.area] + tokens


def translate_shell_command(session: ShellSession, tokens: list[str]) -> tuple[str, Any]:
    if not tokens:
        return "noop", None

    first = str(tokens[0] or "").strip().lower()
    if first in {"help", "?"}:
        return "help", tokens[1:]
    if first == "menu":
        return "menu", None
    if first == "whereami":
        return "whereami", None
    if first in {"clear", "cls"}:
        return "clear", None
    if first == "back":
        return "back", None
    if first in {"exit", "quit"}:
        return "exit", None
    if first == "enter":
        if len(tokens) < 2:
            raise CliError("Usage: enter <area>")
        area = str(tokens[1] or "").strip().lower()
        if area not in SHELL_AREA_CONTEXTS:
            raise CliError(f"Unknown area '{area}'")
        return "enter", area
    if first == "use":
        if session.area == "service":
            if len(tokens) < 2:
                raise CliError("Usage: use <service_id|apiName>")
            return "use-service", tokens[1]
        if session.area == "services":
            if len(tokens) < 2:
                raise CliError("Usage: use <service_id|apiName>")
            return "use-service", tokens[1]
        if len(tokens) >= 3 and str(tokens[1] or "").strip().lower() == "service":
            return "use-service", tokens[2]
        raise CliError("Usage: use service <service_id|apiName>")

    if first in SHELL_AREA_CONTEXTS and len(tokens) == 1:
        return "enter", first
    if first in TOP_LEVEL_AREAS:
        return "command", tokens

    if session.area == "root":
        raise CliError("Enter an area or run a top-level command. Use 'menu' for options.")
    if session.area == "service":
        return "command", translate_service_context_command(session, tokens)
    return "command", translate_area_context_command(session, tokens)


def run_cli_command(argv: list[str], allow_shell: bool = True) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not allow_shell and getattr(args, "area", None) == "shell":
        raise CliError("Nested shell invocation is not supported from inside the shell")
    ctx = build_context(args)
    enforce_sign_in(args, ctx.profile)
    return int(args.handler(ctx))


def execute_shell_command(session: ShellSession, argv: list[str]) -> int:
    try:
        result = run_cli_command(argv, allow_shell=False)
    finally:
        refresh_shell_session(session)
    if session.area == "service" and session.service_id:
        try:
            ensure_service_context_valid(session)
        except CliError as exc:
            if argv[:2] == ["services", "delete"] and len(argv) > 2 and argv[2] == session.service_id:
                clear_service_context(session, area="services")
            else:
                print_warning(f"warning: {exc}")
    return result


def run_shell_loop(session: ShellSession) -> int:
    if readline is not None and sys.stdin.isatty():
        # GNU readline supplies cursor movement, history, delete/home/end,
        # Ctrl-A/E/K/U/L and familiar shell editing in every convo prompt.
        readline.parse_and_bind('set editing-mode emacs')
        readline.parse_and_bind('"\\C-l": clear-screen')
        history_path = Path(os.environ.get("LIWIRO_CLI_HISTORY", str(Path.home() / ".liwiro_cli_history")))
        try:
            readline.read_history_file(str(history_path))
        except (OSError, IOError):
            pass
    while session.running:
        refresh_shell_session(session)
        try:
            raw_line = input(session.prompt())
        except EOFError:
            print("")
            break
        except KeyboardInterrupt:
            print("")
            continue

        line = str(raw_line or "").strip()
        if not line:
            continue

        try:
            tokens = shlex.split(line)
            action, payload = translate_shell_command(session, tokens)
            if action == "noop":
                continue
            if action == "help":
                render_shell_help(session, payload or [])
                continue
            if action == "menu":
                render_shell_menu(session)
                continue
            if action == "whereami":
                shell_whereami(session)
                continue
            if action == "clear":
                print("\033[H\033[2J", end="")
                continue
            if action == "back":
                if session.area == "service":
                    clear_service_context(session, area="services")
                elif session.area != "root":
                    clear_service_context(session, area="root")
                continue
            if action == "enter":
                target_area = str(payload or "root")
                enforce_shell_area_access(session, target_area)
                clear_service_context(session, area=target_area)
                continue
            if action == "use-service":
                set_service_context(session, str(payload or ""))
                continue
            if action == "exit":
                session.running = False
                continue
            if action == "command":
                execute_shell_command(session, list(payload or []))
                continue
        except CliError as exc:
            print_error_line(f"error: {exc}")
        except SystemExit:
            # argparse already printed the usage error for invalid shell-forwarded argv.
            continue
    if readline is not None and sys.stdin.isatty():
        try:
            readline.write_history_file(str(history_path))
        except (OSError, IOError):
            pass
    return 0


def handle_auth_status(ctx: CliContext) -> int:
    data = ctx.client.request("GET", "/auth/status")
    emit(
        ctx,
        data,
        renderer=lambda payload: print_kv(
            payload,
            [
                "configured",
                "hasFrontendCreds",
                "vdbUsersExist",
                "authFile",
                "vdbTransport",
                "vdbServerUrl",
                "vdbUnixSocketPath",
                "vdbNamedPipePath",
            ],
        ),
    )
    return 0


def handle_auth_vdb_status(ctx: CliContext) -> int:
    query = {
        "vdb_transport": ctx.args.vdb_transport or "",
        "vdb_server_url": ctx.args.vdb_server_url or "",
        "vdb_unix_socket_path": ctx.args.vdb_unix_socket_path or "",
        "vdb_named_pipe_path": ctx.args.vdb_named_pipe_path or "",
        "attempt_autostart": "1" if ctx.args.attempt_autostart else "",
    }
    data = ctx.client.request("GET", "/auth/vdb-connection-status", query=query)
    emit(
        ctx,
        data,
        renderer=lambda payload: print_kv(
            payload,
            ["status", "available", "detail", "transport", "localTarget", "autostartAttempted"],
        ),
    )
    return 0


def handle_auth_login(ctx: CliContext) -> int:
    username = str(ctx.args.username or "").strip()
    password = str(ctx.args.password or "").strip()
    if not username:
        username = input("Liwiro username: ").strip()
    if not password:
        password = getpass.getpass("Liwiro password: ")

    data = _perform_auth_login(ctx, username, password, extra_payload={})
    if not bool(data.get("vdbRuntimeReady", True)):
        repaired = _maybe_repair_vdb_runtime_credentials(ctx, username, password)
        if repaired is not None:
            data = repaired

    emit(
        ctx,
        data,
        renderer=lambda payload: _render_auth_login(payload),
    )
    return 0


def _perform_auth_login(ctx: CliContext, username: str, password: str, extra_payload: dict | None = None) -> dict:
    payload = {"username": username, "password": password}
    optional_pairs = {
        "vdb_transport": ctx.args.vdb_transport,
        "vdb_server_url": ctx.args.vdb_server_url,
        "vdb_unix_socket_path": ctx.args.vdb_unix_socket_path,
        "vdb_named_pipe_path": ctx.args.vdb_named_pipe_path,
        "vdb_app_username": ctx.args.vdb_app_username,
        "vdb_app_password": ctx.args.vdb_app_password,
        "liwiro_super_admin_username": ctx.args.liwiro_super_admin_username,
        "liwiro_super_admin_password": ctx.args.liwiro_super_admin_password,
    }
    for key, value in optional_pairs.items():
        if str(value or "").strip():
            payload[key] = value
    for key, value in (extra_payload or {}).items():
        if str(value or "").strip():
            payload[key] = value

    data = ctx.client.request("POST", "/auth/signin", body=payload)
    token = str(data.get("token") or "").strip()
    if not token:
        raise CliError("Login succeeded but no token was returned.")

    set_profile_values(
        ctx,
        backend=ctx.client.backend,
        token=token,
        username=str(data.get("username") or username).strip(),
        vdb_portal_token="",
    )
    ctx.client.token = token
    return data


def _prompt_with_default(prompt: str, default: str) -> str:
    suffix = f" [{default}]" if str(default or "").strip() else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or str(default or "").strip()


def _prompt_vdb_transport(default: str) -> str:
    while True:
        value = _prompt_with_default("VDB transport (unixsocket/http/namedpipe)", default).lower()
        if value in {"unixsocket", "http", "namedpipe"}:
            return value
        print_warning("warning: transport must be one of unixsocket, http, or namedpipe")


def _normalize_cli_vdb_transport(value: str) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in {"http", "namedpipe", "unixsocket"}:
        return candidate
    return "unixsocket"


def _maybe_repair_vdb_runtime_credentials(ctx: CliContext, username: str, password: str) -> dict | None:
    if not sys.stdin.isatty():
        return None
    answer = input(colorize("Re-enter VDB runtime credentials now? [y/N]: ", "bold", "yellow")).strip().lower()
    if answer not in {"y", "yes"}:
        return None

    status_payload = {}
    try:
        status_payload = ctx.client.request("GET", "/auth/status")
    except CliError:
        status_payload = {}

    default_transport = _normalize_cli_vdb_transport(
        (status_payload or {}).get("vdbTransport")
        or (status_payload or {}).get("defaultVdbTransport")
        or ctx.args.vdb_transport
        or "unixsocket"
    )
    default_server_url = str(
        (status_payload or {}).get("vdbServerUrl")
        or (status_payload or {}).get("defaultVdbServerUrl")
        or ctx.args.vdb_server_url
        or DEFAULT_VDB_HTTP_URL
    ).strip()
    default_socket_path = str(
        (status_payload or {}).get("vdbUnixSocketPath")
        or (status_payload or {}).get("defaultVdbUnixSocketPath")
        or ctx.args.vdb_unix_socket_path
        or resolve_default_vdb_socket_path()
    ).strip()
    default_named_pipe_path = str(
        (status_payload or {}).get("vdbNamedPipePath")
        or (status_payload or {}).get("defaultVdbNamedPipePath")
        or ctx.args.vdb_named_pipe_path
        or r"\\.\pipe\verun_vdb"
    ).strip()
    default_vdb_username = str(ctx.args.vdb_app_username or "Liwiro").strip() or "Liwiro"

    print_info("Enter replacement VDB runtime credentials.")
    transport = _prompt_vdb_transport(default_transport)
    repair_payload = {
        "vdb_transport": transport,
        "vdb_app_username": _prompt_with_default("VDB app/admin username", default_vdb_username),
    }
    if transport == "http":
        repair_payload["vdb_server_url"] = _prompt_with_default("VDB server URL", default_server_url)
    elif transport == "namedpipe":
        repair_payload["vdb_named_pipe_path"] = _prompt_with_default("VDB named pipe path", default_named_pipe_path)
    else:
        repair_payload["vdb_unix_socket_path"] = _prompt_with_default("VDB Unix socket path", default_socket_path)
    repair_payload["vdb_app_password"] = getpass.getpass("VDB app/admin password: ")

    print_info("Retrying sign-in with updated VDB runtime credentials...")
    return _perform_auth_login(ctx, username, password, extra_payload=repair_payload)


def _render_auth_login(payload: dict) -> None:
    print(f"Authenticated as {payload.get('username')} ({payload.get('role')})")
    if payload.get("bootstrap"):
        print("Bootstrap mode: first-time setup completed through the CLI.")
    for notice in payload.get("bootstrapNotices") or []:
        print(f"- {notice}")
    if not bool(payload.get("vdbRuntimeReady", True)):
        print_warning(
            f"warning: sign-in succeeded, but VDB runtime is not ready: {payload.get('vdbRuntimeError') or 'unknown error'}"
        )


def handle_auth_logout(ctx: CliContext) -> int:
    if ctx.client.token:
        try:
            ctx.client.request("POST", "/auth/logout", body={}, require_auth=True)
        except CliError:
            pass
    set_profile_values(ctx, token="", username="", vdb_portal_token="")
    if not ctx.args.json:
        print("Logged out.")
    else:
        print_json({"message": "Logged out"})
    return 0


def handle_auth_me(ctx: CliContext) -> int:
    data = ctx.client.request("GET", "/auth/me", require_auth=True)
    emit(
        ctx,
        data,
        renderer=lambda payload: print_kv(
            payload,
            [
                "username",
                "role",
                "is_super_admin",
                "service_access",
                "permissions",
            ],
        ),
    )
    return 0


def handle_health_check(ctx: CliContext) -> int:
    health_payload = ctx.client.request("GET", "/health")
    auth_status = ctx.client.request("GET", "/auth/status")
    license_payload = ctx.client.request("GET", "/license")
    result = {
        "backend": ctx.client.backend,
        "health": health_payload,
        "authStatus": auth_status,
        "license": license_payload,
        "authenticated": False,
        "profile": ctx.profile_name,
        "local": collect_local_status(ctx, target="all"),
    }
    if ctx.client.token:
        try:
            result["me"] = ctx.client.request("GET", "/auth/me", require_auth=True)
            result["authenticated"] = True
        except CliError as exc:
            result["meError"] = str(exc)
    portal_token = str(ctx.profile.get("vdb_portal_token") or "").strip()
    if portal_token:
        try:
            result["vdb"] = {
                "connection": ctx.client.request("GET", "/platform/vdb/connection", require_auth=True),
                "whoami": ctx.client.request(
                    "GET",
                    "/platform/vdb/whoami",
                    require_auth=True,
                    headers={"X-VDB-Portal-Token": portal_token},
                ),
                "context": ctx.client.request(
                    "GET",
                    "/platform/vdb/context",
                    require_auth=True,
                    headers={"X-VDB-Portal-Token": portal_token},
                ),
            }
        except CliError as exc:
            result["vdbError"] = str(exc)
    emit(ctx, result, renderer=_render_health_check)
    return 0


def _render_health_check(payload: dict) -> None:
    print(f"backend: {payload.get('backend')}")
    print(f"profile: {payload.get('profile')}")
    print(f"authenticated: {payload.get('authenticated')}")
    health = payload.get("health") or {}
    print(f"health.status: {health.get('status') or health.get('service') or 'ok'}")
    auth_status = payload.get("authStatus") or {}
    print(f"configured: {auth_status.get('configured')}")
    print(f"vdbTransport: {auth_status.get('vdbTransport')}")
    if payload.get("me"):
        print(f"user: {(payload.get('me') or {}).get('username')}")
    if payload.get("vdb"):
        print("vdb: connected")
    for item in payload.get("local") or []:
        state = "up" if item.get("healthy") else "down"
        print(f"local.{item.get('target')}: {state} ({item.get('detail')})")


def handle_license_show(ctx: CliContext) -> int:
    data = ctx.client.request("GET", "/license")
    emit(ctx, data, renderer=lambda payload: print_kv(payload, list(payload.keys())))
    return 0


def _render_capabilities_list(payload: dict) -> None:
    rows = payload.get("capabilities") or []
    body = []
    for item in rows:
        permissions = ", ".join(str(entry) for entry in (item.get("permissions") or []))
        stages = ", ".join(str(entry) for entry in (item.get("stageSupport") or []))
        body.append(
            [
                item.get("capabilityId") or "",
                item.get("surfaceId") or "",
                item.get("executionMode") or "",
                item.get("actionFamily") or "",
                "yes" if item.get("allowed", True) else "no",
                permissions,
                stages,
            ]
        )
    print_table(
        ["Capability", "Surface", "Mode", "Family", "Allowed", "Permissions", "Stages"],
        body,
    )


def _render_capability_show(payload: dict) -> None:
    manual_links = payload.get("manualLinks") or []
    print_kv(
        payload,
        [
            "capabilityId",
            "title",
            "summary",
            "subsystem",
            "surfaceId",
            "surfacePath",
            "actionFamily",
            "executionMode",
            "artifactKind",
            "riskLevel",
            "requiresAuth",
            "allowed",
        ],
    )
    print(f"{format_label('permissions')}: {', '.join(payload.get('permissions') or []) or '-'}")
    print(f"{format_label('missingPermissions')}: {', '.join(payload.get('missingPermissions') or []) or '-'}")
    print(f"{format_label('stageSupport')}: {', '.join(payload.get('stageSupport') or []) or '-'}")
    if manual_links:
        print(format_label("manualLinks") + ":")
        for item in manual_links:
            print(f"  - {(item or {}).get('title')}: {(item or {}).get('href')}")


def handle_capabilities_list(ctx: CliContext) -> int:
    query = {
        "client": str(ctx.args.client or "").strip(),
        "surfaceId": str(ctx.args.surface_id or "").strip(),
        "executableOnly": "1" if ctx.args.executable_only else "",
        "includeUnavailable": "1" if ctx.args.include_unavailable else "",
    }
    data = ctx.client.request("GET", "/platform/capabilities", query=query)
    emit(ctx, data, renderer=_render_capabilities_list)
    return 0


def handle_capabilities_show(ctx: CliContext) -> int:
    capability_id = str(ctx.args.capability_id or "").strip()
    data = ctx.client.request("GET", f"/platform/capabilities/{parse.quote(capability_id, safe='')}")
    emit(ctx, data, renderer=_render_capability_show)
    return 0


def handle_profiles_list(ctx: CliContext) -> int:
    rows = []
    for name, profile in sorted(ctx.state.get("profiles", {}).items()):
        rows.append(
            {
                "name": name,
                "current": name == ctx.state.get("current_profile"),
                "backend": profile.get("backend"),
                "username": profile.get("username"),
                "token": bool(profile.get("token")),
                "vdb_portal_token": bool(profile.get("vdb_portal_token")),
            }
        )
    emit(ctx, {"profiles": rows}, renderer=_render_profiles_list)
    return 0


def _render_profiles_list(payload: dict) -> None:
    rows = payload.get("profiles") or []
    headers = ["Profile", "Current", "Backend", "User", "Auth", "VDB"]
    body = []
    for item in rows:
        body.append(
            [
                item.get("name") or "",
                "*" if item.get("current") else "",
                item.get("backend") or "",
                item.get("username") or "",
                "yes" if item.get("token") else "no",
                "yes" if item.get("vdb_portal_token") else "no",
            ]
        )
    print_table(headers, body)


def handle_profiles_show(ctx: CliContext) -> int:
    profile_name = str(ctx.args.name or ctx.profile_name).strip() or ctx.profile_name
    _, profile = get_profile(ctx.state, profile_name, create=False)
    data = {
        "name": profile_name,
        "backend": profile.get("backend"),
        "username": profile.get("username"),
        "has_token": bool(profile.get("token")),
        "has_vdb_portal_token": bool(profile.get("vdb_portal_token")),
    }
    emit(ctx, data, renderer=lambda payload: print_kv(payload, list(payload.keys())))
    return 0


def handle_profiles_use(ctx: CliContext) -> int:
    name = str(ctx.args.name or "").strip()
    if not name:
        raise CliError("Profile name is required")
    get_profile(ctx.state, name, create=False)
    ctx.state["current_profile"] = name
    save_state(ctx.state)
    if ctx.args.json:
        print_json({"current_profile": name})
    else:
        print(f"Current profile: {name}")
    return 0


def handle_profiles_set_backend(ctx: CliContext) -> int:
    name = str(ctx.args.name or "").strip()
    backend = str(ctx.args.backend_url or "").strip()
    if not name or not backend:
        raise CliError("Profile name and backend URL are required")
    _, profile = get_profile(ctx.state, name, create=True)
    profile["backend"] = backend.rstrip("/")
    ctx.state["profiles"][name] = profile
    save_state(ctx.state)
    if ctx.args.json:
        print_json({"profile": name, "backend": profile["backend"]})
    else:
        print(f"{name}: {profile['backend']}")
    return 0


def handle_profiles_delete(ctx: CliContext) -> int:
    name = str(ctx.args.name or "").strip()
    profiles = ctx.state.get("profiles", {})
    if name not in profiles:
        raise CliError(f"Profile '{name}' does not exist")
    if len(profiles) == 1:
        raise CliError("At least one profile must remain")
    if not confirm_action(f"Delete profile '{name}'?", assume_yes=ctx.args.yes):
        raise CliError("Cancelled")
    del profiles[name]
    if ctx.state.get("current_profile") == name:
        ctx.state["current_profile"] = next(iter(profiles))
    save_state(ctx.state)
    if ctx.args.json:
        print_json({"deleted": name, "current_profile": ctx.state.get("current_profile")})
    else:
        print(f"Deleted profile '{name}'")
    return 0


def read_platform_settings(client: LiwiroClient) -> dict:
    data = client.request("GET", "/platform/settings", require_auth=True)
    return data if isinstance(data, dict) else {}


def handle_settings_show(ctx: CliContext) -> int:
    data = read_platform_settings(ctx.client)
    emit(
        ctx,
        data,
        renderer=lambda payload: [print(f"{key}: {bool(payload.get(key, SETTING_KEYS[key]))}") for key in SETTING_KEYS],
    )
    return 0


def handle_settings_set(ctx: CliContext) -> int:
    current = read_platform_settings(ctx.client)
    updates = {}
    for assignment in ctx.args.assignments:
        if "=" not in assignment:
            raise CliError(f"Expected KEY=VALUE, got '{assignment}'")
        raw_key, raw_value = assignment.split("=", 1)
        updates[canonical_setting_name(raw_key)] = coerce_bool(raw_value)
    payload = {**current, **updates}
    data = ctx.client.request("PUT", "/platform/settings", body=payload, require_auth=True)
    emit(
        ctx,
        data,
        renderer=lambda payload: _render_settings_updates(payload, list(updates.keys())),
    )
    return 0


def _render_settings_updates(payload: dict, keys: list[str]) -> None:
    print("Updated settings:")
    for key in keys:
        print(f"- {key} = {bool(payload.get(key))}")


def handle_users_list(ctx: CliContext) -> int:
    data = ctx.client.request("GET", "/platform/users", require_auth=True)
    rows = data if isinstance(data, list) else []
    emit(ctx, rows, renderer=render_users_table)
    return 0


def handle_users_show(ctx: CliContext) -> int:
    data = ctx.client.request("GET", "/platform/users", require_auth=True)
    rows = data if isinstance(data, list) else []
    username = str(ctx.args.username or "").strip().lower()
    match = next((item for item in rows if str(item.get("username") or "").strip().lower() == username), None)
    if not match:
        raise CliError(f"User '{ctx.args.username}' not found")
    emit(ctx, match, renderer=lambda payload: print_json(payload))
    return 0


def handle_users_create(ctx: CliContext) -> int:
    body = build_user_body(ctx, ctx.args)
    body["username"] = str(ctx.args.username or body.get("username") or "").strip()
    if not body["username"]:
        raise CliError("username is required")
    if not str(body.get("password") or "").strip():
        body["password"] = getpass.getpass(f"Password for {body['username']}: ")
    data = ctx.client.request("POST", "/platform/users", body=body, require_auth=True)
    emit(ctx, data, renderer=lambda payload: print_json(payload))
    return 0


def handle_users_update(ctx: CliContext) -> int:
    existing_rows = ctx.client.request("GET", "/platform/users", require_auth=True)
    existing = next(
        (
            item
            for item in (existing_rows if isinstance(existing_rows, list) else [])
            if str(item.get("username") or "").strip().lower() == str(ctx.args.username or "").strip().lower()
        ),
        None,
    )
    if not existing:
        raise CliError(f"User '{ctx.args.username}' not found")
    body = build_user_body(ctx, ctx.args, existing=existing)
    if not body:
        raise CliError("No updates supplied")
    if "password" not in body and ctx.args.prompt_password:
        body["password"] = getpass.getpass(f"New password for {ctx.args.username}: ")
    data = ctx.client.request("PUT", f"/platform/users/{ctx.args.username}", body=body, require_auth=True)
    emit(ctx, data, renderer=lambda payload: print_json(payload))
    return 0


def handle_users_delete(ctx: CliContext) -> int:
    username = str(ctx.args.username or "").strip()
    if not confirm_action(f"Delete user '{username}'?", assume_yes=ctx.args.yes):
        raise CliError("Cancelled")
    data = ctx.client.request("DELETE", f"/platform/users/{username}", require_auth=True)
    emit(ctx, data, renderer=lambda payload: print(payload.get("message") or f"Deleted {username}"))
    return 0


def handle_services_list(ctx: CliContext) -> int:
    path = "/services" if ctx.args.full else "/services?summary=1"
    if ctx.args.refresh == "on":
        path += "&refresh=1" if "?" in path else "?refresh=1"
    elif ctx.args.refresh == "off":
        path += "&refresh=0" if "?" in path else "?refresh=0"
    data = ctx.client.request("GET", path, require_auth=True)
    rows = data if isinstance(data, list) else []
    emit(ctx, rows, renderer=render_service_table)
    return 0


def handle_services_show(ctx: CliContext) -> int:
    data = ctx.client.request("GET", f"/services/{ctx.args.service_id}", require_auth=True)
    if ctx.args.out_file:
        target = Path(ctx.args.out_file).expanduser().resolve()
        target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    emit(
        ctx,
        data,
        renderer=lambda payload: print_kv(
            payload,
            [
                "apiName",
                "processId",
                "status",
                "port",
                "rootUrl",
                "runtimeUrl",
                "liwiroDocsUrl",
                "productionMode",
                "managementRoutesEnabled",
            ],
        ),
    )
    return 0


def execute_platform_action(
    ctx: CliContext,
    *,
    capability_id: str,
    input_payload: dict | None = None,
    artifact: dict | None = None,
) -> dict:
    body: dict[str, Any] = {"capabilityId": str(capability_id or "").strip()}
    if isinstance(input_payload, dict) and input_payload:
        body["input"] = input_payload
    if isinstance(artifact, dict) and artifact:
        body["artifact"] = artifact
    return ctx.client.request(
        "POST",
        "/platform/actions/execute",
        body=body,
        require_auth=True,
    )


def execute_verse_service_manager_action(
    ctx: CliContext,
    *,
    action: str,
    service_id: str,
    delete_data: bool | None = None,
) -> dict:
    capability_id = f"service.manager.{str(action or '').strip().lower()}"
    input_payload = {
        "processId": str(service_id or "").strip(),
    }
    if delete_data is not None:
        input_payload["deleteData"] = bool(delete_data)
    return execute_platform_action(
        ctx,
        capability_id=capability_id,
        input_payload=input_payload,
    )


def handle_services_start(ctx: CliContext) -> int:
    data = execute_verse_service_manager_action(ctx, action="start", service_id=ctx.args.service_id)
    emit(ctx, data, renderer=lambda payload: print(payload.get("message") or "Service started."))
    return 0


def handle_services_stop(ctx: CliContext) -> int:
    data = execute_verse_service_manager_action(ctx, action="stop", service_id=ctx.args.service_id)
    emit(ctx, data, renderer=lambda payload: print(payload.get("message") or "Service stopped."))
    return 0


def handle_services_delete(ctx: CliContext) -> int:
    if ctx.args.delete_data and ctx.args.keep_data:
        raise CliError("Choose either --delete-data or --keep-data, not both.")
    if not confirm_action(f"Delete service '{ctx.args.service_id}'?", assume_yes=ctx.args.yes):
        raise CliError("Cancelled")

    if ctx.args.delete_data:
        delete_data = True
    elif ctx.args.keep_data:
        delete_data = False
    else:
        delete_data = bool(read_platform_settings(ctx.client).get("deleteDataWithServiceByDefault", True))
    data = execute_verse_service_manager_action(
        ctx,
        action="delete",
        service_id=ctx.args.service_id,
        delete_data=delete_data,
    )
    emit(ctx, data, renderer=_render_service_delete)
    return 0


def _render_service_delete(payload: dict) -> None:
    print(payload.get("message") or "Service deleted.")
    cleanup = payload.get("data_cleanup") if isinstance(payload, dict) else None
    if isinstance(cleanup, dict):
        print(f"deleteData: {cleanup.get('requested')}")
        print(f"droppedDomain: {cleanup.get('droppedDomain')}")


def should_start_after_generation(ctx: CliContext) -> bool:
    if ctx.args.start:
        return True
    if ctx.args.no_start:
        return False
    settings = read_platform_settings(ctx.client)
    return bool(settings.get("startServicesAfterGenerationByDefault", True))


def default_lapis_template() -> dict:
    return {
        "metadata": {"apiName": "", "documentation": {"enabled": True}},
        "auth": {"enabled": False},
        "models": {},
        "endpoints": {},
        "modules": [],
    }


def handle_services_generate(ctx: CliContext) -> int:
    lapis_config = read_json_payload_for_services(
        file_path=ctx.args.lapis_file,
        stdin_flag=ctx.args.stdin,
        edit_flag=ctx.args.edit,
        initial_data=default_lapis_template(),
        label="LAPIS configuration",
        allow_default=False,
    )
    data = ctx.client.request("POST", "/generate", body=lapis_config, require_auth=True)
    if not should_start_after_generation(ctx):
        process_id = str(data.get("process_id") or "").strip()
        if process_id:
            ctx.client.request("POST", f"/services/{process_id}/stop", body={}, require_auth=True)
            data["stopped_after_generation"] = True
    emit(ctx, data, renderer=_render_service_generate)
    return 0


def _render_service_generate(payload: dict) -> None:
    print(payload.get("message") or "Service generated.")
    if payload.get("process_id"):
        print(f"process_id: {payload.get('process_id')}")
    if payload.get("root_url"):
        print(f"root_url: {payload.get('root_url')}")
    if payload.get("liwiro_docs_url"):
        print(f"docs_url: {payload.get('liwiro_docs_url')}")
    if payload.get("stopped_after_generation"):
        print("Service was stopped after generation to match platform defaults.")


def handle_services_update(ctx: CliContext) -> int:
    if ctx.args.stdin and ctx.args.manager_state_stdin:
        raise CliError("Use stdin for either LAPIS or manager_state, not both")
    existing = ctx.client.request("GET", f"/services/{ctx.args.service_id}", require_auth=True)
    existing_lapis = existing.get("lapis_config") if isinstance(existing.get("lapis_config"), dict) else {}
    existing_manager = existing.get("managerState") if isinstance(existing.get("managerState"), dict) else {}

    lapis_config = None
    if ctx.args.lapis_file or ctx.args.stdin or ctx.args.edit:
        lapis_config = read_json_payload_for_services(
            file_path=ctx.args.lapis_file,
            stdin_flag=ctx.args.stdin,
            edit_flag=ctx.args.edit,
            initial_data=existing_lapis or default_lapis_template(),
            label="LAPIS configuration",
            allow_default=False,
        )

    manager_state = read_optional_json_payload(
        file_path=ctx.args.manager_state_file,
        stdin_flag=ctx.args.manager_state_stdin,
        edit_flag=ctx.args.manager_state_edit,
        initial_data=existing_manager or {},
        label="manager_state",
    )

    body = {"restart": not ctx.args.no_restart}
    if lapis_config is not None:
        body["lapis_config"] = lapis_config
    if manager_state is not None:
        body["manager_state"] = manager_state
    if ctx.args.service_documentation_key:
        body["service_documentation_key"] = ctx.args.service_documentation_key
    if "lapis_config" not in body and "manager_state" not in body:
        raise CliError("Provide LAPIS config and/or manager_state for update")

    data = ctx.client.request("PUT", f"/services/{ctx.args.service_id}", body=body, require_auth=True)
    emit(
        ctx,
        data,
        renderer=lambda payload: print_kv(payload, ["apiName", "processId", "status", "port", "rootUrl", "runtimeUrl"]),
    )
    return 0


def handle_services_download_auth_keys(ctx: CliContext) -> int:
    data = ctx.client.request("GET", f"/services/{ctx.args.service_id}/auth-keys", require_auth=True)
    if not isinstance(data, dict):
        raise CliError("Unexpected auth-key export payload.")

    target_dir = Path(ctx.args.out_dir or ".").expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    service_stem = safe_filename_segment(data.get("service") or "service")
    written = []
    for item in data.get("files") or []:
        original_name = str(item.get("filename") or "").strip()
        if not original_name:
            continue
        path = target_dir / original_name
        path.write_text(str(item.get("content") or ""), encoding="utf-8")
        written.append(str(path))
    warning_path = target_dir / f"{service_stem}-auth-material-warning.txt"
    warning_path.write_text(str(data.get("caution") or "").strip() + "\n", encoding="utf-8")
    written.append(str(warning_path))

    output = dict(data)
    output["writtenFiles"] = written
    emit(ctx, output, renderer=_render_auth_key_download)
    return 0


def _render_auth_key_download(payload: dict) -> None:
    print(f"Exported authentication material for {payload.get('service')}:")
    for path in payload.get("writtenFiles") or []:
        print(f"- {path}")
    print(f"Caution: {payload.get('caution')}")


def handle_vdb_status(ctx: CliContext) -> int:
    data = {"connection": ctx.client.request("GET", "/platform/vdb/connection", require_auth=True)}
    portal_token = str(ctx.profile.get("vdb_portal_token") or "").strip()
    if portal_token:
        try:
            data["whoami"] = ctx.client.request(
                "GET",
                "/platform/vdb/whoami",
                require_auth=True,
                headers={"X-VDB-Portal-Token": portal_token},
            )
            data["context"] = ctx.client.request(
                "GET",
                "/platform/vdb/context",
                require_auth=True,
                headers={"X-VDB-Portal-Token": portal_token},
            )
            data["portalConnected"] = True
        except CliError as exc:
            data["portalConnected"] = False
            data["portalError"] = str(exc)
    else:
        data["portalConnected"] = False
    emit(ctx, data, renderer=_render_vdb_status)
    return 0


def _render_vdb_status(payload: dict) -> None:
    connection = payload.get("connection") or {}
    print(f"transport: {connection.get('vdb_transport')}")
    print(f"server_url: {connection.get('vdb_server_url')}")
    print(f"unix_socket: {connection.get('vdb_unix_socket_path')}")
    print(f"named_pipe: {connection.get('vdb_named_pipe_path')}")
    print(f"portal_connected: {payload.get('portalConnected')}")
    if payload.get("context"):
        data = (payload.get("context") or {}).get("data") or payload.get("context") or {}
        print(f"context.domain: {data.get('domain')}")
        print(f"context.database: {data.get('database')}")


def handle_vdb_connect(ctx: CliContext) -> int:
    payload = {
        "mode": ctx.args.mode,
        "vdb_transport": ctx.args.vdb_transport,
        "vdb_server_url": ctx.args.vdb_server_url,
        "vdb_unix_socket_path": ctx.args.vdb_unix_socket_path,
        "vdb_named_pipe_path": ctx.args.vdb_named_pipe_path,
        "save_credentials": ctx.args.save_credentials,
    }
    username = str(ctx.args.username or "").strip()
    password = str(ctx.args.password or "").strip()
    if ctx.args.mode == "super_admin" and not username:
        username = input("VDB super admin username: ").strip()
    if username:
        payload["username"] = username
    if username and not password:
        password = getpass.getpass("VDB password: ")
    if password:
        payload["password"] = password

    data = ctx.client.request("POST", "/platform/vdb/session", body=payload, require_auth=True)
    portal_token = str(data.get("portalToken") or "").strip()
    if not portal_token:
        raise CliError("VDB session created but no portal token was returned")
    set_profile_values(ctx, vdb_portal_token=portal_token)
    emit(ctx, data, renderer=_render_vdb_connect)
    return 0


def _render_vdb_connect(payload: dict) -> None:
    print(f"portalToken: {payload.get('portalToken')}")
    print(f"mode: {payload.get('mode')}")
    print(f"username: {payload.get('username')}")
    print(f"transport: {payload.get('vdb_transport')}")
    context_data = (payload.get("context") or {}).get("data") or payload.get("context") or {}
    if context_data:
        print(f"context.domain: {context_data.get('domain')}")
        print(f"context.database: {context_data.get('database')}")


def handle_vdb_disconnect(ctx: CliContext) -> int:
    token = str(ctx.profile.get("vdb_portal_token") or "").strip()
    if token:
        try:
            ctx.client.request(
                "DELETE",
                "/platform/vdb/session",
                body={},
                require_auth=True,
                headers={"X-VDB-Portal-Token": token},
            )
        except CliError:
            pass
    set_profile_values(ctx, vdb_portal_token="")
    if ctx.args.json:
        print_json({"message": "VDB portal session cleared"})
    else:
        print("VDB portal session cleared")
    return 0


def handle_vdb_whoami(ctx: CliContext) -> int:
    data = ctx.client.request("GET", "/platform/vdb/whoami", require_auth=True, headers=portal_headers(ctx))
    emit(ctx, data, renderer=lambda payload: print_json(payload))
    return 0


def handle_vdb_context(ctx: CliContext) -> int:
    data = ctx.client.request("GET", "/platform/vdb/context", require_auth=True, headers=portal_headers(ctx))
    emit(ctx, data, renderer=lambda payload: print_json(payload))
    return 0


def handle_vdb_query(ctx: CliContext) -> int:
    command = None
    if ctx.args.from_file:
        command = load_text_file(ctx.args.from_file, label="VDB command")
    elif ctx.args.stdin:
        command = read_stdin_text()
    elif ctx.args.edit:
        command = edit_text("context\n", suffix=".vql")
    else:
        command = str(ctx.args.query or "")
    command = str(command or "").strip()
    if not command:
        raise CliError("Provide a readable VDB command inline, with --from-file, --stdin, or --edit")
    if command.startswith(("{", "[")):
        raise CliError("Use readable VDB syntax, for example: read users")

    data = ctx.client.request(
        "POST",
        "/platform/vdb/query",
        body={"query": command},
        require_auth=True,
        headers=portal_headers(ctx),
    )
    emit(ctx, data, renderer=lambda payload: print_json(payload))
    return 0


def handle_vdb_export(ctx: CliContext) -> int:
    domains = normalize_service_access(ctx.args.domain)
    if ctx.args.all_domains:
        options = ctx.client.request(
            "GET",
            "/platform/vdb/options",
            require_auth=True,
            headers=portal_headers(ctx),
        )
        domains = normalize_service_access((options or {}).get("domains") or [])
    if not domains:
        raise CliError("Specify at least one --domain or use --all-domains")
    payload = {
        "action": "export",
        "out_dir": str(ctx.args.out_dir or "").strip() or "/tmp/vdb-exports",
        "domains": domains,
    }
    data = ctx.client.request(
        "POST",
        "/platform/vdb/query",
        body={"query": payload},
        require_auth=True,
        headers=portal_headers(ctx),
    )
    emit(ctx, data, renderer=_render_vdb_export)
    return 0


def _render_vdb_export(payload: dict) -> None:
    data = payload.get("data") or {}
    print(f"zip_file: {data.get('zip_file')}")
    print(f"out_dir: {data.get('out_dir')}")
    print(f"exported_domains: {','.join(data.get('exported_domains') or [])}")
    skipped = data.get("skipped_domains") or {}
    if skipped:
        print(f"skipped_domains: {json.dumps(skipped)}")


def handle_vdb_options(ctx: CliContext) -> int:
    data = ctx.client.request("GET", "/platform/vdb/options", require_auth=True, headers=portal_headers(ctx))
    emit(ctx, data, renderer=_render_vdb_options)
    return 0


def _render_vdb_options(payload: dict) -> None:
    for key in ["domains", "dbs", "collections", "models", "scripts", "users", "roles", "permissions"]:
        values = payload.get(key) or []
        print(f"{key}:")
        if values:
            for value in values:
                print(f"- {value}")
        else:
            print("-")


def handle_vdb_domains_list(ctx: CliContext) -> int:
    data = ctx.client.request("GET", "/platform/vdb/domains", require_auth=True)
    emit(
        ctx,
        data,
        renderer=lambda payload: print("\n".join(payload.get("domains") or []) if payload.get("domains") else "(no domains)"),
    )
    return 0


def handle_vdb_domains_create(ctx: CliContext) -> int:
    payload = {"domain": ctx.args.domain, "db": ctx.args.database}
    data = ctx.client.request("POST", "/platform/vdb/domains", body=payload, require_auth=True)
    emit(ctx, data, renderer=lambda body: print(f"Created domain {body.get('domain')} with db {body.get('database')}"))
    return 0


def handle_vi_status(ctx: CliContext) -> int:
    data = ctx.client.request("GET", "/platform/vi/connection", require_auth=True)
    emit(ctx, data, renderer=lambda payload: print_kv(payload, list(payload.keys())))
    return 0


def handle_vi_config_get(ctx: CliContext) -> int:
    return handle_vi_status(ctx)


def handle_vi_config_set(ctx: CliContext) -> int:
    if not ctx.args.source_dir:
        raise CliError("source_dir is required")
    data = ctx.client.request(
        "PUT",
        "/platform/vi/connection",
        body={"source_dir": ctx.args.source_dir},
        require_auth=True,
    )
    emit(ctx, data, renderer=lambda payload: print_kv(payload, ["source_dir", "files_count", "repl_active"]))
    return 0


def handle_vi_dirs_list(ctx: CliContext) -> int:
    query = {"path": ctx.args.path} if ctx.args.path else None
    data = ctx.client.request("GET", "/platform/vi/directories", query=query, require_auth=True)
    emit(ctx, data, renderer=_render_vi_directories)
    return 0


def _render_vi_directories(payload: dict) -> None:
    print(f"path: {payload.get('path')}")
    print(f"source_dir: {payload.get('source_dir')}")
    print("directories:")
    directories = payload.get("directories") or []
    if not directories:
        print("-")
    for item in directories:
        print(f"- {item.get('name')}: {item.get('path')}")


def handle_vi_files_list(ctx: CliContext) -> int:
    data = ctx.client.request("GET", "/platform/vi/files", require_auth=True)
    rows = data.get("files") if isinstance(data, dict) else []
    emit(ctx, rows, renderer=render_vi_files_table)
    return 0


def handle_vi_files_read(ctx: CliContext) -> int:
    data = ctx.client.request("GET", f"/platform/vi/files/{ctx.args.path}", require_auth=True)
    if ctx.args.out_file:
        target = Path(ctx.args.out_file).expanduser().resolve()
        target.write_text(str(data.get("content") or ""), encoding="utf-8")
    emit(
        ctx,
        data,
        renderer=lambda payload: print(payload.get("content") or ""),
    )
    return 0


def handle_vi_files_write(ctx: CliContext) -> int:
    initial = ""
    try:
        existing = ctx.client.request("GET", f"/platform/vi/files/{ctx.args.path}", require_auth=True)
        initial = str(existing.get("content") or "")
        method = "PUT"
        endpoint = f"/platform/vi/files/{ctx.args.path}"
        payload = {"path": ctx.args.rename_to or ctx.args.path}
    except CliHttpError as exc:
        if exc.status_code != 404:
            raise
        method = "POST"
        endpoint = "/platform/vi/files"
        payload = {"path": ctx.args.rename_to or ctx.args.path}

    content = read_text_payload(
        file_path=ctx.args.from_file,
        stdin_flag=ctx.args.stdin,
        edit_flag=ctx.args.edit,
        inline_text=ctx.args.text,
        initial_text=initial,
        label="VI file content",
        suffix=Path(ctx.args.path).suffix or ".versa",
    )
    payload["content"] = content
    data = ctx.client.request(method, endpoint, body=payload, require_auth=True)
    emit(ctx, data, renderer=lambda body: print(f"Saved {body.get('path')} ({body.get('size')} bytes)"))
    return 0


def handle_vi_files_move(ctx: CliContext) -> int:
    existing = ctx.client.request("GET", f"/platform/vi/files/{ctx.args.path}", require_auth=True)
    payload = {"path": ctx.args.new_path, "content": str(existing.get("content") or "")}
    data = ctx.client.request("PUT", f"/platform/vi/files/{ctx.args.path}", body=payload, require_auth=True)
    emit(ctx, data, renderer=lambda body: print(f"{ctx.args.path} -> {body.get('path')}"))
    return 0


def handle_vi_files_delete(ctx: CliContext) -> int:
    if not confirm_action(f"Delete VI file '{ctx.args.path}'?", assume_yes=ctx.args.yes):
        raise CliError("Cancelled")
    data = ctx.client.request("DELETE", f"/platform/vi/files/{ctx.args.path}", require_auth=True)
    emit(ctx, data, renderer=lambda payload: print(payload.get("message") or "File deleted"))
    return 0


def handle_vi_run(ctx: CliContext) -> int:
    data = ctx.client.request("POST", f"/platform/vi/files/{ctx.args.path}/run", body={}, require_auth=True)
    emit(ctx, data, renderer=_render_vi_run)
    return 0


def _render_vi_run(payload: dict) -> None:
    print(f"path: {payload.get('path')}")
    print(f"exitCode: {payload.get('exitCode')}")
    if payload.get("stdout"):
        print("stdout:")
        print(payload.get("stdout"))
    if payload.get("stderr"):
        print("stderr:")
        print(payload.get("stderr"))


def handle_vi_repl_start(ctx: CliContext) -> int:
    data = ctx.client.request("POST", "/platform/vi/repl/session", body={}, require_auth=True)
    emit(ctx, data, renderer=_render_vi_repl_payload)
    return 0


def handle_vi_repl_send(ctx: CliContext) -> int:
    source = read_text_payload(
        file_path=ctx.args.from_file,
        stdin_flag=ctx.args.stdin,
        edit_flag=ctx.args.edit,
        inline_text=ctx.args.source,
        initial_text="",
        label="VI REPL input",
        suffix=".versa",
    )
    data = ctx.client.request("POST", "/platform/vi/repl/input", body={"source": source}, require_auth=True)
    emit(ctx, data, renderer=_render_vi_repl_payload)
    return 0


def _render_vi_repl_payload(payload: dict) -> None:
    if payload.get("output"):
        print(payload.get("output"))
    if payload.get("stderr"):
        print(payload.get("stderr"), file=sys.stderr)
    if payload.get("prompt"):
        print(f"prompt: {payload.get('prompt')}")
    if "active" in payload:
        print(f"active: {payload.get('active')}")


def handle_vi_repl_stop(ctx: CliContext) -> int:
    data = ctx.client.request("DELETE", "/platform/vi/repl/session", body={}, require_auth=True)
    emit(ctx, data, renderer=lambda payload: print(payload.get("message") or "VI REPL session closed"))
    return 0


def handle_modules_catalog(ctx: CliContext) -> int:
    data = ctx.client.request("GET", "/platform/vi/modules/catalog", require_auth=True)
    emit(ctx, data, renderer=_render_modules_catalog)
    return 0


def _render_modules_catalog(payload: dict) -> None:
    print(f"username: {payload.get('username')}")
    print(f"is_super_admin: {payload.get('is_super_admin')}")
    print(f"available_domains: {', '.join(payload.get('available_domains') or [])}")
    print(f"reserved_names: {', '.join(payload.get('reserved_names') or [])}")
    print("")
    render_modules_table(payload.get("modules") or [])


def handle_modules_list(ctx: CliContext) -> int:
    data = ctx.client.request("GET", "/platform/vi/modules", require_auth=True)
    rows = data.get("modules") if isinstance(data, dict) else []
    emit(ctx, rows, renderer=render_modules_table)
    return 0


def handle_modules_show(ctx: CliContext) -> int:
    data = ctx.client.request("GET", f"/platform/vi/modules/{ctx.args.name}", require_auth=True)
    emit(ctx, data, renderer=lambda payload: print_json(payload.get("module") or payload))
    return 0


def handle_modules_create(ctx: CliContext) -> int:
    body = build_module_body(ctx.args)
    if not str(body.get("name") or "").strip():
        raise CliError("Module name is required")
    data = ctx.client.request("POST", "/platform/vi/modules", body=body, require_auth=True)
    emit(ctx, data, renderer=lambda payload: print_json(payload.get("module") or payload))
    return 0


def handle_modules_update(ctx: CliContext) -> int:
    existing_payload = ctx.client.request("GET", f"/platform/vi/modules/{ctx.args.name}", require_auth=True)
    existing = existing_payload.get("module") if isinstance(existing_payload, dict) else {}
    body = build_module_body(ctx.args, existing=existing if isinstance(existing, dict) else {})
    if not body:
        raise CliError("No updates supplied")
    data = ctx.client.request("PUT", f"/platform/vi/modules/{ctx.args.name}", body=body, require_auth=True)
    emit(ctx, data, renderer=lambda payload: print_json(payload.get("module") or payload))
    return 0


def handle_modules_delete(ctx: CliContext) -> int:
    if not confirm_action(f"Delete VI module '{ctx.args.name}'?", assume_yes=ctx.args.yes):
        raise CliError("Cancelled")
    data = ctx.client.request("DELETE", f"/platform/vi/modules/{ctx.args.name}", require_auth=True)
    emit(ctx, data, renderer=lambda payload: print(payload.get("message") or "Module deleted"))
    return 0


def handle_modules_assign_domain(ctx: CliContext) -> int:
    module_name = str(ctx.args.name or "").strip()
    last_response = None
    for domain in normalize_service_access(ctx.args.domain):
        last_response = ctx.client.request(
            "POST",
            f"/platform/vi/modules/{module_name}/domains",
            body={"domain": domain},
            require_auth=True,
        )
    if last_response is None:
        raise CliError("At least one domain is required")
    emit(ctx, last_response, renderer=lambda payload: print_json(payload.get("module") or payload))
    return 0


def handle_local_status(ctx: CliContext) -> int:
    rows = collect_local_status(ctx, target=ctx.args.target)
    emit(ctx, rows, renderer=_render_local_status)
    return 0


def _render_local_status(rows: list[dict]) -> None:
    headers = ["Target", "Tracked", "PID", "Running", "Healthy", "Detail"]
    body = []
    for item in rows:
        body.append(
            [
                item.get("target") or "",
                "yes" if item.get("tracked") else "no",
                item.get("pid") or "",
                "yes" if item.get("running") else "no",
                "yes" if item.get("healthy") else "no",
                item.get("detail") or "",
            ]
        )
    print_table(headers, body)


def handle_local_start(ctx: CliContext) -> int:
    target = ctx.args.target
    if ctx.args.foreground:
        if target in {"vdb", "all"}:
            ensure_vdb_mit_acceptance()
        command, cwd, env, _, _, _, _ = build_local_command(ctx.args)
        result = subprocess.run(command, cwd=str(cwd), env=env, check=False)
        return int(result.returncode)

    data = start_local_target_in_background(
        ctx.state,
        target,
        backend_port=int(ctx.args.backend_port or 5000),
        frontend_port=int(ctx.args.frontend_port or 3000),
        vdb_transport=str(ctx.args.vdb_transport or "unixsocket").strip().lower() or "unixsocket",
        vdb_http_url=str(ctx.args.vdb_http_url or DEFAULT_VDB_HTTP_URL).strip() or DEFAULT_VDB_HTTP_URL,
        vdb_socket_path=str(ctx.args.vdb_socket_path or resolve_default_vdb_socket_path()).strip() or resolve_default_vdb_socket_path(),
    )
    emit(ctx, data, renderer=lambda payload: _render_local_start(payload))
    return 0


def _render_local_start(payload: dict) -> None:
    print(f"target: {payload.get('target')}")
    print(f"pid: {payload.get('pid')}")
    print(f"log_file: {payload.get('log_file')}")
    if payload.get("backend_url"):
        print(f"backend_url: {payload.get('backend_url')}")
    if payload.get("frontend_url"):
        print(f"frontend_url: {payload.get('frontend_url')}")
    if payload.get("vdb_target"):
        print(f"vdb_target: {payload.get('vdb_target')}")


def stop_local_target(ctx: CliContext, target: str) -> dict:
    processes = state_local_processes(ctx.state)
    entry = processes.get(target)
    pid = int((entry or {}).get("pid") or 0)
    stopped = False
    fallback_pids = []

    def _entry_port(url_key: str, default: int) -> int:
        value = str((entry or {}).get(url_key) or "").strip()
        if not value:
            return default
        try:
            return int(parse.urlparse(value).port or default)
        except ValueError:
            return default

    if pid:
        stopped = terminate_pid(pid)
    elif target == "backend":
        fallback_pids = find_pids_by_port(_entry_port("backend_url", 5000))
    elif target == "frontend":
        fallback_pids = find_pids_by_port(_entry_port("frontend_url", 3000))
    elif target == "vdb":
        transport = str((entry or {}).get("transport") or "unixsocket").strip().lower() or "unixsocket"
        if transport == "http":
            fallback_pids = find_pids_by_port(resolve_vdb_http_port(str((entry or {}).get("vdb_http_url") or DEFAULT_VDB_HTTP_URL)))
        else:
            fallback_pids = find_pids_by_socket(str((entry or {}).get("vdb_socket_path") or resolve_default_vdb_socket_path()))
    elif target == "all":
        backend_entry = processes.get("backend") or {}
        frontend_entry = processes.get("frontend") or {}
        vdb_entry = processes.get("vdb") or {}
        backend_port = int(parse.urlparse(str(backend_entry.get("backend_url") or DEFAULT_BACKEND)).port or 5000)
        frontend_port = int(parse.urlparse(str(frontend_entry.get("frontend_url") or DEFAULT_FRONTEND_URL)).port or 3000)
        vdb_http_port = resolve_vdb_http_port(str(vdb_entry.get("vdb_http_url") or DEFAULT_VDB_HTTP_URL))
        vdb_socket_path = str(vdb_entry.get("vdb_socket_path") or resolve_default_vdb_socket_path())
        fallback_pids = list(
            {
                *find_pids_by_port(frontend_port),
                *find_pids_by_port(backend_port),
                *find_pids_by_port(vdb_http_port),
                *find_pids_by_socket(vdb_socket_path),
            }
        )

    for fallback_pid in fallback_pids:
        if terminate_pid(fallback_pid):
            stopped = True

    remove_local_process(ctx, target)
    if target == "all":
        for name in ["backend", "frontend", "vdb"]:
            remove_local_process(ctx, name)
    return {"target": target, "pid": pid, "stopped": stopped or not pid}


def handle_local_stop(ctx: CliContext) -> int:
    result = stop_local_target(ctx, ctx.args.target)
    emit(ctx, result, renderer=lambda payload: print(f"Stopped {payload.get('target')}"))
    return 0


def handle_local_restart(ctx: CliContext) -> int:
    stop_local_target(ctx, ctx.args.target)
    return handle_local_start(ctx)


def handle_local_logs(ctx: CliContext) -> int:
    entry = local_process_entry(ctx, ctx.args.target)
    if not entry:
        raise CliError(f"No tracked log file for target '{ctx.args.target}'")
    log_file = Path(str(entry.get("log_file") or "")).expanduser()
    if not log_file.exists():
        raise CliError(f"Log file not found: {log_file}")
    lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = lines[-int(ctx.args.lines or 50):]
    if ctx.args.json:
        print_json({"target": ctx.args.target, "log_file": str(log_file), "lines": tail})
    else:
        print(f"log_file: {log_file}")
        for line in tail:
            print(line)
    return 0


def handle_shell(ctx: CliContext) -> int:
    session = ShellSession(
        profile_name=ctx.profile_name,
        backend=ctx.client.backend,
        timeout=int(ctx.args.timeout),
    )
    return run_shell_loop(session)


def add_user_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--from-file", help="Load the user payload from a JSON file")
    parser.add_argument("--edit", action="store_true", help="Open the user payload in $EDITOR")
    parser.add_argument("--password", help="User password")
    parser.add_argument("--role", help="Platform role")
    parser.add_argument("--service-access", action="append", default=None, help="Allowed service id or api name; repeat as needed")
    parser.add_argument("--permissions-json", help="Inline JSON or JSON file path for permissions")
    parser.add_argument("--permissions-file", help="JSON file for permissions")
    parser.add_argument("--rbac-json", help="Inline JSON or JSON file path for liwiro_rbac")
    parser.add_argument("--rbac-file", help="JSON file for liwiro_rbac")


def add_module_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--from-file", help="Load the module payload from a JSON file")
    parser.add_argument("--edit", action="store_true", help="Open the module payload in $EDITOR")
    parser.add_argument("--title", help="Module title")
    parser.add_argument("--description", help="Module description")
    parser.add_argument("--scope", choices=["domain", "global"], help="Module scope")
    parser.add_argument("--assigned-domain", action="append", default=None, help="Assigned domain; repeat as needed")
    parser.add_argument("--source-file", help="Path to Versa source file")
    parser.add_argument("--source-text", help="Inline Versa source")
    parser.add_argument("--config-schema-json", help="Inline JSON or JSON file path for config_schema")
    parser.add_argument("--config-schema-file", help="JSON file for config_schema")
    parser.add_argument("--config-defaults-json", help="Inline JSON or JSON file path for config_defaults")
    parser.add_argument("--config-defaults-file", help="JSON file for config_defaults")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="liwiro_cli",
        description="Liwiro command line interface",
        epilog=CLI_ROOT_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--backend", default="", help=f"Liwiro backend URL (default: {DEFAULT_BACKEND})")
    parser.add_argument("--json", action="store_true", help="Print raw JSON responses")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds")
    parser.add_argument("--profile", default="", help="Profile name to use from ~/.liwiro_cli.json")

    subparsers = parser.add_subparsers(dest="area", required=True)

    shell_parser = subparsers.add_parser(
        "shell",
        help="Start the interactive Liwiro shell",
        description="Start the interactive Liwiro shell.",
        epilog=SHELL_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    shell_parser.set_defaults(handler=handle_shell)

    auth_parser = subparsers.add_parser("auth", help="Authenticate and inspect Liwiro access")
    auth_sub = auth_parser.add_subparsers(dest="action", required=True)

    auth_status = auth_sub.add_parser("status", help="Show bootstrap/auth status")
    auth_status.set_defaults(handler=handle_auth_status)

    auth_vdb_status = auth_sub.add_parser("vdb-status", help="Probe the configured VDB connection")
    auth_vdb_status.add_argument("--vdb-transport", dest="vdb_transport", help="Transport override")
    auth_vdb_status.add_argument("--vdb-server-url", dest="vdb_server_url", help="HTTP transport URL override")
    auth_vdb_status.add_argument("--vdb-unix-socket-path", dest="vdb_unix_socket_path", help="Unix socket path override")
    auth_vdb_status.add_argument("--vdb-named-pipe-path", dest="vdb_named_pipe_path", help="Named pipe path override")
    auth_vdb_status.add_argument("--attempt-autostart", action="store_true", help="Attempt local VDB transport autostart")
    auth_vdb_status.set_defaults(handler=handle_auth_vdb_status)

    auth_login = auth_sub.add_parser("login", help="Sign in or bootstrap Liwiro")
    auth_login.add_argument("--username", help="Liwiro username")
    auth_login.add_argument("--password", help="Liwiro password")
    auth_login.add_argument("--vdb-transport", dest="vdb_transport", help="Bootstrap/login VDB transport")
    auth_login.add_argument("--vdb-server-url", dest="vdb_server_url", help="Bootstrap/login VDB server URL")
    auth_login.add_argument("--vdb-unix-socket-path", dest="vdb_unix_socket_path", help="Bootstrap/login VDB Unix socket path")
    auth_login.add_argument("--vdb-named-pipe-path", dest="vdb_named_pipe_path", help="Bootstrap/login VDB named pipe path")
    auth_login.add_argument("--vdb-app-username", dest="vdb_app_username", help="Bootstrap VDB app username")
    auth_login.add_argument("--vdb-app-password", dest="vdb_app_password", help="Bootstrap VDB app password")
    auth_login.add_argument("--liwiro-super-admin-username", dest="liwiro_super_admin_username", help="Bootstrap Liwiro super admin username")
    auth_login.add_argument("--liwiro-super-admin-password", dest="liwiro_super_admin_password", help="Bootstrap Liwiro super admin password")
    auth_login.set_defaults(handler=handle_auth_login)

    auth_logout = auth_sub.add_parser("logout", help="Sign out and clear the stored token")
    auth_logout.set_defaults(handler=handle_auth_logout)

    auth_me = auth_sub.add_parser("me", help="Show the current Liwiro session")
    auth_me.set_defaults(handler=handle_auth_me)

    capabilities_parser = subparsers.add_parser("capabilities", help="Inspect the shared Liwiro capability catalog")
    capabilities_sub = capabilities_parser.add_subparsers(dest="action", required=True)
    capabilities_list = capabilities_sub.add_parser("list", help="List platform capabilities")
    capabilities_list.add_argument("--client", choices=["verse", "cli", "ui"], default="", help="Filter capabilities to one client")
    capabilities_list.add_argument("--surface-id", default="", help="Filter capabilities to one surface id")
    capabilities_list.add_argument("--executable-only", action="store_true", help="Show only executable/page-action capabilities")
    capabilities_list.add_argument("--include-unavailable", action="store_true", help="Include capabilities you are not currently allowed to execute")
    capabilities_list.set_defaults(handler=handle_capabilities_list)
    capabilities_show = capabilities_sub.add_parser("show", help="Show one platform capability")
    capabilities_show.add_argument("capability_id", help="Capability id")
    capabilities_show.set_defaults(handler=handle_capabilities_show)

    health_parser = subparsers.add_parser("health", help="Check backend, auth, VDB, VI, and local health")
    health_sub = health_parser.add_subparsers(dest="action", required=True)
    health_check = health_sub.add_parser("check", help="Run a control-plane health check")
    health_check.set_defaults(handler=handle_health_check)

    license_parser = subparsers.add_parser("license", help="Inspect license disclosure")
    license_sub = license_parser.add_subparsers(dest="action", required=True)
    license_show = license_sub.add_parser("show", help="Show backend license disclosure")
    license_show.set_defaults(handler=handle_license_show)

    profiles_parser = subparsers.add_parser("profiles", help="Manage CLI backend/auth profiles")
    profiles_sub = profiles_parser.add_subparsers(dest="action", required=True)
    profiles_list = profiles_sub.add_parser("list", help="List saved CLI profiles")
    profiles_list.set_defaults(handler=handle_profiles_list)
    profiles_show = profiles_sub.add_parser("show", help="Show one profile")
    profiles_show.add_argument("name", nargs="?", help="Profile name")
    profiles_show.set_defaults(handler=handle_profiles_show)
    profiles_use = profiles_sub.add_parser("use", help="Select the active profile")
    profiles_use.add_argument("name", help="Profile name")
    profiles_use.set_defaults(handler=handle_profiles_use)
    profiles_set_backend = profiles_sub.add_parser("set-backend", help="Create/update a profile backend URL")
    profiles_set_backend.add_argument("name", help="Profile name")
    profiles_set_backend.add_argument("backend_url", help="Backend URL")
    profiles_set_backend.set_defaults(handler=handle_profiles_set_backend)
    profiles_delete = profiles_sub.add_parser("delete", help="Delete a saved profile")
    profiles_delete.add_argument("name", help="Profile name")
    profiles_delete.add_argument("--yes", action="store_true", help="Skip the delete confirmation prompt")
    profiles_delete.set_defaults(handler=handle_profiles_delete)

    settings_parser = subparsers.add_parser("settings", help="Read or update platform settings")
    settings_sub = settings_parser.add_subparsers(dest="action", required=True)
    settings_show = settings_sub.add_parser("show", help="Show platform settings")
    settings_show.set_defaults(handler=handle_settings_show)
    settings_set = settings_sub.add_parser("set", help="Update platform settings with KEY=VALUE pairs")
    settings_set.add_argument("assignments", nargs="+", help="Setting updates such as productionMode=on")
    settings_set.set_defaults(handler=handle_settings_set)

    users_parser = subparsers.add_parser("users", help="Manage Liwiro platform users")
    users_sub = users_parser.add_subparsers(dest="action", required=True)
    users_list = users_sub.add_parser("list", help="List users")
    users_list.set_defaults(handler=handle_users_list)
    users_show = users_sub.add_parser("show", help="Show one user")
    users_show.add_argument("username", help="Username")
    users_show.set_defaults(handler=handle_users_show)
    users_create = users_sub.add_parser("create", help="Create a user")
    users_create.add_argument("username", help="Username")
    add_user_common_arguments(users_create)
    users_create.set_defaults(handler=handle_users_create)
    users_update = users_sub.add_parser("update", help="Update a user")
    users_update.add_argument("username", help="Username")
    users_update.add_argument("--prompt-password", action="store_true", help="Prompt for a new password")
    add_user_common_arguments(users_update)
    users_update.set_defaults(handler=handle_users_update)
    users_delete = users_sub.add_parser("delete", help="Delete a user")
    users_delete.add_argument("username", help="Username")
    users_delete.add_argument("--yes", action="store_true", help="Skip the delete confirmation prompt")
    users_delete.set_defaults(handler=handle_users_delete)

    services_parser = subparsers.add_parser("services", help="Manage generated services")
    services_sub = services_parser.add_subparsers(dest="action", required=True)
    services_list = services_sub.add_parser("list", help="List services")
    services_list.add_argument("--refresh", choices=["auto", "on", "off"], default="auto", help="Override backend runtime refresh behavior")
    services_list.add_argument("--full", action="store_true", help="Request full service documents instead of summary rows")
    services_list.set_defaults(handler=handle_services_list)
    services_show = services_sub.add_parser("show", help="Show one service")
    services_show.add_argument("service_id", help="Service process id")
    services_show.add_argument("--out-file", help="Write the JSON payload to a file")
    services_show.set_defaults(handler=handle_services_show)
    services_start = services_sub.add_parser("start", help="Start a service")
    services_start.add_argument("service_id", help="Service process id")
    services_start.set_defaults(handler=handle_services_start)
    services_stop = services_sub.add_parser("stop", help="Stop a service")
    services_stop.add_argument("service_id", help="Service process id")
    services_stop.set_defaults(handler=handle_services_stop)
    services_delete = services_sub.add_parser("delete", help="Delete a service")
    services_delete.add_argument("service_id", help="Service process id")
    services_delete.add_argument("--delete-data", action="store_true", help="Delete the service data workspace too")
    services_delete.add_argument("--keep-data", action="store_true", help="Keep the service data workspace")
    services_delete.add_argument("--yes", action="store_true", help="Skip the delete confirmation prompt")
    services_delete.set_defaults(handler=handle_services_delete)
    services_generate = services_sub.add_parser(
        "generate",
        help="Generate a service from LAPIS JSON",
        description=SERVICES_GENERATE_HELP,
        epilog=SERVICES_GENERATE_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    services_generate.add_argument("lapis_file", nargs="?", help="Path to LAPIS JSON file")
    services_generate.add_argument("--stdin", action="store_true", help="Read LAPIS JSON from stdin")
    services_generate.add_argument("--edit", action="store_true", help="Edit LAPIS JSON in $EDITOR before submit")
    services_generate.add_argument("--start", action="store_true", help="Leave the service running after generation")
    services_generate.add_argument("--no-start", action="store_true", help="Stop the service after generation")
    services_generate.set_defaults(handler=handle_services_generate)
    services_update = services_sub.add_parser(
        "update",
        help="Update a service",
        description=SERVICES_UPDATE_HELP,
        epilog=SERVICES_UPDATE_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    services_update.add_argument("service_id", help="Service process id")
    services_update.add_argument("lapis_file", nargs="?", help="Path to LAPIS JSON file")
    services_update.add_argument("--stdin", action="store_true", help="Read LAPIS JSON from stdin")
    services_update.add_argument("--edit", action="store_true", help="Edit the current LAPIS JSON in $EDITOR")
    services_update.add_argument("--no-restart", action="store_true", help="Persist the config without restarting the service")
    services_update.add_argument("--service-documentation-key", help="Override the documentation key before hashing")
    services_update.add_argument("--manager-state-file", help="JSON file for manager_state")
    services_update.add_argument("--manager-state-stdin", action="store_true", help="Read manager_state JSON from stdin")
    services_update.add_argument("--manager-state-edit", action="store_true", help="Edit manager_state JSON in $EDITOR")
    services_update.set_defaults(handler=handle_services_update)
    services_auth_keys = services_sub.add_parser("download-auth-keys", help="Download auth-service signing material")
    services_auth_keys.add_argument("service_id", help="Service process id")
    services_auth_keys.add_argument("--out-dir", default=".", help="Directory to write the exported files into")
    services_auth_keys.set_defaults(handler=handle_services_download_auth_keys)

    vdb_parser = subparsers.add_parser("vdb", help="Use the Liwiro VDB portal from the CLI")
    vdb_sub = vdb_parser.add_subparsers(dest="action", required=True)
    vdb_status = vdb_sub.add_parser("status", help="Show saved VDB portal/session status")
    vdb_status.set_defaults(handler=handle_vdb_status)
    vdb_connect = vdb_sub.add_parser("connect", help="Create and store a VDB portal session")
    vdb_connect.add_argument("--mode", choices=["app", "super_admin"], default="app", help="Session mode")
    vdb_connect.add_argument("--username", help="VDB username override")
    vdb_connect.add_argument("--password", help="VDB password override")
    vdb_connect.add_argument("--vdb-transport", dest="vdb_transport", help="Transport override")
    vdb_connect.add_argument("--vdb-server-url", dest="vdb_server_url", help="HTTP server URL override")
    vdb_connect.add_argument("--vdb-unix-socket-path", dest="vdb_unix_socket_path", help="Unix socket path override")
    vdb_connect.add_argument("--vdb-named-pipe-path", dest="vdb_named_pipe_path", help="Named pipe path override")
    vdb_connect.add_argument("--save-credentials", action="store_true", help="Persist VDB super-admin credentials when allowed")
    vdb_connect.set_defaults(handler=handle_vdb_connect)
    vdb_disconnect = vdb_sub.add_parser("disconnect", help="Clear the stored VDB portal session")
    vdb_disconnect.set_defaults(handler=handle_vdb_disconnect)
    vdb_whoami = vdb_sub.add_parser("whoami", help="Show VDB whoami from the active portal session")
    vdb_whoami.set_defaults(handler=handle_vdb_whoami)
    vdb_context = vdb_sub.add_parser("context", help="Show VDB context from the active portal session")
    vdb_context.set_defaults(handler=handle_vdb_context)
    vdb_query = vdb_sub.add_parser(
        "query",
        help="Submit a readable VDB command",
        description=VDB_QUERY_HELP,
        epilog=VDB_QUERY_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    vdb_query.add_argument("query", nargs="?", help="Inline readable VDB command")
    vdb_query.add_argument("--from-file", help="Load readable VDB commands from file")
    vdb_query.add_argument("--stdin", action="store_true", help="Read VDB commands from stdin")
    vdb_query.add_argument("--edit", action="store_true", help="Edit VDB commands in $EDITOR")
    vdb_query.set_defaults(handler=handle_vdb_query)
    vdb_export = vdb_sub.add_parser("export", help="Run a VDB export query")
    vdb_export.add_argument("--domain", action="append", default=None, help="Domain to export; repeat as needed")
    vdb_export.add_argument("--all-domains", action="store_true", help="Export all available domains")
    vdb_export.add_argument("--out-dir", default="/tmp/vdb-exports", help="Output directory for VDB export")
    vdb_export.set_defaults(handler=handle_vdb_export)
    vdb_options = vdb_sub.add_parser("options", help="List VDB portal options")
    vdb_options.set_defaults(handler=handle_vdb_options)
    vdb_domains = vdb_sub.add_parser("domains", help="Manage VDB domains")
    vdb_domains_sub = vdb_domains.add_subparsers(dest="subaction", required=True)
    vdb_domains_list = vdb_domains_sub.add_parser("list", help="List VDB domains")
    vdb_domains_list.set_defaults(handler=handle_vdb_domains_list)
    vdb_domains_create = vdb_domains_sub.add_parser("create", help="Create a VDB domain")
    vdb_domains_create.add_argument("domain", help="Domain name")
    vdb_domains_create.add_argument("--database", default="main", help="Initial database name")
    vdb_domains_create.set_defaults(handler=handle_vdb_domains_create)

    vi_parser = subparsers.add_parser("vi", help="Use the Liwiro VI portal from the CLI")
    vi_sub = vi_parser.add_subparsers(dest="action", required=True)
    vi_status = vi_sub.add_parser("status", help="Show VI connection/runtime status")
    vi_status.set_defaults(handler=handle_vi_status)
    vi_config = vi_sub.add_parser("config", help="Get or set VI portal configuration")
    vi_config_sub = vi_config.add_subparsers(dest="subaction", required=True)
    vi_config_get = vi_config_sub.add_parser("get", help="Show VI portal config")
    vi_config_get.set_defaults(handler=handle_vi_config_get)
    vi_config_set = vi_config_sub.add_parser("set", help="Update VI portal config")
    vi_config_set.add_argument("--source-dir", required=True, help="New VI portal source directory")
    vi_config_set.set_defaults(handler=handle_vi_config_set)
    vi_dirs = vi_sub.add_parser("dirs", help="Browse allowed VI directories")
    vi_dirs_sub = vi_dirs.add_subparsers(dest="subaction", required=True)
    vi_dirs_list = vi_dirs_sub.add_parser("list", help="List subdirectories")
    vi_dirs_list.add_argument("path", nargs="?", help="Path to inspect")
    vi_dirs_list.set_defaults(handler=handle_vi_dirs_list)
    vi_files = vi_sub.add_parser("files", help="Manage VI portal files")
    vi_files_sub = vi_files.add_subparsers(dest="subaction", required=True)
    vi_files_list = vi_files_sub.add_parser("list", help="List VI portal files")
    vi_files_list.set_defaults(handler=handle_vi_files_list)
    vi_files_read = vi_files_sub.add_parser("read", help="Read a VI file")
    vi_files_read.add_argument("path", help="Relative VI file path")
    vi_files_read.add_argument("--out-file", help="Write the content to a file")
    vi_files_read.set_defaults(handler=handle_vi_files_read)
    vi_files_write = vi_files_sub.add_parser(
        "write",
        help="Create or update a VI file",
        description=VI_FILES_WRITE_HELP,
        epilog=VI_FILES_WRITE_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    vi_files_write.add_argument("path", help="Relative VI file path")
    vi_files_write.add_argument("--from-file", help="Read content from a file")
    vi_files_write.add_argument("--stdin", action="store_true", help="Read content from stdin")
    vi_files_write.add_argument("--edit", action="store_true", help="Edit file content in $EDITOR")
    vi_files_write.add_argument("--text", help="Inline file content")
    vi_files_write.add_argument("--rename-to", help="Rename the file while writing")
    vi_files_write.set_defaults(handler=handle_vi_files_write)
    vi_files_move = vi_files_sub.add_parser("move", help="Rename a VI file")
    vi_files_move.add_argument("path", help="Current relative path")
    vi_files_move.add_argument("new_path", help="New relative path")
    vi_files_move.set_defaults(handler=handle_vi_files_move)
    vi_files_delete = vi_files_sub.add_parser("delete", help="Delete a VI file")
    vi_files_delete.add_argument("path", help="Relative VI file path")
    vi_files_delete.add_argument("--yes", action="store_true", help="Skip the delete confirmation prompt")
    vi_files_delete.set_defaults(handler=handle_vi_files_delete)
    vi_run = vi_sub.add_parser("run", help="Execute a VI file")
    vi_run.add_argument("path", help="Relative VI file path")
    vi_run.set_defaults(handler=handle_vi_run)
    vi_repl = vi_sub.add_parser("repl", help="Use the VI REPL")
    vi_repl_sub = vi_repl.add_subparsers(dest="subaction", required=True)
    vi_repl_start = vi_repl_sub.add_parser("start", help="Start or attach to the VI REPL")
    vi_repl_start.set_defaults(handler=handle_vi_repl_start)
    vi_repl_send = vi_repl_sub.add_parser(
        "send",
        help="Send source to the VI REPL",
        description=VI_REPL_SEND_HELP,
        epilog=VI_REPL_SEND_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    vi_repl_send.add_argument("source", nargs="?", help="Inline source")
    vi_repl_send.add_argument("--from-file", help="Read REPL input from a file")
    vi_repl_send.add_argument("--stdin", action="store_true", help="Read REPL input from stdin")
    vi_repl_send.add_argument("--edit", action="store_true", help="Edit REPL input in $EDITOR")
    vi_repl_send.set_defaults(handler=handle_vi_repl_send)
    vi_repl_stop = vi_repl_sub.add_parser("stop", help="Stop the VI REPL session")
    vi_repl_stop.set_defaults(handler=handle_vi_repl_stop)

    modules_parser = subparsers.add_parser("modules", help="Manage Liwiro VI modules")
    modules_sub = modules_parser.add_subparsers(dest="action", required=True)
    modules_catalog = modules_sub.add_parser("catalog", help="Show visible modules, domains, and reserved names")
    modules_catalog.set_defaults(handler=handle_modules_catalog)
    modules_list = modules_sub.add_parser("list", help="List visible VI modules")
    modules_list.set_defaults(handler=handle_modules_list)
    modules_show = modules_sub.add_parser("show", help="Show one VI module")
    modules_show.add_argument("name", help="Module name")
    modules_show.set_defaults(handler=handle_modules_show)
    modules_create = modules_sub.add_parser("create", help="Create a VI module")
    modules_create.add_argument("name", help="Module name")
    add_module_common_arguments(modules_create)
    modules_create.set_defaults(handler=handle_modules_create)
    modules_update = modules_sub.add_parser("update", help="Update a VI module")
    modules_update.add_argument("name", help="Module name")
    add_module_common_arguments(modules_update)
    modules_update.set_defaults(handler=handle_modules_update)
    modules_delete = modules_sub.add_parser("delete", help="Delete a VI module")
    modules_delete.add_argument("name", help="Module name")
    modules_delete.add_argument("--yes", action="store_true", help="Skip the delete confirmation prompt")
    modules_delete.set_defaults(handler=handle_modules_delete)
    modules_assign_domain = modules_sub.add_parser("assign-domain", help="Assign one or more domains to a VI module")
    modules_assign_domain.add_argument("name", help="Module name")
    modules_assign_domain.add_argument("domain", nargs="+", help="Domain name(s)")
    modules_assign_domain.set_defaults(handler=handle_modules_assign_domain)

    local_parser = subparsers.add_parser("local", help="Control the local Liwiro/VDB/frontend stack")
    local_sub = local_parser.add_subparsers(dest="action", required=True)
    local_status = local_sub.add_parser("status", help="Show local process and health status")
    local_status.add_argument("target", nargs="?", default="all", choices=["all", "backend", "frontend", "vdb"], help="Target to inspect")
    local_status.set_defaults(handler=handle_local_status)
    local_start = local_sub.add_parser("start", help="Start local services in the background")
    local_start.add_argument("target", choices=["all", "backend", "frontend", "vdb"], help="Target to start")
    local_start.add_argument("--foreground", action="store_true", help="Run in the foreground instead of the background")
    local_start.add_argument("--vdb-transport", choices=["unixsocket", "http"], default="unixsocket", help="Local VDB transport")
    local_start.add_argument("--vdb-http-url", default=DEFAULT_VDB_HTTP_URL, help="Local VDB HTTP URL")
    local_start.add_argument("--vdb-socket-path", default=resolve_default_vdb_socket_path(), help="Local VDB Unix socket path")
    local_start.add_argument("--backend-port", type=int, default=5000, help="Backend port")
    local_start.add_argument("--frontend-port", type=int, default=3000, help="Frontend port")
    local_start.set_defaults(handler=handle_local_start)
    local_stop = local_sub.add_parser("stop", help="Stop local services")
    local_stop.add_argument("target", choices=["all", "backend", "frontend", "vdb"], help="Target to stop")
    local_stop.set_defaults(handler=handle_local_stop)
    local_restart = local_sub.add_parser("restart", help="Restart local services")
    local_restart.add_argument("target", choices=["all", "backend", "frontend", "vdb"], help="Target to restart")
    local_restart.add_argument("--vdb-transport", choices=["unixsocket", "http"], default="unixsocket", help="Local VDB transport")
    local_restart.add_argument("--vdb-http-url", default=DEFAULT_VDB_HTTP_URL, help="Local VDB HTTP URL")
    local_restart.add_argument("--vdb-socket-path", default=resolve_default_vdb_socket_path(), help="Local VDB Unix socket path")
    local_restart.add_argument("--backend-port", type=int, default=5000, help="Backend port")
    local_restart.add_argument("--frontend-port", type=int, default=3000, help="Frontend port")
    local_restart.add_argument("--foreground", action="store_true", help="Run in the foreground instead of the background")
    local_restart.set_defaults(handler=handle_local_restart)
    local_logs = local_sub.add_parser("logs", help="Show the last lines from a tracked local process log")
    local_logs.add_argument("target", choices=["all", "backend", "frontend", "vdb"], help="Target")
    local_logs.add_argument("--lines", type=int, default=50, help="Number of lines to show")
    local_logs.set_defaults(handler=handle_local_logs)

    return parser


def build_context(args: argparse.Namespace) -> CliContext:
    state = load_state()
    requested_profile = str(args.profile or state.get("current_profile") or DEFAULT_PROFILE).strip() or DEFAULT_PROFILE
    profile_name, profile = get_profile(state, requested_profile, create=True)
    backend = str(args.backend or profile.get("backend") or DEFAULT_BACKEND).strip() or DEFAULT_BACKEND
    profile["backend"] = backend.rstrip("/")
    state["profiles"][profile_name] = profile
    if not args.area == "profiles" or args.action not in {"use", "delete"}:
        state["current_profile"] = profile_name
    save_state(state)
    client = LiwiroClient(backend=backend, token=str(profile.get("token") or ""), timeout=args.timeout)
    return CliContext(args=args, state=state, profile_name=profile_name, profile=profile, client=client)


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if not raw_argv and sys.stdin.isatty():
        raw_argv = ["shell"]
    return run_cli_command(raw_argv)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CliHttpError as exc:
        print_error_line(f"error: {exc}")
        if exc.status_code == 401:
            raise SystemExit(2)
        if exc.status_code == 403:
            raise SystemExit(3)
        if exc.status_code == 404:
            raise SystemExit(4)
        raise SystemExit(1)
    except CliError as exc:
        print_error_line(f"error: {exc}")
        raise SystemExit(1)
