# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

from dotenv import load_dotenv
from functools import lru_cache
import os
import json
import platform
import re
import sys
from pathlib import Path
from jsonschema import validate
from jsonschema.exceptions import ValidationError

from app.dry_run_validation import validate_generated_service_dry_run
from app.versa_validation import validate_lapis_versa_scripts


_BACKEND_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _BACKEND_DIR.parent
_REPO_ROOT = _PROJECT_DIR.parent
_PLATFORM_CACHE_PATH = _REPO_ROOT / "tmp" / "platform-runtime.json"


def _load_environment_files():
    loaded = []
    root_env = _PROJECT_DIR / ".env"
    root_env_local = _PROJECT_DIR / ".env.local"
    backend_env = _BACKEND_DIR / ".env"
    backend_env_local = _BACKEND_DIR / ".env.local"
    if root_env.exists():
        load_dotenv(root_env, override=False)
        loaded.append(str(root_env))
    if root_env_local.exists():
        load_dotenv(root_env_local, override=True)
        loaded.append(str(root_env_local))
    if backend_env.exists():
        load_dotenv(backend_env, override=True)
        loaded.append(str(backend_env))
    if backend_env_local.exists():
        load_dotenv(backend_env_local, override=True)
        loaded.append(str(backend_env_local))
    if not loaded:
        load_dotenv()
    return loaded


_LOADED_ENV_FILES = _load_environment_files()


def _resolve_project_path(raw_value: str | Path | None, *, default: str | Path = "") -> str:
    value = str(raw_value or "").strip()
    if not value:
        value = str(default or "").strip()
    if not value:
        return ""
    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path.resolve())

    candidates: list[Path] = []

    def add_candidate(base: Path):
        candidate = (base / path).resolve()
        if candidate not in candidates:
            candidates.append(candidate)

    first_part = path.parts[0] if path.parts else ""
    if first_part in {".", ".."}:
        add_candidate(_BACKEND_DIR)
        add_candidate(_PROJECT_DIR)
        add_candidate(_PROJECT_DIR.parent)
    else:
        if first_part == _PROJECT_DIR.name:
            add_candidate(_PROJECT_DIR.parent)
            add_candidate(_PROJECT_DIR)
        else:
            add_candidate(_PROJECT_DIR)
            add_candidate(_PROJECT_DIR.parent)
        add_candidate(_BACKEND_DIR)

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return str(candidates[0] if candidates else path.resolve())


_JSON_LIKE_NUMBER_RE = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")


def _is_identifier_start(char):
    return bool(char) and (char.isalpha() or char in {"_", "$"})


def _is_identifier_part(char):
    return bool(char) and (char.isalnum() or char in {"_", "$"})


class _JsonLikeParser:
    def __init__(self, text):
        self.text = str(text or "")
        self.index = 0

    def parse(self):
        self._skip_ignorable()
        value = self._parse_value()
        self._skip_ignorable()
        if self.index != len(self.text):
            self._error("Unexpected trailing content")
        return value

    def _peek(self, offset=0):
        position = self.index + offset
        if position < 0 or position >= len(self.text):
            return ""
        return self.text[position]

    def _advance(self):
        char = self._peek()
        self.index += 1
        return char

    def _error(self, message):
        raise ValueError(f"{message} at position {self.index + 1}")

    def _skip_ignorable(self):
        while self.index < len(self.text):
            char = self._peek()
            if char.isspace():
                self.index += 1
                continue
            if char == "/" and self._peek(1) == "/":
                self.index += 2
                while self.index < len(self.text):
                    next_char = self._advance()
                    if next_char in {"\n", "\r"}:
                        break
                continue
            if char == "/" and self._peek(1) == "*":
                end_index = self.text.find("*/", self.index + 2)
                if end_index == -1:
                    self._error("Unterminated block comment")
                self.index = end_index + 2
                continue
            break

    def _expect(self, char):
        self._skip_ignorable()
        if self._peek() != char:
            self._error(f"Expected '{char}'")
        self.index += 1

    def _parse_value(self):
        self._skip_ignorable()
        char = self._peek()
        if not char:
            self._error("Unexpected end of input")
        if char == "{":
            return self._parse_object()
        if char == "[":
            return self._parse_array()
        if char in {'"', "'"}:
            return self._parse_string()
        if char == "-" or char.isdigit():
            return self._parse_number()
        if self.text.startswith("true", self.index) and not _is_identifier_part(self._peek(4)):
            self.index += 4
            return True
        if self.text.startswith("false", self.index) and not _is_identifier_part(self._peek(5)):
            self.index += 5
            return False
        if self.text.startswith("null", self.index) and not _is_identifier_part(self._peek(4)):
            self.index += 4
            return None
        self._error(f"Unexpected token '{char}'")

    def _parse_object(self):
        out = {}
        self._expect("{")
        self._skip_ignorable()
        if self._peek() == "}":
            self.index += 1
            return out
        while True:
            self._skip_ignorable()
            char = self._peek()
            if char in {'"', "'"}:
                key = self._parse_string()
            else:
                key = self._parse_identifier("object key")
            self._expect(":")
            out[key] = self._parse_value()
            self._skip_ignorable()
            if self._peek() == ",":
                self.index += 1
                self._skip_ignorable()
                if self._peek() == "}":
                    self.index += 1
                    break
                continue
            if self._peek() == "}":
                self.index += 1
                break
            self._error("Expected ',' or '}'")
        return out

    def _parse_array(self):
        out = []
        self._expect("[")
        self._skip_ignorable()
        if self._peek() == "]":
            self.index += 1
            return out
        while True:
            out.append(self._parse_value())
            self._skip_ignorable()
            if self._peek() == ",":
                self.index += 1
                self._skip_ignorable()
                if self._peek() == "]":
                    self.index += 1
                    break
                continue
            if self._peek() == "]":
                self.index += 1
                break
            self._error("Expected ',' or ']'")
        return out

    def _parse_string(self):
        quote = self._advance()
        out = []
        while self.index < len(self.text):
            char = self._advance()
            if char == quote:
                return "".join(out)
            if char in {"\n", "\r"}:
                self._error("Unterminated string")
            if char != "\\":
                out.append(char)
                continue
            if self.index >= len(self.text):
                self._error("Unterminated escape sequence")
            escaped = self._advance()
            if escaped == "u":
                hex_digits = self.text[self.index:self.index + 4]
                if len(hex_digits) != 4 or not re.fullmatch(r"[0-9a-fA-F]{4}", hex_digits):
                    self._error("Invalid unicode escape")
                out.append(chr(int(hex_digits, 16)))
                self.index += 4
                continue
            escape_map = {
                '"': '"',
                "'": "'",
                "\\": "\\",
                "/": "/",
                "b": "\b",
                "f": "\f",
                "n": "\n",
                "r": "\r",
                "t": "\t",
            }
            if escaped not in escape_map:
                self._error(f"Invalid escape '\\{escaped}'")
            out.append(escape_map[escaped])
        self._error("Unterminated string")

    def _parse_identifier(self, context):
        char = self._peek()
        if not _is_identifier_start(char):
            self._error(f"Expected {context}")
        value = [char]
        self.index += 1
        while _is_identifier_part(self._peek()):
            value.append(self._advance())
        return "".join(value)

    def _parse_number(self):
        match = _JSON_LIKE_NUMBER_RE.match(self.text[self.index:])
        if not match:
            self._error("Invalid number")
        token = match.group(0)
        self.index += len(token)
        if "." in token or "e" in token.lower():
            return float(token)
        return int(token)


def parse_json_like_text(value):
    text = str(value or "").strip()
    if not text:
        raise ValueError("Input is empty")
    try:
        return json.loads(text)
    except Exception:
        return _JsonLikeParser(text).parse()


def parse_json_like_object(value, label="JSON object"):
    parsed = parse_json_like_text(value)
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must decode to a JSON object")
    return parsed

def _load_liwiro_auth_config():
    backend_dir = Path(__file__).resolve().parent
    default_path = backend_dir / ".runtime" / "liwiro.vdb.auth.json"
    explicit_path = str(os.getenv("LIWIRO_VDB_AUTH_CONFIG") or "").strip()
    configured_path = Path(_resolve_project_path(explicit_path or str(default_path), default=default_path))

    selected_path = configured_path
    if not selected_path.exists():
        # An explicit path is an isolation boundary. Falling back here can load
        # credentials from an unrelated installation or developer checkout.
        if explicit_path:
            return {}, configured_path
        fallback_candidates = [
            backend_dir / "liwiro.vdb.auth.json",
            backend_dir / ".runtime" / "liwiro.vdb.auth.json",
            _PROJECT_DIR / ".runtime" / "liwiro.vdb.auth.json",
        ]
        for candidate in fallback_candidates:
            if candidate.exists():
                selected_path = candidate
                break
        else:
            return {}, configured_path

    try:
        with selected_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise RuntimeError("Liwiro auth config must be a JSON object")
        return data, selected_path
    except Exception as e:
        # Auto-recover broken/partial JSON so backend can still boot and show first-time setup.
        try:
            backup_path = selected_path.with_suffix(selected_path.suffix + ".broken")
            try:
                if backup_path.exists():
                    backup_path.unlink()
            except Exception:
                pass
            try:
                selected_path.replace(backup_path)
            except Exception:
                # If rename fails, attempt to overwrite in place.
                pass
            selected_path.parent.mkdir(parents=True, exist_ok=True)
            selected_path.write_text("{}", encoding="utf-8")
            print(
                f"[LIWIRO] Recovered invalid auth config at {selected_path}. "
                f"Backed up previous contents to {backup_path} (if rename succeeded). Error: {e}"
            )
            return {}, selected_path
        except Exception as recover_exc:
            raise RuntimeError(
                f"Failed to load Liwiro auth config {selected_path}: {e}; "
                f"auto-recovery also failed: {recover_exc}"
            )


_LIWIRO_AUTH_CONFIG, _LIWIRO_AUTH_PATH = _load_liwiro_auth_config()

def _cfg_value(env_key: str, auth_key: str, fallback: str):
    """Prefer persisted auth config when available; fall back to env/default."""
    auth_val = _LIWIRO_AUTH_CONFIG.get(auth_key)
    if auth_val is not None and str(auth_val).strip() != "":
        return auth_val
    return os.getenv(env_key, fallback)


def _cfg_env_value(env_key: str, fallback: str):
    return os.getenv(env_key, fallback)


def _env_bool(env_key: str, fallback: bool) -> bool:
    raw = os.getenv(env_key)
    if raw is None:
        return fallback
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return fallback


def _normalize_platform_label(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if text.startswith("win"):
        return "windows"
    if text in {"darwin", "mac", "macos", "osx"}:
        return "macos"
    if text.startswith("linux"):
        return "linux"
    return text


def _classify_host_platform(system_name: str | None, os_name_value: str | None, sys_platform_value: str | None) -> str:
    system_text = _normalize_platform_label(system_name)
    os_text = str(os_name_value or "").strip().lower()
    sys_text = str(sys_platform_value or "").strip().lower()

    if os_text == "nt" or sys_text.startswith("win") or system_text == "windows":
        return "windows"
    if system_text == "macos" or sys_text == "darwin":
        return "macos"
    if system_text == "linux" or sys_text.startswith("linux"):
        return "linux"
    if os_text == "posix":
        return "linux"
    if system_text:
        return system_text
    return "linux"


def _detect_platform_runtime_info() -> dict:
    system_name = str(platform.system() or "").strip()
    os_name_value = str(os.name or "").strip()
    sys_platform_value = str(sys.platform or "").strip()
    shell_path = str(os.getenv("SHELL") or os.getenv("COMSPEC") or "").strip()
    shell_name = Path(shell_path).name if shell_path else ""
    info = {
        "schema": 1,
        "platform": _classify_host_platform(system_name, os_name_value, sys_platform_value),
        "system": system_name,
        "os_name": os_name_value,
        "sys_platform": sys_platform_value,
        "machine": str(platform.machine() or "").strip(),
        "release": str(platform.release() or "").strip(),
        "shell": shell_name,
        "cache_path": str(_PLATFORM_CACHE_PATH),
    }
    return info


def _load_platform_cache_file() -> dict | None:
    try:
        if not _PLATFORM_CACHE_PATH.exists():
            return None
        with _PLATFORM_CACHE_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            return None
        cached_platform = _normalize_platform_label(payload.get("platform"))
        if cached_platform not in {"windows", "linux", "macos"}:
            return None
        payload["platform"] = cached_platform
        return payload
    except Exception:
        return None


def _write_platform_cache_file(payload: dict) -> None:
    try:
        _PLATFORM_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _PLATFORM_CACHE_PATH.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except Exception:
        pass


def _platform_cache_matches_runtime(cached: dict, detected: dict) -> bool:
    return (
        str(cached.get("platform") or "").strip().lower() == str(detected.get("platform") or "").strip().lower()
        and str(cached.get("os_name") or "").strip().lower() == str(detected.get("os_name") or "").strip().lower()
        and str(cached.get("sys_platform") or "").strip().lower() == str(detected.get("sys_platform") or "").strip().lower()
    )


@lru_cache(maxsize=1)
def platform_runtime_info() -> dict:
    detected = _detect_platform_runtime_info()
    cached = _load_platform_cache_file()
    if cached and _platform_cache_matches_runtime(cached, detected):
        return {**cached, "cache_path": str(_PLATFORM_CACHE_PATH)}
    return {**detected, "cache_path": str(_PLATFORM_CACHE_PATH), "detected_by": "python"}


def platform_cache_path() -> str:
    return str(_PLATFORM_CACHE_PATH)


def vdb_host_platform() -> str:
    return str(platform_runtime_info().get("platform") or "linux").strip().lower() or "linux"


def supports_named_pipe_transport() -> bool:
    return vdb_host_platform() == "windows"


def supports_unix_socket_transport() -> bool:
    return not supports_named_pipe_transport()


def default_vdb_transport_mode() -> str:
    return "namedpipe" if supports_named_pipe_transport() else "unixsocket"


def default_vdb_unix_socket_path() -> str:
    if os.path.isdir("/run") and os.access("/run", os.W_OK):
        return "/run/vdb.sock"
    return "/tmp/vdb.sock"


def default_vdb_named_pipe_path() -> str:
    return r"\\.\pipe\verun_vdb"


def normalize_vdb_named_pipe_path(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        text = default_vdb_named_pipe_path()
    text = text.replace("/", "\\")
    text = text.replace("\x0b", "\\v")
    text = "".join(ch for ch in text if ord(ch) >= 32 and ord(ch) != 127)
    parts = [
        part for part in text.split("\\")
        if part and part != "." and part.lower() != "pipe"
    ]
    pipe_name = str(parts[-1] if parts else "verun_vdb").strip() or "verun_vdb"
    return "\\\\.\\pipe\\" + pipe_name


_LAPIS_OPERATION_TYPE_ALIASES = {
    "crud": "crud",
    "resource": "crud",
    "rest": "crud",
    "custom": "custom",
    "query": "custom",
    "vql": "custom",
    "script": "script",
    "versa": "script",
    "code": "script",
}


_LAPIS_CRUD_OPERATION_ALIASES = {
    "create": "create",
    "create_one": "create",
    "create_many": "create",
    "post": "create",
    "insert": "create",
    "read": "read",
    "read_one": "read",
    "read_many": "read",
    "get": "read",
    "get_one": "read",
    "get_many": "read",
    "list": "read",
    "fetch": "read",
    "fetch_one": "read",
    "fetch_many": "read",
    "query": "read",
    "update": "update",
    "update_one": "update",
    "update_many": "update",
    "put": "update",
    "patch": "update",
    "edit": "update",
    "delete": "delete",
    "delete_one": "delete",
    "delete_many": "delete",
    "remove": "delete",
    "remove_one": "delete",
    "remove_many": "delete",
}


def normalize_lapis_operation_type(value: str | None) -> str:
    token = str(value or "").strip().lower().replace("-", "_")
    return _LAPIS_OPERATION_TYPE_ALIASES.get(token, token)


def normalize_lapis_crud_operation(value: str | None) -> str:
    token = str(value or "").strip().lower().replace("-", "_")
    return _LAPIS_CRUD_OPERATION_ALIASES.get(token, token)


def normalize_lapis_config_contract(config: dict | None) -> dict:
    payload = dict(config or {})
    metadata = dict(payload.get("metadata") or {})
    # rateLimiting was introduced after the original LAPIS contract. Keep old
    # service documents valid by materializing a safe disabled default; service
    # generation can then enforce it only when explicitly enabled.
    rate_limiting = dict(metadata.get("rateLimiting") or {})
    rate_limiting.setdefault("enabled", False)
    rate_limiting.setdefault("limit", 0)
    rate_limiting.setdefault("timeframe", "minute")
    metadata["rateLimiting"] = rate_limiting
    payload["metadata"] = metadata
    endpoint_map = payload.get("endpoints") if isinstance(payload.get("endpoints"), dict) else {}
    normalized_endpoints = {}

    for endpoint_id, raw_endpoint in endpoint_map.items():
        if not isinstance(raw_endpoint, dict):
            normalized_endpoints[endpoint_id] = raw_endpoint
            continue
        endpoint = dict(raw_endpoint)
        operation_type = normalize_lapis_operation_type(endpoint.get("operationType"))
        if operation_type:
            endpoint["operationType"] = operation_type
        if operation_type == "crud":
            crud_operation = normalize_lapis_crud_operation(endpoint.get("crudOperation"))
            if crud_operation:
                endpoint["crudOperation"] = crud_operation
        normalized_endpoints[endpoint_id] = endpoint

    payload["endpoints"] = normalized_endpoints
    return payload


def _default_vi_portal_source_dir() -> str:
    backend_dir = Path(__file__).resolve().parent
    return str((backend_dir.parent / "vi_portal_sources").resolve())


def _default_vi_custom_modules_dir() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    return str((repo_root / "verun" / "vi" / "custom_modules").resolve())


def _default_verse_root() -> str:
    backend_dir = Path(__file__).resolve().parent
    return str((backend_dir.parent / "verse").resolve())


def _default_verse_data_dir() -> str:
    backend_dir = Path(__file__).resolve().parent
    return str((backend_dir.parent / "data" / "verse").resolve())


class Config:
    HOST_PLATFORM = vdb_host_platform()
    PLATFORM_CACHE_PATH = platform_cache_path()
    VDB_TRANSPORT = _cfg_value("VDB_TRANSPORT", "vdb_transport", default_vdb_transport_mode())
    LIWIRO_AUTH_PATH = str(_LIWIRO_AUTH_PATH)
    VDB_SERVER_URL = _cfg_value("VDB_SERVER_URL", "vdb_server_url", "http://localhost:1957")
    VDB_UNIX_SOCKET_PATH = _cfg_value("VDB_UNIX_SOCKET_PATH", "vdb_unix_socket_path", default_vdb_unix_socket_path())
    VDB_NAMED_PIPE_PATH = normalize_vdb_named_pipe_path(
        _cfg_value("VDB_NAMED_PIPE_PATH", "vdb_named_pipe_path", default_vdb_named_pipe_path())
    )
    VI_PORTAL_SOURCE_DIR = _resolve_project_path(os.getenv("VI_PORTAL_SOURCE_DIR"), default=_default_vi_portal_source_dir())
    VI_CUSTOM_MODULES_DIR = _resolve_project_path(os.getenv("VI_CUSTOM_MODULES_DIR"), default=_default_vi_custom_modules_dir())
    VERSE_ROOT = _resolve_project_path(os.getenv("VERSE_ROOT"), default=_default_verse_root())
    VERSE_DATA_DIR = _resolve_project_path(os.getenv("VERSE_DATA_DIR"), default=_default_verse_data_dir())
    AI_PROVIDER = os.getenv("AI_PROVIDER", "openai")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
    GOOGLE_MODEL = os.getenv("GOOGLE_MODEL", "gemini-3-flash-preview")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    VERSE_PROACTIVE_SCHEDULER_INTERVAL_SECONDS = int(os.getenv("VERSE_PROACTIVE_SCHEDULER_INTERVAL_SECONDS", "60") or 60)
    VDB_USERNAME = _cfg_value("VDB_USERNAME", "vdb_username", "")
    VDB_PASSWORD = _cfg_env_value("VDB_PASSWORD", "")
    LIWIRO_APP_USERNAME = _cfg_env_value("LIWIRO_APP_USERNAME", "Liwiro")
    LIWIRO_APP_PASSWORD = _cfg_env_value("LIWIRO_APP_PASSWORD", VDB_PASSWORD)
    VDB_SUPER_ADMIN_USERNAME = _cfg_env_value("VDB_SUPER_ADMIN_USERNAME", "")
    VDB_SUPER_ADMIN_PASSWORD = _cfg_env_value("VDB_SUPER_ADMIN_PASSWORD", "")
    LIWIRO_DOMAIN = _cfg_value("LIWIRO_DOMAIN", "liwiro_domain", "liwiro")
    LIWIRO_DB = _cfg_value("LIWIRO_DB", "liwiro_db", "config")
    # Debug mode must be opt-in; production and managed launches must never
    # expose the Werkzeug debugger by default.
    FLASK_DEBUG = _env_bool("FLASK_DEBUG", False)
    LIWIRO_FRONTEND = os.getenv("LIWIRO_FRONTEND")
    
    LAPIS_SCHEMA = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "LAPIS Service Configuration",
        "type": "object",
        "properties": {
            "metadata": {
                "type": "object",
                "properties": {
                    "apiName": {"type": "string"},
                    "basePath": {"type": "string", "pattern": "^/.*"},
                    "version": {"type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$"},
                    "database": {"type": "string", "pattern": "^[a-zA-Z0-9_\\-]+$"},
                    "developerNotes": {"type": "string"},
                    "setupApiKey": {"type": "string"},
                    "documentation": {
                        "type": "object",
                        "properties": {
                            "enabled": {"type": "boolean"},
                            "key": {"type": "string"},
                            "keyHash": {"type": "string"}
                        },
                        "required": ["enabled"]
                    },
                    "env": {
                        "type": "object",
                        "patternProperties": {
                            "^[A-Z_][A-Z0-9_]*$": {
                                "type": ["string", "number", "boolean"]
                            }
                        },
                        "additionalProperties": False
                    },
                    "seedData": {
                        "type": "object",
                        "properties": {
                            "enabled": {"type": "boolean"},
                            "collections": {"type": "object"}
                        }
                    },
                    "rateLimiting": {
                        "type": "object",
                        "properties": {
                            "enabled": {"type": "boolean"},
                            "limit": {"type": "number"},
                            "timeframe": {"type": "string", "enum": ["second", "minute", "hour", "day"]}
                        },
                        "required": ["enabled", "limit", "timeframe"]
                    }
                },
                "required": ["apiName", "basePath", "version"]
            },
            "auth": {
                "type": "object",
                "properties": {
                    "enabled": {"type": "boolean"},
                    "isAuthService": {"type": "boolean"},
                    "keyManagement": {"type": "string", "enum": ["auto", "manual"]},
                    "privateKey": {"type": "string"},
                    "publicKey": {"type": "string"},
                    "authModel": {"type": "string"},
                    "authServiceName": {"type": "string"},
                    "customEndpoints": {
                        "type": "object",
                        "properties": {
                            "enabled": {"type": "boolean"},
                            "signIn": {"type": "string"},
                            "signOut": {"type": "string"},
                            "signUp": {"type": "string"},
                            "register": {"type": "string"},
                            "forgotPassword": {"type": "string"},
                            "resetPassword": {"type": "string"}
                        },
                        "required": ["enabled", "signIn", "signUp"]
                    },
                    "useAsymmetricJWT": {"type": "boolean"},
                    "authServicePublicKey": {"type": "string"},
                    "defaultSuperAdmin": {
                        "type": "object",
                        "properties": {
                            "enabled": {"type": "boolean"},
                            "username": {"type": "string"},
                            "email": {"type": "string"},
                            "password": {"type": "string"},
                            "role": {"type": "string"}
                        }
                    },
                    "passwordResetPage": {
                        "type": "object",
                        "properties": {
                            "enabled": {"type": "boolean"},
                            "submissionMode": {"type": "string", "enum": ["auto_form", "custom_page"]},
                            "customPageBaseUrl": {"type": "string"},
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "submitLabel": {"type": "string"},
                            "loadingMessage": {"type": "string"},
                            "successMessage": {"type": "string"},
                            "failureMessage": {"type": "string"}
                        }
                    }
                },
                "required": ["enabled", "isAuthService", "keyManagement", "customEndpoints"]
            },
            "models": {
                "type": "object",
                "patternProperties": {
                    "^[a-zA-Z0-9_-]+$": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "collection": {"type": "string"},
                            "fields": {
                                "type": "object",
                                "patternProperties": {
                                    "^[a-zA-Z0-9_-]+$": {
                                        "type": "object",
                                        "properties": {
                                            "id": {"type": "string"},
                                            "name": {"type": "string"},
                                            "type": {"type": "string", "enum": ["string", "number", "boolean", "date", "object"]},
                                            "required": {"type": "boolean"},
                                            "unique": {"type": "boolean"},
                                            "default": {"type": "boolean"},
                                            "defaultValue": {"type": ["string", "number", "boolean", "object", "array"]},
                                            "objectTemplate": {"type": "string"},
                                            "embeddedFields": {
                                                "type": "array",
                                                "items": {"$ref": "#/definitions/field"},
                                                "maxItems": 3
                                            },
                                            "depth": {"type": "number", "maximum": 3}
                                        },
                                        "required": ["id", "name", "type", "required"]
                                    }
                                }
                            }
                        },
                        "required": ["name", "collection", "fields"]
                    }
                }
            },
            "endpoints": {
                "type": "object",
                "patternProperties": {
                    "^[a-zA-Z0-9_-]+$": {
                        "type": "object",
                        "properties": {
                            "enabled": {"type": "boolean"},
                            "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"]},
                            "path": {"type": "string"},
                            "operationType": {"type": "string", "enum": ["crud", "custom", "script"]},
                            "crudOperation": {"type": "string", "enum": ["create", "read", "update", "delete"]},
                            "linkedModel": {"type": "string"},
                            "defaultParameters": {
                                "type": "object",
                                "properties": {
                                    "data": {
                                        "type": "object",
                                        "properties": {
                                            "enabled": {"type": "boolean"},
                                            "name": {"type": "string"}
                                        }
                                    },
                                    "query": {
                                        "type": "object",
                                        "properties": {
                                            "enabled": {"type": "boolean"},
                                            "name": {"type": "string"},
                                            "operator": {"type": "string", "enum": ["$eq", "$lt", "$gt", "$lte", "$gte", "$ne", "$in", "$nin"]}
                                        }
                                    }
                                }
                            },
                            "requiresAuth": {"type": "boolean"},
                            "developerNotes": {"type": "string"},
                            "documentation": {
                                "type": "object",
                                "properties": {
                                    "summary": {"type": "string"},
                                    "description": {"type": "string"},
                                    "sections": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "title": {"type": "string"},
                                                "body": {"type": "string"}
                                            },
                                            "required": ["title", "body"]
                                        }
                                    }
                                }
                            },
                            "exampleParams": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "object"},
                                    "body": {"type": "object"},
                                    "headers": {"type": "object"}
                                }
                            },
                            "parameters": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "in": {"type": "string", "enum": ["query", "header", "path", "body"]},
                                        "type": {"type": "string", "enum": ["string", "number", "boolean", "array", "object"]},
                                        "required": {"type": "boolean"},
                                        "description": {"type": "string"}
                                    },
                                    "required": ["name", "in", "type"]
                                }
                            },
                            "vqlQuery": {"type": "string"},
                            "versaScript": {"type": "string"}
                        },
                        "required": ["method", "path", "operationType"]
                    }
                }
            },
            "modules": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
                        "config": {"type": "object"}
                    },
                    "required": ["name"]
                }
            },
            "sharedModules": {
                "type": "object",
                "patternProperties": {
                    "^[A-Za-z_][A-Za-z0-9_]*$": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "source": {"type": "string"},
                            "scope": {"type": "string", "enum": ["domain", "global"]},
                            "serviceDomain": {"type": "string"},
                            "service_domain": {"type": "string"},
                            "assignedDomains": {"type": "array", "items": {"type": "string"}},
                            "assigned_domains": {"type": "array", "items": {"type": "string"}},
                            "configSchema": {"type": "object"},
                            "config_schema": {"type": "object"},
                            "configDefaults": {"type": "object"},
                            "config_defaults": {"type": "object"},
                        },
                        "required": ["source"],
                    }
                },
            }
        },
        "required": ["metadata", "auth", "models", "endpoints"],
        "definitions": {
            "field": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "type": {"type": "string"},
                    "required": {"type": "boolean"},
                    "unique": {"type": "boolean"},
                    "default": {"type": "boolean"},
                    "defaultValue": {"type": ["string", "number", "boolean", "object", "array"]},
                    "objectTemplate": {"type": "string"},
                    "embeddedFields": {"type": "array", "items": {"$ref": "#/definitions/field"}},
                    "depth": {"type": "number"}
                }
            }
        }
    }

    @staticmethod
    def _validate_endpoint_semantics(config):
        endpoint_map = (config or {}).get("endpoints") or {}
        model_map = (config or {}).get("models") or {}
        modules_list = (config or {}).get("modules") or []
        shared_modules = (config or {}).get("sharedModules") or {}
        model_names = {
            str((model or {}).get("name") or "").strip()
            for model in model_map.values()
            if isinstance(model, dict) and str((model or {}).get("name") or "").strip()
        }
        seen_modules = set()

        for index, module in enumerate(modules_list):
            if not isinstance(module, dict):
                return False, f"Module entry #{index + 1} must be an object"
            module_name = str(module.get("name") or "").strip()
            if not module_name:
                return False, f"Module entry #{index + 1} requires name"
            lowered = module_name.lower()
            if lowered in seen_modules:
                return False, f"Duplicate module reference '{module_name}' in LAPIS modules"
            seen_modules.add(lowered)
            if module.get("config") is not None and not isinstance(module.get("config"), dict):
                return False, f"Module '{module_name}' config must be an object"

        for module_name, module in shared_modules.items() if isinstance(shared_modules, dict) else []:
            entry_name = str(module_name or "").strip()
            if not entry_name:
                return False, "sharedModules keys must be non-empty identifiers"
            if not isinstance(module, dict):
                return False, f"sharedModules.{entry_name} must be an object"
            source = str(module.get("source") or "").strip()
            if not source:
                return False, f"sharedModules.{entry_name} requires source"
            for key in ("configSchema", "config_schema", "configDefaults", "config_defaults"):
                if key in module and module.get(key) is not None and not isinstance(module.get(key), dict):
                    return False, f"sharedModules.{entry_name}.{key} must be an object"
            for key in ("assignedDomains", "assigned_domains"):
                if key in module and module.get(key) is not None and not isinstance(module.get(key), list):
                    return False, f"sharedModules.{entry_name}.{key} must be an array"

        for endpoint_id, endpoint in endpoint_map.items():
            if not isinstance(endpoint, dict):
                continue
            endpoint_key = str(endpoint_id or "").strip() or "<unknown>"
            op_type = str(endpoint.get("operationType") or "").strip().lower()

            if op_type == "crud":
                crud_op = str(endpoint.get("crudOperation") or "").strip().lower()
                linked_model = str(endpoint.get("linkedModel") or "").strip()
                if not crud_op:
                    return False, f"Endpoint '{endpoint_key}' requires crudOperation when operationType is 'crud'"
                if not linked_model:
                    return False, f"Endpoint '{endpoint_key}' requires linkedModel when operationType is 'crud'"
                if model_names and linked_model not in model_names:
                    return False, f"Endpoint '{endpoint_key}' references unknown linkedModel '{linked_model}'"

            if op_type == "custom":
                query_text = endpoint.get("vqlQuery")
                if not isinstance(query_text, str) or not query_text.strip():
                    return False, f"Endpoint '{endpoint_key}' requires vqlQuery when operationType is 'custom'"
                from app.vdb_commands import validate_command
                try:
                    validate_command(query_text)
                except ValueError as exc:
                    return False, f"Endpoint '{endpoint_key}' vqlQuery: {exc}"

            if op_type == "script":
                script_text = endpoint.get("versaScript")
                if not isinstance(script_text, str) or not script_text.strip():
                    return False, f"Endpoint '{endpoint_key}' requires versaScript when operationType is 'script'"

        return True, None

    @staticmethod
    def validate_lapis_config(config):
        detail = Config.validate_lapis_config_detailed(config, include_dry_run=False)
        return bool(detail.get("valid")), detail.get("error")

    @staticmethod
    def validate_lapis_config_detailed(config, include_dry_run: bool = False):
        try:
            normalized = normalize_lapis_config_contract(config)
            validate(instance=normalized, schema=Config.LAPIS_SCHEMA)
            valid, error = Config._validate_endpoint_semantics(normalized)
            if not valid:
                return {
                    "valid": False,
                    "error": error,
                    "normalized": normalized,
                    "versaIssues": [],
                }
            versa_issues = validate_lapis_versa_scripts(normalized)
            if versa_issues:
                first_issue = versa_issues[0]
                return {
                    "valid": False,
                    "error": str(first_issue.get("error") or f"Endpoint '{first_issue.get('endpointId') or 'endpoint'}' has invalid Versa syntax."),
                    "normalized": normalized,
                    "versaIssues": versa_issues,
                }
            dry_run = validate_generated_service_dry_run(normalized) if include_dry_run else None
            if include_dry_run and not dry_run.get("ok"):
                errors = list(dry_run.get("errors") or [])
                primary_error = str(errors[0] or "Dry-run validation failed.").strip()
                return {
                    "valid": False,
                    "error": primary_error,
                    "normalized": normalized,
                    "versaIssues": [],
                    "dryRun": dry_run,
                }
            return {
                "valid": True,
                "error": None,
                "normalized": normalized,
                "versaIssues": [],
                "dryRun": dry_run,
            }
        except ValidationError as e:
            return {
                "valid": False,
                "error": e.message,
                "normalized": None,
                "versaIssues": [],
                "dryRun": None,
            }
        except Exception as e:
            return {
                "valid": False,
                "error": str(e),
                "normalized": None,
                "versaIssues": [],
                "dryRun": None,
            }
