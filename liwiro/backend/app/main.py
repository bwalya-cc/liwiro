# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import copy
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import select
import shutil
import signal
import socket
import stat
import subprocess
import secrets
import sys
import tempfile
import threading
import time
from typing import Any
from urllib.parse import urlparse


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utcnow_iso() -> str:
    return _utcnow().isoformat()


try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

import psutil
import requests
import re
import logging
from flask import Flask, Blueprint, request, jsonify, current_app, has_request_context, has_app_context, g
from flask_sock import Sock
from simple_websocket import ConnectionClosed
from app.vdb import VDBClient
from app.vdb_bson import read_bson_value, BsonDecodeError
from app.vdb_transport import (
    VDBNamedPipeTransport,
    VDBTransportConnectionError,
    VDBTransportProtocolError,
    VDBTransportRequestError,
    VDBUnixSocketTransport,
    build_vdb_transport,
    host_platform,
    is_local_vdb_url,
    normalize_local_vdb_http_url,
    normalize_vdb_transport_mode,
    resolve_vdb_named_pipe_path,
    resolve_vdb_unix_socket_path,
    _validate_flat_vdb_payload,
)
from app import license_info
from app.auth_data import (
    ROLE_VIEWER,
    ROLE_SERVICE_MANAGER,
    ROLE_ADMIN,
    WILDCARD_SERVICE_ACCESS,
    find_auth_user as _find_auth_user,
    load_normalized_auth_data as _load_normalized_auth_data_impl,
    normalize_liwiro_rbac as _normalize_liwiro_rbac,
    normalize_platform_role as _normalize_platform_role,
    normalize_service_access as _normalize_service_access,
    normalize_user_permissions as _normalize_user_permissions,
    save_normalized_auth_data as _save_normalized_auth_data_impl,
)
from app.feature_flags import feature_flag_definitions, feature_flag_enabled, feature_flags_with_defaults
from app.lapis_repair import collect_lapis_validation_issues, repair_lapis_config_recursively
from app.platform_capabilities import (
    capability_id_for_artifact,
    get_platform_capability,
    list_platform_capabilities,
)
from app.vi_modules import (
    delete_module_record,
    list_module_records,
    load_module_record,
    normalize_module_name,
    reserved_module_names,
    validate_module_name,
    write_module_record,
)
from app.versa_validation import validate_versa_source
from app.verse import VerseService
from app.verse.mind_share import MindShareValidationError
from app.verse.providers.base import (
    AIAuthenticationError,
    AIConfigurationError,
    AIProviderError,
    AIRateLimitError,
)
from app.verse.providers.factory import build_ai_provider
from config import (
    Config,
    default_vdb_named_pipe_path,
    default_vdb_transport_mode,
    default_vdb_unix_socket_path,
    normalize_lapis_config_contract,
    supports_named_pipe_transport,
    supports_unix_socket_transport,
)
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

from utils.process_manager import ProcessManager
from utils.service_capabilities import summarize_media_capabilities
from utils.auth_helpers import normalize_username, username_variants

main_bp = Blueprint("main", __name__)
sock = Sock()
LIWIRO_APP_USERNAME = "Liwiro"
VI_REPL_PRIMARY_PROMPT = "> "
VI_REPL_CONTINUATION_PROMPT = "... "
VI_TERMINAL_DEFAULT_COLS = 120
VI_TERMINAL_DEFAULT_ROWS = 32
VI_TERMINAL_BUFFER_LIMIT = 200_000
VI_TERMINAL_CHUNK_LIMIT = 512
VI_TERMINAL_DEGRADED_RETRY_MS = 3_000
VERSE_NOTIFICATION_MIN_INTERVAL_MS = 25_000
VERSE_NOTIFICATION_FAILURE_BASE_MS = 30_000
VERSE_NOTIFICATION_FAILURE_MAX_MS = 300_000
VDB_HTTP_AUTOSTART_FAILURE_BASE_MS = 15_000
VDB_HTTP_AUTOSTART_FAILURE_MAX_MS = 120_000
_RESILIENCE_BUCKET_VERSE_NOTIFICATIONS = "verse_notifications"
_RESILIENCE_BUCKET_VDB_HTTP_AUTOSTART = "vdb_http_autostart"


def _resilience_state_lock():
    lock = getattr(current_app, "resilience_state_lock", None)
    if lock is None:
        lock = threading.RLock()
        current_app.resilience_state_lock = lock
    return lock


def _resilience_backoff_ms(failure_count: int, *, base_delay_ms: int, max_delay_ms: int) -> int:
    normalized_failures = max(1, int(failure_count or 1))
    return min(int(max_delay_ms), int(base_delay_ms) * (2 ** max(0, normalized_failures - 1)))


def _resilience_state_snapshot(bucket_name: str, key: str) -> dict[str, Any]:
    with _resilience_state_lock():
        state = getattr(current_app, "resilience_state", {})
        bucket = state.get(str(bucket_name or "").strip(), {})
        entry = bucket.get(str(key or "").strip(), {})
        return dict(entry) if isinstance(entry, dict) else {}


def _resilience_remaining_ms(entry: dict[str, Any], field_name: str) -> int:
    try:
        deadline = float((entry or {}).get(field_name) or 0)
    except (TypeError, ValueError):
        deadline = 0
    return max(0, int((deadline - time.time()) * 1000))


def _resilience_record_success(bucket_name: str, key: str, *, next_allowed_ms: int = 0) -> dict[str, Any]:
    now = time.time()
    with _resilience_state_lock():
        state = getattr(current_app, "resilience_state", {})
        bucket = state.setdefault(str(bucket_name or "").strip(), {})
        entry = dict(bucket.get(str(key or "").strip(), {}) or {})
        entry.update(
            {
                "failureCount": 0,
                "retryAfterMs": 0,
                "pausedUntil": 0,
                "nextAllowedAt": now + (max(0, int(next_allowed_ms or 0)) / 1000) if next_allowed_ms else 0,
                "lastError": "",
                "degraded": False,
            }
        )
        bucket[str(key or "").strip()] = entry
        current_app.resilience_state = state
        return dict(entry)


def _resilience_record_failure(
    bucket_name: str,
    key: str,
    *,
    error: str = "",
    base_delay_ms: int,
    max_delay_ms: int,
) -> dict[str, Any]:
    now = time.time()
    with _resilience_state_lock():
        state = getattr(current_app, "resilience_state", {})
        bucket = state.setdefault(str(bucket_name or "").strip(), {})
        entry = dict(bucket.get(str(key or "").strip(), {}) or {})
        failure_count = max(1, int(entry.get("failureCount") or 0) + 1)
        retry_after_ms = _resilience_backoff_ms(
            failure_count,
            base_delay_ms=base_delay_ms,
            max_delay_ms=max_delay_ms,
        )
        entry.update(
            {
                "failureCount": failure_count,
                "retryAfterMs": retry_after_ms,
                "pausedUntil": now + (retry_after_ms / 1000),
                "nextAllowedAt": 0,
                "lastError": str(error or "").strip(),
                "degraded": True,
            }
        )
        bucket[str(key or "").strip()] = entry
        current_app.resilience_state = state
        return dict(entry)


def _jsonify_with_retry_after(payload: dict[str, Any], status_code: int = 200):
    response = jsonify(payload)
    response.status_code = status_code
    retry_after_ms = max(0, int((payload or {}).get("retryAfterMs") or 0))
    if retry_after_ms > 0:
        response.headers["Retry-After"] = str(max(1, (retry_after_ms + 999) // 1000))
    return response


def _username_variants(username: str) -> list[str]:
    return username_variants(username)


def _normalize_username(username: str) -> str:
    return normalize_username(username)


def _service_query(process_id: str) -> dict:
    return {"processId": {"$eq": str(process_id)}}


def _service_name_query(api_name: str) -> dict:
    return {"apiName": {"$eq": str(api_name)}}


def _join_route(base_path: Any, sub_path: Any) -> str:
    """Join a service base path and route without duplicating the base path."""
    base = str(base_path or "").strip().strip("/")
    sub = str(sub_path or "").strip().strip("/")
    if base and (sub == base or sub.startswith(f"{base}/")):
        route = sub
    else:
        route = "/".join(part for part in (base, sub) if part)
    return f"/{route}" if route else "/"


def _runtime_cfg(key: str):
    # Re-read persisted AI values so a long-lived worker and a restarted worker
    # observe the same configuration source.
    if key in {"AI_PROVIDER", "OPENAI_API_KEY", "OPENAI_MODEL", "GOOGLE_API_KEY", "GOOGLE_MODEL", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"}:
        try:
            path = _backend_env_local_path()
            runtime_keys = set(getattr(current_app, "ai_config_runtime_keys", set()))
            runtime_mtimes = getattr(current_app, "ai_config_runtime_mtimes", {})
            current_mtime = path.stat().st_mtime_ns if path.exists() else None
            if key in runtime_keys and runtime_mtimes.get(key) == current_mtime:
                return current_app.config.get(key, getattr(Config, key, None))
            from dotenv import dotenv_values
            value = dotenv_values(path).get(key)
            if value is not None:
                current_app.config[key] = value
                if key in runtime_keys:
                    runtime_mtimes[key] = current_mtime
                return value
        except Exception:
            pass
    return current_app.config.get(key, getattr(Config, key, None))


def _load_normalized_auth_data() -> dict:
    if has_request_context():
        cached = getattr(g, "_liwiro_auth_data", None)
        if isinstance(cached, dict):
            return copy.deepcopy(cached)
        loaded = _load_normalized_auth_data_impl()
        g._liwiro_auth_data = copy.deepcopy(loaded)
        return loaded
    return _load_normalized_auth_data_impl()


def _save_normalized_auth_data(data: dict) -> dict:
    saved = _save_normalized_auth_data_impl(data)
    if has_request_context():
        g._liwiro_auth_data = copy.deepcopy(saved)
    return saved


def _normalized_named_pipe_path(value: str | None = None) -> str:
    return resolve_vdb_named_pipe_path(current_app.config, value)


def _backend_env_local_path() -> Path:
    configured = str(os.getenv("LIWIRO_ENV_LOCAL_PATH") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / ".env.local"


def _upsert_env_local_values(updates: dict[str, str | None]) -> None:
    path = _backend_env_local_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    updated = content
    changed = False

    for key, raw_value in updates.items():
        value = str(raw_value or "").strip()
        if not value:
            continue
        line = f"{key}={value}"
        pattern = re.compile(rf"(?m)^{re.escape(key)}=.*$")
        if pattern.search(updated):
            next_content = pattern.sub(lambda _match, replacement=line: replacement, updated, count=1)
        else:
            next_content = updated
            if next_content and not next_content.endswith("\n"):
                next_content += "\n"
            next_content += line + "\n"
        if next_content != updated:
            updated = next_content
            changed = True

    if changed or not path.exists():
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=str(path.parent),
                prefix=f".{path.name}.", delete=False
            ) as handle:
                handle.write(updated)
                handle.flush()
                os.fsync(handle.fileno())
                temp_path = Path(handle.name)
            os.chmod(temp_path, stat.S_IRUSR | stat.S_IWUSR)
            os.replace(temp_path, path)
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)


def _persist_runtime_vdb_env(
    *,
    vdb_transport: str,
    vdb_server_url: str,
    vdb_unix_socket_path: str,
    vdb_named_pipe_path: str,
    vdb_username: str,
    vdb_password: str,
    liwiro_domain: str,
    liwiro_db: str,
) -> None:
    _upsert_env_local_values({
        "VDB_TRANSPORT": str(vdb_transport or "").strip(),
        "VDB_SERVER_URL": str(vdb_server_url or "").strip(),
        "VDB_UNIX_SOCKET_PATH": str(vdb_unix_socket_path or "").strip(),
        "VDB_NAMED_PIPE_PATH": _normalized_named_pipe_path(vdb_named_pipe_path),
        "VDB_USERNAME": _normalize_username(vdb_username),
        "VDB_PASSWORD": str(vdb_password or "").strip(),
        "LIWIRO_APP_USERNAME": _normalize_username(vdb_username),
        "LIWIRO_APP_PASSWORD": str(vdb_password or "").strip(),
        "LIWIRO_DOMAIN": str(liwiro_domain or "").strip(),
        "LIWIRO_DB": str(liwiro_db or "").strip(),
    })


def _verse_service() -> VerseService:
    signature = (
        str(_runtime_cfg("VERSE_ROOT") or "").strip(),
        str(_runtime_cfg("VERSE_DATA_DIR") or "").strip(),
        str(_runtime_cfg("AI_PROVIDER") or "").strip(),
        str(_runtime_cfg("GOOGLE_MODEL") or "").strip(),
        str(_runtime_cfg("GOOGLE_API_KEY") or "").strip(),
        str(_runtime_cfg("ANTHROPIC_MODEL") or "").strip(),
        str(_runtime_cfg("ANTHROPIC_API_KEY") or "").strip(),
        str(_runtime_cfg("OPENAI_MODEL") or "").strip(),
        str(_runtime_cfg("OPENAI_API_KEY") or "").strip(),
    )
    service = getattr(current_app, "verse_service", None)
    if service is not None and getattr(current_app, "verse_service_signature", None) == signature:
        return service
    provider_config = {
        "AI_PROVIDER": _runtime_cfg("AI_PROVIDER"),
        "GOOGLE_API_KEY": _runtime_cfg("GOOGLE_API_KEY"),
        "GOOGLE_MODEL": _runtime_cfg("GOOGLE_MODEL"),
        "ANTHROPIC_API_KEY": _runtime_cfg("ANTHROPIC_API_KEY"),
        "ANTHROPIC_MODEL": _runtime_cfg("ANTHROPIC_MODEL"),
        "OPENAI_API_KEY": _runtime_cfg("OPENAI_API_KEY"),
        "OPENAI_MODEL": _runtime_cfg("OPENAI_MODEL"),
    }
    service = VerseService(
        verse_root=_runtime_cfg("VERSE_ROOT"),
        data_dir=_runtime_cfg("VERSE_DATA_DIR"),
        provider_config=provider_config,
        platform_context_loader=_verse_proactive_platform_snapshot,
    )
    current_app.verse_service = service
    current_app.verse_service_signature = signature
    return service


_AI_PROVIDER_SPECS = {
    "openai": {"label": "OpenAI", "keyConfig": "OPENAI_API_KEY", "modelConfig": "OPENAI_MODEL", "defaultModel": "gpt-5-mini"},
    "google": {"label": "Google Gemini", "keyConfig": "GOOGLE_API_KEY", "modelConfig": "GOOGLE_MODEL", "defaultModel": "gemini-3-flash-preview"},
    "anthropic": {"label": "Anthropic Claude", "keyConfig": "ANTHROPIC_API_KEY", "modelConfig": "ANTHROPIC_MODEL", "defaultModel": "claude-sonnet-4-6"},
}

_AI_ENV_PERSIST_LOCK = threading.RLock()
_PROACTIVE_THREAD_LOCK = threading.Lock()


def _ai_key_provider_hint(value: Any) -> str | None:
    key = str(value or "").strip()
    if key.startswith("sk-ant-"):
        return "anthropic"
    if key.startswith(("sk-proj-", "sk-svcacct-")):
        return "openai"
    if key.startswith("AIza"):
        return "google"
    return None


def _validate_ai_key_assignment(provider_id: str, api_key: str) -> None:
    hinted = _ai_key_provider_hint(api_key)
    if hinted and hinted != provider_id:
        expected = {"openai": "OpenAI", "anthropic": "Anthropic", "google": "Google"}[hinted]
        selected = _AI_PROVIDER_SPECS[provider_id]["label"]
        article = "an" if expected[0].lower() in "aeiou" else "a"
        raise ValueError(f"This looks like {article} {expected} API key. Save it under {expected}, not {selected}.")


def _ai_config_status(session: dict | None = None) -> dict[str, Any]:
    selected = str(_runtime_cfg("AI_PROVIDER") or "openai").strip().lower()
    if selected not in _AI_PROVIDER_SPECS:
        selected = "openai"
    providers = [
        {
            "id": provider_id,
            "label": spec["label"],
            "model": str(_runtime_cfg(spec["modelConfig"]) or spec["defaultModel"]).strip(),
            "configured": bool(str(_runtime_cfg(spec["keyConfig"]) or "").strip()),
            "default": provider_id == selected,
        }
        for provider_id, spec in _AI_PROVIDER_SPECS.items()
    ]
    selected_provider = next(item for item in providers if item["id"] == selected)
    return {
        "configured": bool(selected_provider["configured"]),
        "anyConfigured": any(item["configured"] for item in providers),
        "defaultProvider": selected,
        "canManage": _is_super_admin_session(session),
        "providers": providers,
    }


def _persist_ai_env_values(updates: dict[str, str]) -> None:
    """Persist AI settings atomically and serialize concurrent writers."""
    path = _backend_env_local_path()
    lock_path = path.with_name(f"{path.name}.lock")
    with _AI_ENV_PERSIST_LOCK:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+", encoding="utf-8") as lock_handle:
            try:
                os.chmod(lock_path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass
            if fcntl is not None:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                _persist_ai_env_values_unlocked(path, updates)
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def _persist_ai_env_values_unlocked(path: Path, updates: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    updated = path.read_text(encoding="utf-8") if path.exists() else ""
    for key, raw_value in updates.items():
        line = f"{key}={json.dumps(str(raw_value or ''), ensure_ascii=True)}"
        pattern = re.compile(rf"(?m)^{re.escape(key)}=.*$")
        if pattern.search(updated):
            updated = pattern.sub(lambda _match, replacement=line: replacement, updated, count=1)
        else:
            if updated and not updated.endswith("\n"):
                updated += "\n"
            updated += line + "\n"

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=str(path.parent), prefix=f".{path.name}.", delete=False) as handle:
            handle.write(updated)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        os.chmod(temp_path, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _sanitize_ai_config_text(value: Any, *, field: str, max_length: int) -> str:
    text = str(value or "").strip()
    if "\n" in text or "\r" in text:
        raise ValueError(f"{field} must be a single line")
    if len(text) > max_length:
        raise ValueError(f"{field} is too long")
    return text

def _verse_trim_text(value: Any, limit: int = 240) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: max(limit - 3, 0)].rstrip()}..."


def _verse_sanitize_string_dict(value: Any, *, allowed_keys: tuple[str, ...], item_limit: int = 8, string_limit: int = 220) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    payload: dict[str, Any] = {}
    for key in allowed_keys:
        if key not in value:
            continue
        raw = value.get(key)
        if isinstance(raw, list):
            items = [_verse_trim_text(item, min(string_limit, 120)) for item in raw]
            items = [item for item in items if item][:item_limit]
            if items:
                payload[key] = items
            continue
        if isinstance(raw, dict):
            nested: dict[str, Any] = {}
            for nested_key, nested_value in list(raw.items())[:item_limit]:
                nested_key_text = _verse_trim_text(nested_key, 80)
                nested_value_text = _verse_trim_text(nested_value, min(string_limit, 120))
                if nested_key_text and nested_value_text:
                    nested[nested_key_text] = nested_value_text
            if nested:
                payload[key] = nested
            continue
        if isinstance(raw, bool):
            payload[key] = raw
            continue
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            payload[key] = raw
            continue
        text = _verse_trim_text(raw, string_limit)
        if text:
            payload[key] = text
    return payload


def _verse_sanitize_metrics(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    payload: dict[str, Any] = {}
    for key, raw in list(value.items())[:12]:
        key_text = _verse_trim_text(key, 80)
        if not key_text:
            continue
        if isinstance(raw, bool):
            payload[key_text] = raw
            continue
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            payload[key_text] = raw
            continue
        text = _verse_trim_text(raw, 120)
        if text:
            payload[key_text] = text
    return payload


def _verse_sanitize_records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    records: list[dict[str, Any]] = []
    for item in value[:8]:
        if not isinstance(item, dict):
            continue
        record: dict[str, Any] = {}
        for key, raw in list(item.items())[:10]:
            key_text = _verse_trim_text(key, 80)
            if not key_text:
                continue
            if isinstance(raw, bool):
                record[key_text] = raw
                continue
            if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                record[key_text] = raw
                continue
            text = _verse_trim_text(raw, 240)
            if text:
                record[key_text] = text
        if record:
            records.append(record)
    return records


def _verse_sanitize_available_actions(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    actions: list[dict[str, Any]] = []
    for item in value[:8]:
        sanitized = _verse_sanitize_string_dict(
            item,
            allowed_keys=("id", "label", "description", "kind", "targetPath", "targetId"),
            item_limit=6,
            string_limit=180,
        )
        if sanitized:
            actions.append(sanitized)
    return actions


def _normalize_verse_request_context(context: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(context, dict):
        return {}
    normalized: dict[str, Any] = {}
    for key, limit in (("pathname", 160), ("screen", 160), ("pageKind", 80), ("pageSummary", 900)):
        text = _verse_trim_text(context.get(key), limit)
        if text:
            normalized[key] = text

    focus = _verse_sanitize_string_dict(
        context.get("focus"),
        allowed_keys=("kind", "label", "identifier", "id", "name", "title", "status", "contentSummary", "contentPreview", "path", "reason"),
        string_limit=360,
    )
    if focus:
        normalized["focus"] = focus

    selection = _verse_sanitize_string_dict(
        context.get("selection"),
        allowed_keys=("kind", "id", "ids", "name", "title", "status", "targetPath"),
        string_limit=200,
    )
    if selection:
        normalized["selection"] = selection

    entity = _verse_sanitize_string_dict(
        context.get("entity"),
        allowed_keys=("kind", "id", "name", "title", "status", "path", "owner"),
        string_limit=200,
    )
    if entity:
        normalized["entity"] = entity

    metrics = _verse_sanitize_metrics(context.get("metrics"))
    if metrics:
        normalized["metrics"] = metrics

    actions = _verse_sanitize_available_actions(context.get("availableActions"))
    if actions:
        normalized["availableActions"] = actions

    records = _verse_sanitize_records(context.get("records"))
    if records:
        normalized["records"] = records

    return normalized


def _verse_request_context(body: dict | None = None) -> tuple[str, dict]:
    payload = dict(body or {})
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    screen = str(
        payload.get("screen")
        or payload.get("currentScreen")
        or context.get("screen")
        or context.get("pathname")
        or "/verse-ai"
    ).strip()
    platform_context = _normalize_verse_request_context(context)
    for key in ("screen", "pathname", "pageKind"):
        value = payload.get(key)
        if value in {None, ""} and isinstance(context, dict):
            value = context.get(key)
        text = _verse_trim_text(value, 160 if key != "pageKind" else 80)
        if text:
            platform_context[key] = text
    platform_context.setdefault("screen", screen)
    return screen, platform_context


def _run_with_proactive_leader_lock(app: Flask, work) -> bool:
    """Run one proactive operation only when this worker owns the tick lock."""
    if fcntl is None:
        # Windows and restricted runtimes may not expose POSIX file locks. A
        # process-local nonblocking lock still prevents duplicate ticks among
        # threads in the same worker. Cross-process coordination requires the
        # POSIX file lock above and is unavailable on platforms without fcntl.
        if not _PROACTIVE_THREAD_LOCK.acquire(blocking=False):
            return False
        try:
            work()
            return True
        finally:
            _PROACTIVE_THREAD_LOCK.release()
    try:
        data_dir = Path(str(app.config.get("VERSE_DATA_DIR") or _runtime_cfg("VERSE_DATA_DIR") or ".")).expanduser()
        data_dir.mkdir(parents=True, exist_ok=True)
        lock_path = data_dir / ".proactive-scheduler.lock"
        lock_handle = lock_path.open("a+", encoding="utf-8")
        os.chmod(lock_path, stat.S_IRUSR | stat.S_IWUSR)
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock_handle.close()
            return False
    except OSError:
        app.logger.exception("Unable to acquire Verse proactive scheduler leadership lock")
        return False
    try:
        work()
        return True
    finally:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        finally:
            lock_handle.close()


def _start_verse_proactive_startup_recovery(app: Flask) -> None:
    if getattr(app, "verse_startup_recovery_started", False):
        return
    if app.debug and str(os.getenv("WERKZEUG_RUN_MAIN") or "").strip().lower() not in {"1", "true"}:
        return

    app.verse_startup_recovery_started = True
    stop_event = threading.Event()
    app.verse_startup_recovery_stop = stop_event

    def _recover() -> None:
        with app.app_context():
            for attempt in range(2):
                try:
                    if attempt:
                        if stop_event.wait(1.0):
                            return
                    if stop_event.is_set():
                        return
                    _run_with_proactive_leader_lock(app, lambda: _verse_service().recover_missed_proactive_evaluations())
                    return
                except PermissionError:
                    if attempt == 1:
                        current_app.logger.warning("Verse proactive startup recovery skipped because schedule state was unavailable")
                except Exception:
                    current_app.logger.exception("Verse proactive startup recovery failed")
                    return

    thread = threading.Thread(
        target=_recover,
        name="verse-proactive-startup-recovery",
        daemon=True,
    )
    app.verse_startup_recovery_thread = thread
    thread.start()


def _start_verse_proactive_scheduler(app: Flask) -> None:
    """Run proactive evaluations server-side so they do not depend on a tab."""
    if getattr(app, "verse_proactive_scheduler_started", False):
        return
    if app.debug and str(os.getenv("WERKZEUG_RUN_MAIN") or "").strip().lower() not in {"1", "true"}:
        return
    app.verse_proactive_scheduler_started = True
    # Configuration is user-controlled (environment/config files); malformed
    # values must not prevent the API from starting. Keep a conservative
    # minimum so a busy worker cannot spin in a tight loop.
    interval = _verse_proactive_scheduler_interval_seconds(app)
    stop_event = threading.Event()
    app.verse_proactive_scheduler_stop = stop_event

    def _run() -> None:
        with app.app_context():
            while not stop_event.is_set():
                try:
                    _run_with_proactive_leader_lock(app, lambda: _verse_service().run_due_proactive_evaluations())
                except Exception:
                    current_app.logger.exception("Verse proactive scheduler failed")
                stop_event.wait(interval)

    thread = threading.Thread(target=_run, name="verse-proactive-scheduler", daemon=True)
    app.verse_proactive_scheduler_thread = thread
    thread.start()


def _stop_verse_background_workers(app: Flask, timeout: float = 5.0) -> None:
    """Stop and join Verse background workers owned by an app instance.

    Flask does not provide an application-object destructor, so callers that
    create short-lived app instances (tests, CLI tools, reloaders) can use this
    explicit lifecycle hook to prevent daemon workers from touching torn-down
    workspaces.
    """
    events = (
        getattr(app, "verse_startup_recovery_stop", None),
        getattr(app, "verse_proactive_scheduler_stop", None),
    )
    for event in events:
        if event is not None:
            event.set()
    current = threading.current_thread()
    for thread in (
        getattr(app, "verse_startup_recovery_thread", None),
        getattr(app, "verse_proactive_scheduler_thread", None),
    ):
        if thread is not None and thread.is_alive() and thread is not current:
            thread.join(timeout=max(0.0, float(timeout)))


def _verse_proactive_scheduler_interval_seconds(app: Flask) -> int:
    """Return a safe scheduler interval for potentially malformed config."""
    try:
        value = int(app.config.get("VERSE_PROACTIVE_SCHEDULER_INTERVAL_SECONDS", 60) or 60)
    except (TypeError, ValueError):
        value = 60
    return max(10, value)


def _verse_collaboration_level(body: dict | None = None) -> str:
    payload = dict(body or {})
    return str(
        payload.get("collaborationLevel")
        or payload.get("collaboration_level")
        or ""
    ).strip()


def _verse_proactive_mode_enabled(body: dict | None = None) -> Any:
    payload = dict(body or {})
    if "proactiveModeEnabled" in payload:
        return payload.get("proactiveModeEnabled")
    if "proactive_mode_enabled" in payload:
        return payload.get("proactive_mode_enabled")
    return None


def _verse_agent_settings(body: dict | None = None) -> dict[str, Any]:
    payload = dict(body or {})
    raw = payload.get("agents") if isinstance(payload.get("agents"), dict) else payload.get("agentSettings") if isinstance(payload.get("agentSettings"), dict) else {}
    return {
        str(agent_id or "").strip(): dict(settings or {})
        for agent_id, settings in dict(raw or {}).items()
        if str(agent_id or "").strip() and isinstance(settings, dict)
    }


def _verse_prerequisite_status(session: dict | None = None) -> dict[str, Any]:
    conn = _vdb_portal_connection_info()
    media_env_keys = (
        "MEDIA_STORAGE_PROVIDER",
        "MEDIA_STORAGE_BUCKET",
        "MEDIA_STORAGE_BASE_URL",
        "CLOUDINARY_CLOUD_NAME",
        "CLOUDINARY_API_KEY",
        "CLOUDINARY_API_SECRET",
    )
    media_configured = any(str(_runtime_cfg(key) or "").strip() for key in media_env_keys)
    is_super_admin = _is_super_admin_session(session)
    return {
        "vdb": {
            "appCredentialsReady": bool(str(_runtime_cfg("LIWIRO_APP_USERNAME") or "").strip() and str(_runtime_cfg("LIWIRO_APP_PASSWORD") or "").strip()),
            "superAdminSaved": bool(str(conn.get("vdb_super_admin_username") or "").strip() and conn.get("has_saved_vdb_super_admin_password")),
            "superAdminSession": bool(is_super_admin),
            "domain": str(conn.get("liwiro_domain") or "").strip(),
            "database": str(conn.get("liwiro_db") or "").strip(),
        },
        "media": {
            "configured": bool(media_configured),
            "provider": str(_runtime_cfg("MEDIA_STORAGE_PROVIDER") or "").strip(),
        },
        "workspaceEnvRoute": "/platform/vi/workspace-env",
        "canBootstrapAppAccount": bool(is_super_admin),
    }


def _verse_proactive_platform_snapshot(username: str) -> dict[str, Any]:
    from app.verse.telemetry import PlatformTelemetry
    auth_data = _load_normalized_auth_data()
    auth_user = _find_auth_user(auth_data, username) or {}
    session_like = {
        "username": str(username or "").strip(),
        "role": auth_user.get("role"),
        "service_access": auth_user.get("service_access") or auth_user.get("serviceAccess") or [],
        "is_super_admin": bool(auth_user.get("is_super_admin")),
    }
    services_summary: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    if getattr(current_app, "vdb_client", None):
        try:
            _use_runtime_workspace()
            success, services = current_app.vdb_client.read_documents("services", {})
            if success and isinstance(services, list):
                production_mode = _production_mode_enabled(auth_data.get("settings") or {})
                visible_services = _filter_accessible_services(session_like, services)
                for raw_service in visible_services:
                    lapis = raw_service.get("lapis_config") if isinstance(raw_service.get("lapis_config"), dict) else {}
                    metadata = lapis.get("metadata") if isinstance(lapis.get("metadata"), dict) else {}
                    documentation = metadata.get("documentation") if isinstance(metadata.get("documentation"), dict) else {}
                    status = str(raw_service.get("status") or "UNKNOWN").strip().upper() or "UNKNOWN"
                    status_counts[status] = status_counts.get(status, 0) + 1
                    services_summary.append(
                        {
                            "processId": str(raw_service.get("processId") or raw_service.get("process_id") or "").strip(),
                            "apiName": str(raw_service.get("apiName") or metadata.get("apiName") or "").strip(),
                            "status": status,
                            "port": raw_service.get("port"),
                            "basePath": str(raw_service.get("basePath") or metadata.get("basePath") or "").strip(),
                            "productionMode": bool(production_mode),
                            "docsEnabled": bool(documentation.get("enabled")),
                            "mediaCapabilities": raw_service.get("mediaCapabilities") if isinstance(raw_service.get("mediaCapabilities"), dict) else {},
                        }
                    )
        except Exception as exc:
            services_summary = [{"error": str(exc)}]

    return {
        "generatedAt": _utcnow_iso(),
        "username": str(username or "").strip(),
        "prerequisites": _verse_prerequisite_status(session_like),
        "platformSettings": _platform_settings_with_defaults(auth_data.get("settings") or {}),
        "serviceStatusCounts": status_counts,
        "services": services_summary,
        "activity": PlatformTelemetry(_runtime_cfg("VERSE_DATA_DIR")).rows(
            username, [item["apiName"] for item in services_summary if item.get("apiName")]
        ),
        "capabilities": [
            {
                "capabilityId": str(item.get("capabilityId") or "").strip(),
                "summary": str(item.get("summary") or "").strip(),
                "surfaceId": str(item.get("surfaceId") or "").strip(),
            }
            for item in list_platform_capabilities(client="verse")
        ],
    }


def _platform_vdb_defaults() -> dict:
    return {
        "hostPlatform": host_platform(),
        "supportsNamedPipe": bool(supports_named_pipe_transport()),
        "supportsUnixSocket": bool(supports_unix_socket_transport()),
        "defaultVdbTransport": str(default_vdb_transport_mode()),
        "defaultVdbServerUrl": str(getattr(Config, "VDB_SERVER_URL", "http://127.0.0.1:1957") or "http://127.0.0.1:1957").strip(),
        "defaultVdbUnixSocketPath": str(default_vdb_unix_socket_path() or "").strip(),
        "defaultVdbNamedPipePath": str(default_vdb_named_pipe_path() or "").strip(),
        "defaultVdbExportOutDir": _default_vdb_export_out_dir(),
    }


def _requested_vdb_transport_mode(value: str | None) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    if text in {"namedpipe", "named_pipe", "pipe", "ipc", "af_pipe"}:
        return "namedpipe"
    if text in {"unixsocket", "unix_socket", "unix", "socket", "uds"}:
        return "unixsocket"
    if text in {"http", "httpserver", "http_server", "tcp", "tcp_loopback"}:
        return "http"
    return normalize_vdb_transport_mode(value)


def _default_vdb_export_out_dir() -> str:
    configured = str(
        os.getenv("VDB_EXPORT_OUT_DIR")
        or getattr(Config, "VDB_EXPORT_OUT_DIR", "")
        or ""
    ).strip()
    if configured:
        return str(Path(configured).expanduser())
    return str((Path(tempfile.gettempdir()) / "vdb-exports").resolve())


def _use_runtime_workspace() -> None:
    current_app.vdb_client.use_domain(_runtime_cfg("LIWIRO_DOMAIN"))
    current_app.vdb_client.use_database(_runtime_cfg("LIWIRO_DB"))


def _platform_permissions_for_role(role: str) -> set[str]:
    role = _normalize_platform_role(role)
    if role == ROLE_ADMIN:
        return {"VIEW_SERVICES", "MANAGE_SERVICES"}
    if role == ROLE_SERVICE_MANAGER:
        return {"VIEW_SERVICES", "MANAGE_SERVICES"}
    return {"VIEW_SERVICES"}


def _build_auth_session_payload(username: str, auth_user: dict | None, bootstrap: bool) -> dict:
    role = ROLE_ADMIN if bootstrap else _normalize_platform_role((auth_user or {}).get("role"))
    is_super_admin = True if bootstrap else bool((auth_user or {}).get("is_super_admin", False))
    service_access = (
        [WILDCARD_SERVICE_ACCESS]
        if bootstrap
        else _normalize_service_access((auth_user or {}).get("service_access"))
    )
    if role == ROLE_ADMIN and WILDCARD_SERVICE_ACCESS not in service_access:
        service_access = [WILDCARD_SERVICE_ACCESS]

    return {
        "username": username,
        "role": role,
        "is_super_admin": is_super_admin,
        "service_access": service_access,
        "permissions_overrides": _normalize_user_permissions((auth_user or {}).get("permissions")),
        "liwiro_rbac": _normalize_liwiro_rbac((auth_user or {}).get("liwiro_rbac"), is_super_admin=is_super_admin),
        "permissions": sorted(_platform_permissions_for_role(role)),
    }


def _auth_sessions_path() -> Path:
    auth_path = Path(str(getattr(Config, "LIWIRO_AUTH_PATH", "") or "")).expanduser()
    if auth_path.name:
        return auth_path.with_name("liwiro.frontend.sessions.json")
    return Path(__file__).resolve().parents[1] / ".runtime" / "liwiro.frontend.sessions.json"


def _load_persisted_auth_sessions() -> dict[str, dict]:
    sessions_path = _auth_sessions_path()
    try:
        if not sessions_path.exists():
            return {}
        payload = json.loads(sessions_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    sessions: dict[str, dict] = {}
    for token, session in payload.items():
        if isinstance(token, str) and token.strip() and isinstance(session, dict):
            sessions[token.strip()] = session
    return sessions


def _persist_auth_sessions() -> None:
    if not has_app_context():
        return
    sessions_path = _auth_sessions_path()
    try:
        sessions_path.parent.mkdir(parents=True, exist_ok=True)
        sessions_path.write_text(
            json.dumps(current_app.auth_sessions, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    except Exception:
        current_app.logger.warning("Unable to persist frontend auth sessions.", exc_info=True)


def _require_platform_permission(permission: str):
    session = _session_from_header()
    if not session:
        return jsonify({"error": "Authentication required"}), 401
    role = session.get("role", "viewer")
    if permission not in _platform_permissions_for_role(role):
        return jsonify({"error": "Insufficient platform permissions"}), 403
    return None


def _is_super_admin_session(session: dict | None) -> bool:
    return bool((session or {}).get("is_super_admin", False))


def _require_super_admin():
    session = _session_from_header()
    if not session:
        return jsonify({"error": "Authentication required"}), 401
    if not _is_super_admin_session(session):
        return jsonify({"error": "Super admin privileges required"}), 403
    return None


def _sync_service_runtime_state(service_doc: dict) -> dict:
    service = dict(service_doc or {})
    process_id = str(service.get("processId") or "")
    running = False
    if process_id.isdigit():
        try:
            pid = int(process_id)
            if psutil.pid_exists(pid):
                proc = psutil.Process(pid)
                running = bool(proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE)
        except Exception:
            running = False
    service["status"] = "RUNNING" if running else "NOT_RUNNING"
    if not running:
        service["port"] = None
    return service


def _sync_service_runtime_env(service_doc: dict) -> tuple[dict, bool]:
    service = dict(service_doc or {})
    lapis_config = service.get("lapis_config")
    if not isinstance(lapis_config, dict):
        return service, False

    runtime_port_raw = service.get("port")
    if runtime_port_raw is None:
        return service, False

    try:
        runtime_port = str(int(float(str(runtime_port_raw).strip())))
    except Exception:
        return service, False

    updated_lapis = copy.deepcopy(lapis_config)
    metadata = updated_lapis.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        updated_lapis["metadata"] = metadata
    env_cfg = metadata.get("env")
    if not isinstance(env_cfg, dict):
        env_cfg = {}
        metadata["env"] = env_cfg

    changed = False
    if str(env_cfg.get("PORT") or "").strip() != runtime_port:
        env_cfg["PORT"] = runtime_port
        changed = True

    configured_reset = str(env_cfg.get("PASSWORD_RESET_URL") or "").strip()
    if configured_reset:
        updated_reset = configured_reset
        if "{PORT}" in updated_reset:
            updated_reset = updated_reset.replace("{PORT}", runtime_port)
        elif "127.0.0.1:5001" in updated_reset:
            updated_reset = updated_reset.replace("127.0.0.1:5001", f"127.0.0.1:{runtime_port}")
        if updated_reset != configured_reset:
            env_cfg["PASSWORD_RESET_URL"] = updated_reset
            changed = True

    if changed:
        service["lapis_config"] = updated_lapis
    return service, changed


def _session_from_header():
    if not has_request_context():
        return None
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None
    return current_app.auth_sessions.get(token)


def _vdb_portal_connection_info() -> dict:
    auth_data = _load_normalized_auth_data()
    return {
        "vdb_transport": normalize_vdb_transport_mode(
            auth_data.get("vdb_transport") or _runtime_cfg("VDB_TRANSPORT") or default_vdb_transport_mode()
        ),
        "vdb_server_url": str(
            auth_data.get("vdb_server_url") or _runtime_cfg("VDB_SERVER_URL") or ""
        ).strip(),
        "vdb_unix_socket_path": str(
            auth_data.get("vdb_unix_socket_path") or _runtime_cfg("VDB_UNIX_SOCKET_PATH") or ""
        ).strip(),
        "vdb_named_pipe_path": _normalized_named_pipe_path(
            auth_data.get("vdb_named_pipe_path") or _runtime_cfg("VDB_NAMED_PIPE_PATH") or ""
        ),
        "vdb_app_username": str(
            auth_data.get("vdb_username") or _runtime_cfg("VDB_USERNAME") or ""
        ).strip(),
        "has_saved_vdb_app_password": bool(
            str(_runtime_cfg("LIWIRO_APP_PASSWORD") or _runtime_cfg("VDB_PASSWORD") or "").strip()
        ),
        "vdb_super_admin_username": str(auth_data.get("vdb_super_admin_username") or "").strip(),
        "has_saved_vdb_super_admin_password": bool(str(_runtime_cfg("VDB_SUPER_ADMIN_PASSWORD") or "").strip()),
        "liwiro_domain": str(
            auth_data.get("liwiro_domain") or _runtime_cfg("LIWIRO_DOMAIN") or ""
        ).strip(),
        "liwiro_db": str(auth_data.get("liwiro_db") or _runtime_cfg("LIWIRO_DB") or "").strip(),
        **_platform_vdb_defaults(),
    }


def _apply_runtime_vdb_config(
    *,
    vdb_transport: str,
    vdb_server_url: str,
    vdb_unix_socket_path: str,
    vdb_named_pipe_path: str,
    vdb_username: str | None = None,
    vdb_password: str | None = None,
    liwiro_domain: str | None = None,
    liwiro_db: str | None = None,
) -> None:
    resolved_transport = normalize_vdb_transport_mode(vdb_transport)
    resolved_server_url = str(vdb_server_url or "").strip()
    if resolved_transport == "http":
        resolved_server_url = str(
            normalize_local_vdb_http_url(resolved_server_url or "http://127.0.0.1:1957")
        ).strip()
    elif resolved_transport == "namedpipe":
        resolved_server_url = str(
            normalize_local_vdb_http_url(resolved_server_url or "http://127.0.0.1:1957")
        ).strip()
        vdb_named_pipe_path = resolve_vdb_named_pipe_path(current_app.config, vdb_named_pipe_path)
    current_app.config["VDB_TRANSPORT"] = resolved_transport
    current_app.config["VDB_SERVER_URL"] = resolved_server_url
    current_app.config["VDB_UNIX_SOCKET_PATH"] = str(vdb_unix_socket_path or "").strip()
    current_app.config["VDB_NAMED_PIPE_PATH"] = str(vdb_named_pipe_path or "").strip()
    if vdb_username is not None:
        current_app.config["VDB_USERNAME"] = _normalize_username(vdb_username)
    if vdb_password is not None:
        current_app.config["VDB_PASSWORD"] = str(vdb_password or "").strip()
    if liwiro_domain is not None:
        current_app.config["LIWIRO_DOMAIN"] = str(liwiro_domain or "").strip()
    if liwiro_db is not None:
        current_app.config["LIWIRO_DB"] = str(liwiro_db or "").strip()


def _resolve_local_vdb_http_target(server_url: str | None) -> dict | None:
    normalized_url = str(
        normalize_local_vdb_http_url(str(server_url or "").strip() or "http://127.0.0.1:1957")
    ).strip()
    if not normalized_url:
        return None

    parsed = urlparse(normalized_url)
    if parsed.scheme != "http":
        return None
    if not parsed.hostname or not is_local_vdb_url(normalized_url):
        return None

    port = parsed.port or 1957
    base_url = f"http://127.0.0.1:{port}"
    return {
        "server_url": normalized_url,
        "base_url": base_url,
        "health_url": f"{base_url}/health",
        "port": port,
    }


def _is_vdb_http_healthy(server_url: str | None, timeout: float = 2.0) -> bool:
    target = _resolve_local_vdb_http_target(server_url)
    if not target:
        return False
    try:
        response = requests.get(target["health_url"], timeout=timeout)
    except requests.RequestException:
        return False
    return bool(response.ok)


def _probe_vdb_http_status(server_url: str | None, timeout: float = 2.0) -> dict:
    normalized_url = str(
        normalize_local_vdb_http_url(str(server_url or "").strip() or "http://127.0.0.1:1957")
    ).strip()
    parsed = urlparse(normalized_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return {
            "transport": "http",
            "available": False,
            "status": "unavailable",
            "target": normalized_url or "",
            "detail": "Invalid HTTP server URL",
            "localTarget": False,
        }

    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    target_url = f"{parsed.scheme}://{host}:{port}"
    health_url = f"{parsed.scheme}://{host}:{port}/health"
    local_target = bool(is_local_vdb_url(normalized_url))
    try:
        response = requests.get(health_url, timeout=timeout)
    except requests.RequestException:
        return {
            "transport": "http",
            "available": False,
            "status": "unavailable",
            "target": target_url,
            "detail": "HTTP server unavailable",
            "localTarget": local_target,
        }

    if response.ok:
        return {
            "transport": "http",
            "available": True,
            "status": "available",
            "target": target_url,
            "detail": "HTTP server available",
            "localTarget": local_target,
        }
    return {
        "transport": "http",
        "available": False,
        "status": "unavailable",
        "target": target_url,
        "detail": f"HTTP server responded with status {response.status_code}",
        "localTarget": local_target,
    }


def _probe_vdb_unix_socket_status(socket_path: str | None, timeout: float = 1.0) -> dict:
    if not supports_unix_socket_transport():
        return {
            "transport": "unixsocket",
            "available": False,
            "status": "unavailable",
            "target": "",
            "detail": "Unix sockets are unavailable on this host",
            "localTarget": False,
        }
    resolved_path = resolve_vdb_unix_socket_path(current_app.config, socket_path)
    if not resolved_path:
        return {
            "transport": "unixsocket",
            "available": False,
            "status": "unavailable",
            "target": "",
            "detail": "No Unix socket path configured",
            "localTarget": True,
        }
    if not os.path.exists(resolved_path):
        return {
            "transport": "unixsocket",
            "available": False,
            "status": "unavailable",
            "target": resolved_path,
            "detail": "Unix socket unavailable",
            "localTarget": True,
        }
    try:
        socket_mode = os.stat(resolved_path).st_mode
    except OSError:
        return {
            "transport": "unixsocket",
            "available": False,
            "status": "unavailable",
            "target": resolved_path,
            "detail": "Unix socket unavailable",
            "localTarget": True,
        }
    if not stat.S_ISSOCK(socket_mode):
        return {
            "transport": "unixsocket",
            "available": False,
            "status": "unavailable",
            "target": resolved_path,
            "detail": "Configured path is not a Unix socket",
            "localTarget": True,
        }
    try:
        VDBUnixSocketTransport(resolved_path).health(timeout=max(1, int(timeout)))
    except (VDBTransportConnectionError, VDBTransportProtocolError, VDBTransportRequestError):
        return {
            "transport": "unixsocket",
            "available": False,
            "status": "unavailable",
            "target": resolved_path,
            "detail": "Unix socket unavailable",
            "localTarget": True,
        }

    return {
        "transport": "unixsocket",
        "available": True,
        "status": "available",
        "target": resolved_path,
        "detail": "Unix socket available",
        "localTarget": True,
    }


def _probe_vdb_named_pipe_status(named_pipe_path: str | None, timeout: float = 1.0) -> dict:
    if not supports_named_pipe_transport():
        return {
            "transport": "namedpipe",
            "available": False,
            "status": "unsupported",
            "target": "",
            "detail": "Named pipes are only supported on Windows",
            "localTarget": False,
        }

    resolved_path = resolve_vdb_named_pipe_path(current_app.config, named_pipe_path)
    if not resolved_path:
        return {
            "transport": "namedpipe",
            "available": False,
            "status": "unavailable",
            "target": "",
            "detail": "No named pipe path configured",
            "localTarget": True,
        }

    try:
        VDBNamedPipeTransport(resolved_path).health(timeout=max(1, int(timeout)))
    except (VDBTransportConnectionError, VDBTransportProtocolError, VDBTransportRequestError):
        return {
            "transport": "namedpipe",
            "available": False,
            "status": "unavailable",
            "target": resolved_path,
            "detail": "Named pipe unavailable",
            "localTarget": True,
        }

    return {
        "transport": "namedpipe",
        "available": True,
        "status": "available",
        "target": resolved_path,
        "detail": "Named pipe available",
        "localTarget": True,
    }


def _probe_vdb_transport_status(
    transport_mode: str | None,
    server_url: str | None = None,
    socket_path: str | None = None,
    named_pipe_path: str | None = None,
) -> dict:
    resolved_mode = _requested_vdb_transport_mode(transport_mode)
    if resolved_mode == "http":
        return _probe_vdb_http_status(server_url)
    if resolved_mode == "namedpipe":
        return _probe_vdb_named_pipe_status(named_pipe_path)
    return _probe_vdb_unix_socket_status(socket_path)


def _read_log_tail(log_path: Path, line_limit: int = 8) -> str:
    try:
        if not log_path.is_file():
            return ""
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return ""
    excerpt = [line.strip() for line in lines[-line_limit:] if line.strip()]
    return " | ".join(excerpt)


def _vdb_jar_contains_class(jar_path: Path, class_name: str) -> bool:
    try:
        import zipfile

        member_name = str(class_name or "").strip().replace(".", "/") + ".class"
        if not member_name:
            return False
        with zipfile.ZipFile(jar_path, "r") as archive:
            return member_name in archive.namelist()
    except Exception:
        return False


def _summarize_named_pipe_autostart_error(message: str, *, jar_path: Path | None = None) -> str:
    text = str(message or "").strip()
    lowered = text.lower()
    if "classnotfoundexception" in lowered or "could not find or load main class verun.vdb.vdbnamedpipe" in lowered:
        if jar_path:
            return (
                "The direct VDB named-pipe runtime is missing from the current build. "
                f"Rebuild Verun VDB so {jar_path.name} includes verun.vdb.VDBNamedPipe."
            )
        return "The direct VDB named-pipe runtime is missing from the current build."
    if "named-pipe interface exited during auto-start:" in text:
        text = text.split("named-pipe interface exited during auto-start:", 1)[1].strip()
    if "did not become healthy:" in text:
        text = text.split("did not become healthy:", 1)[1].strip()
    if " | " in text:
        text = text.split(" | ")[-1].strip()
    return text or "Named-pipe interface is unavailable."


class _LiwiroAccessLogFilter(logging.Filter):
    QUIET_PATTERNS = (
        'GET /auth/status ',
        'GET /auth/vdb-connection-status',
    )

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        return not any(pattern in message for pattern in self.QUIET_PATTERNS)


def _friendly_transport_prepare_error(
    transport_mode: str | None,
    message: str | None,
    *,
    named_pipe_path: str | None = None,
) -> str:
    text = str(message or "").strip()
    resolved_mode = normalize_vdb_transport_mode(transport_mode)
    if resolved_mode == "namedpipe":
        resolved_path = resolve_vdb_named_pipe_path(current_app.config, named_pipe_path)
        if "ClassNotFoundException: verun.vdb.VDBNamedPipe" in text or "Could not find or load main class verun.vdb.VDBNamedPipe" in text:
            return (
                "Direct VDB named-pipe support is not available in the current Verun build. "
                "Rebuild Verun VDB, then start Liwiro again."
            )
        if "did not become healthy" in text or "exited during auto-start" in text:
            return f"Direct VDB named-pipe interface is unavailable at {resolved_path}."
        if "Named pipes are only supported on Windows" in text:
            return text
        return text or f"Direct VDB named-pipe interface is unavailable at {resolved_path}."
    return text or "VDB transport is unavailable."


def _background_creationflags() -> int:
    if os.name != "nt":
        return 0
    return int(
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "DETACHED_PROCESS", 0)
    )


def _resolve_bash_executable() -> str | None:
    bash_path = shutil.which("bash")
    if bash_path:
        return bash_path
    shell_path = str(os.getenv("SHELL") or "").strip()
    if shell_path and Path(shell_path).name.lower().startswith("bash"):
        return shell_path
    for candidate in (
        Path(os.environ.get("ProgramFiles", "")) / "Git" / "bin" / "bash.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Git" / "usr" / "bin" / "bash.exe",
        Path(os.environ.get("ProgramW6432", "")) / "Git" / "bin" / "bash.exe",
        Path(os.environ.get("ProgramW6432", "")) / "Git" / "usr" / "bin" / "bash.exe",
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def _launch_background_process(command: list[str], *, cwd: str, env: dict, log_handle) -> subprocess.Popen:
    return subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=os.name != "nt",
        creationflags=_background_creationflags(),
        close_fds=True,
    )


def _autostart_local_vdb_http_if_needed(app: Flask, server_url: str | None) -> tuple[bool, str]:
    target = _resolve_local_vdb_http_target(server_url)
    if not target:
        return True, "Skipping VDB HTTP auto-start for non-local or non-HTTP target"
    if _is_vdb_http_healthy(target["server_url"]):
        return True, f"VDB HTTP already healthy at {target['base_url']}"

    verun_root = _resolve_verun_root()
    if not verun_root:
        return False, "Cannot resolve verun root for local VDB HTTP auto-start"

    serve_script = verun_root / "vdb" / "scripts" / "serve.sh"
    workdir = _resolve_vdb_workdir()
    if not serve_script.is_file():
        if os.name != "nt":
            return False, f"VDB HTTP start script not found at {serve_script}"
    if not workdir.is_dir():
        return False, f"VDB working directory not found at {workdir}"

    log_dir = workdir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "http-autostart.log"
    env = os.environ.copy()
    env["VDB_HTTP_PORT"] = str(target["port"])
    command: list[str]
    if os.name == "nt":
        jar_path = verun_root / "vdb" / "target" / "vdb-1.0.0-jar-with-dependencies.jar"
        if not jar_path.is_file():
            return False, f"VDB jar not found at {jar_path}"
        command = ["java", "-cp", str(jar_path), "verun.vdb.VDBHttpServer"]
    else:
        command = [str(serve_script)]

    try:
        with log_path.open("ab") as log_handle:
            proc = _launch_background_process(command, cwd=str(workdir), env=env, log_handle=log_handle)
    except Exception as exc:
        return False, f"Failed to launch local VDB HTTP server: {exc}"

    deadline = time.time() + 25
    while time.time() < deadline:
        if _is_vdb_http_healthy(target["server_url"], timeout=1.0):
            setattr(app, "_liwiro_vdb_http_process", proc)
            return True, f"Started local VDB HTTP server at {target['base_url']}"
        if proc.poll() is not None:
            log_excerpt = _read_log_tail(log_path)
            if log_excerpt:
                return False, f"Local VDB HTTP server exited during auto-start: {log_excerpt}"
            return False, "Local VDB HTTP server exited during auto-start"
        time.sleep(0.5)

    if proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            pass
    log_excerpt = _read_log_tail(log_path)
    if log_excerpt:
        return False, f"Local VDB HTTP server did not become healthy: {log_excerpt}"
    return False, f"Local VDB HTTP server did not become healthy at {target['base_url']}"


def _stop_autostarted_vdb_http(app: Flask, server_url: str | None) -> tuple[bool, str]:
    """Stop only an HTTP server started by this backend, never an external listener."""
    proc = getattr(app, "_liwiro_vdb_http_process", None)
    if proc is None or proc.poll() is not None:
        setattr(app, "_liwiro_vdb_http_process", None)
        return True, "No backend-managed VDB HTTP server was running"
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception as exc:
        return False, f"Unable to stop the backend-managed VDB HTTP server: {exc}"
    if proc.poll() is None:
        return False, "The backend-managed VDB HTTP server did not stop"
    setattr(app, "_liwiro_vdb_http_process", None)
    target = _resolve_local_vdb_http_target(server_url)
    if target and _is_vdb_http_healthy(target["server_url"], timeout=1.0):
        return False, "The VDB HTTP listener is still healthy after stop"
    return True, "Stopped the backend-managed VDB HTTP server"


def _autostart_local_vdb_named_pipe_if_needed(
    app: Flask,
    server_url: str | None,
    named_pipe_path: str | None,
) -> tuple[bool, str]:
    if not supports_named_pipe_transport():
        return False, "Named pipes are only supported on Windows"

    resolved_path = resolve_vdb_named_pipe_path(app.config, named_pipe_path)
    if not resolved_path:
        return False, "No named pipe path configured"

    existing_status = _probe_vdb_named_pipe_status(resolved_path)
    if bool(existing_status.get("available")):
        return True, f"Named pipe already healthy at {resolved_path}"

    verun_root = _resolve_verun_root()
    if not verun_root:
        return False, "Cannot resolve verun root for named-pipe auto-start"

    workdir = _resolve_vdb_workdir()
    if not workdir.is_dir():
        return False, f"VDB working directory not found at {workdir}"

    log_dir = workdir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "namedpipe-autostart.log"
    env = os.environ.copy()
    env["VDB_NAMED_PIPE_PATH"] = resolved_path
    launcher = verun_root / "vdb" / "scripts" / "namedpipe.sh"
    if not launcher.is_file():
        return False, f"Named-pipe launcher not found at {launcher}"
    # `supports_named_pipe_transport` is the authoritative platform probe;
    # using it here also keeps emulated Windows/container integrations aligned.
    if os.name == "nt" or supports_named_pipe_transport():
        bash_executable = _resolve_bash_executable()
        if not bash_executable:
            return False, "Bash is required to launch the named-pipe interface on Windows"
        command = [bash_executable, str(launcher)]
    else:
        command = [str(launcher)]

    try:
        log_path.write_text("", encoding="utf-8")
        with log_path.open("ab") as log_handle:
            proc = _launch_background_process(
                command,
                cwd=str(workdir),
                env=env,
                log_handle=log_handle,
            )
    except Exception as exc:
        return False, f"Failed to launch named-pipe interface: {exc}"

    deadline = time.time() + 20
    while time.time() < deadline:
        status = _probe_vdb_named_pipe_status(resolved_path, timeout=1.0)
        if bool(status.get("available")):
            return True, f"Started named-pipe interface at {resolved_path}"
        if proc.poll() is not None:
            log_excerpt = _read_log_tail(log_path)
            if log_excerpt:
                return False, _summarize_named_pipe_autostart_error(log_excerpt)
            return False, "Named-pipe interface exited during auto-start"
        time.sleep(0.4)

    if proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            pass
    log_excerpt = _read_log_tail(log_path)
    if log_excerpt:
        return False, _summarize_named_pipe_autostart_error(log_excerpt)
    return False, f"Named-pipe interface did not become healthy at {resolved_path}"


def _ensure_vdb_transport_ready(
    app: Flask,
    transport_mode: str | None,
    server_url: str | None,
    socket_path: str | None = None,
    named_pipe_path: str | None = None,
) -> tuple[bool, str]:
    resolved_mode = normalize_vdb_transport_mode(transport_mode)
    if resolved_mode == "http":
        return _autostart_local_vdb_http_if_needed(app, server_url)
    stopped, stop_message = _stop_autostarted_vdb_http(app, server_url)
    if not stopped:
        return False, f"Cannot stop the active VDB HTTP server before switching to IPC: {stop_message}"
    if resolved_mode == "namedpipe":
        return _autostart_local_vdb_named_pipe_if_needed(app, server_url, named_pipe_path)
    resolved_socket_path = resolve_vdb_unix_socket_path(app.config, socket_path)
    if _probe_vdb_unix_socket_status(resolved_socket_path).get("available"):
        return True, f"Unix socket transport ready ({resolved_socket_path})"
    return False, f"Unix socket transport is unavailable at {resolved_socket_path}"


def _vdb_portal_session_from_header():
    token = str(request.headers.get("X-VDB-Portal-Token") or "").strip()
    if not token:
        return None, ""
    session_payload = current_app.vdb_portal_sessions.get(token)
    if not session_payload:
        return None, token
    requester = _session_from_header()
    if not requester:
        return None, token
    owner_username = _normalize_username(session_payload.get("owner_username"))
    requester_username = _normalize_username(requester.get("username"))
    if not owner_username or not requester_username or owner_username != requester_username:
        return None, token
    return session_payload, token


def _vdb_portal_query(session_payload: dict, query: dict):
    session_id = str(session_payload.get("session_id") or "").strip()
    if not session_id:
        return False, {"error": "Invalid VDB portal session"}
    try:
        transport = build_vdb_transport(
            current_app,
            server_url=str(session_payload.get("vdb_server_url") or "").strip(),
            socket_path=str(session_payload.get("vdb_unix_socket_path") or "").strip(),
            named_pipe_path=str(session_payload.get("vdb_named_pipe_path") or "").strip(),
            transport_mode=str(session_payload.get("vdb_transport") or session_payload.get("transport_kind") or "").strip(),
            prefer_socket=str(session_payload.get("transport_kind") or "").strip().lower() != "http",
            allow_http_fallback=True,
        )
        query = _canonicalize_vdb_query(query)
        data = transport.vql(session_id, query, timeout=30)
        return True, data if isinstance(data, dict) else {"data": data}
    except VDBTransportRequestError as exc:
        payload = exc.payload if isinstance(exc.payload, dict) else {}
        return False, {
            "error": str((payload or {}).get("error") or (payload or {}).get("message") or str(exc) or "VDB query failed")
        }
    except (VDBTransportConnectionError, VDBTransportProtocolError) as exc:
        return False, {"error": str(exc)}
    except Exception as exc:
        return False, {"error": str(exc)}


def _canonicalize_vdb_query(query: dict) -> dict:
    """Validate public command text while supporting trusted internal action objects."""
    if isinstance(query, str):
        from app.vdb_commands import validate_command
        return validate_command(query)
    if not isinstance(query, (dict, list)) or (isinstance(query, dict) and "action" not in query and "commands" not in query):
        raise ValueError("Use a readable VDB command, for example: read users")
    return _validate_flat_vdb_payload(query)
def _vdb_data_as_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("data", "domains", "owned_domains", "ownedDomains"):
            inner = value.get(key)
            if isinstance(inner, list):
                return inner
    return []


def _vdb_data_as_str_list(value) -> list[str]:
    out: list[str] = []
    for item in _vdb_data_as_list(value):
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out


def _vdb_payload_data(value):
    if isinstance(value, dict) and "data" in value:
        return value.get("data")
    return value


def _normalize_domain_list(raw_values: list) -> list[str]:
    normalized = []
    for value in raw_values or []:
        text = str(value or "").strip().lower()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _all_vdb_domains() -> list[str]:
    try:
        ok, domains = current_app.vdb_client.list_domains()
    except Exception:
        ok, domains = False, []
    if ok:
        return _normalize_domain_list(_vdb_data_as_list(domains))
    return []


def _latest_vdb_portal_session_for_user(username: str) -> dict | None:
    target = _normalize_username(username)
    if not target:
        return None
    latest = None
    latest_issued = ""
    for payload in (current_app.vdb_portal_sessions or {}).values():
        if _normalize_username((payload or {}).get("owner_username")) != target:
            continue
        issued = str((payload or {}).get("issuedAt") or "")
        if latest is None or issued > latest_issued:
            latest = payload
            latest_issued = issued
    return latest


def _create_saved_vdb_super_admin_session() -> tuple[bool, dict]:
    requester = _session_from_header()
    if not requester:
        return False, {"error": "Authentication required", "status_code": 401}
    if not _is_super_admin_session(requester):
        return False, {"error": "Only Liwiro super admin can use saved VDB super admin access", "status_code": 403}

    conn = _vdb_portal_connection_info()
    auth_data = _load_normalized_auth_data()
    username = _normalize_username(auth_data.get("vdb_super_admin_username") or conn.get("vdb_super_admin_username"))
    password = str(_runtime_cfg("VDB_SUPER_ADMIN_PASSWORD") or "").strip()
    if not username or not password:
        return False, {"error": "Saved VDB super admin credentials are required", "status_code": 400}

    vdb_transport = normalize_vdb_transport_mode(conn.get("vdb_transport") or "unixsocket")
    server_url = str(conn.get("vdb_server_url") or "").strip()
    portal_socket_path = resolve_vdb_unix_socket_path(current_app.config, conn.get("vdb_unix_socket_path"))
    portal_named_pipe_path = resolve_vdb_named_pipe_path(current_app.config, conn.get("vdb_named_pipe_path"))

    ready, ready_msg = _ensure_vdb_transport_ready(
        current_app,
        vdb_transport,
        server_url,
        portal_socket_path,
        portal_named_pipe_path,
    )
    if not ready:
        return False, {"error": f"VDB transport could not be prepared: {ready_msg}", "status_code": 503}

    try:
        transport = build_vdb_transport(
            current_app,
            server_url=server_url,
            socket_path=portal_socket_path,
            named_pipe_path=portal_named_pipe_path,
            transport_mode=vdb_transport,
            prefer_socket=True,
            allow_http_fallback=True,
        )
        auth_json = transport.auth(username, password, timeout=30)
        session_id = str((auth_json or {}).get("sessionId") or "").strip()
        if not session_id:
            return False, {"error": "VDB authentication succeeded but no sessionId was returned", "status_code": 502}
        if isinstance(transport, VDBUnixSocketTransport):
            transport_kind = "unixsocket"
        elif isinstance(transport, VDBNamedPipeTransport):
            transport_kind = "namedpipe"
        else:
            transport_kind = "http"
        return True, {
            "mode": "super_admin",
            "username": username,
            "owner_username": _normalize_username(requester.get("username")),
            "vdb_transport": transport_kind,
            "vdb_server_url": server_url,
            "vdb_unix_socket_path": portal_socket_path,
            "vdb_named_pipe_path": portal_named_pipe_path,
            "transport_kind": transport_kind,
            "session_id": session_id,
        }
    except VDBTransportRequestError as exc:
        payload = exc.payload if isinstance(exc.payload, dict) else {}
        return False, {
            "error": str((payload or {}).get("error") or (payload or {}).get("message") or str(exc) or "VDB authentication failed"),
            "status_code": 401,
        }
    except Exception as exc:
        return False, {"error": f"Failed to authenticate against VDB: {exc}", "status_code": 500}


def _resolve_vdb_rbac_session() -> tuple[dict | None, dict | None]:
    session_payload, token = _vdb_portal_session_from_header()
    if token and not session_payload:
        return None, {"error": "VDB portal session not found or not owned by current user", "status_code": 404}
    if session_payload:
        return session_payload, None
    ok, payload = _create_saved_vdb_super_admin_session()
    if not ok:
        return None, payload
    return payload, None


def _normalize_vdb_user_permissions_payload(username: str, payload) -> dict:
    data = _vdb_payload_data(payload)
    row = data if isinstance(data, dict) else {}
    normalized_username = _normalize_username((row or {}).get("username") or username)
    return {
        "username": normalized_username,
        "owned_domains": _normalize_domain_list((row or {}).get("owned_domains") or (row or {}).get("ownedDomains") or []),
        "db_permissions": (row or {}).get("db_permissions") if isinstance((row or {}).get("db_permissions"), dict) else {},
        "collection_permissions": (row or {}).get("collection_permissions") if isinstance((row or {}).get("collection_permissions"), dict) else {},
    }


def _collect_vdb_rbac_overview(session_payload: dict) -> tuple[bool, dict]:
    out = {
        "users": [],
        "roles": {},
        "permissions": [],
        "domains": [],
        "user_permissions": [],
    }

    users_ok, users_result = _vdb_portal_query(session_payload, {"action": "tumi", "operation": "list", "resource": "users"})
    if not users_ok:
        return False, users_result if isinstance(users_result, dict) else {"error": "Failed to list VDB users"}
    usernames = _vdb_data_as_str_list(users_result)
    out["users"] = usernames

    roles_ok, roles_result = _vdb_portal_query(session_payload, {"action": "tumi", "operation": "list", "resource": "roles"})
    if roles_ok:
        role_payload = _vdb_payload_data(roles_result)
        out["roles"] = role_payload if isinstance(role_payload, dict) else {}

    perms_ok, perms_result = _vdb_portal_query(session_payload, {"action": "tumi", "operation": "list", "resource": "permissions"})
    if perms_ok:
        perm_payload = _vdb_payload_data(perms_result)
        if isinstance(perm_payload, list):
            out["permissions"] = [str(item or "").strip() for item in perm_payload if str(item or "").strip()]

    domains_ok, domains_result = _vdb_portal_query(session_payload, {"action": "tumi", "operation": "list", "resource": "domains_and_owners"})
    if domains_ok:
        domain_payload = _vdb_payload_data(domains_result)
        out["domains"] = domain_payload if isinstance(domain_payload, list) else []

    for username in usernames:
        details_ok, details_result = _vdb_portal_query(session_payload, {"action": "tumi", "operation": "list", "resource": "permissions", "username": username})
        if details_ok:
            out["user_permissions"].append(_normalize_vdb_user_permissions_payload(username, details_result))

    return True, out


def _session_accessible_domains(session: dict | None) -> list[str]:
    if not session:
        return []
    if _is_super_admin_session(session):
        return _all_vdb_domains()

    username = _normalize_username((session or {}).get("username"))
    portal_session = _latest_vdb_portal_session_for_user(username)
    if portal_session:
        list_ok, list_result = _vdb_portal_query(portal_session, {"action": "list", "resource": "domains"})
        whoami_ok, whoami_result = _vdb_portal_query(portal_session, {"action": "whoami"})
        tumi_ok, tumi_result = _vdb_portal_query(portal_session, {"action": "tumi", "operation": "list", "resource": "owned_domains"})

        visible = _normalize_domain_list(_vdb_data_as_list(list_result if list_ok else []))
        whoami_data = whoami_result.get("data") if whoami_ok and isinstance(whoami_result, dict) else {}
        whoami_owned = _normalize_domain_list(
            _vdb_data_as_list((whoami_data or {}).get("owned_domains") or (whoami_data or {}).get("ownedDomains") or [])
        )
        tumi_owned = _normalize_domain_list(_vdb_data_as_list(tumi_result if tumi_ok else []))
        owned = tumi_owned or whoami_owned
        if owned and visible:
            overlap = [domain for domain in owned if domain in visible]
            if overlap:
                return overlap
        if owned:
            return owned
        if visible:
            return visible

    return _all_vdb_domains()


def _module_source_payload(module: dict) -> dict:
    if not isinstance(module, dict):
        return {}
    return {
        "name": str(module.get("name") or "").strip(),
        "title": str(module.get("title") or module.get("name") or "").strip(),
        "description": str(module.get("description") or "").strip(),
        "scope": str(module.get("scope") or "domain").strip().lower(),
        "owner_username": str(module.get("owner_username") or "").strip(),
        "owner_domains": _normalize_domain_list(module.get("owner_domains") or []),
        "assigned_domains": _normalize_domain_list(module.get("assigned_domains") or []),
        "domain_restore": _normalize_domain_list(module.get("domain_restore") or []),
        "service_domain": str(module.get("service_domain") or module.get("serviceDomain") or "").strip().lower(),
        "config_schema": module.get("config_schema") if isinstance(module.get("config_schema"), dict) else {},
        "config_defaults": module.get("config_defaults") if isinstance(module.get("config_defaults"), dict) else {},
        "created_at": str(module.get("created_at") or datetime.now(timezone.utc).isoformat()),
        "updated_at": str(module.get("updated_at") or datetime.now(timezone.utc).isoformat()),
        "created_by": str(module.get("created_by") or "").strip().lower(),
        "updated_by": str(module.get("updated_by") or "").strip().lower(),
    }


def _vi_module_visible_to_session(module: dict, session: dict | None, accessible_domains: list[str] | None = None) -> bool:
    if not isinstance(module, dict):
        return False
    if _is_super_admin_session(session):
        return True
    if str(module.get("scope") or "").strip().lower() == "global":
        return True
    username = _normalize_username((session or {}).get("username"))
    if username and username == _normalize_username(module.get("owner_username")):
        return True
    assigned_domains = set(_normalize_domain_list(module.get("assigned_domains") or []))
    visible_domains = set(_normalize_domain_list(accessible_domains or _session_accessible_domains(session)))
    return bool(assigned_domains & visible_domains)


def _vi_module_editable_by_session(module: dict, session: dict | None) -> bool:
    if not isinstance(module, dict) or not session:
        return False
    if _is_super_admin_session(session):
        return True
    return _normalize_username(module.get("owner_username")) == _normalize_username((session or {}).get("username"))


def _serialize_vi_module(module: dict, include_source: bool = False) -> dict:
    payload = {
        "name": str(module.get("name") or "").strip(),
        "title": str(module.get("title") or module.get("name") or "").strip(),
        "description": str(module.get("description") or "").strip(),
        "scope": str(module.get("scope") or "domain").strip().lower(),
        "owner_username": str(module.get("owner_username") or "").strip(),
        "owner_domains": _normalize_domain_list(module.get("owner_domains") or []),
        "assigned_domains": _normalize_domain_list(module.get("assigned_domains") or []),
        "domain_restore": _normalize_domain_list(module.get("domain_restore") or []),
        "service_domain": str(module.get("service_domain") or module.get("serviceDomain") or "").strip().lower(),
        "config_schema": module.get("config_schema") if isinstance(module.get("config_schema"), dict) else {},
        "config_defaults": module.get("config_defaults") if isinstance(module.get("config_defaults"), dict) else {},
        "created_at": str(module.get("created_at") or ""),
        "updated_at": str(module.get("updated_at") or ""),
        "created_by": str(module.get("created_by") or "").strip().lower(),
        "updated_by": str(module.get("updated_by") or "").strip().lower(),
    }
    if include_source:
        payload["source"] = str(module.get("source") or "")
    return payload


def _normalize_vi_module_body(
    body: dict,
    *,
    existing: dict | None,
    session: dict | None,
    accessible_domains: list[str],
) -> tuple[dict, str]:
    actor_username = _normalize_username((session or {}).get("username"))
    is_super_admin = _is_super_admin_session(session)
    module_name = validate_module_name(body.get("name") if existing is None else existing.get("name"))
    scope = str(body.get("scope") or (existing or {}).get("scope") or "domain").strip().lower()
    if scope not in {"domain", "global"}:
        scope = "domain"
    if scope == "global" and not is_super_admin:
        raise ValueError("Only a super admin can assign global scope")

    requested_domains = _normalize_domain_list(
        body.get("assigned_domains")
        if "assigned_domains" in body
        else body.get("assignedDomains")
        if "assignedDomains" in body
        else (existing or {}).get("assigned_domains")
        or []
    )
    if not is_super_admin and accessible_domains:
        requested_domains = [domain for domain in requested_domains if domain in accessible_domains]

    owner_domains = _normalize_domain_list((existing or {}).get("owner_domains") or [])
    owner_domains = _normalize_domain_list(owner_domains + requested_domains)
    if not owner_domains and actor_username and accessible_domains:
        owner_domains = list(accessible_domains)

    previous_scope = str((existing or {}).get("scope") or "domain").strip().lower()
    domain_restore = _normalize_domain_list((existing or {}).get("domain_restore") or [])
    if scope == "global":
        domain_restore = _normalize_domain_list(domain_restore + _normalize_domain_list((existing or {}).get("assigned_domains") or []) + requested_domains)
        requested_domains = []
    elif previous_scope == "global":
        restored = requested_domains or domain_restore or owner_domains
        if owner_domains:
            restored = [domain for domain in restored if domain in owner_domains]
        requested_domains = _normalize_domain_list(restored)

    record = {
        "name": module_name,
        "title": str(body.get("title") or (existing or {}).get("title") or module_name).strip() or module_name,
        "description": str(body.get("description") or (existing or {}).get("description") or "").strip(),
        "scope": scope,
        "owner_username": str((existing or {}).get("owner_username") or actor_username).strip().lower(),
        "owner_domains": owner_domains,
        "assigned_domains": requested_domains,
        "domain_restore": domain_restore,
        "service_domain": str(
            body.get("service_domain")
            or body.get("serviceDomain")
            or (existing or {}).get("service_domain")
            or ""
        ).strip().lower(),
        "config_schema": body.get("config_schema") if isinstance(body.get("config_schema"), dict) else (existing or {}).get("config_schema") or {},
        "config_defaults": body.get("config_defaults") if isinstance(body.get("config_defaults"), dict) else (existing or {}).get("config_defaults") or {},
        "created_at": str((existing or {}).get("created_at") or datetime.now(timezone.utc).isoformat()),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "created_by": str((existing or {}).get("created_by") or actor_username).strip().lower(),
        "updated_by": actor_username,
    }
    source = str(body.get("source") if "source" in body else (existing or {}).get("source") or "")
    return record, source


def _visible_vi_modules_for_session(session: dict | None, include_source: bool = False) -> tuple[list[dict], list[str]]:
    accessible_domains = _session_accessible_domains(session)
    modules = [
        module
        for module in list_module_records(include_source=include_source, app_config=current_app.config)
        if _vi_module_visible_to_session(module, session, accessible_domains)
    ]
    modules.sort(key=lambda item: (str(item.get("scope") or "") != "global", str(item.get("name") or "")))
    return modules, accessible_domains


def _normalize_service_modules(lapis_config: dict | None) -> list[dict]:
    raw_modules = (lapis_config or {}).get("modules") or []
    normalized = []
    seen = set()
    for item in raw_modules:
        if not isinstance(item, dict):
            continue
        name = normalize_module_name(item.get("name"))
        if not name or name in seen:
            continue
        seen.add(name)
        normalized.append(
            {
                "name": name,
                "config": item.get("config") if isinstance(item.get("config"), dict) else {},
            }
        )
    return normalized


def _normalize_lapis_shared_modules(lapis_config: dict | None) -> dict[str, dict]:
    raw_shared = (lapis_config or {}).get("sharedModules") or {}
    if not isinstance(raw_shared, dict):
        return {}
    normalized: dict[str, dict] = {}
    for raw_name, raw_entry in raw_shared.items():
        name = normalize_module_name(raw_name)
        if not name or not isinstance(raw_entry, dict):
            continue
        scope = str(raw_entry.get("scope") or "domain").strip().lower()
        if scope not in {"domain", "global"}:
            scope = "domain"
        assigned_domains = _normalize_domain_list(
            raw_entry.get("assigned_domains")
            if "assigned_domains" in raw_entry
            else raw_entry.get("assignedDomains")
            if "assignedDomains" in raw_entry
            else []
        )
        normalized[name] = {
            "name": name,
            "title": str(raw_entry.get("title") or name).strip() or name,
            "description": str(raw_entry.get("description") or "").strip(),
            "scope": scope,
            "service_domain": str(
                raw_entry.get("service_domain")
                or raw_entry.get("serviceDomain")
                or ""
            ).strip().lower(),
            "assigned_domains": assigned_domains,
            "config_schema": raw_entry.get("config_schema")
            if isinstance(raw_entry.get("config_schema"), dict)
            else raw_entry.get("configSchema")
            if isinstance(raw_entry.get("configSchema"), dict)
            else {},
            "config_defaults": raw_entry.get("config_defaults")
            if isinstance(raw_entry.get("config_defaults"), dict)
            else raw_entry.get("configDefaults")
            if isinstance(raw_entry.get("configDefaults"), dict)
            else {},
            "source": str(raw_entry.get("source") or ""),
        }
    return normalized


def _sync_lapis_shared_modules(lapis_config: dict | None, session: dict | None) -> dict:
    config = dict(lapis_config or {})
    normalized_shared = _normalize_lapis_shared_modules(config)
    service_domain = str(((config.get("metadata") or {}).get("apiName") or "")).strip().lower()
    accessible_domains = _session_accessible_domains(session)
    actor_username = _normalize_username((session or {}).get("username"))
    is_super_admin = _is_super_admin_session(session)
    persisted: dict[str, dict] = {}

    for module_name, module in normalized_shared.items():
        existing = load_module_record(module_name, include_source=True, app_config=current_app.config)
        if existing and not _vi_module_editable_by_session(existing, session):
            raise ValueError(f"Only the module owner or a super admin can update shared module '{module_name}'")

        requested_scope = str(module.get("scope") or "domain").strip().lower()
        if requested_scope == "global" and not is_super_admin:
            requested_scope = "domain"

        assigned_domains = _normalize_domain_list(module.get("assigned_domains") or [])
        resolved_service_domain = str(module.get("service_domain") or service_domain).strip().lower()
        if requested_scope == "domain" and resolved_service_domain:
            assigned_domains = _normalize_domain_list(assigned_domains + [resolved_service_domain])
        if not is_super_admin and accessible_domains:
            assigned_domains = [domain for domain in assigned_domains if domain in accessible_domains]

        owner_domains = _normalize_domain_list(((existing or {}).get("owner_domains") or []) + assigned_domains)
        if not owner_domains and resolved_service_domain:
            owner_domains = [resolved_service_domain]

        record = {
            "name": module_name,
            "title": module.get("title") or module_name,
            "description": module.get("description") or "",
            "scope": requested_scope,
            "owner_username": str((existing or {}).get("owner_username") or actor_username).strip().lower(),
            "owner_domains": owner_domains,
            "assigned_domains": [] if requested_scope == "global" else assigned_domains,
            "domain_restore": _normalize_domain_list(
                (existing or {}).get("domain_restore")
                or owner_domains
                or assigned_domains
            ),
            "service_domain": resolved_service_domain,
            "config_schema": module.get("config_schema") or {},
            "config_defaults": module.get("config_defaults") or {},
            "created_at": str((existing or {}).get("created_at") or datetime.now(timezone.utc).isoformat()),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "created_by": str((existing or {}).get("created_by") or actor_username).strip().lower(),
            "updated_by": actor_username,
        }
        saved = write_module_record(record, str(module.get("source") or ""), current_app.config)
        persisted[module_name] = {
            "title": str(saved.get("title") or module_name),
            "description": str(saved.get("description") or ""),
            "source": str(saved.get("source") or ""),
            "scope": str(saved.get("scope") or "domain"),
            "service_domain": str(saved.get("service_domain") or resolved_service_domain or ""),
            "assigned_domains": _normalize_domain_list(saved.get("assigned_domains") or []),
            "config_schema": saved.get("config_schema") if isinstance(saved.get("config_schema"), dict) else {},
            "config_defaults": saved.get("config_defaults") if isinstance(saved.get("config_defaults"), dict) else {},
        }

    config["sharedModules"] = persisted
    return config


def _sync_lapis_service_modules(lapis_config: dict | None, session: dict | None) -> dict:
    config = dict(lapis_config or {})
    selected_modules = _normalize_service_modules(config)
    if not selected_modules:
        config["modules"] = []
        return config

    accessible_domains = _session_accessible_domains(session)
    service_domain = str(((config.get("metadata") or {}).get("apiName") or "")).strip().lower()
    by_name = {
        str(module.get("name") or "").strip(): module
        for module in list_module_records(include_source=True, app_config=current_app.config)
    }

    for entry in selected_modules:
        name = str(entry.get("name") or "").strip()
        module = by_name.get(name)
        if not module:
            raise ValueError(f"Unknown VI module '{name}'")
        if not _vi_module_visible_to_session(module, session, accessible_domains):
            raise ValueError(f"VI module '{name}' is not available to the current user")
        if str(module.get("scope") or "").strip().lower() == "domain" and service_domain:
            if not accessible_domains or service_domain in accessible_domains or _is_super_admin_session(session):
                next_domains = _normalize_domain_list((module.get("assigned_domains") or []) + [service_domain])
                next_owner_domains = _normalize_domain_list((module.get("owner_domains") or []) + [service_domain])
                if next_domains != _normalize_domain_list(module.get("assigned_domains") or []):
                    write_module_record(
                        {
                            **_module_source_payload(module),
                            "assigned_domains": next_domains,
                            "owner_domains": next_owner_domains,
                        },
                        str(module.get("source") or ""),
                        current_app.config,
                    )

    config["modules"] = selected_modules
    return config


def _service_domain_absent(domain_name: str) -> tuple[bool, str]:
    normalized_domain = str(domain_name or "").strip().lower()
    if not normalized_domain:
        return True, ""

    list_ok, domains = current_app.vdb_client.list_domains()
    if list_ok:
        visible_domains = _normalize_domain_list(_vdb_data_as_list(domains))
        return normalized_domain not in visible_domains, ""

    switched = current_app.vdb_client.use_domain(normalized_domain)
    _use_runtime_workspace()
    if switched:
        return False, ""
    return True, "Domain visibility could not be verified via list; fallback switch treated it as absent."


def _drop_service_domain_and_verify(domain_name: str) -> tuple[bool, dict]:
    normalized_domain = str(domain_name or "").strip().lower()
    result = {
        "droppedDomain": False,
        "droppedDb": False,
        "alreadyAbsent": False,
        "warnings": [],
        "errors": [],
    }
    if not normalized_domain:
        result["errors"].append("Service domain is missing")
        return False, result
    if normalized_domain in {"liwiro", "default"}:
        result["errors"].append("Service data deletion skipped for protected/shared domain")
        return False, result

    _use_runtime_workspace()
    drop_ok, drop_res = current_app.vdb_client.drop_domain(normalized_domain)
    if drop_ok:
        result["droppedDomain"] = True
        result["droppedDb"] = True
    else:
        message = ""
        if isinstance(drop_res, dict):
            message = str(drop_res.get("error") or drop_res.get("message") or "").strip()
        else:
            message = str(drop_res or "").strip()
        lowered = message.lower()
        if "not found" in lowered or "does not exist" in lowered or "unknown domain" in lowered:
            result["alreadyAbsent"] = True
            result["droppedDomain"] = True
            result["droppedDb"] = True
            if message:
                result["warnings"].append(message)
        else:
            result["errors"].append(message or f"Failed to drop domain '{normalized_domain}'")

    absent, verify_note = _service_domain_absent(normalized_domain)
    if verify_note:
        result["warnings"].append(verify_note)
    if not absent:
        result["errors"].append(f"Service domain '{normalized_domain}' still exists after deletion attempt")
        result["droppedDomain"] = False
        result["droppedDb"] = False

    _use_runtime_workspace()
    return absent, result


def _platform_settings_with_defaults(raw_settings: dict | None) -> dict:
    settings = dict(raw_settings or {})
    feature_flags = feature_flags_with_defaults(settings.get("featureFlags") if isinstance(settings.get("featureFlags"), dict) else {})
    return {
        "productionMode": bool(settings.get("productionMode", False)),
        "startServicesOnStartup": bool(settings.get("startServicesOnStartup", False)),
        "autoRefreshServiceStatus": bool(settings.get("autoRefreshServiceStatus", True)),
        "deleteDataWithServiceByDefault": bool(settings.get("deleteDataWithServiceByDefault", True)),
        "startServicesAfterGenerationByDefault": bool(settings.get("startServicesAfterGenerationByDefault", True)),
        "retryFailedBatchOpsByDefault": bool(settings.get("retryFailedBatchOpsByDefault", True)),
        "featureFlags": feature_flags,
        "featureFlagDefinitions": feature_flag_definitions(),
    }


def _production_mode_enabled(raw_settings: dict | None = None) -> bool:
    if raw_settings is None:
        auth_data = _load_normalized_auth_data()
        raw_settings = auth_data.get("settings") or {}
    return bool(_platform_settings_with_defaults(raw_settings).get("productionMode", False))


def _frontend_auth_or_forbid():
    session = _session_from_header()
    if not session:
        return jsonify({"error": "Authentication required"}), 401
    return None


def _request_is_loopback() -> bool:
    if not has_request_context():
        return False
    candidates = [request.remote_addr, *(request.access_route or [])]
    for candidate in candidates:
        value = str(candidate or "").strip().lower()
        if not value:
            continue
        if value in {"127.0.0.1", "::1", "localhost"}:
            return True
        if value.startswith("::ffff:127.0.0.1"):
            return True
    return False


def _session_from_request_token():
    if not has_request_context():
        return None
    session = _session_from_header()
    if session:
        return session
    token = str(request.args.get("token") or request.args.get("authToken") or "").strip()
    if not token:
        return None
    return current_app.auth_sessions.get(token)


def _current_vi_request_session() -> dict | None:
    session = _session_from_header() or _session_from_request_token()
    if not isinstance(session, dict):
        return None
    return dict(session)


def _role_from_session(session: dict | None) -> str:
    return _normalize_platform_role((session or {}).get("role"))


def _session_service_access(session: dict | None) -> list[str]:
    return _normalize_service_access((session or {}).get("service_access"))


def _session_permission_rules(session: dict | None, effect: str | None = None) -> list[dict]:
    rules = _normalize_user_permissions((session or {}).get("permissions_overrides"))
    if effect is None:
        return rules
    wanted = str(effect or "").strip().upper()
    return [rule for rule in rules if str(rule.get("effect") or "ALLOW").strip().upper() == wanted]


def _match_permission_service(rule: dict, service_doc: dict | None) -> bool:
    service = dict(service_doc or {})
    wanted = str(rule.get("service") or "").strip().lower()
    if wanted in {"", "*", "all"}:
        return True
    api_name = str(service.get("apiName") or "").strip().lower()
    process_id = str(service.get("processId") or "").strip().lower()
    return wanted in {api_name, process_id}


def _session_has_direct_service_access(session: dict | None, service_doc: dict | None) -> bool:
    access = _session_service_access(session)
    if WILDCARD_SERVICE_ACCESS in access:
        return True
    service = dict(service_doc or {})
    names = {
        str(service.get("apiName") or "").strip(),
        str(service.get("processId") or "").strip(),
    }
    names = {value for value in names if value}
    return bool(names) and any(item in names for item in access)


def _permission_rule_matches(
    rule: dict,
    service_doc: dict | None,
    required_types: set[str] | None = None,
    endpoint: str | None = None,
    model: str | None = None,
    target_service: str | None = None,
    allow_service_level_match: bool = False,
) -> bool:
    rule_type = str(rule.get("type") or "").strip().upper()
    if required_types and rule_type not in required_types:
        return False
    if not _match_permission_service(rule, service_doc):
        return False

    endpoint_value = str(endpoint or "").strip().lower()
    model_value = str(model or "").strip().lower()
    target_value = str(target_service or "").strip().lower()

    if rule_type == "SERVICE_ALL":
        return True
    if rule_type == "SERVICE_ENDPOINT":
        rule_endpoint = str(rule.get("endpoint") or "").strip().lower()
        if not endpoint_value:
            return allow_service_level_match or rule_endpoint in {"", "*", "all"}
        return rule_endpoint in {"", "*", "all"} or rule_endpoint == endpoint_value
    if rule_type == "SERVICE_MODEL":
        rule_model = str(rule.get("model") or "").strip().lower()
        if not model_value:
            return allow_service_level_match or rule_model in {"", "*", "all"}
        return rule_model in {"", "*", "all"} or rule_model == model_value
    if rule_type == "CROSS_SERVICE":
        rule_target = str(rule.get("targetService") or "").strip().lower()
        if not target_value:
            return allow_service_level_match or rule_target in {"", "*", "all"}
        return rule_target in {"", "*", "all"} or rule_target == target_value
    return False


def _session_has_matching_permission_rule(
    session: dict | None,
    service_doc: dict | None,
    effect: str = "ALLOW",
    required_types: set[str] | None = None,
    endpoint: str | None = None,
    model: str | None = None,
    target_service: str | None = None,
    allow_service_level_match: bool = False,
) -> bool:
    rules = _session_permission_rules(session, effect=effect)
    if not rules:
        return False
    for rule in rules:
        if _permission_rule_matches(
            rule,
            service_doc,
            required_types=required_types,
            endpoint=endpoint,
            model=model,
            target_service=target_service,
            allow_service_level_match=allow_service_level_match,
        ):
            return True
    return False


def _session_is_service_permission_denied(
    session: dict | None,
    service_doc: dict | None,
    required_types: set[str] | None = None,
    endpoint: str | None = None,
    model: str | None = None,
    target_service: str | None = None,
) -> bool:
    deny_types = {"SERVICE_ALL"}
    if required_types:
        deny_types.update(required_types)
    return _session_has_matching_permission_rule(
        session,
        service_doc,
        effect="DENY",
        required_types=deny_types,
        endpoint=endpoint,
        model=model,
        target_service=target_service,
        allow_service_level_match=False,
    )


def _session_has_fine_grained_service_permission(
    session: dict | None,
    service_doc: dict | None,
    required_types: set[str] | None = None,
    endpoint: str | None = None,
    model: str | None = None,
    target_service: str | None = None,
) -> bool:
    if _session_is_service_permission_denied(
        session,
        service_doc,
        required_types=required_types,
        endpoint=endpoint,
        model=model,
        target_service=target_service,
    ):
        return False
    return _session_has_matching_permission_rule(
        session,
        service_doc,
        effect="ALLOW",
        required_types=required_types,
        endpoint=endpoint,
        model=model,
        target_service=target_service,
        allow_service_level_match=False,
    )


def _session_can_access_service(session: dict | None, service_doc: dict | None) -> bool:
    service = dict(service_doc or {})
    names = {
        str(service.get("apiName") or "").strip(),
        str(service.get("processId") or "").strip(),
    }
    names = {value for value in names if value}
    if not names:
        return False
    if _session_is_service_permission_denied(session, service_doc, required_types={"SERVICE_ALL"}):
        return False
    if _session_has_direct_service_access(session, service_doc):
        return True
    return _session_has_matching_permission_rule(
        session,
        service_doc,
        effect="ALLOW",
        required_types={"SERVICE_ALL", "SERVICE_ENDPOINT", "SERVICE_MODEL", "CROSS_SERVICE"},
        allow_service_level_match=True,
    )


def _changed_endpoint_paths(old_config: dict, new_config: dict) -> set[str]:
    changed = set()
    old_eps = old_config.get("endpoints") or {}
    new_eps = new_config.get("endpoints") or {}
    endpoint_ids = set(old_eps.keys()) | set(new_eps.keys())
    for endpoint_id in endpoint_ids:
        old_ep = old_eps.get(endpoint_id)
        new_ep = new_eps.get(endpoint_id)
        if old_ep == new_ep:
            continue
        path = str((new_ep or old_ep or {}).get("path") or endpoint_id).strip()
        changed.add(path or endpoint_id)
    return changed


def _changed_model_names(old_config: dict, new_config: dict) -> set[str]:
    changed = set()
    old_models = old_config.get("models") or {}
    new_models = new_config.get("models") or {}
    model_ids = set(old_models.keys()) | set(new_models.keys())
    for model_id in model_ids:
        old_model = old_models.get(model_id)
        new_model = new_models.get(model_id)
        if old_model == new_model:
            continue
        name = str((new_model or old_model or {}).get("name") or model_id).strip()
        changed.add(name or model_id)
    return changed


def _session_can_modify_service_config(session: dict | None, service_doc: dict, old_config: dict, new_config: dict) -> bool:
    if _session_is_service_permission_denied(session, service_doc, required_types={"SERVICE_ALL"}):
        return False

    changed_endpoints = _changed_endpoint_paths(old_config or {}, new_config or {})
    changed_models = _changed_model_names(old_config or {}, new_config or {})
    if not changed_endpoints and not changed_models:
        if _session_has_direct_service_access(session, service_doc):
            return True
        return _session_has_fine_grained_service_permission(session, service_doc, required_types={"SERVICE_ALL"})

    for endpoint in changed_endpoints:
        if _session_is_service_permission_denied(
            session,
            service_doc,
            required_types={"SERVICE_ENDPOINT"},
            endpoint=endpoint,
        ):
            return False
        if _session_has_direct_service_access(session, service_doc):
            continue
        if not _session_has_fine_grained_service_permission(
            session,
            service_doc,
            required_types={"SERVICE_ALL", "SERVICE_ENDPOINT"},
            endpoint=endpoint,
        ):
            return False

    for model in changed_models:
        if _session_is_service_permission_denied(
            session,
            service_doc,
            required_types={"SERVICE_MODEL"},
            model=model,
        ):
            return False
        if _session_has_direct_service_access(session, service_doc):
            continue
        if not _session_has_fine_grained_service_permission(
            session,
            service_doc,
            required_types={"SERVICE_ALL", "SERVICE_MODEL"},
            model=model,
        ):
            return False
    return True


def _filter_accessible_services(session: dict | None, services: list[dict]) -> list[dict]:
    if _role_from_session(session) == ROLE_ADMIN:
        return services
    return [svc for svc in services if _session_can_access_service(session, svc)]


def _grant_user_service_access(username: str, *service_keys: str) -> None:
    keys = [str(key or "").strip() for key in service_keys if str(key or "").strip()]
    if not keys:
        return
    data = _load_normalized_auth_data()
    target = _find_auth_user(data, username)
    if not target:
        return
    role = _normalize_platform_role(target.get("role"))
    if role == ROLE_ADMIN:
        target["service_access"] = [WILDCARD_SERVICE_ACCESS]
        _save_normalized_auth_data(data)
        return
    existing = _normalize_service_access(target.get("service_access"))
    for key in keys:
        if key not in existing:
            existing.append(key)
    target["service_access"] = existing
    _save_normalized_auth_data(data)


def _reconcile_service_runtime_states(app: Flask) -> list[dict] | None:
    app.config["LIWIRO_SERVICE_COUNT_HINT"] = 0
    if not getattr(app, "vdb_client", None):
        return None
    try:
        with app.app_context():
            _use_runtime_workspace()
            success, services = app.vdb_client.read_documents("services", {})
            if not success or not isinstance(services, list):
                return None
            synced_services = []
            for service in services:
                synced_services.append(_maybe_sync_service_state(service, persist=True))
            app.config["LIWIRO_SERVICE_COUNT_HINT"] = len(synced_services)
            return synced_services
    except Exception as exc:
        app.logger.warning(f"Service runtime reconciliation failed: {exc}")
    return None


def _update_service_state_in_store(process_id: str, updates: dict) -> None:
    try:
        _use_runtime_workspace()
        updated, update_result = current_app.vdb_client.update_document("services", _service_query(process_id), updates)
        if not updated:
            return jsonify({"error": (update_result or {}).get("error", "Failed to persist service update")}), 500
    except Exception:
        # Keep reads resilient even if persistence update fails.
        pass


def _maybe_sync_service_state(service_doc: dict, persist: bool = True) -> dict:
    service = dict(service_doc or {})
    before_status = str(service.get("status") or "").upper()
    before_port = service.get("port")
    synced = _sync_service_runtime_state(service)
    synced, env_changed = _sync_service_runtime_env(synced)
    after_status = str(synced.get("status") or "").upper()
    after_port = synced.get("port")
    if persist and (
        before_status != after_status
        or before_port != after_port
        or env_changed
    ):
        updates = {
            "status": after_status,
            "port": after_port,
        "updatedAt": _utcnow_iso(),
        }
        if env_changed:
            updates["lapis_config"] = synced.get("lapis_config")
        _update_service_state_in_store(str(synced.get("processId") or ""), updates)
    return synced


def _authorize_or_forbid(required: str):
    if not getattr(current_app, "vdb_client", None):
        ok, msg = _initialize_vdb_runtime(current_app)
        if not ok or not getattr(current_app, "vdb_client", None):
            return jsonify({"error": f"VDB runtime is not ready: {msg}"}), 503
    domain = _runtime_cfg("LIWIRO_DOMAIN")
    db = _runtime_cfg("LIWIRO_DB")
    if not current_app.vdb_client.async_authorize(required, domain, db):
        return jsonify({"error": "RBAC authorization failed"}), 403
    return None


def _initialize_services_collection(client: VDBClient):
    services_schema = {
        "apiName": {"type": "string", "required": True},
        "processId": {"type": "string", "required": True},
        "status": {"type": "string", "required": True},
        "port": {"type": "number", "required": True},
        "createdAt": {"type": "string", "required": True},
    }
    success, _ = client.create_collection("services", services_schema)
    return success


def _initialize_vdb_runtime(
    app: Flask,
    repair_admin_candidates: list[tuple[str, str, str]] | None = None,
):
    try:
        with app.app_context():
            ready, ready_msg = _ensure_vdb_transport_ready(
                app,
                app.config.get("VDB_TRANSPORT"),
                app.config.get("VDB_SERVER_URL"),
                app.config.get("VDB_UNIX_SOCKET_PATH"),
                app.config.get("VDB_NAMED_PIPE_PATH"),
            )
            if not ready:
                requested_runtime_transport = normalize_vdb_transport_mode(app.config.get("VDB_TRANSPORT"))
                runtime_server_candidate = str(app.config.get("VDB_SERVER_URL") or "").strip()
                if requested_runtime_transport in {"unixsocket", "namedpipe"} and is_local_vdb_url(runtime_server_candidate):
                    http_ready, http_message = _autostart_local_vdb_http_if_needed(app, runtime_server_candidate)
                    if http_ready:
                        app.config["VDB_TRANSPORT"] = "http"
                        ready = True
                        ready_msg = http_message
                    else:
                        ready_msg = f"{ready_msg}; HTTP fallback failed: {http_message}"
            if not ready:
                app.vdb_client = None
                _set_vdb_runtime_state(app, False, ready_msg)
                return False, ready_msg
            runtime_transport = normalize_vdb_transport_mode(app.config.get("VDB_TRANSPORT"))
            runtime_server_url = str(app.config.get("VDB_SERVER_URL") or "").strip()
            runtime_socket_path = str(app.config.get("VDB_UNIX_SOCKET_PATH") or "").strip()
            runtime_named_pipe_path = str(app.config.get("VDB_NAMED_PIPE_PATH") or "").strip()
            runtime_username = _normalize_username(app.config.get("VDB_USERNAME"))
            runtime_password = str(app.config.get("VDB_PASSWORD") or "").strip()
            runtime_domain = str(app.config.get("LIWIRO_DOMAIN") or Config.LIWIRO_DOMAIN).strip() or Config.LIWIRO_DOMAIN

            if not runtime_username or not runtime_password:
                app.vdb_client = None
                _set_vdb_runtime_state(app, False, "Saved VDB application credentials are missing.")
                return False, "Saved VDB application credentials are missing."

            verified, verify_msg = _verify_vdb_auth(
                runtime_server_url,
                runtime_username,
                runtime_password,
                transport_mode=runtime_transport,
                socket_path=runtime_socket_path,
                named_pipe_path=runtime_named_pipe_path,
            )
            # Settings can retain a Unix-socket selection after the VDB
            # runtime has been started on HTTP (the managed startup default).
            # Retry the local HTTP endpoint before treating a valid account as
            # invalid, then persist the working transport for subsequent boots.
            if (
                not verified
                and runtime_transport == "unixsocket"
                and runtime_server_url
                and is_local_vdb_url(runtime_server_url)
            ):
                http_ready, _ = _autostart_local_vdb_http_if_needed(app, runtime_server_url)
                if http_ready:
                    http_verified, http_msg = _verify_vdb_auth(
                        runtime_server_url,
                        runtime_username,
                        runtime_password,
                        transport_mode="http",
                        socket_path="",
                        named_pipe_path="",
                    )
                    if http_verified:
                        runtime_transport = "http"
                        app.config["VDB_TRANSPORT"] = "http"
                        _persist_runtime_vdb_env(
                            vdb_transport="http",
                            vdb_server_url=runtime_server_url,
                            vdb_unix_socket_path=runtime_socket_path,
                            vdb_named_pipe_path=runtime_named_pipe_path,
                            vdb_username=runtime_username,
                            vdb_password=runtime_password,
                            liwiro_domain=str(app.config.get("LIWIRO_DOMAIN") or Config.LIWIRO_DOMAIN),
                            liwiro_db=str(app.config.get("LIWIRO_DB") or Config.LIWIRO_DB),
                        )
                        verified, verify_msg = True, "Authenticated via HTTP fallback"
                    else:
                        verify_msg = http_msg or verify_msg
            if not verified:
                repaired, repair_msg = _repair_runtime_vdb_app_account(
                    vdb_server_url=runtime_server_url,
                    vdb_transport=runtime_transport,
                    vdb_unix_socket_path=runtime_socket_path,
                    vdb_named_pipe_path=runtime_named_pipe_path,
                    vdb_username=runtime_username,
                    vdb_password=runtime_password,
                    liwiro_domain=runtime_domain,
                    repair_admin_candidates=repair_admin_candidates,
                    initial_error=verify_msg,
                )
                if not repaired:
                    app.vdb_client = None
                    _set_vdb_runtime_state(app, False, repair_msg if repair_msg else verify_msg)
                    return False, repair_msg if repair_msg else verify_msg
            client = VDBClient(app)
            domain = app.config.get("LIWIRO_DOMAIN", Config.LIWIRO_DOMAIN)
            db = app.config.get("LIWIRO_DB", Config.LIWIRO_DB)
            if not client.ensure_workspace(domain, db):
                app.vdb_client = None
                detail = str(getattr(client, "workspace_error", "") or "").strip()
                message = f"Failed to prepare VDB workspace {domain}/{db}" + (f": {detail}" if detail else "")
                _set_vdb_runtime_state(app, False, message)
                return False, message
            if not _initialize_services_collection(client):
                app.logger.warning("Could not verify/create services collection")

            app.vdb_client = client
            if getattr(app, "process_manager", None) is None:
                app.process_manager = ProcessManager(app)
            else:
                app.process_manager.vdb_client = client
            context = client.get_context()
            if isinstance(context, dict):
                app.logger.info(
                    f"VDB runtime ready: {context.get('domain', domain)}/{context.get('database', db)} ({ready_msg})"
                )
            else:
                app.logger.info(f"VDB runtime ready: {domain}/{db} ({ready_msg})")
        _set_vdb_runtime_state(app, True, "")
        return True, "VDB runtime initialized"
    except Exception as exc:
        app.logger.warning(f"VDB runtime not ready: {exc}")
        app.vdb_client = None
        _set_vdb_runtime_state(app, False, str(exc))
        return False, str(exc)


def _set_vdb_runtime_state(app: Flask, ready: bool, error: str = "") -> None:
    app.vdb_runtime_ready = bool(ready)
    app.vdb_runtime_error = "" if ready else str(error or "").strip()


def _autostart_services_if_enabled(app: Flask, services: list[dict] | None = None) -> None:
    try:
        auth_data = _load_normalized_auth_data()
        settings = auth_data.get("settings") or {}
        if not bool(settings.get("startServicesOnStartup", False)):
            return
        if not getattr(app, "vdb_client", None):
            return

        with app.app_context():
            boot_services = services
            if boot_services is None:
                _use_runtime_workspace()
                success, boot_services = app.vdb_client.read_documents("services", {})
                if not success or not isinstance(boot_services, list):
                    return
            for service in boot_services:
                synced = _maybe_sync_service_state(service, persist=True)
                if str(synced.get("status") or "").upper() == "RUNNING":
                    continue
                lapis_config = synced.get("lapis_config")
                api_name = synced.get("apiName")
                if not isinstance(lapis_config, dict) or not api_name:
                    continue
                try:
                    new_pid, port = app.process_manager.start_api_service(lapis_config, api_name)
                    app.vdb_client.update_document(
                        "services",
                        _service_query(str(synced.get("processId") or "")),
                        {
                            "processId": str(new_pid),
                            "status": "RUNNING",
                            "port": port,
        "updatedAt": _utcnow_iso(),
                        },
                    )
                except Exception as exc:
                    app.logger.warning(f"Auto-start failed for {api_name}: {exc}")
    except Exception as exc:
        app.logger.warning(f"Auto-start settings check failed: {exc}")


def _ensure_vdb_user(
    vdb_server_url: str,
    admin_username: str,
    admin_password: str,
    username: str,
    password: str,
    domain: str,
    transport_mode: str | None = None,
    socket_path: str | None = None,
    named_pipe_path: str | None = None,
    repair_existing: bool = False,
):
    """Create user if missing. This is best-effort bootstrap for first-time setup."""
    try:
        transport = build_vdb_transport(
            current_app,
            server_url=vdb_server_url,
            socket_path=socket_path,
            named_pipe_path=named_pipe_path,
            transport_mode=transport_mode,
            prefer_socket=True,
            allow_http_fallback=True,
        )
        auth_json = transport.auth(admin_username, admin_password, timeout=15)
        session_id = auth_json.get("sessionId")
        if not session_id:
            return False, "Failed to obtain VDB session for bootstrap"

        def _vql(tumi_payload: dict):
            return transport.vql(session_id, tumi_payload, timeout=15)

        # Current VDB user bootstrap is handled through TUMI.
        create_payload = {
            "action": "tumi", "operation": "create",
            "username": username,
            "password": password,
            "email": f"{username}@local.com",
            "role": "APP",
        }
        try:
            body = _vql(create_payload)
        except VDBTransportRequestError as exc:
            text = str(exc.raw_body or exc).lower()
            if "already exists" in text or "duplicate" in text:
                if not repair_existing:
                    return True, "User already exists"
                try:
                    _vql({"action": "tumi", "operation": "delete", "username": username})
                    _vql(create_payload)
                    return True, "User repaired"
                except VDBTransportRequestError as inner_exc:
                    return False, f"VDB user repair failed: {inner_exc.raw_body or inner_exc}"
            return False, f"VDB createUser failed: {exc.raw_body or exc}"

        if isinstance(body, dict):
            status = str(body.get("status", "")).lower()
            if status == "error":
                msg = str(body.get("message", ""))
                if "already exists" in msg.lower() or "duplicate" in msg.lower():
                    if not repair_existing:
                        return True, "User already exists"
                    try:
                        delete_body = _vql({"action": "tumi", "operation": "delete", "username": username})
                        if str((delete_body or {}).get("status", "")).lower() == "error":
                            return False, f"VDB deleteUser failed during repair: {delete_body}"
                        recreate_body = _vql(create_payload)
                        if str((recreate_body or {}).get("status", "")).lower() == "error":
                            return False, f"VDB recreateUser failed during repair: {recreate_body}"
                        return True, "User repaired"
                    except VDBTransportRequestError as inner_exc:
                        return False, f"VDB user repair failed: {inner_exc.raw_body or inner_exc}"
                return False, f"VDB createUser failed: {msg or body}"

        return True, "User created"
    except Exception as exc:
        return False, str(exc)


def _verify_vdb_auth(
    vdb_server_url: str,
    username: str,
    password: str,
    transport_mode: str | None = None,
    socket_path: str | None = None,
    named_pipe_path: str | None = None,
):
    try:
        transport = build_vdb_transport(
            current_app,
            server_url=vdb_server_url,
            socket_path=socket_path,
            named_pipe_path=named_pipe_path,
            transport_mode=transport_mode,
            prefer_socket=True,
            allow_http_fallback=True,
        )
        last_error = "Invalid credentials"
        for candidate in _username_variants(username) or [username]:
            try:
                payload = transport.auth(candidate, password, timeout=15)
            except VDBTransportRequestError as exc:
                last_error = _summarize_vdb_auth_failure(
                    exc.payload if isinstance(exc.payload, dict) else (exc.raw_body or str(exc)),
                    candidate,
                )
                continue
            if payload.get("sessionId"):
                return True, "Authenticated"
            last_error = "VDB authentication succeeded but no session was returned."
        return False, last_error
    except Exception as exc:
        return False, str(exc)


def _collect_vdb_repair_admin_candidates(
    auth_data: dict | None = None,
    extra_candidates: list[tuple[str, str, str]] | None = None,
) -> list[tuple[str, str, str]]:
    candidates: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add_candidate(username: str | None, password: str | None, label: str) -> None:
        normalized_username = _normalize_username(username)
        normalized_password = str(password or "").strip()
        if not normalized_username or not normalized_password:
            return
        key = (normalized_username, normalized_password)
        if key in seen:
            return
        seen.add(key)
        candidates.append((normalized_username, normalized_password, label))

    for username, password, label in extra_candidates or []:
        add_candidate(username, password, label)

    auth_payload = auth_data if isinstance(auth_data, dict) else _load_normalized_auth_data()
    add_candidate(
        auth_payload.get("vdb_super_admin_username"),
        _runtime_cfg("VDB_SUPER_ADMIN_PASSWORD"),
        "saved VDB super admin credentials",
    )
    return candidates


def _repair_runtime_vdb_app_account(
    *,
    vdb_server_url: str,
    vdb_transport: str,
    vdb_unix_socket_path: str,
    vdb_named_pipe_path: str,
    vdb_username: str,
    vdb_password: str,
    liwiro_domain: str,
    repair_admin_candidates: list[tuple[str, str, str]] | None = None,
    initial_error: str = "",
) -> tuple[bool, str]:
    auth_data = _load_normalized_auth_data()
    candidates = _collect_vdb_repair_admin_candidates(auth_data, repair_admin_candidates)
    if not candidates:
        detail = str(initial_error or "").strip()
        suffix = f": {detail}" if detail else ""
        return False, f"Saved VDB app credentials for '{vdb_username}' could not be verified{suffix}"

    last_error = str(initial_error or "").strip() or f"Saved VDB app credentials for '{vdb_username}' are invalid."
    for admin_username, admin_password, label in candidates:
        admin_ok, admin_msg = _verify_vdb_auth(
            vdb_server_url,
            admin_username,
            admin_password,
            transport_mode=vdb_transport,
            socket_path=vdb_unix_socket_path,
            named_pipe_path=vdb_named_pipe_path,
        )
        if not admin_ok:
            last_error = admin_msg
            continue

        repaired_ok, repaired_msg = _ensure_vdb_user(
            vdb_server_url=vdb_server_url,
            admin_username=admin_username,
            admin_password=admin_password,
            username=vdb_username,
            password=vdb_password,
            domain=liwiro_domain,
            transport_mode=vdb_transport,
            socket_path=vdb_unix_socket_path,
            named_pipe_path=vdb_named_pipe_path,
            repair_existing=True,
        )
        if not repaired_ok:
            current_app.logger.warning(
                f"Failed to repair VDB app user '{vdb_username}' using {label}: {repaired_msg}"
            )
            last_error = f"Saved VDB app credentials for '{vdb_username}' are invalid and automatic repair failed."
            continue

        retry_ok, retry_msg = _verify_vdb_auth(
            vdb_server_url,
            vdb_username,
            vdb_password,
            transport_mode=vdb_transport,
            socket_path=vdb_unix_socket_path,
            named_pipe_path=vdb_named_pipe_path,
        )
        if retry_ok:
            current_app.logger.info(
                f"Repaired VDB app user '{vdb_username}' using {label}."
            )
            return True, "Authenticated"
        last_error = retry_msg

    return False, f"Saved VDB app credentials for '{vdb_username}' are invalid and automatic repair failed."


def _summarize_vdb_auth_failure(raw_error, username: str | None = None) -> str:
    payload = raw_error if isinstance(raw_error, dict) else {}
    message = ""
    if payload:
        message = str(payload.get("error") or payload.get("message") or "").strip()
    if not message:
        text = str(raw_error or "").strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    message = str(parsed.get("error") or parsed.get("message") or "").strip()
            except Exception:
                message = ""
        if not message:
            message = text

    lowered = message.lower()
    if "wrong password for vdb user" in lowered:
        if username:
            return f"Wrong password for VDB user '{username}'."
        return "Wrong VDB password."
    if "invalid credentials" in lowered:
        return "Invalid VDB username or password."
    if "unknown vdb user" in lowered or ("user" in lowered and "not found" in lowered):
        if username:
            return f"VDB user '{username}' was not found."
        return "VDB user was not found."
    if "no vdb users configured" in lowered:
        return "No VDB users are configured."
    if "no session id returned" in lowered:
        return "VDB authentication succeeded but no session was returned."
    return message or "VDB authentication failed."


def _build_bootstrap_vdb_auth_error(
    app_user: str,
    *,
    app_user_exists: bool,
    has_super_admin: bool,
    auth_error: str,
) -> str:
    auth_summary = _summarize_vdb_auth_failure(auth_error, app_user)
    if not app_user_exists and not has_super_admin:
        return (
            f"Liwiro application user '{app_user}' was not found in VDB. "
            "No VDB super admin is configured."
        )
    if not app_user_exists:
        return (
            f"Liwiro application user '{app_user}' was not found in VDB. "
            "The provided VDB super admin credentials were not accepted."
        )
    if not has_super_admin:
        return (
            "No VDB super admin is configured. "
            f"Liwiro application user '{app_user}' could not authenticate."
        )
    return f"Unable to authenticate Liwiro VDB app account '{app_user}': {auth_summary}"


def _prepare_documentation_key(lapis_config: dict, explicit_key: str | None = None, existing_hash: str | None = None) -> None:
    if not isinstance(lapis_config, dict):
        return

    metadata = lapis_config.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
        lapis_config["metadata"] = metadata

    documentation = metadata.setdefault("documentation", {})
    if not isinstance(documentation, dict):
        documentation = {}
        metadata["documentation"] = documentation

    provided_key = str(explicit_key or "").strip()
    inline_key = str(documentation.get("key") or "").strip()
    chosen_key = provided_key or inline_key
    current_hash = str(documentation.get("keyHash") or "").strip()
    fallback_hash = str(existing_hash or "").strip()

    if chosen_key:
        documentation["keyHash"] = generate_password_hash(chosen_key)
        documentation["key"] = chosen_key
    elif current_hash:
        documentation["keyHash"] = current_hash
    elif fallback_hash:
        documentation["keyHash"] = fallback_hash


def _resolve_verun_root() -> Path | None:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[4] / "verun",  # .../liwiro/verun
        here.parents[3] / "verun",  # .../liwiro/liwiro/verun (fallback)
    ]
    for candidate in candidates:
        if candidate.exists() and (candidate / "vdb").exists():
            return candidate
    return None


def _resolve_vdb_workdir() -> Path:
    """Return a writable cwd for VDB's relative logs and session files."""
    configured = str(os.getenv("LIWIRO_VDB_WORKDIR") or "").strip()
    if configured:
        workdir = Path(configured).expanduser()
    else:
        runtime_logs = str(os.getenv("LIWIRO_RUNTIME_LOG_DIR") or "").strip()
        if runtime_logs:
            workdir = Path(runtime_logs).expanduser() / "vdb-workdir"
        else:
            workdir = Path(tempfile.gettempdir()) / "liwiro" / "vdb-workdir"
    try:
        workdir.mkdir(parents=True, exist_ok=True)
        return workdir.resolve()
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "liwiro" / "vdb-workdir"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback.resolve()


def _cached_vdb_user_records(users_dir: Path) -> list[dict] | None:
    if not has_request_context():
        return None
    cache = getattr(g, "_liwiro_vdb_user_records", None)
    if not isinstance(cache, dict):
        cache = {}
        g._liwiro_vdb_user_records = cache
    try:
        cache_key = str(users_dir.resolve())
    except Exception:
        cache_key = str(users_dir)
    cached = cache.get(cache_key)
    return cached if isinstance(cached, list) else None


def _store_cached_vdb_user_records(users_dir: Path, records: list[dict]) -> list[dict]:
    if has_request_context():
        cache = getattr(g, "_liwiro_vdb_user_records", None)
        if not isinstance(cache, dict):
            cache = {}
            g._liwiro_vdb_user_records = cache
        try:
            cache_key = str(users_dir.resolve())
        except Exception:
            cache_key = str(users_dir)
        cache[cache_key] = records
    return records


def _vdb_has_any_user(verun_root: Path) -> bool:
    users_dir = verun_root / "vdb" / "__data__" / "sys" / "users"
    return len(_vdb_user_records(users_dir)) > 0


def _vdb_user_records(users_dir: Path) -> list[dict]:
    cached = _cached_vdb_user_records(users_dir)
    if cached is not None:
        return cached

    manifest = users_dir / "users.bson"
    records: list[dict] = []

    if manifest.exists():
        try:
            data = read_bson_value(manifest)
            if isinstance(data, list):
                records.extend(item for item in data if isinstance(item, dict))
        except (BsonDecodeError, Exception):
            pass

    if records:
        return _store_cached_vdb_user_records(users_dir, records)

    if not users_dir.exists():
        return _store_cached_vdb_user_records(users_dir, [])

    for path in sorted(users_dir.glob("*.bson")):
        if path.name == "users.bson":
            continue
        try:
            data = read_bson_value(path)
        except (BsonDecodeError, Exception):
            continue
        if isinstance(data, dict):
            records.append(data)
    return _store_cached_vdb_user_records(users_dir, records)


def _vdb_has_super_admin(verun_root: Path) -> bool:
    users_dir = verun_root / "vdb" / "__data__" / "sys" / "users"
    try:
        for user in _vdb_user_records(users_dir):
            if not isinstance(user, dict):
                continue
            role = str(user.get("role") or "").strip().upper().replace("-", "_")
            if role == "SUPER_ADMIN":
                return True
            try:
                if int(user.get("role_level", 0)) >= 100:
                    return True
            except Exception:
                pass
        return False
    except (BsonDecodeError, Exception):
        return False


def _vdb_usernames(verun_root: Path) -> list[str]:
    users_dir = verun_root / "vdb" / "__data__" / "sys" / "users"
    try:
        names = []
        for user in _vdb_user_records(users_dir):
            if isinstance(user, dict) and user.get("username"):
                names.append(str(user["username"]))
        return names
    except (BsonDecodeError, Exception):
        return []


def _vdb_has_user(verun_root: Path, username: str) -> bool:
    target = str(username or "").strip()
    if not target:
        return False
    target_norm = target.lower()
    return any(str(name).strip().lower() == target_norm for name in _vdb_usernames(verun_root))


def _resolve_vi_jar_path(verun_root: Path | None = None) -> Path | None:
    root = verun_root or _resolve_verun_root()
    if not root:
        return None
    return root / "vi" / "target" / "vi-1.0.0-jar-with-dependencies.jar"


def _default_vi_portal_source_dir() -> Path:
    return (Path(__file__).resolve().parents[2] / "vi_portal_sources").resolve()


def _normalize_vi_portal_source_dir(path_value: str) -> Path:
    raw = str(path_value or "").strip()
    if not raw:
        raise ValueError("Source directory is required")
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = (Path(__file__).resolve().parents[2] / candidate).resolve()
    else:
        candidate = candidate.resolve()
    if candidate.exists() and not candidate.is_dir():
        raise ValueError("Source directory must be a folder")
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def _resolve_vi_portal_source_dir() -> Path:
    auth_data = _load_normalized_auth_data()
    configured = str(_runtime_cfg("VI_PORTAL_SOURCE_DIR") or auth_data.get("vi_portal_source_dir") or "").strip()
    try:
        source_dir = _normalize_vi_portal_source_dir(configured) if configured else _default_vi_portal_source_dir()
    except ValueError:
        source_dir = _default_vi_portal_source_dir()
    source_dir.mkdir(parents=True, exist_ok=True)
    return source_dir


def _vi_workspace_env_path(source_dir: Path | None = None) -> Path:
    root = source_dir if isinstance(source_dir, Path) else _resolve_vi_portal_source_dir()
    return root / ".env"


def _strip_env_quotes(value: str) -> str:
    text = str(value or "").strip()
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]
    return text


def _parse_env_file_text(env_text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_line in str(env_text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        normalized_key = str(key or "").strip().upper()
        if not normalized_key or not re.fullmatch(r"[A-Z_][A-Z0-9_]*", normalized_key):
            continue
        parsed[normalized_key] = _strip_env_quotes(value)
    return parsed


def _read_vi_workspace_env_text(source_dir: Path | None = None) -> str:
    env_path = _vi_workspace_env_path(source_dir)
    try:
        return env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    except Exception:
        return ""


def _write_vi_workspace_env_text(env_text: str, source_dir: Path | None = None) -> str:
    env_path = _vi_workspace_env_path(source_dir)
    env_path.parent.mkdir(parents=True, exist_ok=True)
    normalized = str(env_text or "").rstrip()
    env_path.write_text(f"{normalized}\n" if normalized else "", encoding="utf-8")
    return str(env_path)


def _path_within_root(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _vi_portal_directory_roots() -> list[dict]:
    project_root = Path(__file__).resolve().parents[2].resolve()
    source_dir = _resolve_vi_portal_source_dir()
    roots: list[dict] = []
    seen: set[str] = set()

    for label, candidate in [
        ("Configured source", source_dir),
        ("Project root", project_root),
        ("Home", Path.home()),
    ]:
        try:
            resolved = candidate.expanduser().resolve()
        except Exception:
            continue
        if not resolved.exists() or not resolved.is_dir():
            continue
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        roots.append({"label": label, "path": key})

    return roots


def _resolve_vi_portal_directory_path(path_value: str) -> Path:
    raw = str(path_value or "").strip()
    if raw:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = (Path(__file__).resolve().parents[2] / candidate).resolve()
        else:
            candidate = candidate.resolve()
    else:
        candidate = _resolve_vi_portal_source_dir()

    if not candidate.exists():
        raise ValueError("Directory does not exist")
    if not candidate.is_dir():
        raise ValueError("Directory must be a folder")

    allowed_roots = [Path(entry["path"]) for entry in _vi_portal_directory_roots()]
    if not any(candidate == root or _path_within_root(candidate, root) for root in allowed_roots):
        raise ValueError("Directory is outside the allowed browse roots")

    return candidate


def _vi_portal_directory_listing(path_value: str) -> dict:
    target_dir = _resolve_vi_portal_directory_path(path_value)
    directories: list[dict] = []
    try:
        for child in sorted(target_dir.iterdir(), key=lambda item: item.name.lower()):
            if not child.is_dir():
                continue
            directories.append({"name": child.name, "path": str(child.resolve())})
    except PermissionError as exc:
        raise ValueError(f"Unable to read directory: {exc}") from exc

    roots = _vi_portal_directory_roots()
    parent_dir = target_dir.parent.resolve() if target_dir.parent != target_dir else None
    parent_path = ""
    if parent_dir and any(parent_dir == Path(entry["path"]) or _path_within_root(parent_dir, Path(entry["path"])) for entry in roots):
        parent_path = str(parent_dir)

    return {
        "path": str(target_dir),
        "name": target_dir.name or str(target_dir),
        "parent": parent_path,
        "directories": directories,
        "roots": roots,
        "source_dir": str(_resolve_vi_portal_source_dir()),
    }


def _normalize_vi_portal_relpath(path_value: str) -> str:
    candidate = Path(str(path_value or "").strip().replace("\\", "/"))
    if not str(candidate):
        raise ValueError("File path is required")
    if candidate.is_absolute():
        raise ValueError("Absolute paths are not allowed")
    parts = [part for part in candidate.parts if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        raise ValueError("Invalid file path")
    normalized = Path(*parts)
    if not normalized.suffix:
        normalized = normalized.with_suffix(".versa")
    if normalized.suffix.lower() != ".versa":
        raise ValueError("Only .versa files are supported")
    return normalized.as_posix()


def _resolve_vi_portal_file_path(path_value: str, create_parent: bool = False) -> tuple[Path, str]:
    source_dir = _resolve_vi_portal_source_dir()
    relative_path = _normalize_vi_portal_relpath(path_value)
    file_path = (source_dir / relative_path).resolve()
    file_path.relative_to(source_dir)
    if create_parent:
        file_path.parent.mkdir(parents=True, exist_ok=True)
    return file_path, relative_path


def _vi_portal_file_metadata(file_path: Path, source_dir: Path | None = None, *, file_stat: os.stat_result | None = None) -> dict:
    root = source_dir or _resolve_vi_portal_source_dir()
    stat_result = file_stat if file_stat is not None else file_path.stat()
    return {
        "path": file_path.relative_to(root).as_posix(),
        "name": file_path.name,
        "extension": file_path.suffix.lower(),
        "size": int(stat_result.st_size),
        "modifiedAt": datetime.fromtimestamp(stat_result.st_mtime, timezone.utc).isoformat(),
    }


def _iter_vi_portal_source_files(source_dir: Path | None = None):
    root = source_dir or _resolve_vi_portal_source_dir()
    for file_path in sorted(root.rglob("*")):
        try:
            file_stat = file_path.stat()
        except OSError:
            continue
        if not stat.S_ISREG(file_stat.st_mode) or file_path.suffix.lower() != ".versa":
            continue
        yield file_path, file_stat


def _count_vi_portal_files(source_dir: Path | None = None) -> int:
    return sum(1 for _file_path, _file_stat in _iter_vi_portal_source_files(source_dir))


def _list_vi_portal_files() -> list[dict]:
    source_dir = _resolve_vi_portal_source_dir()
    return [
        _vi_portal_file_metadata(file_path, source_dir, file_stat=file_stat)
        for file_path, file_stat in _iter_vi_portal_source_files(source_dir)
    ]


def _resolve_vi_portal_existing_file(path_value: str, allow_basename_match: bool = False) -> tuple[Path, str]:
    file_path, relative_path = _resolve_vi_portal_file_path(path_value)
    if not file_path.exists() or not file_path.is_file():
        if not allow_basename_match:
            raise FileNotFoundError(relative_path)
        raw_value = str(path_value or "").strip().replace("\\", "/")
        if not raw_value:
            raise FileNotFoundError(relative_path)
        raw_path = Path(raw_value)
        lookup_names = {raw_value, raw_path.name}
        if not raw_path.suffix:
            lookup_names.update(
                {
                    f"{raw_value}.versa",
                    f"{raw_path.name}.versa",
                }
            )

        source_dir = _resolve_vi_portal_source_dir()
        matches: dict[str, tuple[Path, str]] = {}
        for candidate in sorted(source_dir.rglob("*")):
            if not candidate.is_file() or candidate.suffix.lower() != ".versa":
                continue
            candidate_rel = candidate.relative_to(source_dir).as_posix()
            if candidate_rel in lookup_names or candidate.name in lookup_names:
                matches[candidate_rel] = (candidate, candidate_rel)
                continue
            if any("/" not in name and candidate_rel.endswith(f"/{name}") for name in lookup_names):
                matches[candidate_rel] = (candidate, candidate_rel)
        if not matches:
            raise FileNotFoundError(relative_path)
        if len(matches) > 1:
            raise ValueError(f"Multiple VI files match: {raw_value}")
        return next(iter(matches.values()))
    return file_path, relative_path


def _read_vi_portal_file(path_value: str, allow_basename_match: bool = False) -> dict:
    file_path, relative_path = _resolve_vi_portal_existing_file(path_value, allow_basename_match=allow_basename_match)
    return {
        **_vi_portal_file_metadata(file_path),
        "content": file_path.read_text(encoding="utf-8"),
    }


def _write_vi_portal_file(path_value: str, content: str) -> dict:
    file_path, _ = _resolve_vi_portal_file_path(path_value, create_parent=True)
    file_path.write_text(str(content or ""), encoding="utf-8")
    return _read_vi_portal_file(path_value)


def _delete_vi_portal_file(path_value: str) -> str:
    file_path, relative_path = _resolve_vi_portal_existing_file(path_value)
    file_path.unlink()
    return relative_path


def _preferred_vi_module_domain(session: dict | None = None) -> str:
    session = session if isinstance(session, dict) else _current_vi_request_session()
    username = _normalize_username((session or {}).get("username"))
    portal_session = _latest_vdb_portal_session_for_user(username)
    if portal_session:
        context_ok, context_result = _vdb_portal_query(portal_session, {"action": "context"})
        if context_ok and isinstance(context_result, dict):
            context_data = context_result.get("data") if isinstance(context_result.get("data"), dict) else context_result
            domain_name = str((context_data or {}).get("domain") or "").strip().lower()
            if domain_name:
                return domain_name
    accessible = _session_accessible_domains(session)
    if accessible:
        return accessible[0]
    return str(current_app.config.get("LIWIRO_DOMAIN") or Config.LIWIRO_DOMAIN or "").strip().lower()


def _vi_runtime_env(
    extra: dict | None = None,
    session_context: dict | None = None,
    preferred_domain: str | None = None,
) -> dict:
    env = dict(os.environ)
    env.update(_parse_env_file_text(_read_vi_workspace_env_text()))
    env["VI_CUSTOM_MODULES_DIR"] = str(current_app.config.get("VI_CUSTOM_MODULES_DIR") or getattr(Config, "VI_CUSTOM_MODULES_DIR", "") or "")
    resolved_domain = str(preferred_domain or "").strip().lower()
    if not resolved_domain:
        try:
            resolved_domain = _preferred_vi_module_domain(session_context)
        except RuntimeError as exc:
            if "Working outside of request context" not in str(exc):
                raise
            resolved_domain = str(current_app.config.get("LIWIRO_DOMAIN") or Config.LIWIRO_DOMAIN or "").strip().lower()
    if resolved_domain:
        env["LIWIRO_VI_MODULE_DOMAIN"] = resolved_domain
    if isinstance(extra, dict):
        for key, value in extra.items():
            env[str(key)] = str(value)
    return env


def _run_vi_portal_file(path_value: str) -> tuple[bool, dict]:
    verun_root = _resolve_verun_root()
    vi_jar = _resolve_vi_jar_path(verun_root)
    if not verun_root or not vi_jar or not vi_jar.is_file():
        return False, {
            "error": f"VI runtime jar missing at {vi_jar}" if vi_jar else "Unable to resolve Verun VI runtime",
            "hint": "Build it with: mvn -pl vi -am -DskipTests package",
        }

    file_payload = _read_vi_portal_file(path_value, allow_basename_match=True)
    file_path, relative_path = _resolve_vi_portal_existing_file(path_value, allow_basename_match=True)
    try:
        proc = subprocess.run(
            ["java", "-jar", str(vi_jar), str(file_path), "--msg-only"],
            cwd=file_path.parent,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
            env=_vi_runtime_env(session_context=_current_vi_request_session()),
        )
        payload = {
            "path": relative_path,
            "exitCode": proc.returncode,
            "stdout": str(proc.stdout or "").strip(),
            "stderr": str(proc.stderr or "").strip(),
            "file": file_payload,
        }
        if proc.returncode != 0:
            return False, {**payload, "error": payload["stderr"] or payload["stdout"] or "VI execution failed"}
        return True, payload
    except subprocess.TimeoutExpired:
        return False, {"error": "VI execution timed out", "path": relative_path}
    except Exception as exc:
        return False, {"error": f"VI execution failed: {exc}", "path": relative_path}


def _create_vi_ephemeral_script(path_value: str, source: str) -> tuple[Path, str, list[Path]]:
    requested_path = str(path_value or "").strip() or "scratch/unsaved.versa"
    try:
        hinted_path, relative_path = _resolve_vi_portal_file_path(requested_path, create_parent=True)
    except ValueError:
        hinted_path, relative_path = _resolve_vi_portal_file_path("scratch/unsaved.versa", create_parent=True)

    suffix = hinted_path.suffix.lower()
    if suffix != ".versa":
        suffix = ".versa"
    stem = hinted_path.stem or "unsaved"
    temp_path = hinted_path.with_name(f".liwiro-ephemeral-{stem}-{secrets.token_hex(6)}{suffix}")
    temp_path.write_text(str(source or ""), encoding="utf-8")
    return temp_path, relative_path, [temp_path]


def _set_nonblocking(stream) -> None:
    if stream is None or fcntl is None:
        return
    flags = fcntl.fcntl(stream.fileno(), fcntl.F_GETFL)
    fcntl.fcntl(stream.fileno(), fcntl.F_SETFL, flags | os.O_NONBLOCK)


def _set_fd_nonblocking(fd: int | None) -> None:
    if fd is None:
        return
    try:
        os.set_blocking(fd, False)
        return
    except AttributeError:
        pass
    if fcntl is None:
        return
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)


def _normalize_vi_terminal_size(cols: int | None = None, rows: int | None = None) -> tuple[int, int]:
    try:
        normalized_cols = int(cols if cols is not None else VI_TERMINAL_DEFAULT_COLS)
    except (TypeError, ValueError):
        normalized_cols = VI_TERMINAL_DEFAULT_COLS
    try:
        normalized_rows = int(rows if rows is not None else VI_TERMINAL_DEFAULT_ROWS)
    except (TypeError, ValueError):
        normalized_rows = VI_TERMINAL_DEFAULT_ROWS
    normalized_cols = min(max(normalized_cols, 40), 240)
    normalized_rows = min(max(normalized_rows, 12), 120)
    return normalized_cols, normalized_rows


def _set_vi_terminal_winsize(fd: int | None, cols: int, rows: int) -> None:
    return


def _detect_vi_terminal_prompt(text: str, fallback: str | None = None) -> str:
    sample = str(text or "")
    if sample.endswith(VI_REPL_CONTINUATION_PROMPT):
        return VI_REPL_CONTINUATION_PROMPT
    if sample.endswith(VI_REPL_PRIMARY_PROMPT):
        return VI_REPL_PRIMARY_PROMPT
    return str(fallback or VI_REPL_PRIMARY_PROMPT)


def _append_vi_terminal_output(session: dict, data) -> None:
    if isinstance(data, bytes):
        text = data.decode("utf-8", errors="replace")
    else:
        text = str(data or "")
    if not text:
        return
    lock = session.get("lock")
    if lock is None:
        return
    with lock:
        current_buffer = str(session.get("buffer") or "")
        next_buffer = (current_buffer + text)[-VI_TERMINAL_BUFFER_LIMIT:]
        next_seq = int(session.get("next_seq") or 1)
        chunks = session.get("chunks")
        if chunks is None:
            chunks = deque(maxlen=VI_TERMINAL_CHUNK_LIMIT)
            session["chunks"] = chunks
        chunks.append((next_seq, text))
        session["next_seq"] = next_seq + 1
        session["buffer"] = next_buffer
        session["prompt"] = _detect_vi_terminal_prompt(next_buffer[-16:], session.get("prompt"))
        session["updatedAt"] = _utcnow_iso()


def _vi_terminal_snapshot(session: dict) -> tuple[str, int, str]:
    lock = session.get("lock")
    if lock is None:
        return "", 0, str(session.get("prompt") or VI_REPL_PRIMARY_PROMPT)
    with lock:
        buffer_text = str(session.get("buffer") or "")
        last_seq = max(0, int(session.get("next_seq") or 1) - 1)
        prompt = str(session.get("prompt") or VI_REPL_PRIMARY_PROMPT)
    return buffer_text, last_seq, prompt


def _pending_vi_terminal_chunks(session: dict, last_seq: int) -> list[tuple[int, str]]:
    lock = session.get("lock")
    if lock is None:
        return []
    with lock:
        chunks = list(session.get("chunks") or [])
    return [(seq, chunk) for seq, chunk in chunks if seq > last_seq]


def _vi_terminal_sessions_guard():
    lock = getattr(current_app, "vi_terminal_sessions_lock", None)
    if lock is None:
        lock = threading.RLock()
        current_app.vi_terminal_sessions_lock = lock
    return lock


def _close_vi_terminal_fds(session: dict) -> None:
    for key in ("master_fd", "slave_fd"):
        fd = session.get(key)
        if fd is None:
            continue
        try:
            os.close(fd)
        except OSError:
            pass
        session[key] = None
    proc = session.get("process")
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(proc, stream_name, None) if proc is not None else None
        if stream is None:
            continue
        try:
            stream.close()
        except Exception:
            pass


def _cleanup_vi_terminal_artifacts(session: dict) -> None:
    lock = session.get("lock")
    if lock is not None:
        with lock:
            raw_paths = list(session.get("cleanupPaths") or [])
            session["cleanupPaths"] = []
    else:
        raw_paths = list(session.get("cleanupPaths") or [])
        session["cleanupPaths"] = []

    for raw_path in raw_paths:
        try:
            cleanup_path = Path(str(raw_path))
        except Exception:
            continue
        try:
            cleanup_path.unlink(missing_ok=True)
        except TypeError:
            try:
                if cleanup_path.exists():
                    cleanup_path.unlink()
            except OSError:
                pass
        except OSError:
            pass


def _flush_vi_terminal_buffers(session: dict, *, flush_input: bool = True, flush_output: bool = True) -> None:
    return


def _terminate_vi_terminal_process(session: dict) -> None:
    proc = session.get("process")
    if proc is None:
        return
    try:
        if proc.poll() is None:
            try:
                if str(session.get("mode") or "repl") == "repl" and proc.stdin is not None:
                    proc.stdin.write(b"exit\n")
                    proc.stdin.flush()
            except Exception:
                pass
            try:
                proc.terminate()
                proc.wait(timeout=1.5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=0.5)
                except Exception:
                    pass
    except Exception:
        pass
    _close_vi_terminal_fds({"process": proc})
    session["process"] = None


def _launch_vi_terminal_process(
    session: dict,
    command: list[str],
    cwd: Path,
    mode: str,
    prompt: str | None = None,
    restart_repl_on_exit: bool = False,
) -> tuple[bool, subprocess.Popen | dict]:
    try:
        popen_kwargs = {
            "cwd": cwd,
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": False,
            "bufsize": 0,
            "env": _vi_runtime_env(
                session_context=session.get("auth_session"),
                preferred_domain=session.get("preferred_module_domain"),
            ),
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            popen_kwargs["start_new_session"] = True
        proc = subprocess.Popen(
            command,
            **popen_kwargs,
        )
    except Exception as exc:
        return False, {"error": f"Failed to start VI terminal process: {exc}"}

    lock = session.get("lock")
    if lock is None:
        return False, {"error": "VI terminal session is not available"}
    with lock:
        session["process"] = proc
        session["mode"] = str(mode or "repl").strip().lower() or "repl"
        session["prompt"] = str(prompt if prompt is not None else (VI_REPL_PRIMARY_PROMPT if session["mode"] == "repl" else ""))
        session["cwd"] = str(cwd)
        session["restart_repl_on_exit"] = bool(restart_repl_on_exit)
        session["switchingProcess"] = False
        session["active"] = True
        session["exitCode"] = None
        session["exitNotified"] = False
        session["updatedAt"] = _utcnow_iso()
    return True, proc


def _wait_for_vi_terminal_activity(session: dict, proc: subprocess.Popen, timeout_seconds: float = 0.25) -> None:
    deadline = time.time() + max(timeout_seconds, 0.1)
    while time.time() < deadline:
        buffer_text, _, prompt = _vi_terminal_snapshot(session)
        if buffer_text or prompt != VI_REPL_PRIMARY_PROMPT or proc.poll() is not None:
            break
        time.sleep(0.02)


def _start_vi_terminal_repl_process(session: dict) -> tuple[bool, subprocess.Popen | dict]:
    verun_root = _resolve_verun_root()
    vi_jar = _resolve_vi_jar_path(verun_root)
    source_dir = _resolve_vi_portal_source_dir()
    if not verun_root or not vi_jar or not vi_jar.is_file():
        return False, {
            "error": f"VI runtime jar missing at {vi_jar}" if vi_jar else "Unable to resolve Verun VI runtime",
            "hint": "Build it with: mvn -pl vi -am -DskipTests package",
        }
    _flush_vi_terminal_buffers(session)
    return _launch_vi_terminal_process(
        session,
        ["java", "-jar", str(vi_jar)],
        cwd=source_dir,
        mode="repl",
        prompt=VI_REPL_PRIMARY_PROMPT,
        restart_repl_on_exit=False,
    )


def _mark_vi_terminal_session_inactive(
    session: dict,
    return_code: int | None = None,
    *,
    exit_message: str | None = None,
) -> None:
    lock = session.get("lock")
    if lock is None:
        return
    with lock:
        session["process"] = None
        session["switchingProcess"] = False
        session["active"] = False
        session["exitCode"] = return_code
        session["updatedAt"] = _utcnow_iso()
        should_append_exit = bool(return_code is not None and not session.get("exitNotified") and not exit_message)
        should_append_custom = bool(exit_message and not session.get("exitNotified"))
        if should_append_exit or should_append_custom:
            session["exitNotified"] = True
    _cleanup_vi_terminal_artifacts(session)
    if exit_message and should_append_custom:
        _append_vi_terminal_output(session, exit_message)
    elif should_append_exit:
        _append_vi_terminal_output(session, f"\r\n[VI terminal exited with code {return_code}]\r\n")


def _vi_terminal_switch_in_progress(session: dict, stale_after_seconds: float = 2.0) -> bool:
    if not bool(session.get("switchingProcess")) or bool(session.get("restart_repl_on_exit")):
        return False
    updated_at = str(session.get("updatedAt") or "").strip()
    if not updated_at:
        return True
    try:
        updated_dt = datetime.fromisoformat(updated_at)
    except ValueError:
        return True
    return (_utcnow() - updated_dt).total_seconds() < max(0.1, float(stale_after_seconds or 0))


def _reconcile_vi_terminal_session(session_key: str, session: dict | None, *, wait_timeout: float = 0.25) -> dict | None:
    if not isinstance(session, dict):
        return session

    proc = session.get("process")
    if proc is not None and proc.poll() is None:
        _ensure_vi_terminal_reader(session_key, session)
        return session

    if _vi_terminal_switch_in_progress(session):
        return session

    return_code = proc.poll() if proc is not None else session.get("exitCode")
    mode = str(session.get("mode") or "repl").strip().lower() or "repl"
    lock = session.get("lock")
    should_restart_repl = False
    if lock is not None:
        with lock:
            live_proc = session.get("process")
            if live_proc is not None and live_proc.poll() is None:
                proc = live_proc
            elif mode == "file" and bool(session.get("restart_repl_on_exit")):
                session["restart_repl_on_exit"] = False
                session["switchingProcess"] = True
                session["exitCode"] = return_code
                session["updatedAt"] = _utcnow_iso()
                should_restart_repl = True

    if proc is not None and proc.poll() is None:
        _ensure_vi_terminal_reader(session_key, session)
        return session

    if should_restart_repl:
        _cleanup_vi_terminal_artifacts(session)
        ok, next_proc = _start_vi_terminal_repl_process(session)
        if ok:
            _ensure_vi_terminal_reader(session_key, session)
            _wait_for_vi_terminal_activity(session, next_proc, timeout_seconds=wait_timeout)
            return session
        _mark_vi_terminal_session_inactive(
            session,
            return_code,
            exit_message=f"\r\n[VI terminal failed to return to REPL: {str((next_proc or {}).get('error') or 'unknown error')}]\r\n",
        )
        return session

    _mark_vi_terminal_session_inactive(session, return_code)
    return session


def _vi_terminal_session_metadata(session_key: str, session: dict | None) -> dict:
    session = _reconcile_vi_terminal_session(session_key, session)
    session_data = dict(session or {})
    proc = session_data.get("process")
    switching_process = bool(session_data.get("switchingProcess"))
    restarting_after_file = bool(
        str(session_data.get("mode") or "repl") == "file" and session_data.get("restart_repl_on_exit")
    )
    active = bool(
        session_data.get("active", True)
        and (switching_process or restarting_after_file or (proc and proc.poll() is None))
    )
    cols = int(session_data.get("cols") or VI_TERMINAL_DEFAULT_COLS)
    rows = int(session_data.get("rows") or VI_TERMINAL_DEFAULT_ROWS)
    buffer_text, last_seq, prompt = _vi_terminal_snapshot(session_data) if session_data else ("", 0, VI_REPL_PRIMARY_PROMPT)
    return {
        "sessionKey": session_key,
        "active": active,
        "prompt": prompt,
        "cols": cols,
        "rows": rows,
        "createdAt": str(session_data.get("createdAt") or ""),
        "updatedAt": str(session_data.get("updatedAt") or ""),
        "sourceDir": str(_resolve_vi_portal_source_dir()),
        "mode": str(session_data.get("mode") or "repl"),
        "cwd": str(session_data.get("cwd") or _resolve_vi_portal_source_dir()),
        "bufferLength": len(buffer_text),
        "lastSeq": last_seq,
        "exitCode": session_data.get("exitCode"),
        "switchingProcess": switching_process,
    }


def _vi_terminal_reader_loop(app: Flask, session_key: str) -> None:
    tracked_process: subprocess.Popen | None = None
    stream_readers: list[threading.Thread] = []

    def _read_stream(proc: subprocess.Popen, stream_name: str) -> None:
        stream = getattr(proc, stream_name, None)
        if stream is None:
            return
        while True:
            try:
                raw = stream.read(4096)
            except Exception:
                raw = b""
            if not raw:
                return
            with app.app_context():
                live_session = getattr(app, "vi_terminal_sessions", {}).get(session_key)
                if not live_session or live_session.get("process") is not proc:
                    return
                _append_vi_terminal_output(live_session, raw)

    while True:
        with app.app_context():
            sessions = getattr(app, "vi_terminal_sessions", {})
            session = sessions.get(session_key)
        if not session:
            return

        proc = session.get("process")
        if proc is None:
            if not bool(session.get("switchingProcess")) and not bool(session.get("active", True)):
                return
            time.sleep(0.01)
            continue

        if proc is not tracked_process:
            tracked_process = proc
            stream_readers = []
            for stream_name in ("stdout", "stderr"):
                stream = getattr(proc, stream_name, None)
                if stream is None:
                    continue
                reader = threading.Thread(
                    target=_read_stream,
                    args=(proc, stream_name),
                    daemon=True,
                    name=f"vi-terminal-{session_key}-{stream_name}",
                )
                stream_readers.append(reader)
                reader.start()

        return_code = proc.poll()
        if return_code is None:
            time.sleep(0.01)
            continue

        for reader in list(stream_readers):
            reader.join(timeout=0.1)
        with app.app_context():
            live_session = getattr(app, "vi_terminal_sessions", {}).get(session_key)
            if not live_session:
                return
            if live_session.get("process") is not proc:
                continue
            if bool(live_session.get("switchingProcess")):
                time.sleep(0.01)
                continue
            if str(live_session.get("mode") or "repl") == "file" and bool(live_session.get("restart_repl_on_exit")):
                live_session["restart_repl_on_exit"] = False
                live_session["exitCode"] = return_code
                live_session["switchingProcess"] = True
                live_session["updatedAt"] = _utcnow_iso()
                _cleanup_vi_terminal_artifacts(live_session)
                ok, next_proc = _start_vi_terminal_repl_process(live_session)
                if ok:
                    _wait_for_vi_terminal_activity(live_session, next_proc)
                    continue
                _mark_vi_terminal_session_inactive(
                    live_session,
                    return_code,
                    exit_message=f"\r\n[VI terminal failed to return to REPL: {str((next_proc or {}).get('error') or 'unknown error')}]\r\n",
                )
                return
            _mark_vi_terminal_session_inactive(live_session, return_code)
        return


def _vi_terminal_session_key() -> str:
    return _vi_repl_session_key()


def _ensure_vi_terminal_reader(session_key: str, session: dict) -> None:
    reader = session.get("reader")
    if isinstance(reader, threading.Thread) and reader.is_alive():
        return
    reader = threading.Thread(
        target=_vi_terminal_reader_loop,
        args=(current_app._get_current_object(), session_key),
        daemon=True,
        name=f"vi-terminal-{session_key}",
    )
    session["reader"] = reader
    reader.start()


def _vi_terminal_poll_payload(session_key: str, session: dict | None, last_seq: int = 0) -> dict:
    normalized_last_seq = max(0, int(last_seq or 0))
    metadata = _vi_terminal_session_metadata(session_key, session)
    if not isinstance(session, dict):
        return {
            **metadata,
            "chunks": [],
            "reset": normalized_last_seq <= 0,
            "lastSeq": 0,
            "degraded": True,
            "retryAfterMs": VI_TERMINAL_DEGRADED_RETRY_MS,
            "reason": "VI terminal session is not active",
        }

    buffer_text, current_last_seq, _ = _vi_terminal_snapshot(session)
    lock = session.get("lock")
    chunk_rows: list[tuple[int, str]] = []
    earliest_seq = current_last_seq + 1
    if lock is not None:
        with lock:
            chunk_rows = list(session.get("chunks") or [])
    else:
        chunk_rows = list(session.get("chunks") or [])
    if chunk_rows:
        earliest_seq = int(chunk_rows[0][0])

    reset_required = normalized_last_seq <= 0 or (chunk_rows and normalized_last_seq < earliest_seq - 1)
    if reset_required:
        chunks = [{"seq": current_last_seq, "data": buffer_text}] if buffer_text else []
    else:
        chunks = [{"seq": seq, "data": chunk} for seq, chunk in chunk_rows if seq > normalized_last_seq]

    payload = {
        **metadata,
        "chunks": chunks,
        "reset": reset_required,
        "lastSeq": current_last_seq,
    }
    if not bool(metadata.get("active")):
        payload["degraded"] = True
        payload["retryAfterMs"] = VI_TERMINAL_DEGRADED_RETRY_MS
        payload["reason"] = "VI terminal session is not active"
    else:
        payload["degraded"] = False
        payload["retryAfterMs"] = 0
        payload["reason"] = ""
    return payload


def _resize_vi_terminal_session(session_key: str, cols: int | None = None, rows: int | None = None) -> tuple[bool, dict]:
    sessions = getattr(current_app, "vi_terminal_sessions", {})
    session = sessions.get(session_key)
    if not session:
        return False, {"error": "VI terminal session is not active"}
    normalized_cols, normalized_rows = _normalize_vi_terminal_size(cols, rows)
    lock = session.get("lock")
    if lock is None:
        return False, {"error": "VI terminal session is not available"}
    with lock:
        session["cols"] = normalized_cols
        session["rows"] = normalized_rows
        session["updatedAt"] = _utcnow_iso()
    return True, _vi_terminal_session_metadata(session_key, session)


def _terminate_vi_terminal_session(session_key: str) -> None:
    with _vi_terminal_sessions_guard():
        sessions = getattr(current_app, "vi_terminal_sessions", {})
        session = sessions.pop(session_key, None)
        current_app.vi_terminal_sessions = sessions
    if not isinstance(session, dict):
        return
    _terminate_vi_terminal_process(session)
    _cleanup_vi_terminal_artifacts(session)
    _close_vi_terminal_fds(session)


def _ensure_vi_terminal_session(cols: int | None = None, rows: int | None = None) -> tuple[bool, dict]:
    auth_session = _current_vi_request_session() or {}
    preferred_module_domain = _preferred_vi_module_domain(auth_session)
    session_key = _vi_terminal_session_key()
    normalized_cols, normalized_rows = _normalize_vi_terminal_size(cols, rows)
    terminal_session: dict | None = None
    proc: subprocess.Popen | None = None
    start_error: dict | None = None
    startup_failed = False

    with _vi_terminal_sessions_guard():
        sessions = getattr(current_app, "vi_terminal_sessions", {})
        existing = sessions.get(session_key)
        if isinstance(existing, dict):
            existing = _reconcile_vi_terminal_session(session_key, existing)
            sessions[session_key] = existing
            current_app.vi_terminal_sessions = sessions
        if existing:
            if auth_session:
                existing["auth_session"] = auth_session
            if preferred_module_domain:
                existing["preferred_module_domain"] = preferred_module_domain
            existing_proc = existing.get("process")
            if bool(existing.get("active")) and (
                _vi_terminal_switch_in_progress(existing)
                or (existing_proc is not None and existing_proc.poll() is None)
            ):
                lock = existing.get("lock")
                if lock is not None:
                    with lock:
                        existing["cols"] = normalized_cols
                        existing["rows"] = normalized_rows
                        existing["updatedAt"] = _utcnow_iso()
                else:
                    existing["cols"] = normalized_cols
                    existing["rows"] = normalized_rows
                    existing["updatedAt"] = _utcnow_iso()
                return True, _vi_terminal_session_metadata(session_key, existing)

        if existing:
            sessions.pop(session_key, None)
            current_app.vi_terminal_sessions = sessions
            _terminate_vi_terminal_process(existing)
            _cleanup_vi_terminal_artifacts(existing)
            _close_vi_terminal_fds(existing)

        verun_root = _resolve_verun_root()
        vi_jar = _resolve_vi_jar_path(verun_root)
        if not verun_root or not vi_jar or not vi_jar.is_file():
            return False, {
                "error": f"VI runtime jar missing at {vi_jar}" if vi_jar else "Unable to resolve Verun VI runtime",
                "hint": "Build it with: mvn -pl vi -am -DskipTests package",
            }

        try:
            terminal_session = {
                "process": None,
                "prompt": VI_REPL_PRIMARY_PROMPT,
                "createdAt": _utcnow_iso(),
                "updatedAt": _utcnow_iso(),
                "cols": normalized_cols,
                "rows": normalized_rows,
                "buffer": "",
                "chunks": deque(maxlen=VI_TERMINAL_CHUNK_LIMIT),
                "next_seq": 1,
                "active": True,
                "exitCode": None,
                "mode": "repl",
                "cwd": str(_resolve_vi_portal_source_dir()),
                "restart_repl_on_exit": False,
                "switchingProcess": True,
                "cleanupPaths": [],
                "lock": threading.Lock(),
                "auth_session": auth_session,
                "preferred_module_domain": preferred_module_domain,
            }
            sessions[session_key] = terminal_session
            current_app.vi_terminal_sessions = sessions
            ok, proc_or_error = _start_vi_terminal_repl_process(terminal_session)
            if not ok:
                startup_failed = True
                sessions.pop(session_key, None)
                current_app.vi_terminal_sessions = sessions
                start_error = proc_or_error if isinstance(proc_or_error, dict) else {"error": "Failed to start VI terminal"}
            else:
                proc = proc_or_error
                _ensure_vi_terminal_reader(session_key, terminal_session)
        except Exception as exc:
            startup_failed = True
            start_error = {"error": f"Failed to start VI terminal: {exc}"}
            if terminal_session is not None:
                sessions.pop(session_key, None)
                current_app.vi_terminal_sessions = sessions

    if startup_failed:
        if terminal_session is not None:
            _terminate_vi_terminal_process(terminal_session)
            _cleanup_vi_terminal_artifacts(terminal_session)
            _close_vi_terminal_fds(terminal_session)
        return False, start_error or {"error": "Failed to start VI terminal"}

    if terminal_session is None or proc is None:
        return False, {"error": "Failed to start VI terminal"}

    _wait_for_vi_terminal_activity(terminal_session, proc, timeout_seconds=0.35)
    return True, _vi_terminal_session_metadata(session_key, terminal_session)


def _write_vi_terminal_input(source: str) -> tuple[bool, dict]:
    ok, session_info = _ensure_vi_terminal_session()
    if not ok:
        return False, session_info
    session_key = str(session_info.get("sessionKey") or _vi_terminal_session_key())
    session = getattr(current_app, "vi_terminal_sessions", {}).get(session_key)
    session = _reconcile_vi_terminal_session(session_key, session, wait_timeout=0.05)
    if not session:
        return False, {"error": "VI terminal session is not active"}
    proc = session.get("process")
    if not proc or proc.poll() is not None:
        return False, {"error": "VI terminal session is not active"}
    chunk = str(source or "")
    mode = str(session.get("mode") or "repl").strip().lower() or "repl"
    prompt = str(session.get("prompt") if session.get("prompt") is not None else VI_REPL_PRIMARY_PROMPT)
    if mode == "repl" and not chunk.strip() and prompt == VI_REPL_PRIMARY_PROMPT:
        return True, _vi_terminal_session_metadata(session_key, session)
    normalized_chunk = chunk if mode != "repl" else ("\n" if not chunk.strip() else _normalize_vi_repl_input(chunk, prompt))
    outbound_chunk = normalized_chunk if normalized_chunk.endswith("\n") else f"{normalized_chunk}\n"
    try:
        payload = outbound_chunk.encode("utf-8")
        proc.stdin.write(payload)
        proc.stdin.flush()
    except Exception as exc:
        recovered_session = _reconcile_vi_terminal_session(session_key, session, wait_timeout=0.05)
        metadata = _vi_terminal_session_metadata(session_key, recovered_session)
        if bool(metadata.get("active")):
            return True, metadata
        return False, {"error": f"Failed to send input to VI terminal: {exc}"}
    lock = session.get("lock")
    if lock is not None:
        with lock:
            session["updatedAt"] = _utcnow_iso()
    else:
        session["updatedAt"] = _utcnow_iso()
    return True, _vi_terminal_session_metadata(session_key, session)


def _run_vi_terminal_path(
    file_path: Path,
    relative_path: str,
    *,
    cleanup_paths: list[Path] | None = None,
    ephemeral: bool = False,
) -> tuple[bool, dict]:
    ok, session_info = _ensure_vi_terminal_session()
    if not ok:
        return False, session_info
    session_key = str(session_info.get("sessionKey") or _vi_terminal_session_key())
    session = getattr(current_app, "vi_terminal_sessions", {}).get(session_key)
    if not session:
        return False, {"error": "VI terminal session is not active"}

    verun_root = _resolve_verun_root()
    vi_jar = _resolve_vi_jar_path(verun_root)
    if not verun_root or not vi_jar or not vi_jar.is_file():
        return False, {
            "error": f"VI runtime jar missing at {vi_jar}" if vi_jar else "Unable to resolve Verun VI runtime",
            "hint": "Build it with: mvn -pl vi -am -DskipTests package",
        }

    normalized_cleanup_paths = [Path(path) for path in (cleanup_paths or [])]
    lock = session.get("lock")
    if lock is not None:
        with lock:
            session["restart_repl_on_exit"] = False
            session["switchingProcess"] = True
            session["active"] = True
            session["updatedAt"] = _utcnow_iso()
    _terminate_vi_terminal_process(session)
    _cleanup_vi_terminal_artifacts(session)
    _flush_vi_terminal_buffers(session)
    if lock is not None:
        with lock:
            session["cleanupPaths"] = [str(path) for path in normalized_cleanup_paths]
    ok, proc = _launch_vi_terminal_process(
        session,
        ["java", "-jar", str(vi_jar), str(file_path), "--msg-only"],
        cwd=file_path.parent,
        mode="file",
        prompt="",
        restart_repl_on_exit=True,
    )
    if not ok:
        if lock is not None:
            with lock:
                session["switchingProcess"] = False
                session["active"] = False
                session["cleanupPaths"] = []
                session["updatedAt"] = _utcnow_iso()
        for cleanup_path in normalized_cleanup_paths:
            try:
                cleanup_path.unlink(missing_ok=True)
            except TypeError:
                try:
                    if cleanup_path.exists():
                        cleanup_path.unlink()
                except OSError:
                    pass
            except OSError:
                pass
        return False, proc
    _ensure_vi_terminal_reader(session_key, session)
    _wait_for_vi_terminal_activity(session, proc, timeout_seconds=0.12)
    quick_exit_code = proc.poll()
    if quick_exit_code is not None and lock is not None:
        should_restart_repl = False
        with lock:
            if (
                session.get("process") is proc
                and str(session.get("mode") or "repl").strip().lower() == "file"
                and bool(session.get("restart_repl_on_exit"))
            ):
                session["restart_repl_on_exit"] = False
                session["switchingProcess"] = True
                session["exitCode"] = quick_exit_code
                session["updatedAt"] = _utcnow_iso()
                should_restart_repl = True
        if should_restart_repl:
            _cleanup_vi_terminal_artifacts(session)
            restart_ok, restart_result = _start_vi_terminal_repl_process(session)
            if restart_ok:
                _ensure_vi_terminal_reader(session_key, session)
                _wait_for_vi_terminal_activity(session, restart_result, timeout_seconds=0.25)
            else:
                _mark_vi_terminal_session_inactive(
                    session,
                    quick_exit_code,
                    exit_message=(
                        "\r\n[VI terminal failed to return to REPL: "
                        + str((restart_result or {}).get("error") or "unknown error")
                        + "]\r\n"
                    ),
                )
    payload = _vi_terminal_session_metadata(session_key, session)
    payload["path"] = relative_path
    if ephemeral:
        payload["ephemeral"] = True
    return True, payload


def _run_vi_terminal_file(path_value: str) -> tuple[bool, dict]:
    file_path, relative_path = _resolve_vi_portal_existing_file(path_value, allow_basename_match=True)
    return _run_vi_terminal_path(file_path, relative_path)


def _run_vi_terminal_source(path_value: str, source: str) -> tuple[bool, dict]:
    temp_path, relative_path, cleanup_paths = _create_vi_ephemeral_script(path_value, source)
    return _run_vi_terminal_path(temp_path, relative_path, cleanup_paths=cleanup_paths, ephemeral=True)


def _signal_vi_terminal_session(signal_name: str) -> tuple[bool, dict]:
    session_key = _vi_terminal_session_key()
    session = getattr(current_app, "vi_terminal_sessions", {}).get(session_key)
    if not session or not session.get("process") or session["process"].poll() is not None:
        return False, {"error": "VI terminal session is not active"}
    wanted = str(signal_name or "SIGINT").strip().upper() or "SIGINT"
    if wanted != "SIGINT":
        return False, {"error": f"Unsupported signal: {wanted}"}
    try:
        if os.name == "nt" and hasattr(signal, "CTRL_BREAK_EVENT"):
            session["process"].send_signal(signal.CTRL_BREAK_EVENT)
        else:
            session["process"].send_signal(signal.SIGINT)
    except Exception as exc:
        try:
            session["process"].send_signal(signal.SIGINT)
        except Exception:
            return False, {"error": f"Failed to signal VI terminal: {exc}"}
    session["updatedAt"] = _utcnow_iso()
    return True, _vi_terminal_session_metadata(session_key, session)


def _vi_repl_session_key() -> str:
    session = _current_vi_request_session() or {}
    return _normalize_username(session.get("username")) or "anonymous"


def _terminate_vi_repl_session(session_key: str) -> None:
    sessions = getattr(current_app, "vi_repl_sessions", {})
    repl_session = sessions.pop(session_key, None)
    proc = (repl_session or {}).get("process") if isinstance(repl_session, dict) else None
    if not proc:
        return
    try:
        if proc.stdin:
            try:
                proc.stdin.write("exit\n")
                proc.stdin.flush()
            except Exception:
                pass
        proc.terminate()
        proc.wait(timeout=1.5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _sanitize_vi_repl_stdout(stdout_text: str) -> str:
    lines: list[str] = []
    for raw_line in str(stdout_text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line
        while True:
            trimmed = False
            for candidate in (VI_REPL_CONTINUATION_PROMPT, VI_REPL_PRIMARY_PROMPT):
                if line.startswith(candidate):
                    line = line[len(candidate):]
                    trimmed = True
                    break
            if not trimmed:
                break
        if line.strip():
            lines.append(line.rstrip())
    return "\n".join(lines).strip()


def _drain_vi_repl_output(repl_session: dict, idle_timeout: float = 0.03, max_wait: float = 2.0) -> tuple[str, str, str, int | None]:
    proc = repl_session["process"]
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    prompt = str(repl_session.get("prompt") or VI_REPL_PRIMARY_PROMPT)
    deadline = time.time() + max_wait
    last_read_at = time.time()

    while time.time() < deadline:
        streams = [stream for stream in (proc.stdout, proc.stderr) if stream is not None]
        if not streams:
            break
        try:
            ready, _, _ = select.select(streams, [], [], 0.01)
        except (OSError, ValueError):
            ready = []
        if ready:
            for stream in ready:
                try:
                    chunk = stream.read()
                except BlockingIOError:
                    chunk = ""
                if not chunk:
                    continue
                if stream is proc.stdout:
                    stdout_chunks.append(chunk)
                else:
                    stderr_chunks.append(chunk)
                last_read_at = time.time()
            continue

        current_stdout = "".join(stdout_chunks)
        if current_stdout.endswith((VI_REPL_PRIMARY_PROMPT, VI_REPL_CONTINUATION_PROMPT)) and (time.time() - last_read_at) >= idle_timeout:
            break
        if proc.poll() is not None and (time.time() - last_read_at) >= idle_timeout:
            break

    stdout_text = "".join(stdout_chunks)
    stderr_text = "".join(stderr_chunks)
    for candidate in (VI_REPL_CONTINUATION_PROMPT, VI_REPL_PRIMARY_PROMPT):
        if stdout_text.endswith(candidate):
            prompt = candidate
            stdout_text = stdout_text[: -len(candidate)]
            break
    stdout_text = _sanitize_vi_repl_stdout(stdout_text)
    stderr_text = str(stderr_text or "").strip()
    repl_session["prompt"] = prompt
    return stdout_text, stderr_text, prompt, proc.poll()


def _bootstrap_vi_repl_session(repl_session: dict) -> tuple[str, str, str]:
    proc = repl_session["process"]
    bootstrap_lines = [
        "json_xml import *;",
        "vdb import *;",
        "http import *;",
        "email import *;",
        "crypto import *;",
        "jwt import *;",
        "time import *;",
        "datetime import *;",
    ]
    try:
        proc.stdin.write("\n".join(bootstrap_lines) + "\n")
        proc.stdin.flush()
    except Exception:
        return "", "", str(repl_session.get("prompt") or VI_REPL_PRIMARY_PROMPT)
    return _drain_vi_repl_output(repl_session)[:3]


def _normalize_vi_repl_input(source: str, prompt: str) -> str:
    text = str(source or "").replace("\r\n", "\n")
    if not text:
        return ""
    if prompt != VI_REPL_PRIMARY_PROMPT:
        return text
    if "\n" in text:
        return text
    stripped = text.rstrip()
    if not stripped:
        return ""
    if stripped.endswith((";", "{", "}")):
        return stripped
    return f"{stripped};"


def _ensure_vi_repl_session() -> tuple[bool, dict]:
    auth_session = _current_vi_request_session() or {}
    preferred_module_domain = _preferred_vi_module_domain(auth_session)
    session_key = _vi_repl_session_key()
    sessions = getattr(current_app, "vi_repl_sessions", {})
    existing = sessions.get(session_key)
    if existing and existing.get("process") and existing["process"].poll() is None:
        if auth_session:
            existing["auth_session"] = auth_session
        if preferred_module_domain:
            existing["preferred_module_domain"] = preferred_module_domain
        return True, {
            "sessionKey": session_key,
            "prompt": str(existing.get("prompt") or VI_REPL_PRIMARY_PROMPT),
            "active": True,
        }

    if existing:
        _terminate_vi_repl_session(session_key)

    verun_root = _resolve_verun_root()
    vi_jar = _resolve_vi_jar_path(verun_root)
    if not verun_root or not vi_jar or not vi_jar.is_file():
        return False, {
            "error": f"VI runtime jar missing at {vi_jar}" if vi_jar else "Unable to resolve Verun VI runtime",
            "hint": "Build it with: mvn -pl vi -am -DskipTests package",
        }

    try:
        proc = subprocess.Popen(
            ["java", "-jar", str(vi_jar)],
            cwd=verun_root.parent,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=_vi_runtime_env(session_context=auth_session, preferred_domain=preferred_module_domain),
        )
        _set_nonblocking(proc.stdout)
        _set_nonblocking(proc.stderr)
        repl_session = {
            "process": proc,
            "prompt": VI_REPL_PRIMARY_PROMPT,
        "createdAt": _utcnow_iso(),
            "auth_session": auth_session,
            "preferred_module_domain": preferred_module_domain,
        }
        sessions[session_key] = repl_session
        current_app.vi_repl_sessions = sessions
        banner, stderr_output, prompt, _ = _drain_vi_repl_output(repl_session)
        bootstrap_output, bootstrap_stderr, prompt = _bootstrap_vi_repl_session(repl_session)
        transcript = "\n".join(part for part in [banner.strip(), bootstrap_output.strip()] if part and part.strip())
        stderr_text = "\n".join(part for part in [stderr_output.strip(), bootstrap_stderr.strip()] if part and part.strip())
        return True, {
            "sessionKey": session_key,
            "prompt": prompt,
            "active": True,
            "output": transcript,
            "stderr": stderr_text,
        }
    except Exception as exc:
        return False, {"error": f"Failed to start VI REPL: {exc}"}


def _submit_vi_repl_input(source: str) -> tuple[bool, dict]:
    ok, session_info = _ensure_vi_repl_session()
    if not ok:
        return False, session_info
    session_key = session_info["sessionKey"]
    repl_session = current_app.vi_repl_sessions.get(session_key)
    if not repl_session or repl_session["process"].poll() is not None:
        return False, {"error": "VI REPL session is not active"}
    chunk = str(source or "")
    prompt = str(repl_session.get("prompt") or VI_REPL_PRIMARY_PROMPT)
    if not chunk.strip() and prompt == VI_REPL_PRIMARY_PROMPT:
        return True, {"output": "", "stderr": "", "prompt": prompt, "active": True}
    normalized_chunk = "\n" if not chunk.strip() else _normalize_vi_repl_input(chunk, prompt)
    try:
        repl_session["process"].stdin.write(normalized_chunk)
        if not normalized_chunk.endswith("\n"):
            repl_session["process"].stdin.write("\n")
        repl_session["process"].stdin.flush()
    except Exception as exc:
        _terminate_vi_repl_session(session_key)
        return False, {"error": f"Failed to send input to VI REPL: {exc}"}

    stdout_text, stderr_text, prompt, return_code = _drain_vi_repl_output(repl_session)
    active = return_code is None
    if not active:
        _terminate_vi_repl_session(session_key)
    payload = {
        "output": stdout_text.rstrip(),
        "stderr": stderr_text.rstrip(),
        "prompt": prompt,
        "active": active,
    }
    if not active and not payload["output"] and not payload["stderr"]:
        payload["error"] = f"VI REPL exited with code {return_code}"
    return True, payload


def _decorate_service(
    service_doc: dict,
    *,
    include_lapis_config: bool = True,
    include_routes: bool | None = None,
    include_auth_context: bool | None = None,
    production_mode: bool | None = None,
) -> dict:
    if include_routes is None:
        include_routes = include_lapis_config
    if include_auth_context is None:
        include_auth_context = include_lapis_config
    if production_mode is None:
        production_mode = _production_mode_enabled()

    out = dict(service_doc or {})
    port = out.get("port")
    raw_lapis_cfg = out.get("lapis_config") or {}
    source_lapis_cfg = normalize_lapis_config_contract(raw_lapis_cfg if isinstance(raw_lapis_cfg, dict) else {})
    lapis_cfg = copy.deepcopy(source_lapis_cfg) if include_lapis_config else source_lapis_cfg
    if include_lapis_config:
        out["lapis_config"] = lapis_cfg
    else:
        out.pop("lapis_config", None)
    metadata = lapis_cfg.get("metadata") or {}
    docs_cfg = metadata.get("documentation") or {}
    base_path = str(metadata.get("basePath") or "").strip()
    if base_path and not base_path.startswith("/"):
        base_path = f"/{base_path}"
    docs_enabled = bool(docs_cfg.get("enabled", True))
    docs_key_configured = bool(str(docs_cfg.get("keyHash") or docs_cfg.get("key") or "").strip())
    management_routes_enabled = not bool(production_mode)
    if include_lapis_config and isinstance(docs_cfg, dict):
        docs_cfg.pop("keyHash", None)

    out["productionMode"] = bool(production_mode)
    out["managementRoutesEnabled"] = management_routes_enabled
    out["docsEnabled"] = docs_enabled
    out["docsKeyConfigured"] = docs_key_configured
    out["basePath"] = base_path or "/"
    out["mediaCapabilities"] = summarize_media_capabilities(source_lapis_cfg)
    out["governance"] = _service_governance_summary(source_lapis_cfg)
    base = f"http://127.0.0.1:{port}" if port else None
    if base:
        out["rootUrl"] = f"{base}/"
        out["runtimeUrl"] = f"{base}/liwiro" if management_routes_enabled else None
        out["liwiroDocsUrl"] = f"{base}/liwiro/docs" if docs_enabled and management_routes_enabled else None

    if include_routes:
        endpoints = []
        for endpoint in (lapis_cfg.get("endpoints") or {}).values():
            path = str(endpoint.get("path", "")).strip()
            if path and not path.startswith("/"):
                path = f"/{path}"
            route = f"{base_path.rstrip('/')}{path}"
            if route in {"", "/"}:
                route = "/"
            endpoints.append({
                "method": endpoint.get("method"),
                "path": route,
                "operationType": endpoint.get("operationType"),
            })
        out["routes"] = endpoints
    else:
        out.pop("routes", None)

    auth_cfg = lapis_cfg.get("auth") or {}
    if include_auth_context:
        out["authContext"] = {
            "enabled": bool(auth_cfg.get("enabled", False)),
            "isAuthService": bool(auth_cfg.get("isAuthService", False)),
            "authServiceName": str(auth_cfg.get("authServiceName") or "").strip(),
            "useAsymmetricJWT": bool(auth_cfg.get("useAsymmetricJWT", False)),
        }
    else:
        out.pop("authContext", None)
    out["vdbDomain"] = str(out.get("vdb_domain") or out.get("apiName") or "").strip()
    return out


def _service_governance_summary(config: dict) -> dict:
    """Return deterministic, operator-facing contract readiness evidence."""
    config = config if isinstance(config, dict) else {}
    metadata = config.get("metadata") if isinstance(config.get("metadata"), dict) else {}
    auth = config.get("auth") if isinstance(config.get("auth"), dict) else {}
    endpoints = config.get("endpoints") if isinstance(config.get("endpoints"), dict) else {}
    checks: list[tuple[str, bool, str]] = [
        ("API name", bool(str(metadata.get("apiName") or "").strip()), "Set a stable API name."),
        ("Base path", bool(str(metadata.get("basePath") or "").strip()), "Set an explicit base path."),
        ("Version", bool(str(metadata.get("version") or "").strip()), "Set an API version."),
        ("Documentation", bool((metadata.get("documentation") or {}).get("enabled", True)), "Enable generated service documentation."),
    ]
    protected = [endpoint for endpoint in endpoints.values() if isinstance(endpoint, dict) and endpoint.get("requiresAuth")]
    checks.append(("Authentication", not protected or bool(auth.get("enabled")), "Protected endpoints require authentication to be enabled."))
    documented = [
        endpoint for endpoint in endpoints.values()
        if isinstance(endpoint, dict) and str(((endpoint.get("documentation") or {}).get("summary") or "")).strip()
    ]
    examples = [
        endpoint for endpoint in endpoints.values()
        if isinstance(endpoint, dict) and isinstance(endpoint.get("exampleParams"), dict)
    ]
    endpoint_count = len(endpoints)
    checks.append(("Endpoint summaries", endpoint_count == 0 or len(documented) == endpoint_count, "Add a documentation summary to each endpoint."))
    checks.append(("Request examples", endpoint_count == 0 or len(examples) == endpoint_count, "Add example request parameters to each endpoint."))
    issues = [{"control": name, "message": message} for name, passed, message in checks if not passed]
    passed = len(checks) - len(issues)
    return {
        "score": round((passed / len(checks)) * 100) if checks else 100,
        "status": "ready" if not issues else "needs-attention",
        "issues": issues,
        "endpointDocumentationCoverage": round((len(documented) / endpoint_count) * 100) if endpoint_count else 100,
        "endpointExampleCoverage": round((len(examples) / endpoint_count) * 100) if endpoint_count else 100,
    }


def _lapis_change_impacts(old_config: dict, new_config: dict) -> list[str]:
    """Describe model changes that can break routes before persisting them."""
    old_models = (old_config or {}).get("models") or {}
    new_models = (new_config or {}).get("models") or {}
    old_by_id = {str(key): value for key, value in old_models.items() if isinstance(value, dict)}
    new_by_id = {str(key): value for key, value in new_models.items() if isinstance(value, dict)}
    old_names = {key: str(value.get("name") or key).strip() for key, value in old_by_id.items()}
    new_names = {key: str(value.get("name") or key).strip() for key, value in new_by_id.items()}
    endpoints = (new_config or {}).get("endpoints") or {}
    impacts = []
    for model_id, old_name in old_names.items():
        new_name = new_names.get(model_id, "")
        affected = [
            str(endpoint_id) for endpoint_id, endpoint in endpoints.items()
            if isinstance(endpoint, dict) and str(endpoint.get("linkedModel") or "").strip() == old_name
        ]
        if not new_name:
            if affected:
                impacts.append(f"Removing model '{old_name}' leaves CRUD endpoint(s) {', '.join(affected)} without their linked model.")
        elif new_name != old_name and affected:
            impacts.append(f"Renaming model '{old_name}' to '{new_name}' breaks CRUD endpoint link(s): {', '.join(affected)}.")
        elif new_name == old_name and old_by_id[model_id].get("fields") != new_by_id[model_id].get("fields") and affected:
            impacts.append(f"Changing fields on model '{old_name}' changes the request/data contract for CRUD endpoint(s): {', '.join(affected)}.")
    old_auth_model = str(((old_config or {}).get("auth") or {}).get("authModel") or "").strip()
    if old_auth_model and old_auth_model not in set(new_names.values()):
        impacts.append(f"The authentication model '{old_auth_model}' is no longer present; sign-in and protected routes may stop working.")
    return impacts


def _safe_download_filename_segment(value: str, fallback: str = "service") -> str:
    text = str(value or "").strip().lower()
    chars = []
    for char in text:
        if char.isalnum() or char in {"-", "_"}:
            chars.append(char)
        else:
            chars.append("-")
    normalized = "".join(chars).strip("-_")
    return normalized or fallback


def _service_auth_key_bundle(service_doc: dict) -> dict | None:
    service = dict(service_doc or {})
    lapis_config = service.get("lapis_config") or {}
    if not isinstance(lapis_config, dict):
        return None
    auth_cfg = lapis_config.get("auth") or {}
    if not bool(auth_cfg.get("isAuthService", False)):
        return None

    metadata_cfg = lapis_config.get("metadata") or {}
    api_name = str(service.get("apiName") or metadata_cfg.get("apiName") or "service").strip() or "service"
    stem = _safe_download_filename_segment(api_name)
    key_management = str(auth_cfg.get("keyManagement") or "auto").strip().lower() or "auto"
    private_key = str(auth_cfg.get("privateKey") or "").strip()
    public_key = str(auth_cfg.get("publicKey") or "").strip()
    auth_service_public_key = str(auth_cfg.get("authServicePublicKey") or "").strip()
    setup_api_key = str(metadata_cfg.get("setupApiKey") or "").strip()
    fallback_secret = setup_api_key or api_name or "liwiro"

    files = []
    if private_key:
        files.append(
            {
                "label": "Private Key",
                "filename": f"{stem}-private-key.pem",
                "content": private_key,
            }
        )
    if public_key:
        files.append(
            {
                "label": "Public Key",
                "filename": f"{stem}-public-key.pem",
                "content": public_key,
            }
        )
    if auth_service_public_key and auth_service_public_key != public_key:
        files.append(
            {
                "label": "Auth Service Public Key",
                "filename": f"{stem}-auth-service-public-key.pem",
                "content": auth_service_public_key,
            }
        )

    material_type = "key-pair" if private_key else "shared-secret"
    caution = (
        "These files include live authentication signing material. Keep them out of source control and only distribute them over secure channels."
        if private_key
        else "This service currently signs JWTs with shared-secret material. Anyone with the exported value can mint valid bearer tokens for the service."
    )
    secret_source = ""
    if not private_key:
        active_secret = public_key or fallback_secret
        if public_key:
            secret_source = "auth.publicKey"
        elif setup_api_key:
            secret_source = "metadata.setupApiKey"
        else:
            secret_source = "metadata.apiName fallback"
        if active_secret:
            files.append(
                {
                    "label": "Active Signing Secret",
                    "filename": f"{stem}-signing-secret.txt",
                    "content": active_secret,
                }
            )
            caution = (
                f"{caution} Auto/manual fallback currently resolves from {secret_source}; rotate it before production exposure if you do not want shared-secret signing."
            )

    if not files:
        return {
            "service": api_name,
            "keyManagement": key_management,
            "materialType": material_type,
            "caution": caution,
            "files": [],
        }

    return {
        "service": api_name,
        "keyManagement": key_management,
        "materialType": material_type,
        "caution": caution,
        "secretSource": secret_source,
        "files": files,
    }


@main_bp.route("/")
def home():
    return jsonify({":>": "Welcome to the Liwiro API"})


@main_bp.route("/health", methods=["GET"])
def health():
    return jsonify(license_info.health_payload("LIWIRO_BACKEND")), 200


@main_bp.route("/license", methods=["GET"])
def license_view():
    return jsonify(license_info.license_disclosure()), 200


@main_bp.route("/auth/status", methods=["GET"])
def auth_status():
    data = _load_normalized_auth_data()
    has_frontend_creds = bool(data.get("users"))
    verun_root = _resolve_verun_root()
    vdb_users_exist = bool(verun_root and _vdb_has_any_user(verun_root))
    vdb_usernames = _vdb_usernames(verun_root) if verun_root else []
    # If user store was reset, force first-time setup mode even when auth file still exists.
    configured = bool(has_frontend_creds and vdb_users_exist)
    connection = _vdb_portal_connection_info()
    return jsonify({
        "configured": configured,
        "hasFrontendCreds": has_frontend_creds,
        "authFile": Config.LIWIRO_AUTH_PATH,
        "vdbUsersExist": vdb_users_exist,
        "vdbUsernames": vdb_usernames,
        "vdbTransport": connection.get("vdb_transport"),
        "vdbServerUrl": connection.get("vdb_server_url"),
        "vdbUnixSocketPath": connection.get("vdb_unix_socket_path"),
        "vdbNamedPipePath": connection.get("vdb_named_pipe_path"),
        **_platform_vdb_defaults(),
    }), 200


@main_bp.route("/auth/vdb-connection-status", methods=["GET"])
def auth_vdb_connection_status():
    requested_transport = request.args.get("vdb_transport")
    transport = (
        _requested_vdb_transport_mode(requested_transport)
        if requested_transport is not None and str(requested_transport).strip()
        else normalize_vdb_transport_mode(_runtime_cfg("VDB_TRANSPORT") or default_vdb_transport_mode())
    )
    requested_server_url = request.args.get("vdb_server_url")
    server_url = str(requested_server_url or _runtime_cfg("VDB_SERVER_URL") or "").strip()
    if transport in {"http", "namedpipe"} and not str(requested_server_url or "").strip():
        server_url = str(normalize_local_vdb_http_url(server_url or "http://127.0.0.1:1957")).strip()
    socket_path = str(
        request.args.get("vdb_unix_socket_path") or _runtime_cfg("VDB_UNIX_SOCKET_PATH") or ""
    ).strip()
    named_pipe_path = _normalized_named_pipe_path(
        request.args.get("vdb_named_pipe_path") or _runtime_cfg("VDB_NAMED_PIPE_PATH") or ""
    )
    attempt_autostart = str(request.args.get("attempt_autostart") or "").strip().lower() in {"1", "true", "yes", "on"}
    payload = _probe_vdb_transport_status(
        transport_mode=transport,
        server_url=server_url,
        socket_path=socket_path,
        named_pipe_path=named_pipe_path,
    )
    payload.setdefault("autostartAttempted", False)
    payload.setdefault("autostartDeferred", False)
    payload.setdefault("degraded", False)
    payload.setdefault("retryAfterMs", 0)
    payload.setdefault("reason", "")
    if transport == "http" and attempt_autostart and not bool(payload.get("available")) and bool(payload.get("localTarget")):
        autostart_key = f"http|{str(server_url or '').strip().lower()}"
        autostart_state = _resilience_state_snapshot(_RESILIENCE_BUCKET_VDB_HTTP_AUTOSTART, autostart_key)
        retry_after_ms = _resilience_remaining_ms(autostart_state, "pausedUntil")
        if retry_after_ms > 0:
            payload["status"] = "paused"
            payload["detail"] = "HTTP server unavailable"
            payload["autostartDeferred"] = True
            payload["degraded"] = True
            payload["retryAfterMs"] = retry_after_ms
            payload["reason"] = str(autostart_state.get("lastError") or "Local VDB HTTP auto-start is cooling down").strip()
            return _jsonify_with_retry_after(payload)

        started, message = _autostart_local_vdb_http_if_needed(current_app, server_url)
        if started:
            _resilience_record_success(_RESILIENCE_BUCKET_VDB_HTTP_AUTOSTART, autostart_key)
            payload = _probe_vdb_transport_status(
                transport_mode=transport,
                server_url=server_url,
                socket_path=socket_path,
                named_pipe_path=named_pipe_path,
            )
            payload["detail"] = "HTTP server available"
            payload["autostartDeferred"] = False
            payload["degraded"] = False
            payload["retryAfterMs"] = 0
            payload["reason"] = ""
        else:
            current_app.logger.warning(f"Local VDB transport auto-start failed during status probe: {message}")
            failure_state = _resilience_record_failure(
                _RESILIENCE_BUCKET_VDB_HTTP_AUTOSTART,
                autostart_key,
                error=str(message or "Local VDB HTTP auto-start failed").strip(),
                base_delay_ms=VDB_HTTP_AUTOSTART_FAILURE_BASE_MS,
                max_delay_ms=VDB_HTTP_AUTOSTART_FAILURE_MAX_MS,
            )
            payload["status"] = "paused"
            payload["detail"] = "HTTP server unavailable"
            payload["degraded"] = True
            payload["retryAfterMs"] = int(failure_state.get("retryAfterMs") or 0)
            payload["reason"] = str(message or "").strip()
        payload["autostartAttempted"] = True
    return _jsonify_with_retry_after(payload)


@main_bp.route("/auth/signin", methods=["POST"])
def auth_signin():
    payload = request.get_json(silent=True) or {}
    username = _normalize_username(payload.get("username"))
    password = str(payload.get("password") or "").strip()

    auth_data = _load_normalized_auth_data()
    has_frontend_creds = bool(auth_data.get("users"))
    verun_root = _resolve_verun_root()
    vdb_users_exist = bool(verun_root and _vdb_has_any_user(verun_root))
    configured = bool(has_frontend_creds and vdb_users_exist)
    bootstrap = not configured
    bootstrap_notices = []
    vdb_runtime_ready = bool(getattr(current_app, "vdb_client", None))
    vdb_runtime_error = ""

    if bootstrap:
        vdb_transport = normalize_vdb_transport_mode(payload.get("vdb_transport") or _runtime_cfg("VDB_TRANSPORT"))
        vdb_server_url = str(payload.get("vdb_server_url") or _runtime_cfg("VDB_SERVER_URL")).strip()
        vdb_unix_socket_path = str(payload.get("vdb_unix_socket_path") or _runtime_cfg("VDB_UNIX_SOCKET_PATH")).strip()
        vdb_named_pipe_path = _normalized_named_pipe_path(
            payload.get("vdb_named_pipe_path") or _runtime_cfg("VDB_NAMED_PIPE_PATH")
        )
        if vdb_transport in {"http", "namedpipe"}:
            vdb_server_url = str(
                normalize_local_vdb_http_url(vdb_server_url or "http://127.0.0.1:1957")
            ).strip()
        # Liwiro system workspace is fixed for platform metadata/config.
        liwiro_domain = "liwiro"
        liwiro_db = "config"
        liwiro_super_admin_username = str(
            payload.get("liwiro_super_admin_username")
            or payload.get("liwiro_username")
            or username
            or ""
        )
        liwiro_super_admin_username = _normalize_username(liwiro_super_admin_username)
        liwiro_super_admin_password = str(
            payload.get("liwiro_super_admin_password")
            or payload.get("liwiro_password")
            or password
            or ""
        ).strip()
        app_user = _normalize_username(payload.get("vdb_app_username") or _runtime_cfg("LIWIRO_APP_USERNAME") or LIWIRO_APP_USERNAME)
        app_password = str(
            payload.get("vdb_app_password")
            or _runtime_cfg("LIWIRO_APP_PASSWORD")
            or _runtime_cfg("VDB_PASSWORD")
            or ""
        ).strip()

        if not liwiro_super_admin_username or not liwiro_super_admin_password:
            return jsonify({"error": "Liwiro super admin username and password are required for first-time setup"}), 400
        if not app_user or not app_password:
            return jsonify({"error": "VDB application account username and password cannot be empty"}), 400
        ready, ready_msg = _ensure_vdb_transport_ready(
            current_app,
            vdb_transport,
            vdb_server_url,
            vdb_unix_socket_path,
            vdb_named_pipe_path,
        )
        if not ready:
            return jsonify(
                {
                    "error": "VDB transport could not be prepared for setup: "
                    + _friendly_transport_prepare_error(
                        vdb_transport,
                        ready_msg,
                        named_pipe_path=vdb_named_pipe_path,
                    )
                }
            ), 503

        app_user_exists = bool(verun_root and _vdb_has_user(verun_root, app_user))
        has_super_admin = bool(verun_root and _vdb_has_super_admin(verun_root))
        ok, msg = _verify_vdb_auth(
            vdb_server_url,
            app_user,
            app_password,
            transport_mode=vdb_transport,
            socket_path=vdb_unix_socket_path,
            named_pipe_path=vdb_named_pipe_path,
        )
        if not ok:
            admin_ok, admin_msg = _verify_vdb_auth(
                vdb_server_url,
                liwiro_super_admin_username,
                liwiro_super_admin_password,
                transport_mode=vdb_transport,
                socket_path=vdb_unix_socket_path,
                named_pipe_path=vdb_named_pipe_path,
            )
            if admin_ok:
                created_ok, created_msg = _ensure_vdb_user(
                    vdb_server_url=vdb_server_url,
                    admin_username=liwiro_super_admin_username,
                    admin_password=liwiro_super_admin_password,
                    username=app_user,
                    password=app_password,
                    domain=liwiro_domain,
                    transport_mode=vdb_transport,
                    socket_path=vdb_unix_socket_path,
                    named_pipe_path=vdb_named_pipe_path,
                    repair_existing=True,
                )
                if created_ok:
                    retry_ok, retry_msg = _verify_vdb_auth(
                        vdb_server_url,
                        app_user,
                        app_password,
                        transport_mode=vdb_transport,
                        socket_path=vdb_unix_socket_path,
                        named_pipe_path=vdb_named_pipe_path,
                    )
                    if retry_ok:
                        ok, msg = True, "Authenticated"
                        bootstrap_notices.append(
                            f"Created missing VDB app user '{app_user}' using provided VDB super-admin credentials."
                        )
                    else:
                        msg = retry_msg
                        bootstrap_notices.append(
                            f"Attempted to create VDB app user '{app_user}' but authentication still failed: {created_msg}"
                        )
                else:
                    bootstrap_notices.append(
                        f"Failed to auto-create VDB app user '{app_user}': {created_msg}"
                    )
        if not ok:
            return jsonify(
                {
                    "error": _build_bootstrap_vdb_auth_error(
                        app_user,
                        app_user_exists=app_user_exists,
                        has_super_admin=has_super_admin,
                        auth_error=msg,
                    )
                }
            ), 400

        if verun_root and not has_super_admin:
            bootstrap_notices.append(
                "No VDB super admin was detected in VDB. Setup continued because Liwiro VDB app credentials are valid."
            )
        vdb_username = app_user
        vdb_password = app_password
        username = liwiro_super_admin_username
        password = liwiro_super_admin_password

        auth_data = {
            "vdb_transport": vdb_transport,
            "vdb_server_url": vdb_server_url,
            "vdb_unix_socket_path": vdb_unix_socket_path,
            "vdb_named_pipe_path": vdb_named_pipe_path,
            "vdb_username": vdb_username,
            "liwiro_domain": liwiro_domain,
            "liwiro_db": liwiro_db,
        "created_at": _utcnow_iso(),
            "users": [
                {
                    "username": username,
                    "password_hash": generate_password_hash(password),
                    "role": ROLE_ADMIN,
                    "service_access": [WILDCARD_SERVICE_ACCESS],
                    "permissions": [],
                    "liwiro_rbac": _normalize_liwiro_rbac(None, is_super_admin=True),
                    "is_super_admin": True,
        "created_at": _utcnow_iso(),
                }
            ],
        }
        auth_data = _save_normalized_auth_data(auth_data)
        current_app.config["LIWIRO_DOCS_PASSWORD_HASH"] = str(
            ((auth_data.get("users") or [{}])[0]).get("password_hash") or ""
        )

        # Apply bootstrap credentials immediately without requiring backend restart.
        _apply_runtime_vdb_config(
            vdb_transport=vdb_transport,
            vdb_server_url=vdb_server_url,
            vdb_unix_socket_path=vdb_unix_socket_path,
            vdb_named_pipe_path=vdb_named_pipe_path,
            vdb_username=vdb_username,
            vdb_password=vdb_password,
            liwiro_domain=liwiro_domain,
            liwiro_db=liwiro_db,
        )
        _persist_runtime_vdb_env(
            vdb_transport=vdb_transport,
            vdb_server_url=vdb_server_url,
            vdb_unix_socket_path=vdb_unix_socket_path,
            vdb_named_pipe_path=vdb_named_pipe_path,
            vdb_username=vdb_username,
            vdb_password=vdb_password,
            liwiro_domain=liwiro_domain,
            liwiro_db=liwiro_db,
        )
        ok, msg = _initialize_vdb_runtime(current_app)
        _set_vdb_runtime_state(current_app, ok, "" if ok else msg)
        if not ok:
            return jsonify({"error": f"Bootstrap saved, but backend could not initialize VDB runtime: {msg}"}), 500
    else:
        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400
        auth_user = _find_auth_user(auth_data, username)
        if not auth_user or not check_password_hash(str(auth_user.get("password_hash") or ""), password):
            return jsonify({"error": "Invalid credentials"}), 401
        current_app.config["LIWIRO_DOCS_PASSWORD_HASH"] = str(auth_user.get("password_hash") or "")
        if not getattr(current_app, "vdb_client", None):
            override_vdb_transport = normalize_vdb_transport_mode(
                payload.get("vdb_transport") or auth_data.get("vdb_transport") or _runtime_cfg("VDB_TRANSPORT")
            )
            override_vdb_server_url = str(payload.get("vdb_server_url") or "").strip()
            override_vdb_unix_socket_path = str(payload.get("vdb_unix_socket_path") or "").strip()
            override_vdb_named_pipe_path = (
                _normalized_named_pipe_path(payload.get("vdb_named_pipe_path"))
                if str(payload.get("vdb_named_pipe_path") or "").strip()
                else ""
            )
            override_vdb_username = _normalize_username(payload.get("vdb_app_username") or payload.get("vdb_username"))
            override_vdb_password = str(payload.get("vdb_app_password") or payload.get("vdb_password") or "").strip()

            effective_vdb_transport = override_vdb_transport
            effective_vdb_server_url = override_vdb_server_url or auth_data.get("vdb_server_url", _runtime_cfg("VDB_SERVER_URL"))
            effective_vdb_unix_socket_path = (
                override_vdb_unix_socket_path
                or auth_data.get("vdb_unix_socket_path", _runtime_cfg("VDB_UNIX_SOCKET_PATH"))
            )
            effective_vdb_named_pipe_path = _normalized_named_pipe_path(
                override_vdb_named_pipe_path
                or auth_data.get("vdb_named_pipe_path", _runtime_cfg("VDB_NAMED_PIPE_PATH"))
            )
            if effective_vdb_transport in {"http", "namedpipe"}:
                effective_vdb_server_url = str(
                    normalize_local_vdb_http_url(effective_vdb_server_url or "http://127.0.0.1:1957")
                ).strip()
            effective_vdb_username = _normalize_username(
                override_vdb_username or auth_data.get("vdb_username", _runtime_cfg("VDB_USERNAME"))
            )
            effective_vdb_password = override_vdb_password or _runtime_cfg("VDB_PASSWORD")
            ready, ready_msg = _ensure_vdb_transport_ready(
                current_app,
                effective_vdb_transport,
                effective_vdb_server_url,
                effective_vdb_unix_socket_path,
                effective_vdb_named_pipe_path,
            )
            if not ready:
                return jsonify(
                    {
                        "error": "VDB transport could not be prepared for login: "
                        + _friendly_transport_prepare_error(
                            effective_vdb_transport,
                            ready_msg,
                            named_pipe_path=effective_vdb_named_pipe_path,
                        )
                    }
                ), 503

            _apply_runtime_vdb_config(
                vdb_transport=effective_vdb_transport,
                vdb_server_url=effective_vdb_server_url,
                vdb_unix_socket_path=effective_vdb_unix_socket_path,
                vdb_named_pipe_path=effective_vdb_named_pipe_path,
                vdb_username=effective_vdb_username,
                vdb_password=effective_vdb_password,
                liwiro_domain=auth_data.get("liwiro_domain", _runtime_cfg("LIWIRO_DOMAIN")),
                liwiro_db=auth_data.get("liwiro_db", _runtime_cfg("LIWIRO_DB")),
            )
            if effective_vdb_username and effective_vdb_password:
                _persist_runtime_vdb_env(
                    vdb_transport=effective_vdb_transport,
                    vdb_server_url=effective_vdb_server_url,
                    vdb_unix_socket_path=effective_vdb_unix_socket_path,
                    vdb_named_pipe_path=effective_vdb_named_pipe_path,
                    vdb_username=effective_vdb_username,
                    vdb_password=effective_vdb_password,
                    liwiro_domain=auth_data.get("liwiro_domain", _runtime_cfg("LIWIRO_DOMAIN")),
                    liwiro_db=auth_data.get("liwiro_db", _runtime_cfg("LIWIRO_DB")),
                )
            repair_admin_candidates = []
            if bool((auth_user or {}).get("is_super_admin", False)):
                repair_admin_candidates.append(
                    (
                        username,
                        password,
                        "current Liwiro super admin sign-in",
                    )
                )
            ok, msg = _initialize_vdb_runtime(current_app, repair_admin_candidates=repair_admin_candidates)
            if not ok:
                _set_vdb_runtime_state(current_app, False, msg)
                current_app.logger.warning(
                    f"Frontend credentials verified for '{username}', but VDB runtime init failed during sign-in: {msg}"
                )
                vdb_runtime_ready = False
                vdb_runtime_error = str(msg or "").strip() or "The VDB runtime could not be initialized after sign-in."
            else:
                _set_vdb_runtime_state(current_app, True, "")
                vdb_runtime_ready = True
                vdb_runtime_error = ""
            if ok and (
                "vdb_transport" in payload
                or override_vdb_server_url
                or override_vdb_unix_socket_path
                or override_vdb_named_pipe_path
                or override_vdb_username
                or override_vdb_password
            ):
                auth_data["vdb_transport"] = effective_vdb_transport
                auth_data["vdb_server_url"] = effective_vdb_server_url
                auth_data["vdb_unix_socket_path"] = effective_vdb_unix_socket_path
                auth_data["vdb_named_pipe_path"] = effective_vdb_named_pipe_path
                auth_data["vdb_username"] = effective_vdb_username
                auth_data = _save_normalized_auth_data(auth_data)
        else:
            vdb_runtime_ready = True
            vdb_runtime_error = ""

    token = secrets.token_urlsafe(32)
    auth_user = _find_auth_user(auth_data, username)
    session_username = _normalize_username((auth_user or {}).get("username") or username)
    session_payload = _build_auth_session_payload(session_username, auth_user, bootstrap)
    current_app.auth_sessions[token] = {**session_payload, "issuedAt": _utcnow_iso()}
    _persist_auth_sessions()

    return jsonify({
        "token": token,
        **session_payload,
        "bootstrap": bootstrap,
        "bootstrapNotices": bootstrap_notices if bootstrap else [],
        "vdbRuntimeReady": vdb_runtime_ready,
        "vdbRuntimeError": vdb_runtime_error,
    }), 200


@main_bp.route("/auth/me", methods=["GET"])
def auth_me():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    session = _session_from_header()
    role = _role_from_session(session)
    ai_config = _ai_config_status(session)
    return jsonify(
        {
            "authenticated": True,
            "username": session.get("username"),
            "role": role,
            "is_super_admin": _is_super_admin_session(session),
            "service_access": _session_service_access(session),
            "permissions_overrides": _normalize_user_permissions((session or {}).get("permissions_overrides")),
            "liwiro_rbac": _normalize_liwiro_rbac(
                (session or {}).get("liwiro_rbac"),
                is_super_admin=bool((session or {}).get("is_super_admin", False)),
            ),
            "permissions": sorted(_platform_permissions_for_role(role)),
            "vdbRuntimeReady": bool(getattr(current_app, "vdb_runtime_ready", bool(getattr(current_app, "vdb_client", None)))),
            "vdbRuntimeError": str(getattr(current_app, "vdb_runtime_error", "") or "").strip(),
            "aiConfig": {
                "configured": ai_config["configured"],
                "defaultProvider": ai_config["defaultProvider"],
                "canManage": ai_config["canManage"],
            },
        }
    ), 200


@main_bp.route("/auth/logout", methods=["POST"])
def auth_logout():
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        current_app.auth_sessions.pop(token, None)
        _persist_auth_sessions()
    return jsonify({"message": "Logged out"}), 200


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    werkzeug_logger = logging.getLogger("werkzeug")
    if not any(isinstance(existing, _LiwiroAccessLogFilter) for existing in werkzeug_logger.filters):
        werkzeug_logger.addFilter(_LiwiroAccessLogFilter())
    if str(os.getenv("LIWIRO_MANAGED_STARTUP") or "").strip().lower() in {"1", "true", "yes", "on"}:
        werkzeug_logger.setLevel(logging.WARNING)

    app.secret_key = secrets.token_hex(32)
    app.auth_sessions = _load_persisted_auth_sessions()
    app.vdb_portal_sessions = {}
    app.vi_repl_sessions = {}
    app.vi_terminal_sessions = {}
    app.vi_terminal_sessions_lock = threading.RLock()
    app.resilience_state = {}
    app.resilience_state_lock = threading.RLock()
    app.verse_service = None
    app.verse_service_signature = None
    app.ai_config_runtime_keys = set()
    app.ai_config_runtime_mtimes = {}
    from app.verse.telemetry import install_telemetry
    install_telemetry(app, app.config["VERSE_DATA_DIR"], session_loader=_session_from_header)
    app.vdb_runtime_ready = False
    app.vdb_runtime_error = ""

    configured_origin = Config.LIWIRO_FRONTEND
    allowed_origins = [
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:3001",
        "http://localhost:3001",
    ]
    if configured_origin and configured_origin not in allowed_origins:
        allowed_origins.insert(0, configured_origin)
    CORS(app, resources={r"/*": {"origins": allowed_origins}}, supports_credentials=False)

    app.vdb_client = None
    app.process_manager = ProcessManager(app)
    boot_auth = _load_normalized_auth_data()
    first_user = (boot_auth.get("users") or [{}])[0]
    app.config["LIWIRO_DOCS_PASSWORD_HASH"] = str(first_user.get("password_hash") or "")
    verun_root = _resolve_verun_root()
    boot_has_frontend_creds = bool(boot_auth.get("users"))
    boot_vdb_users_exist = bool(verun_root and _vdb_has_any_user(verun_root))
    with app.app_context():
        _apply_runtime_vdb_config(
            vdb_transport=boot_auth.get("vdb_transport") or app.config.get("VDB_TRANSPORT") or default_vdb_transport_mode(),
            vdb_server_url=boot_auth.get("vdb_server_url") or app.config.get("VDB_SERVER_URL") or "",
            vdb_unix_socket_path=boot_auth.get("vdb_unix_socket_path") or app.config.get("VDB_UNIX_SOCKET_PATH") or "",
            vdb_named_pipe_path=boot_auth.get("vdb_named_pipe_path") or app.config.get("VDB_NAMED_PIPE_PATH") or "",
            vdb_username=boot_auth.get("vdb_username") if "vdb_username" in boot_auth else app.config.get("VDB_USERNAME"),
            vdb_password=app.config.get("VDB_PASSWORD"),
            liwiro_domain=boot_auth.get("liwiro_domain") or app.config.get("LIWIRO_DOMAIN") or Config.LIWIRO_DOMAIN,
            liwiro_db=boot_auth.get("liwiro_db") or app.config.get("LIWIRO_DB") or Config.LIWIRO_DB,
        )
    if boot_has_frontend_creds and boot_vdb_users_exist:
        boot_ready, boot_msg = _initialize_vdb_runtime(app)
        _set_vdb_runtime_state(app, boot_ready, "" if boot_ready else boot_msg)
    boot_services = _reconcile_service_runtime_states(app)
    _autostart_services_if_enabled(app, services=boot_services)

    app.register_blueprint(main_bp)
    sock.init_app(app)
    _start_verse_proactive_startup_recovery(app)
    _start_verse_proactive_scheduler(app)
    return app


@main_bp.route("/generate", methods=["POST"])
def generate():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied

    denied = _authorize_or_forbid("WRITE")
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    lapis_config = normalize_lapis_config_contract(request.json)
    if not lapis_config:
        return jsonify({"error": "Invalid LAPIS configuration"}), 400

    valid, error = Config.validate_lapis_config(lapis_config)
    if not valid:
        return jsonify({"error": f"Invalid LAPIS configuration: {error}"}), 400
    try:
        lapis_config = _sync_lapis_shared_modules(lapis_config, _session_from_header())
        lapis_config = _sync_lapis_service_modules(lapis_config, _session_from_header())
    except ValueError as exc:
        return jsonify({"error": f"Invalid LAPIS configuration: {exc}"}), 400
    _prepare_documentation_key(
        lapis_config,
        existing_hash=str(current_app.config.get("LIWIRO_DOCS_PASSWORD_HASH") or "").strip(),
    )
    docs_cfg = ((lapis_config.get("metadata") or {}).get("documentation") or {})
    if bool(docs_cfg.get("enabled", True)) and not str(docs_cfg.get("keyHash") or "").strip():
        return jsonify({"error": "Unable to auto-configure documentation key hash for this service"}), 400

    try:
        api_name = lapis_config["metadata"]["apiName"]
        if not str(api_name or "").strip():
            return jsonify({"error": "metadata.apiName is required"}), 400

        _use_runtime_workspace()
        existing_ok, existing_services = current_app.vdb_client.read_documents("services", {})
        if existing_ok and isinstance(existing_services, list):
            existing_name = str(api_name).strip().lower()
            collision = any(str(item.get("apiName") or "").strip().lower() == existing_name for item in existing_services)
            if collision:
                return jsonify({"error": f"Error: Service name '{api_name}' already exists. Use a unique name."}), 409

            auth_cfg = lapis_config.get("auth") or {}
            endpoint_cfg = lapis_config.get("endpoints") or {}
            is_auth_service = bool(auth_cfg.get("isAuthService", False))
            has_auth_required_endpoint = any(bool((ep or {}).get("requiresAuth", False)) for ep in endpoint_cfg.values())
            is_authenticated_service = bool(auth_cfg.get("enabled", False)) and bool(auth_cfg.get("useAsymmetricJWT", False)) and not is_auth_service
            needs_external_auth = (has_auth_required_endpoint and not is_auth_service) or is_authenticated_service
            auth_candidates = [
                item for item in existing_services
                if bool(((item.get("lapis_config") or {}).get("auth") or {}).get("isAuthService", False))
            ]
            selected_auth_service = None
            if needs_external_auth:
                lapis_config.setdefault("auth", {})
                lapis_config["auth"]["enabled"] = True
                lapis_config["auth"]["useAsymmetricJWT"] = True
                if not str(lapis_config["auth"].get("keyManagement") or "").strip():
                    lapis_config["auth"]["keyManagement"] = "auto"

                dependency_name = str(lapis_config["auth"].get("authServiceName") or "").strip()
                if dependency_name:
                    selected_auth_service = next(
                        (
                            item
                            for item in auth_candidates
                            if str(item.get("apiName") or "").strip().lower() == dependency_name.lower()
                        ),
                        None,
                    )
                    if not selected_auth_service:
                        return jsonify(
                            {
                                "error": f"Configured authentication service '{dependency_name}' was not found. Select a valid authentication service."
                            }
                        ), 409
                elif len(auth_candidates) == 1:
                    selected_auth_service = auth_candidates[0]
                    lapis_config["auth"]["authServiceName"] = str(selected_auth_service.get("apiName") or "").strip()
                elif len(auth_candidates) == 0:
                    return jsonify(
                        {"error": "No authentication service exists. Create an authentication service before creating protected routes."}
                    ), 409
                else:
                    return jsonify(
                        {"error": "Multiple authentication services exist. Select one authentication service and retry."}
                    ), 409

                selected_auth_cfg = ((selected_auth_service or {}).get("lapis_config") or {}).get("auth") or {}
                selected_public_key = str(
                    selected_auth_cfg.get("publicKey")
                    or selected_auth_cfg.get("authServicePublicKey")
                    or ""
                ).strip()
                if selected_public_key and not str(lapis_config["auth"].get("authServicePublicKey") or "").strip():
                    lapis_config["auth"]["authServicePublicKey"] = selected_public_key
                # Propagate auth bootstrap credentials from the selected auth service
                # so authenticated services can use the same setup/login flow without
                # hardcoding these values in dependent service templates.
                selected_default_super_admin = selected_auth_cfg.get("defaultSuperAdmin")
                if isinstance(selected_default_super_admin, dict):
                    lapis_config["auth"]["defaultSuperAdmin"] = json.loads(
                        json.dumps(selected_default_super_admin)
                    )
                target_metadata = ((selected_auth_service or {}).get("lapis_config") or {}).get("metadata") or {}
                target_custom = selected_auth_cfg.get("customEndpoints") or {}
                target_base_path = str(target_metadata.get("basePath") or "").strip()
                target_sign_in = str(target_custom.get("signIn") or "/signin").strip()
                target_sign_out = str(target_custom.get("signOut") or "/signout").strip()
                target_port = (selected_auth_service or {}).get("port")
                try:
                    target_port = int(float(str(target_port).strip()))
                except Exception:
                    target_port = 0
                if target_port > 0:
                    lapis_config["auth"]["authServiceEndpoint"] = {
                        "baseUrl": f"http://127.0.0.1:{target_port}",
                        "signInPath": _join_route(target_base_path, target_sign_in),
                        "signOutPath": _join_route(target_base_path, target_sign_out),
                    }

            uses_external_jwt = bool(lapis_config.get("auth", {}).get("useAsymmetricJWT", False)) and not is_auth_service
            session = _session_from_header() or {}
            target_service_doc = {"apiName": api_name, "processId": ""}
            explicit_rules = _session_permission_rules(session)
            has_direct_access = _session_has_direct_service_access(session, target_service_doc)
            if _session_is_service_permission_denied(session, target_service_doc, required_types={"SERVICE_ALL"}):
                return jsonify({"error": "Fine-grained policy blocks creation for this service name"}), 403
            if explicit_rules and not has_direct_access:
                if not _session_has_fine_grained_service_permission(
                    session,
                    target_service_doc,
                    required_types={"SERVICE_ALL"},
                ):
                    return jsonify({"error": "Fine-grained policy blocks creation for this service name"}), 403

            if uses_external_jwt:
                dependency_name = str((lapis_config.get("auth") or {}).get("authServiceName") or "").strip().lower()
                if _session_is_service_permission_denied(
                    session,
                    target_service_doc,
                    required_types={"CROSS_SERVICE"},
                    target_service=dependency_name,
                ):
                    return jsonify({"error": "Fine-grained policy blocks cross-service auth dependency for this service"}), 403
                if explicit_rules and not has_direct_access:
                    if not _session_has_fine_grained_service_permission(
                        session,
                        target_service_doc,
                        required_types={"SERVICE_ALL", "CROSS_SERVICE"},
                        target_service=dependency_name,
                    ):
                        return jsonify({"error": "Fine-grained policy blocks cross-service auth dependency for this service"}), 403

        process_id, port = current_app.process_manager.start_api_service(lapis_config, api_name)

        current_app.vdb_client.create_document(
            "services",
            {
                "apiName": api_name,
                "processId": str(process_id),
                "status": "RUNNING",
                "port": port,
                "vdb_domain": api_name,
                "lapis_config": lapis_config,
                "createdAt": datetime.now().isoformat(),
            },
        )
        session = _session_from_header() or {}
        if _role_from_session(session) != ROLE_ADMIN:
            _grant_user_service_access(session.get("username", ""), api_name, str(process_id))
            session_access = _session_service_access(session)
            for key in (api_name, str(process_id)):
                if key and key not in session_access:
                    session_access.append(key)
            session["service_access"] = session_access

        base = f"http://127.0.0.1:{port}"
        docs_cfg = (lapis_config.get("metadata") or {}).get("documentation") or {}
        docs_enabled = bool(docs_cfg.get("enabled", True))
        docs_key_configured = bool(str(docs_cfg.get("keyHash") or "").strip())
        production_mode = _production_mode_enabled()
        return (
            jsonify(
                {
                    "message": f"API service '{api_name}' started on port {port}",
                    "process_id": process_id,
                    "port": port,
                    "runtime_url": None if production_mode else f"{base}/liwiro",
                    "root_url": f"{base}/",
                    "docs_enabled": docs_enabled,
                    "docs_key_configured": docs_key_configured,
                    "liwiro_docs_url": f"{base}/liwiro/docs" if docs_enabled and not production_mode else None,
                    "production_mode": production_mode,
                }
            ),
            201,
        )

    except Exception as e:
        current_app.logger.error(f"Error generating API: {str(e)}")
        return jsonify({"error": str(e)}), 500


def _resolve_service_record_for_manager_action(process_id: str = "", service_name: str = "") -> tuple[dict | None, str]:
    normalized_process_id = str(process_id or "").strip()
    normalized_service_name = str(service_name or "").strip()
    service_doc = None
    if normalized_process_id:
        success, services = current_app.vdb_client.read_documents("services", _service_query(normalized_process_id))
        if success and services:
            service_doc = services[0]
    if service_doc is None and normalized_service_name:
        success, services = current_app.vdb_client.read_documents("services", _service_name_query(normalized_service_name))
        if success and services:
            service_doc = services[0]
    resolved_process_id = str((service_doc or {}).get("processId") or normalized_process_id).strip()
    return service_doc, resolved_process_id


def _preview_service_manager_action(artifact: dict, session: dict | None) -> tuple[dict, int]:
    service_action = artifact.get("serviceAction") if isinstance(artifact.get("serviceAction"), dict) else {}
    action = str(service_action.get("action") or "").strip().lower()
    if action not in {"start", "stop", "delete"}:
        return {"error": "Unsupported service manager action"}, 400

    _use_runtime_workspace()
    service_doc, resolved_process_id = _resolve_service_record_for_manager_action(
        str(service_action.get("processId") or "").strip(),
        str(service_action.get("serviceName") or "").strip(),
    )
    if service_doc is None:
        return {"error": "Service not found"}, 404
    if not _session_can_access_service(session, service_doc):
        return {"error": "Service access denied"}, 403

    return {
        "kind": "service-manager-action",
        "action": action,
        "requiresConfirmation": True,
        "service": {
            "processId": resolved_process_id,
            "apiName": str(service_doc.get("apiName") or ""),
            "status": str(service_doc.get("status") or ""),
        },
        "message": f"Ready to {action} {service_doc.get('apiName') or resolved_process_id}.",
    }, 200


def _normalize_verse_action_bool(value: Any, default: bool = False) -> bool:
    if value in {None, ""}:
        return bool(default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


_GENERIC_SERVICE_MANAGER_CAPABILITY_IDS = {
    "service.manager.start",
    "service.manager.stop",
    "service.manager.delete",
}
_PUBLIC_PLATFORM_CAPABILITY_IDS = {
    "auth.setup.bootstrap",
    "auth.session.manage",
    "docs.wiki.open",
    "platform.navigation.change-location",
}


def _capability_requires_auth(capability: dict[str, Any]) -> bool:
    return str(capability.get("capabilityId") or "").strip() not in _PUBLIC_PLATFORM_CAPABILITY_IDS


def _decorate_platform_capability(capability: dict[str, Any], session: dict | None) -> dict[str, Any]:
    record = dict(capability or {})
    permissions = [str(item).strip() for item in list(record.get("permissions") or []) if str(item).strip()]
    session_permissions = {str(item).strip() for item in list((session or {}).get("permissions") or []) if str(item).strip()}
    requires_auth = _capability_requires_auth(record)
    missing_permissions = [item for item in permissions if item not in session_permissions]
    allowed = (not requires_auth or bool(session)) and not missing_permissions
    record["requiresAuth"] = requires_auth
    record["allowed"] = bool(allowed)
    record["missingPermissions"] = missing_permissions
    return record


def _service_manager_artifact_from_platform_action(
    capability_id: str,
    payload: dict[str, Any],
    artifact: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, tuple[dict, int] | None]:
    action = str(capability_id.rsplit(".", 1)[-1] or "").strip().lower()
    if action not in {"start", "stop", "delete"}:
        return None, ({"error": "Unsupported service manager capability"}, 400)

    action_input = payload.get("input") if isinstance(payload.get("input"), dict) else {}
    if artifact:
        if str(artifact.get("kind") or "").strip() != "service-manager-action":
            return None, ({"error": "Artifact kind does not match capability"}, 400)
        service_action = artifact.get("serviceAction") if isinstance(artifact.get("serviceAction"), dict) else {}
        if not service_action:
            return None, ({"error": "artifact.serviceAction is required"}, 400)
        normalized_artifact = dict(artifact)
        normalized_service_action = dict(service_action)
        normalized_service_action["action"] = action
        normalized_artifact["serviceAction"] = normalized_service_action
        normalized_artifact["capabilityId"] = capability_id
        return normalized_artifact, None

    process_id = str(
        action_input.get("processId")
        or action_input.get("process_id")
        or action_input.get("serviceId")
        or action_input.get("service_id")
        or payload.get("processId")
        or payload.get("serviceId")
        or payload.get("service_id")
        or ""
    ).strip()
    service_name = str(
        action_input.get("serviceName")
        or action_input.get("service_name")
        or payload.get("serviceName")
        or payload.get("service_name")
        or ""
    ).strip()
    if not process_id and not service_name:
        return None, ({"error": "processId or serviceName is required"}, 400)

    service_action = {
        "action": action,
        "processId": process_id,
        "serviceName": service_name,
    }
    delete_data = action_input.get("deleteData", payload.get("deleteData"))
    if delete_data is not None:
        service_action["deleteData"] = delete_data

    return {
        "kind": "service-manager-action",
        "capabilityId": capability_id,
        "serviceAction": service_action,
    }, None


def _resolve_platform_action_request(body: dict[str, Any] | None) -> tuple[dict[str, Any] | None, dict[str, Any], tuple[dict, int] | None]:
    payload = dict(body or {})
    artifact = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else {}
    capability_id = str(payload.get("capabilityId") or "").strip()
    if not capability_id and artifact:
        service_action = artifact.get("serviceAction") if isinstance(artifact.get("serviceAction"), dict) else {}
        capability_id = capability_id_for_artifact(
            str(artifact.get("kind") or "").strip(),
            str(service_action.get("action") or "").strip(),
        )
    if not capability_id:
        return None, {}, ({"error": "capabilityId or a mapped artifact is required"}, 400)

    capability = get_platform_capability(capability_id)
    if capability is None:
        return None, {}, ({"error": "Unknown platform capability"}, 404)

    if capability_id in _GENERIC_SERVICE_MANAGER_CAPABILITY_IDS:
        resolved_artifact, error_response = _service_manager_artifact_from_platform_action(capability_id, payload, artifact)
        if error_response is not None:
            return capability, {}, error_response
        return capability, resolved_artifact or {}, None

    if artifact and not artifact.get("capabilityId"):
        artifact = {**artifact, "capabilityId": capability_id}
    return capability, artifact, None


def _preview_platform_action_message(capability: dict[str, Any]) -> str:
    execution_mode = str(capability.get("executionMode") or "").strip().lower()
    title = str(capability.get("title") or capability.get("capabilityId") or "action").strip()
    surface_id = str(capability.get("surfaceId") or "").strip()
    if execution_mode == "page":
        return f"{title} is staged through the {surface_id or 'target'} surface."
    if execution_mode == "client":
        return f"{title} is a client-side staged action."
    if execution_mode == "server":
        return f"{title} is registered as a server-backed platform action."
    return f"{title} is registered in the Liwiro capability catalog."


def _denial_to_payload(denied: Any) -> tuple[dict, int] | None:
    if not denied:
        return None
    response = denied
    status = getattr(response, "status_code", 500)
    if isinstance(denied, tuple) and denied:
        response = denied[0]
        if len(denied) > 1:
            status = int(denied[1])
    payload = response.get_json(silent=True) if hasattr(response, "get_json") else None
    if not isinstance(payload, dict):
        text = response.get_data(as_text=True) if hasattr(response, "get_data") else ""
        payload = {"error": text or "Request denied"}
    payload.setdefault("error", "Request denied")
    return payload, status


def _preview_platform_action(body: dict[str, Any] | None, session: dict | None) -> tuple[dict, int]:
    capability, artifact, error_response = _resolve_platform_action_request(body)
    if error_response is not None:
        return error_response
    assert capability is not None

    decorated = _decorate_platform_capability(capability, session)
    if decorated.get("requiresAuth") and not session:
        return {"error": "Authentication required", "capabilityId": decorated.get("capabilityId"), "capability": decorated}, 401
    if decorated.get("missingPermissions"):
        return {"error": "Permission denied", "capabilityId": decorated.get("capabilityId"), "capability": decorated}, 403

    capability_id = str(decorated.get("capabilityId") or "").strip()
    if capability_id in _GENERIC_SERVICE_MANAGER_CAPABILITY_IDS:
        denied = _denial_to_payload(_authorize_or_forbid("DATA_ACCESS"))
        if denied:
            return denied
        payload, status = _preview_service_manager_action(artifact, session)
        if isinstance(payload, dict):
            payload["capabilityId"] = capability_id
            payload["capability"] = decorated
            payload["artifact"] = artifact
        return payload, status

    return {
        "ok": True,
        "capabilityId": capability_id,
        "capability": decorated,
        "artifact": artifact or None,
        "previewType": "metadata",
        "requiresConfirmation": "execute" in set(decorated.get("stageSupport") or []),
        "target": {
            "surfaceId": str(decorated.get("surfaceId") or "").strip(),
            "surfacePath": str(decorated.get("surfacePath") or "").strip(),
        },
        "message": _preview_platform_action_message(decorated),
    }, 200


def _execute_platform_action(body: dict[str, Any] | None, session: dict | None) -> tuple[dict, int]:
    capability, artifact, error_response = _resolve_platform_action_request(body)
    if error_response is not None:
        return error_response
    assert capability is not None

    decorated = _decorate_platform_capability(capability, session)
    if decorated.get("requiresAuth") and not session:
        return {"error": "Authentication required", "capabilityId": decorated.get("capabilityId"), "capability": decorated}, 401
    if decorated.get("missingPermissions"):
        return {"error": "Permission denied", "capabilityId": decorated.get("capabilityId"), "capability": decorated}, 403

    capability_id = str(decorated.get("capabilityId") or "").strip()
    if str(decorated.get("executionMode") or "").strip().lower() != "server":
        return {
            "error": "Execution for that capability is handled on the target surface, not through the generic server action endpoint",
            "capabilityId": capability_id,
            "capability": decorated,
        }, 400

    if capability_id in _GENERIC_SERVICE_MANAGER_CAPABILITY_IDS:
        denied = _denial_to_payload(_authorize_or_forbid("WRITE"))
        if denied:
            return denied
        payload, status = _execute_service_manager_action(artifact, session)
        if isinstance(payload, dict):
            payload["capabilityId"] = capability_id
            payload["capability"] = decorated
        return payload, status

    return {
        "error": "Generic execution is not implemented for that capability yet",
        "capabilityId": capability_id,
        "capability": decorated,
    }, 400


def _stop_service_via_manager_action(process_id: str, session: dict | None) -> tuple[dict, int]:
    try:
        process_id_int = int(process_id)
    except ValueError:
        return {"error": "Invalid process ID format"}, 400

    _use_runtime_workspace()
    success, services = current_app.vdb_client.read_documents("services", _service_query(process_id))
    if not success or not services:
        if current_app.process_manager.stop_api_service(process_id_int):
            return {"message": f"Lingering process {process_id} stopped"}, 200
        return {"error": "Service not found"}, 404

    service_info = services[0]
    if not _session_can_access_service(session, service_info):
        return {"error": "Service access denied"}, 403

    if current_app.process_manager.stop_api_service(process_id_int):
        update_success, _ = current_app.vdb_client.update_document(
            "services",
            _service_query(process_id),
            {"status": "NOT_RUNNING", "updatedAt": datetime.now().isoformat()},
        )
        if not update_success:
            current_app.logger.error(f"Failed to update status for service {process_id}")
        return {"message": f"Service {process_id} stopped"}, 200

    current_app.vdb_client.update_document(
        "services",
        _service_query(process_id),
        {"status": "NOT_RUNNING", "updatedAt": datetime.now().isoformat()},
    )
    return {"message": f"Service {process_id} marked stopped"}, 200


def _start_service_via_manager_action(process_id: str, session: dict | None) -> tuple[dict, int]:
    try:
        process_id_int = int(process_id)
    except ValueError:
        return {"error": "Invalid process ID format"}, 400

    _use_runtime_workspace()
    success, services = current_app.vdb_client.read_documents("services", _service_query(process_id))
    if not success or not services:
        return {"error": "Service not found"}, 404

    service_info = services[0]
    if not _session_can_access_service(session, service_info):
        return {"error": "Service access denied"}, 403
    lapis_config = service_info.get("lapis_config")
    if not lapis_config:
        return {"error": "Service configuration missing"}, 400

    result = current_app.process_manager.restart_service(
        process_id_int,
        lapis_config,
        service_info["apiName"],
    )
    if not result or None in result:
        return {"error": "Restart failed"}, 500
    new_process_id, port = result

    current_app.vdb_client.update_document(
        "services",
        _service_query(process_id),
        {
            "status": "RUNNING",
            "processId": str(new_process_id),
            "port": port,
            "updatedAt": datetime.now().isoformat(),
        },
    )
    _grant_user_service_access((session or {}).get("username", ""), service_info.get("apiName"), str(new_process_id))

    production_mode = _production_mode_enabled()
    runtime_url = None if production_mode else f"http://127.0.0.1:{port}/liwiro"
    return (
        {
            "message": f"Service '{service_info['apiName']}' restarted on port {port}",
            "process_id": new_process_id,
            "runtime_url": runtime_url,
        },
        200,
    )


def _delete_service_via_manager_action(process_id: str, session: dict | None, delete_data_flag: bool) -> tuple[dict, int]:
    try:
        process_id_int = int(process_id)
    except ValueError:
        return {"error": "Invalid process ID format"}, 400

    _use_runtime_workspace()
    success, services = current_app.vdb_client.read_documents("services", _service_query(process_id))
    if not success or not services:
        if current_app.process_manager.stop_api_service(process_id_int):
            return {"message": f"Lingering process {process_id} stopped"}, 200
        return {"error": "Service not found"}, 404

    service_info = services[0]
    if not _session_can_access_service(session, service_info):
        return {"error": "Service access denied"}, 403

    port = service_info.get("port")
    process_stopped = current_app.process_manager.stop_api_service(process_id_int)
    data_cleanup = {
        "requested": delete_data_flag,
        "attempted": False,
        "droppedDomain": False,
        "droppedDb": False,
        "warnings": [],
        "errors": [],
    }

    if delete_data_flag:
        data_cleanup["attempted"] = True
        service_domain = str(service_info.get("vdb_domain") or service_info.get("apiName") or "").strip()
        try:
            drop_ok, drop_result = _drop_service_domain_and_verify(service_domain)
            data_cleanup["droppedDomain"] = bool(drop_result.get("droppedDomain"))
            data_cleanup["droppedDb"] = bool(drop_result.get("droppedDb"))
            if drop_result.get("warnings"):
                data_cleanup["warnings"] = [str(item) for item in (drop_result.get("warnings") or []) if str(item).strip()]
            if not drop_ok:
                data_cleanup["errors"].extend([str(item) for item in (drop_result.get("errors") or []) if str(item).strip()])
        except Exception as cleanup_exc:
            data_cleanup["errors"].append(str(cleanup_exc))
        finally:
            _use_runtime_workspace()

    if delete_data_flag and data_cleanup["errors"]:
        current_app.vdb_client.update_document(
            "services",
            _service_query(process_id),
            {
                "status": "STOPPED",
                "updatedAt": datetime.now().isoformat(),
            },
        )
        return {
            "error": "Service process stopped but service data cleanup did not complete",
            "processStopped": bool(process_stopped),
            "data_cleanup": data_cleanup,
        }, 500

    current_app.vdb_client.delete_document("services", _service_query(process_id))
    return {
        "message": f"Service {process_id} deleted",
        "freed_port": port,
        "processStopped": bool(process_stopped),
        "data_cleanup": data_cleanup,
    }, 200


def _execute_service_manager_action(artifact: dict, session: dict | None) -> tuple[dict, int]:
    if not isinstance(artifact, dict):
        return {"error": "artifact is required"}, 400
    if str(artifact.get("kind") or "").strip() != "service-manager-action":
        return {"error": "Unsupported Verse action artifact"}, 400

    service_action = artifact.get("serviceAction") if isinstance(artifact.get("serviceAction"), dict) else {}
    action = str(service_action.get("action") or "").strip().lower()
    if action not in {"start", "stop", "delete"}:
        return {"error": "Unsupported service manager action"}, 400

    delete_data_default = bool(_platform_settings_with_defaults((_load_normalized_auth_data().get("settings") or {})).get("deleteDataWithServiceByDefault", True))
    delete_data_flag = _normalize_verse_action_bool(service_action.get("deleteData"), default=delete_data_default)

    _use_runtime_workspace()
    service_doc, resolved_process_id = _resolve_service_record_for_manager_action(
        str(service_action.get("processId") or "").strip(),
        str(service_action.get("serviceName") or "").strip(),
    )
    if service_doc is None:
        return {"error": "Service not found"}, 404

    if action == "start":
        payload, status = _start_service_via_manager_action(resolved_process_id, session)
    elif action == "stop":
        payload, status = _stop_service_via_manager_action(resolved_process_id, session)
    else:
        payload, status = _delete_service_via_manager_action(resolved_process_id, session, delete_data_flag)

    if status >= 400:
        return payload, status

    refreshed_service = None
    if action != "delete":
        refreshed_doc, refreshed_process_id = _resolve_service_record_for_manager_action(
            str((payload or {}).get("process_id") or resolved_process_id).strip(),
            str(service_doc.get("apiName") or "").strip(),
        )
        if refreshed_doc and _session_can_access_service(session, refreshed_doc):
            refreshed_service = _decorate_service(refreshed_doc, production_mode=_production_mode_enabled())
            resolved_process_id = refreshed_process_id or resolved_process_id

    return {
        "ok": True,
        "message": str(payload.get("message") or f"Service manager action '{action}' completed.").strip(),
        "kind": "service-manager-action",
        "action": action,
        "service": refreshed_service or {
            "processId": resolved_process_id,
            "apiName": str(service_doc.get("apiName") or ""),
            "status": "DELETED" if action == "delete" else str(service_doc.get("status") or ""),
        },
        "result": payload,
    }, 200


@main_bp.route("/services", methods=["GET"])
def list_services():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied

    denied = _authorize_or_forbid("DATA_ACCESS")
    if denied:
        return denied
    denied = _require_platform_permission("VIEW_SERVICES")
    if denied:
        return denied
    try:
        _use_runtime_workspace()

        success, data = current_app.vdb_client.read_documents("services", {})
        if success:
            session = _session_from_header()
            auth_data = _load_normalized_auth_data()
            production_mode = _production_mode_enabled(auth_data.get("settings") or {})
            summary_mode = str(request.args.get("summary") or "").strip().lower() in {"1", "true", "yes", "on"}
            refresh_arg = request.args.get("refresh")
            if refresh_arg is None:
                auto_refresh = bool((auth_data.get("settings") or {}).get("autoRefreshServiceStatus", True))
            else:
                auto_refresh = str(refresh_arg).strip().lower() in {"1", "true", "yes", "on"}
            rows = []
            for item in _filter_accessible_services(session, list(data or [])):
                synced = _maybe_sync_service_state(item, persist=auto_refresh) if auto_refresh else item
                rows.append(
                    _decorate_service(
                        synced,
                        include_lapis_config=not summary_mode,
                        include_routes=not summary_mode,
                        include_auth_context=not summary_mode,
                        production_mode=production_mode,
                    )
                )
            return jsonify(rows), 200
        return jsonify({"error": "Failed to list services"}), 500
    except Exception as e:
        current_app.logger.error(f"Error listing services: {str(e)}")
        return jsonify({"error": str(e)}), 500


@main_bp.route("/services/<string:process_id>", methods=["GET"])
def get_service(process_id):
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied

    denied = _authorize_or_forbid("DATA_ACCESS")
    if denied:
        return denied
    denied = _require_platform_permission("VIEW_SERVICES")
    if denied:
        return denied

    try:
        _use_runtime_workspace()

        success, services = current_app.vdb_client.read_documents("services", _service_query(process_id))
        if not success or not services:
            # Fallback for lingering process after data reset.
            try:
                import psutil
                pid = int(process_id)
                if psutil.pid_exists(pid):
                    proc = psutil.Process(pid)
                    synthesized = {
                        "apiName": f"Lingering Service {process_id}",
                        "processId": process_id,
                        "status": "RUNNING" if proc.is_running() else "UNKNOWN",
                        "port": None,
                        "lapis_config": {},
        "createdAt": _utcnow_iso(),
                    }
                    return jsonify(_decorate_service(synthesized, production_mode=_production_mode_enabled())), 200
            except Exception:
                pass
            return jsonify({"error": "Service not found"}), 404

        session = _session_from_header()
        if not _session_can_access_service(session, services[0]):
            return jsonify({"error": "Service access denied"}), 403
        synced = _maybe_sync_service_state(services[0], persist=True)
        production_mode = _production_mode_enabled()
        return jsonify(_decorate_service(synced, production_mode=production_mode)), 200
    except Exception as e:
        current_app.logger.error(f"Error loading service {process_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500


@main_bp.route("/services/<string:process_id>/auth-keys", methods=["GET"])
def download_service_auth_keys(process_id):
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied

    denied = _authorize_or_forbid("DATA_ACCESS")
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    try:
        _use_runtime_workspace()
        success, services = current_app.vdb_client.read_documents("services", _service_query(process_id))
        if not success or not services:
            return jsonify({"error": "Service not found"}), 404

        service = services[0]
        session = _session_from_header()
        if not _session_can_access_service(session, service):
            return jsonify({"error": "Service access denied"}), 403

        bundle = _service_auth_key_bundle(service)
        if bundle is None:
            return jsonify({"error": "Authentication key export is available only for auth services"}), 404
        if not bundle.get("files"):
            return jsonify({"error": "No authentication key material is available for export on this service"}), 409
        return jsonify(bundle), 200
    except Exception as e:
        current_app.logger.error(f"Error exporting auth keys for service {process_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500


@main_bp.route("/services/<string:process_id>", methods=["PUT"])
def update_service(process_id):
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied

    denied = _authorize_or_forbid("WRITE")
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        body = {}
    lapis_config = normalize_lapis_config_contract(body.get("lapis_config")) if isinstance(body.get("lapis_config"), dict) else body.get("lapis_config")
    manager_state = body.get("manager_state")
    service_documentation_key = str(body.get("service_documentation_key") or "").strip()
    restart = bool(body.get("restart", True))

    if lapis_config is None and manager_state is None:
        return jsonify({"error": "lapis_config or manager_state is required"}), 400
    if lapis_config is not None and not isinstance(lapis_config, dict):
        return jsonify({"error": "lapis_config must be an object when provided"}), 400
    if manager_state is not None and not isinstance(manager_state, dict):
        return jsonify({"error": "manager_state must be an object when provided"}), 400

    if lapis_config is not None:
        valid, error = Config.validate_lapis_config(lapis_config)
        if not valid:
            return jsonify({"error": f"Invalid LAPIS configuration: {error}"}), 400
        try:
            lapis_config = _sync_lapis_shared_modules(lapis_config, _session_from_header())
            lapis_config = _sync_lapis_service_modules(lapis_config, _session_from_header())
        except ValueError as exc:
            return jsonify({"error": f"Invalid LAPIS configuration: {exc}"}), 400

    try:
        _use_runtime_workspace()

        success, services = current_app.vdb_client.read_documents("services", _service_query(process_id))
        if not success or not services:
            return jsonify({"error": "Service not found"}), 404

        service = services[0]
        session = _session_from_header()
        if not _session_can_access_service(session, service):
            return jsonify({"error": "Service access denied"}), 403
        if isinstance(lapis_config, dict):
            next_auth = lapis_config.get("auth") or {}
            dependency_name = str(next_auth.get("authServiceName") or "").strip().lower()
            protected = any(bool((item or {}).get("requiresAuth")) for item in (lapis_config.get("endpoints") or {}).values())
            if dependency_name and protected and not bool(next_auth.get("isAuthService", False)):
                registry_ok, registry_services = current_app.vdb_client.read_documents("services", {})
                dependency = next((item for item in (registry_services if registry_ok else []) if str((item or {}).get("apiName") or "").strip().lower() == dependency_name), None)
                if dependency and str(dependency.get("status") or "").upper() == "RUNNING":
                    dependency_lapis = dependency.get("lapis_config") or {}
                    dependency_auth = dependency_lapis.get("auth") or {}
                    dependency_meta = dependency_lapis.get("metadata") or {}
                    dependency_custom = dependency_auth.get("customEndpoints") or {}
                    try:
                        dependency_port = int(float(str(dependency.get("port") or "").strip()))
                    except Exception:
                        dependency_port = 0
                    if dependency_port > 0:
                        dependency_base_path = str(dependency_meta.get("basePath") or "").strip().strip("/")
                        dependency_sign_in = str(dependency_custom.get("signIn") or "/signin").strip().lstrip("/")
                        dependency_sign_out = str(dependency_custom.get("signOut") or "/signout").strip().lstrip("/")
                        next_auth["authServiceEndpoint"] = {
                            "baseUrl": f"http://127.0.0.1:{dependency_port}",
                            "signInPath": f"/{dependency_base_path}/{dependency_sign_in}".replace("//", "/"),
                            "signOutPath": f"/{dependency_base_path}/{dependency_sign_out}".replace("//", "/"),
                        }
                        lapis_config["auth"] = next_auth
        old_config = service.get("lapis_config") if isinstance(service.get("lapis_config"), dict) else {}
        if lapis_config is not None and not bool(body.get("acknowledgeImpact")):
            impacts = _lapis_change_impacts(old_config, lapis_config)
            if impacts:
                return jsonify({
                    "error": "This change affects existing service dependencies.",
                    "requiresImpactAcknowledgement": True,
                    "impacts": impacts,
                }), 409
        updates = {
            "apiName": service.get("apiName"),
        "updatedAt": _utcnow_iso(),
        }
        if lapis_config is not None:
            existing_docs_hash = str(
                ((old_config.get("metadata") or {}).get("documentation") or {}).get("keyHash") or ""
            ).strip()
            if not _session_can_modify_service_config(session, service, old_config, lapis_config):
                return jsonify({"error": "Fine-grained permission denied for requested endpoint/model modifications"}), 403
            _prepare_documentation_key(
                lapis_config,
                explicit_key=service_documentation_key,
                existing_hash=existing_docs_hash,
            )
            updates["lapis_config"] = lapis_config
            updates["apiName"] = lapis_config.get("metadata", {}).get("apiName", service.get("apiName"))
        if manager_state is not None:
            updates["managerState"] = manager_state

        updated, update_result = current_app.vdb_client.update_document("services", _service_query(process_id), updates)
        if not updated:
            detail = update_result.get("error") if isinstance(update_result, dict) else ""
            return jsonify({"error": str(detail or "Service configuration was not saved")}), 500

        if restart and lapis_config is not None:
            restarted = current_app.process_manager.restart_service(
                int(process_id), lapis_config, updates["apiName"]
            )
            if not restarted or None in restarted:
                return jsonify({"error": "Service updated but restart failed"}), 500
            new_pid, port = restarted
            pid_updated, _ = current_app.vdb_client.update_document(
                "services",
                _service_query(process_id),
                {
                    "processId": str(new_pid),
                    "port": port,
                    "status": "RUNNING",
        "updatedAt": _utcnow_iso(),
                },
            )
            if not pid_updated:
                current_app.vdb_client.update_document(
                    "services",
                    {"apiName": {"$eq": updates["apiName"]}},
                    {
                        "processId": str(new_pid),
                        "port": port,
                        "status": "RUNNING",
        "updatedAt": _utcnow_iso(),
                    },
                )
            _grant_user_service_access((session or {}).get("username", ""), updates["apiName"], str(new_pid))
            success, reloaded = current_app.vdb_client.read_documents("services", _service_query(str(new_pid)))
            if success and reloaded:
                return jsonify(_decorate_service(reloaded[0], production_mode=_production_mode_enabled())), 200

        success, latest = current_app.vdb_client.read_documents("services", _service_query(process_id))
        if success and latest:
            return jsonify(_decorate_service(latest[0], production_mode=_production_mode_enabled())), 200

        return jsonify({"message": "Service updated"}), 200
    except Exception as e:
        current_app.logger.error(f"Error updating service {process_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500


@main_bp.route("/services/<string:process_id>/test-route", methods=["POST"])
def test_service_route(process_id):
    """Run a configured route from the backend so browser CORS cannot block testing."""
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _authorize_or_forbid("WRITE")
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    endpoint_id = str(body.get("endpointId") or "").strip()
    if not endpoint_id:
        return jsonify({"error": "endpointId is required"}), 400
    try:
        _use_runtime_workspace()
        success, services = current_app.vdb_client.read_documents("services", _service_query(process_id))
        if not success or not services:
            return jsonify({"error": "Service not found"}), 404
        service = services[0]
        session = _session_from_header()
        if not _session_can_access_service(session, service):
            return jsonify({"error": "Service access denied"}), 403
        config = service.get("lapis_config") if isinstance(service.get("lapis_config"), dict) else {}
        endpoint_map = config.get("endpoints") or {}
        endpoint = endpoint_map.get(endpoint_id) if isinstance(endpoint_map, dict) else None
        if not isinstance(endpoint, dict):
            return jsonify({"error": "Endpoint not found in this service"}), 404
        if endpoint.get("enabled") is False:
            return jsonify({"error": "Endpoint is disabled"}), 409
        port = int(service.get("port") or 0)
        if port <= 0:
            return jsonify({"error": "Service is not running"}), 409
        method = str(endpoint.get("method") or "GET").upper()
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            return jsonify({"error": "Endpoint has an unsupported HTTP method"}), 400
        path = str(endpoint.get("path") or "/").strip()
        base_path = str(((config.get("metadata") or {}).get("basePath") or "")).strip().strip("/")
        target = f"http://127.0.0.1:{port}/"
        if base_path:
            target += f"{base_path}/"
        target += path.lstrip("/")
        query = body.get("query") if isinstance(body.get("query"), dict) else {}
        if str(endpoint.get("operationType") or "").lower() == "script":
            query = {"__query": json.dumps(query)}
        headers = {"Accept": "application/json"}
        bearer = str(body.get("bearerToken") or "").strip()
        if bearer and bool(endpoint.get("requiresAuth")):
            headers["Authorization"] = f"Bearer {bearer}"
        has_body = method in {"POST", "PUT", "PATCH", "DELETE"}
        response = requests.request(
            method, target, params=query, json=(body.get("body") if has_body and isinstance(body.get("body"), dict) else {}),
            headers=headers, timeout=30,
        )
        text = response.text
        try:
            response_body = response.json()
        except ValueError:
            response_body = text
        return jsonify({"status": response.status_code, "body": response_body}), 200
    except requests.RequestException as exc:
        return jsonify({"error": f"Unable to reach the service: {exc}"}), 502
    except Exception as exc:
        current_app.logger.error(f"Error testing service route {process_id}: {exc}")
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/services/<string:process_id>/auth-action", methods=["POST"])
def proxy_service_auth_action(process_id):
    """Run an auth setup action through Liwiro instead of the browser.

    Generated services run on a different local origin, so direct browser calls to
    their sign-in and setup routes are subject to CORS.  This deliberately allows
    only the fixed auth actions derived from the service LAPIS configuration.
    """
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _authorize_or_forbid("WRITE")
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    action = str(body.get("action") or "").strip().lower()
    if action not in {"signin", "signout", "reset-super-admin"}:
        return jsonify({"error": "Unsupported auth action"}), 400

    try:
        _use_runtime_workspace()
        success, services = current_app.vdb_client.read_documents("services", _service_query(process_id))
        if not success or not services:
            return jsonify({"error": "Service not found"}), 404
        service = services[0]
        session = _session_from_header()
        if not _session_can_access_service(session, service):
            return jsonify({"error": "Service access denied"}), 403

        config = service.get("lapis_config") if isinstance(service.get("lapis_config"), dict) else {}
        auth_config = config.get("auth") if isinstance(config.get("auth"), dict) else {}
        custom_endpoints = auth_config.get("customEndpoints") if isinstance(auth_config.get("customEndpoints"), dict) else {}
        port = int(service.get("port") or 0)
        if port <= 0:
            return jsonify({"error": "Service is not running"}), 409

        if action == "reset-super-admin":
            if not bool(auth_config.get("isAuthService")):
                return jsonify({"error": "Only an authentication service can reset its super admin"}), 400
            path = "/liwiro/setup/reset-super-admin"
        else:
            endpoint_key = "signIn" if action == "signin" else "signOut"
            default_path = "/auth/signin" if action == "signin" else "/auth/signout"
            path = str(custom_endpoints.get(endpoint_key) or default_path) if bool(custom_endpoints.get("enabled")) else default_path

        base_path = "" if action == "reset-super-admin" else str(((config.get("metadata") or {}).get("basePath") or "")).strip().strip("/")
        target = f"http://127.0.0.1:{port}/"
        if base_path:
            target += f"{base_path}/"
        target += path.lstrip("/")
        headers = {"Accept": "application/json"}
        if action == "reset-super-admin":
            setup_key = str(body.get("setupApiKey") or "").strip()
            if not setup_key:
                return jsonify({"error": "Setup API key is required"}), 400
            headers["X-Liwiro-Setup-Key"] = setup_key
        elif action == "signout":
            bearer = str(body.get("bearerToken") or "").strip()
            if not bearer:
                return jsonify({"error": "Bearer token is required for sign out"}), 400
            headers["Authorization"] = f"Bearer {bearer}"

        payload = body.get("body") if isinstance(body.get("body"), dict) else {}
        response = requests.post(target, json=payload, headers=headers, timeout=30)
        try:
            response_body = response.json()
        except ValueError:
            response_body = response.text
        return jsonify({"status": response.status_code, "body": response_body}), 200
    except requests.RequestException as exc:
        return jsonify({"error": f"Unable to reach the service: {exc}"}), 502
    except Exception as exc:
        current_app.logger.error(f"Error proxying auth action for service {process_id}: {exc}")
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/services/<string:process_id>/stop", methods=["POST"])
def stop_service(process_id):
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied

    denied = _authorize_or_forbid("WRITE")
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied
    try:
        session = _session_from_header()
        payload, status = _stop_service_via_manager_action(process_id, session)
        return jsonify(payload), status
    except Exception as e:
        current_app.logger.error(f"Error stopping service: {str(e)}")
        return jsonify({"error": str(e)}), 500


@main_bp.route("/services/<string:process_id>/start", methods=["POST"])
def start_service(process_id):
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied

    denied = _authorize_or_forbid("WRITE")
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied
    try:
        session = _session_from_header()
        payload, status = _start_service_via_manager_action(process_id, session)
        return jsonify(payload), status
    except Exception as e:
        current_app.logger.error(f"Error restarting service: {str(e)}")
        return jsonify({"error": str(e)}), 500


@main_bp.route("/services/<string:process_id>/delete", methods=["DELETE"])
def delete_service(process_id):
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied

    denied = _authorize_or_forbid("WRITE")
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        body = {}
    delete_data_flag = str(
        request.args.get("delete_data")
        or request.args.get("deleteData")
        or body.get("delete_data")
        or body.get("deleteData")
        or ""
    ).strip().lower() in {"1", "true", "yes", "on"}

    try:
        session = _session_from_header()
        payload, status = _delete_service_via_manager_action(process_id, session, delete_data_flag)
        return jsonify(payload), status
    except Exception as e:
        current_app.logger.error(f"Error deleting service: {str(e)}")
        return jsonify({"error": str(e)}), 500


@main_bp.route("/platform/settings", methods=["GET"])
def get_platform_settings():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied

    data = _load_normalized_auth_data()
    return jsonify(_platform_settings_with_defaults(data.get("settings") or {})), 200


@main_bp.route("/platform/api/governance", methods=["GET"])
def get_api_governance_manifest():
    """Expose the platform's API governance contract to operator tooling."""
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _authorize_or_forbid("DATA_ACCESS")
    if denied:
        return denied
    denied = _require_platform_permission("VIEW_SERVICES")
    if denied:
        return denied

    return jsonify(
        {
            "title": "Liwiro API Governance",
            "version": "1.0",
            "sourceOfTruth": "LAPIS",
            "contractStages": [
                "author",
                "validate",
                "generate",
                "document",
                "operate",
                "audit",
            ],
            "controls": {
                "schemaValidation": "/platform/lapis/validate",
                "serviceReadiness": "services[].governance",
                "rateLimiting": "metadata.rateLimiting",
                "authentication": "auth",
                "authorization": "endpoint.requiresAuth and platform RBAC",
                "runtimeWorkspace": "metadata.database",
                "documentation": "metadata.documentation",
                "scriptValidation": "endpoint.versaScript",
            },
            "management": {
                "create": {"method": "POST", "path": "/generate"},
                "list": {"method": "GET", "path": "/services"},
                "inspect": {"method": "GET", "path": "/services/{processId}"},
                "update": {"method": "PUT", "path": "/services/{processId}"},
                "start": {"method": "POST", "path": "/services/{processId}/start"},
                "stop": {"method": "POST", "path": "/services/{processId}/stop"},
                "delete": {"method": "DELETE", "path": "/services/{processId}/delete"},
                "testRoute": {"method": "POST", "path": "/services/{processId}/test-route"},
            },
            "serviceDocumentation": {
                "html": "/liwiro/docs",
                "json": "/liwiro/docs.json",
                "endpointToggle": "/liwiro/docs/endpoints/{endpointId}/enabled",
            },
            "security": {
                "setupCredentialsAreSecrets": True,
                "seedPasswordsAreHashedAndTransient": True,
                "managerStateIsSeparateFromLapis": True,
            },
        }
    ), 200


@main_bp.route("/platform/settings", methods=["PUT"])
def update_platform_settings():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_super_admin()
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    allowed = {
        "productionMode",
        "startServicesOnStartup",
        "autoRefreshServiceStatus",
        "deleteDataWithServiceByDefault",
        "startServicesAfterGenerationByDefault",
        "retryFailedBatchOpsByDefault",
    }
    updates = {k: body.get(k) for k in allowed if k in body}
    raw_feature_flags = body.get("featureFlags") if isinstance(body.get("featureFlags"), dict) else None
    if not updates and raw_feature_flags is None:
        return jsonify({"error": "No valid settings provided"}), 400

    data = _load_normalized_auth_data()
    settings = _platform_settings_with_defaults(data.get("settings") or {})
    for key, value in updates.items():
        settings[key] = bool(value)
    if raw_feature_flags is not None:
        settings["featureFlags"] = feature_flags_with_defaults(raw_feature_flags)
    data["settings"] = {
        **{key: settings.get(key) for key in allowed},
        "featureFlags": feature_flags_with_defaults(settings.get("featureFlags") if isinstance(settings.get("featureFlags"), dict) else {}),
    }
    _save_normalized_auth_data(data)
    return jsonify(_platform_settings_with_defaults(data["settings"])), 200


@main_bp.route("/platform/feature-flags", methods=["GET"])
def get_platform_feature_flags():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied

    data = _load_normalized_auth_data()
    settings = _platform_settings_with_defaults(data.get("settings") or {})
    return jsonify(
        {
            "featureFlags": settings.get("featureFlags") or {},
            "featureFlagDefinitions": settings.get("featureFlagDefinitions") or feature_flag_definitions(),
        }
    ), 200


@main_bp.route("/platform/users", methods=["GET"])
def list_platform_users():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_super_admin()
    if denied:
        return denied

    data = _load_normalized_auth_data()
    users = []
    for user in data.get("users", []):
        users.append(
            {
                "username": user.get("username"),
                "role": _normalize_platform_role(user.get("role")),
                "service_access": _normalize_service_access(user.get("service_access")),
                "permissions": _normalize_user_permissions(user.get("permissions")),
                "liwiro_rbac": _normalize_liwiro_rbac(user.get("liwiro_rbac"), is_super_admin=bool(user.get("is_super_admin", False))),
                "is_super_admin": bool(user.get("is_super_admin", False)),
                "created_at": user.get("created_at"),
            }
        )
    return jsonify(users), 200


@main_bp.route("/platform/users", methods=["POST"])
def create_platform_user():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_super_admin()
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    username = _normalize_username(body.get("username"))
    password = str(body.get("password") or "").strip()
    role = _normalize_platform_role(body.get("role"))
    service_access = _normalize_service_access(body.get("service_access") or body.get("serviceAccess"))
    if not service_access:
        service_access = [WILDCARD_SERVICE_ACCESS]
    if role == ROLE_ADMIN:
        service_access = [WILDCARD_SERVICE_ACCESS]
    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    data = _load_normalized_auth_data()
    if _find_auth_user(data, username):
        return jsonify({"error": f"User '{username}' already exists"}), 409

    data.setdefault("users", []).append(
        {
            "username": username,
            "password_hash": generate_password_hash(password),
            "role": role,
            "service_access": service_access,
            "permissions": _normalize_user_permissions(body.get("permissions")),
            "liwiro_rbac": _normalize_liwiro_rbac(body.get("liwiro_rbac"), is_super_admin=False),
            "is_super_admin": False,
        "created_at": _utcnow_iso(),
        }
    )
    _save_normalized_auth_data(data)
    return jsonify({
        "username": username,
        "role": role,
        "service_access": service_access,
        "permissions": _normalize_user_permissions(body.get("permissions")),
        "liwiro_rbac": _normalize_liwiro_rbac(body.get("liwiro_rbac"), is_super_admin=False),
        "is_super_admin": False,
    }), 201


@main_bp.route("/platform/users/<string:username>", methods=["PUT"])
def update_platform_user(username):
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_super_admin()
    if denied:
        return denied

    target_username = _normalize_username(username)
    body = request.get_json(silent=True) or {}
    data = _load_normalized_auth_data()
    users = data.get("users", [])
    target = None
    for user in users:
        if _normalize_username(user.get("username")) == target_username:
            target = user
            break
    if not target:
        return jsonify({"error": "User not found"}), 404
    if bool(target.get("is_super_admin", False)):
        return jsonify({"error": "Super admin account cannot be edited"}), 400

    if "role" in body:
        target["role"] = _normalize_platform_role(body.get("role"))
    if "service_access" in body or "serviceAccess" in body:
        target["service_access"] = _normalize_service_access(body.get("service_access") or body.get("serviceAccess"))
    if "permissions" in body:
        target["permissions"] = _normalize_user_permissions(body.get("permissions"))
    if "liwiro_rbac" in body:
        target["liwiro_rbac"] = _normalize_liwiro_rbac(body.get("liwiro_rbac"), is_super_admin=False)
    if _normalize_platform_role(target.get("role")) == ROLE_ADMIN:
        target["service_access"] = [WILDCARD_SERVICE_ACCESS]
    if "password" in body and str(body.get("password") or "").strip():
        target["password_hash"] = generate_password_hash(str(body.get("password")).strip())

    _save_normalized_auth_data(data)
    return jsonify({
        "username": target.get("username"),
        "role": _normalize_platform_role(target.get("role")),
        "service_access": _normalize_service_access(target.get("service_access")),
        "permissions": _normalize_user_permissions(target.get("permissions")),
        "liwiro_rbac": _normalize_liwiro_rbac(target.get("liwiro_rbac"), is_super_admin=bool(target.get("is_super_admin", False))),
        "is_super_admin": bool(target.get("is_super_admin", False)),
    }), 200


@main_bp.route("/platform/vdb/connection", methods=["GET"])
def platform_vdb_connection():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    session = _session_from_header() or {}
    connection = _vdb_portal_connection_info()
    return jsonify(
        {
            **connection,
            "can_use_app_mode": True,
            "can_use_super_admin_mode": _is_super_admin_session(session),
        }
    ), 200


@main_bp.route("/platform/vdb/connection", methods=["PUT"])
def update_platform_vdb_connection():
    """Repair persisted backend VDB runtime credentials from Settings."""
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_super_admin()
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"error": "VDB connection settings must be a JSON object"}), 400
    current = _vdb_portal_connection_info()
    transport = normalize_vdb_transport_mode(body.get("vdb_transport") or current.get("vdb_transport"))
    server_url = str(body.get("vdb_server_url") or current.get("vdb_server_url") or "").strip()
    unix_socket = str(body.get("vdb_unix_socket_path") or current.get("vdb_unix_socket_path") or "").strip()
    named_pipe = _normalized_named_pipe_path(body.get("vdb_named_pipe_path") or current.get("vdb_named_pipe_path") or "")
    username = _normalize_username(body.get("vdb_app_username") or current.get("vdb_app_username"))
    password = str(body.get("vdb_app_password") or "").strip() or str(_runtime_cfg("VDB_PASSWORD") or "").strip()
    domain = str(body.get("liwiro_domain") or current.get("liwiro_domain") or "").strip()
    db = str(body.get("liwiro_db") or current.get("liwiro_db") or "").strip()
    if not username or not password:
        return jsonify({"error": "VDB username and password are required. Enter them in Settings."}), 400
    if transport == "http" and not server_url:
        return jsonify({"error": "VDB server URL is required for HTTP transport"}), 400

    if transport in {"http", "namedpipe"}:
        server_url = str(normalize_local_vdb_http_url(server_url or "http://127.0.0.1:1957")).strip()
    requested_ipc = transport in {"unixsocket", "namedpipe"}
    if requested_ipc:
        stopped, stop_message = _stop_autostarted_vdb_http(current_app, server_url)
        if not stopped:
            return jsonify({
                "error": f"Cannot switch to VDB IPC: {stop_message}",
                "revertedTransport": "http",
                "vdb_transport": "http",
            }), 503
    ready, ready_message = _ensure_vdb_transport_ready(current_app, transport, server_url, unix_socket, named_pipe)
    if not ready:
        if requested_ipc:
            fallback_url = str(normalize_local_vdb_http_url(
                current.get("vdb_server_url") or server_url or "http://127.0.0.1:1957"
            )).strip()
            http_ready, http_message = _autostart_local_vdb_http_if_needed(current_app, fallback_url)
            if http_ready:
                _apply_runtime_vdb_config(
                    vdb_transport="http",
                    vdb_server_url=fallback_url,
                    vdb_unix_socket_path=unix_socket,
                    vdb_named_pipe_path=named_pipe,
                    vdb_username=username,
                    vdb_password=password,
                    liwiro_domain=domain,
                    liwiro_db=db,
                )
                _persist_runtime_vdb_env(
                    vdb_transport="http",
                    vdb_server_url=fallback_url,
                    vdb_unix_socket_path=unix_socket,
                    vdb_named_pipe_path=named_pipe,
                    vdb_username=username,
                    vdb_password=password,
                    liwiro_domain=domain,
                    liwiro_db=db,
                )
                auth_data = _load_normalized_auth_data()
                auth_data.update({"vdb_transport": "http", "vdb_server_url": fallback_url})
                _save_normalized_auth_data(auth_data)
                current_app.vdb_client = None
            return jsonify({
                "error": (
                    "VDB IPC was unavailable; reverted to HTTP server. "
                    f"IPC: {ready_message}. HTTP: {http_message}"
                ),
                "revertedTransport": "http",
                "vdb_transport": "http" if http_ready else transport,
            }), 503
        return jsonify({"error": _friendly_transport_prepare_error(transport, ready_message, named_pipe_path=named_pipe)}), 503

    try:
        _apply_runtime_vdb_config(
            vdb_transport=transport,
            vdb_server_url=server_url,
            vdb_unix_socket_path=unix_socket,
            vdb_named_pipe_path=named_pipe,
            vdb_username=username,
            vdb_password=password,
            liwiro_domain=domain,
            liwiro_db=db,
        )
        _persist_runtime_vdb_env(
            vdb_transport=transport,
            vdb_server_url=server_url,
            vdb_unix_socket_path=unix_socket,
            vdb_named_pipe_path=named_pipe,
            vdb_username=username,
            vdb_password=password,
            liwiro_domain=domain,
            liwiro_db=db,
        )
        auth_data = _load_normalized_auth_data()
        auth_data.update({
            "vdb_transport": transport,
            "vdb_server_url": server_url,
            "vdb_unix_socket_path": unix_socket,
            "vdb_named_pipe_path": named_pipe,
            "vdb_username": username,
            "liwiro_domain": domain,
            "liwiro_db": db,
        })
        _save_normalized_auth_data(auth_data)
        current_app.vdb_client = None
        ok, message = _initialize_vdb_runtime(current_app)
        _set_vdb_runtime_state(current_app, ok, "" if ok else message)
        payload = {
            **_vdb_portal_connection_info(),
            "can_use_app_mode": True,
            "can_use_super_admin_mode": True,
            "vdbRuntimeReady": bool(ok),
        }
        if not ok:
            payload["error"] = f"Credentials saved, but VDB runtime initialization failed: {message}"
            return jsonify(payload), 503
        return jsonify(payload), 200
    except Exception as exc:
        current_app.logger.exception("Failed to persist VDB runtime connection settings")
        return jsonify({"error": f"Failed to save VDB runtime settings: {exc}"}), 500


@main_bp.route("/platform/vdb/session", methods=["POST"])
def create_vdb_portal_session():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    mode = str(body.get("mode") or "app").strip().lower()
    requester = _session_from_header() or {}
    requester_is_super_admin = _is_super_admin_session(requester)
    requester_username = _normalize_username(requester.get("username"))
    conn = _vdb_portal_connection_info()
    vdb_transport = normalize_vdb_transport_mode(body.get("vdb_transport") or conn.get("vdb_transport") or default_vdb_transport_mode())
    server_url = str(body.get("vdb_server_url") or conn.get("vdb_server_url") or "").strip()
    portal_socket_path = str(body.get("vdb_unix_socket_path") or _runtime_cfg("VDB_UNIX_SOCKET_PATH") or "").strip()
    portal_named_pipe_path = _normalized_named_pipe_path(
        body.get("vdb_named_pipe_path") or _runtime_cfg("VDB_NAMED_PIPE_PATH") or ""
    )
    save_credentials = bool(body.get("save_credentials", False))
    if vdb_transport == "http" and not server_url:
        return jsonify({"error": "VDB server URL is required"}), 400

    if mode == "super_admin":
        if not requester_is_super_admin:
            return jsonify({"error": "Only Liwiro super admin can create a VDB super admin session"}), 403
        username = _normalize_username(
            body.get("username") or body.get("vdb_super_admin_username") or conn.get("vdb_super_admin_username")
        )
        password = str(
            body.get("password")
            or body.get("vdb_super_admin_password")
            or _runtime_cfg("VDB_SUPER_ADMIN_PASSWORD")
            or ""
        ).strip()
    else:
        username = _normalize_username(body.get("username") or conn.get("vdb_app_username"))
        password = str(body.get("password") or "").strip()
        if not password:
            password = str(_runtime_cfg("VDB_PASSWORD") or "").strip()
        mode = "app"

    if not username or not password:
        return jsonify({"error": "VDB username and password are required"}), 400

    ready, ready_msg = _ensure_vdb_transport_ready(
        current_app,
        vdb_transport,
        server_url,
        portal_socket_path,
        portal_named_pipe_path,
    )
    if not ready:
        return jsonify(
            {
                "error": "VDB transport could not be prepared for portal session: "
                + _friendly_transport_prepare_error(
                    vdb_transport,
                    ready_msg,
                    named_pipe_path=portal_named_pipe_path,
                )
            }
        ), 503

    try:
        transport = build_vdb_transport(
            current_app,
            server_url=server_url,
            socket_path=portal_socket_path,
            named_pipe_path=portal_named_pipe_path,
            transport_mode=vdb_transport,
            prefer_socket=True,
            allow_http_fallback=True,
        )
        auth_json = transport.auth(username, password, timeout=30)
        session_id = str((auth_json or {}).get("sessionId") or "").strip()
        if not session_id:
            return jsonify({"error": "VDB authentication succeeded but no sessionId was returned"}), 502
        if isinstance(transport, VDBUnixSocketTransport):
            transport_kind = "unixsocket"
        elif isinstance(transport, VDBNamedPipeTransport):
            transport_kind = "namedpipe"
        else:
            transport_kind = "http"
        vdb_unix_socket_path = portal_socket_path
        vdb_named_pipe_path = portal_named_pipe_path
    except VDBTransportRequestError as exc:
        return jsonify(
            {
                "error": _summarize_vdb_auth_failure(
                    exc.payload if isinstance(exc.payload, dict) else (exc.raw_body or str(exc)),
                    username,
                )
            }
        ), 401
    except Exception as exc:
        return jsonify({"error": f"Failed to authenticate against VDB: {exc}"}), 500

    portal_token = secrets.token_urlsafe(36)
    issued_at = datetime.now(timezone.utc).isoformat()
    current_app.vdb_portal_sessions[portal_token] = {
        "mode": mode,
        "username": username,
        "owner_username": requester_username,
        "vdb_transport": transport_kind,
        "vdb_server_url": server_url,
        "vdb_unix_socket_path": vdb_unix_socket_path,
        "vdb_named_pipe_path": vdb_named_pipe_path,
        "transport_kind": transport_kind,
        "session_id": session_id,
        "issued_at": issued_at,
    }

    if mode == "super_admin" and save_credentials and requester_is_super_admin:
        auth_data = _load_normalized_auth_data()
        auth_data["vdb_super_admin_username"] = username
        _save_normalized_auth_data(auth_data)

    whoami_ok, whoami_result = _vdb_portal_query(
        current_app.vdb_portal_sessions[portal_token], {"action": "whoami"}
    )
    context_ok, context_result = _vdb_portal_query(
        current_app.vdb_portal_sessions[portal_token], {"action": "context"}
    )
    return jsonify(
        {
            "portalToken": portal_token,
            "mode": mode,
            "username": username,
            "owner_username": requester_username,
            "vdb_transport": transport_kind,
            "vdb_server_url": server_url,
            "vdb_unix_socket_path": vdb_unix_socket_path,
            "vdb_named_pipe_path": vdb_named_pipe_path,
            "issuedAt": issued_at,
            "whoami": whoami_result if whoami_ok else {},
            "context": context_result if context_ok else {},
        }
    ), 200


@main_bp.route("/platform/vdb/session", methods=["DELETE"])
def delete_vdb_portal_session():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied

    session_payload, token = _vdb_portal_session_from_header()
    if token and not session_payload:
        return jsonify({"error": "VDB portal session not found or not owned by current user"}), 404
    if token:
        current_app.vdb_portal_sessions.pop(token, None)
    return jsonify({"message": "VDB portal session cleared"}), 200


@main_bp.route("/platform/vdb/whoami", methods=["GET"])
def platform_vdb_whoami():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied

    session_payload, _ = _vdb_portal_session_from_header()
    if not session_payload:
        return jsonify({"error": "VDB portal session required"}), 401
    whoami_ok, whoami_result = _vdb_portal_query(session_payload, {"action": "whoami"})
    if not whoami_ok:
        return jsonify(whoami_result), 502
    list_ok, list_result = _vdb_portal_query(session_payload, {"action": "list", "resource": "domains"})
    tumi_ok, tumi_result = _vdb_portal_query(session_payload, {"action": "tumi", "operation": "list", "resource": "owned_domains"})

    payload = dict(whoami_result if isinstance(whoami_result, dict) else {"data": whoami_result})
    whoami_data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    whoami_owned = _normalize_domain_list(
        _vdb_data_as_list(whoami_data.get("owned_domains") or whoami_data.get("ownedDomains") or [])
    )
    tumi_owned = _normalize_domain_list(_vdb_data_as_list(tumi_result if tumi_ok else []))
    effective_owned = tumi_owned or whoami_owned
    normalized_owned = effective_owned
    if list_ok:
        visible_domains = _normalize_domain_list(_vdb_data_as_list(list_result))
        normalized_owned = [domain for domain in effective_owned if domain in visible_domains]
    if isinstance(whoami_data, dict):
        whoami_data["owned_domains"] = normalized_owned
        whoami_data["ownedDomains"] = normalized_owned
        payload["data"] = whoami_data
    return jsonify(payload), 200


@main_bp.route("/platform/vdb/context", methods=["GET"])
def platform_vdb_context():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied

    session_payload, _ = _vdb_portal_session_from_header()
    if not session_payload:
        return jsonify({"error": "VDB portal session required"}), 401
    ok, result = _vdb_portal_query(session_payload, {"action": "context"})
    if not ok:
        return jsonify(result), 502
    return jsonify(result), 200


@main_bp.route("/platform/vdb/query", methods=["POST"])
def platform_vdb_query():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    session_payload, _ = _vdb_portal_session_from_header()
    if not session_payload:
        return jsonify({"error": "VDB portal session required"}), 401

    body = request.get_json(silent=True)
    query = body.get("query") if isinstance(body, dict) and "query" in body else body
    if not isinstance(query, str) or not query.strip():
        return jsonify({"error": "Enter a readable VDB command, such as read users or read collection orders"}), 400
    try:
        query = _canonicalize_vdb_query(query)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    ok, result = _vdb_portal_query(session_payload, query)
    if not ok:
        return jsonify(result), 502
    return jsonify(result), 200


@main_bp.route("/platform/vdb/options", methods=["GET"])
def platform_vdb_options():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    session_payload, _ = _vdb_portal_session_from_header()
    if not session_payload:
        return jsonify({"error": "VDB portal session required"}), 401

    options: dict = {
        "domains": [],
        "dbs": [],
        "collections": [],
        "models": [],
        "scripts": [],
        "users": [],
        "roles": [],
        "permissions": [],
        "helpTopics": ["domains", "dbs", "collections", "scripts", "users", "roles", "permissions", "commands"],
    }

    list_domains_ok, list_domains_result = _vdb_portal_query(session_payload, {"action": "list", "resource": "domains"})
    if list_domains_ok:
        options["domains"] = _vdb_data_as_str_list(list_domains_result)

    list_dbs_ok, list_dbs_result = _vdb_portal_query(session_payload, {"action": "list", "resource": "dbs"})
    if list_dbs_ok:
        options["dbs"] = _vdb_data_as_str_list(list_dbs_result)

    list_collections_ok, list_collections_result = _vdb_portal_query(session_payload, {"action": "list", "resource": "collections"})
    if list_collections_ok:
        options["collections"] = _vdb_data_as_str_list(list_collections_result)

    list_models_ok, list_models_result = _vdb_portal_query(session_payload, {"action": "list", "resource": "models"})
    if list_models_ok:
        options["models"] = _vdb_data_as_str_list(list_models_result)

    list_scripts_ok, list_scripts_result = _vdb_portal_query(session_payload, {"action": "list", "resource": "scripts"})
    if list_scripts_ok:
        options["scripts"] = _vdb_data_as_str_list(list_scripts_result)

    tumi_users_ok, tumi_users_result = _vdb_portal_query(session_payload, {"action": "tumi", "operation": "list", "resource": "users"})
    if tumi_users_ok:
        options["users"] = _vdb_data_as_str_list(tumi_users_result)

    tumi_roles_ok, tumi_roles_result = _vdb_portal_query(session_payload, {"action": "tumi", "operation": "list", "resource": "roles"})
    if tumi_roles_ok:
        options["roles"] = _vdb_data_as_str_list(tumi_roles_result)

    tumi_permissions_ok, tumi_permissions_result = _vdb_portal_query(session_payload, {"action": "tumi", "operation": "list", "resource": "permissions"})
    if tumi_permissions_ok:
        options["permissions"] = _vdb_data_as_str_list(tumi_permissions_result)

    return jsonify(options), 200


@main_bp.route("/platform/vdb/rbac/overview", methods=["GET"])
def platform_vdb_rbac_overview():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied

    session_payload, error = _resolve_vdb_rbac_session()
    if error:
        return jsonify({"error": error.get("error")}), int(error.get("status_code") or 400)

    ok, payload = _collect_vdb_rbac_overview(session_payload)
    if not ok:
        return jsonify(payload if isinstance(payload, dict) else {"error": "Failed to load VDB RBAC overview"}), 502
    return jsonify(payload), 200


@main_bp.route("/platform/vdb/rbac/users/<string:username>/permissions", methods=["GET"])
def platform_vdb_rbac_user_permissions(username: str):
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied

    session_payload, error = _resolve_vdb_rbac_session()
    if error:
        return jsonify({"error": error.get("error")}), int(error.get("status_code") or 400)

    normalized = _normalize_username(username)
    if not normalized:
        return jsonify({"error": "username is required"}), 400
    ok, result = _vdb_portal_query(session_payload, {"action": "tumi", "operation": "list", "resource": "permissions", "username": normalized})
    if not ok:
        return jsonify(result if isinstance(result, dict) else {"error": "Failed to load user permissions"}), 502
    return jsonify(_normalize_vdb_user_permissions_payload(normalized, result)), 200


@main_bp.route("/platform/vdb/rbac/command", methods=["POST"])
def platform_vdb_rbac_command():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied

    command = request.get_data(as_text=True).strip()
    if not command:
        return jsonify({"error": "Enter a readable RBAC command, such as create user alice"}), 400
    try:
        from app.vdb_commands import parse_command
        parsed = parse_command(command)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if parsed.get("action") != "tumi":
        return jsonify({"error": "This endpoint accepts readable user, role, grant, revoke, or transfer commands"}), 400

    session_payload, error = _resolve_vdb_rbac_session()
    if error:
        return jsonify({"error": error.get("error")}), int(error.get("status_code") or 400)

    try:
        tumi_query = _canonicalize_vdb_query(command)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    ok, result = _vdb_portal_query(session_payload, tumi_query)
    if not ok:
        return jsonify(result if isinstance(result, dict) else {"error": "VDB RBAC command failed"}), 502
    return jsonify(result), 200


@main_bp.route("/platform/vi/modules/catalog", methods=["GET"])
def platform_vi_module_catalog():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("VIEW_SERVICES")
    if denied:
        return denied

    session = _session_from_header()
    modules, accessible_domains = _visible_vi_modules_for_session(session, include_source=False)
    return jsonify(
        {
            "username": _normalize_username((session or {}).get("username")),
            "is_super_admin": _is_super_admin_session(session),
            "available_domains": accessible_domains,
            "reserved_names": reserved_module_names(),
            "modules": [_serialize_vi_module(module, include_source=False) for module in modules],
        }
    ), 200


@main_bp.route("/platform/vi/modules", methods=["GET"])
def platform_vi_list_modules():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("VIEW_SERVICES")
    if denied:
        return denied

    session = _session_from_header()
    modules, _ = _visible_vi_modules_for_session(session, include_source=False)
    return jsonify({"modules": [_serialize_vi_module(module, include_source=False) for module in modules]}), 200


@main_bp.route("/platform/vi/modules", methods=["POST"])
def platform_vi_create_module():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        body = {}
    session = _session_from_header()
    accessible_domains = _session_accessible_domains(session)

    try:
        name = validate_module_name(body.get("name"))
        if load_module_record(name, include_source=False, app_config=current_app.config):
            return jsonify({"error": f"VI module '{name}' already exists"}), 409
        record, source = _normalize_vi_module_body(body, existing=None, session=session, accessible_domains=accessible_domains)
        created = write_module_record(record, source, current_app.config)
        return jsonify({"module": _serialize_vi_module(created, include_source=True)}), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.error(f"Failed to create VI module: {exc}")
        return jsonify({"error": f"Failed to create VI module: {exc}"}), 500


@main_bp.route("/platform/vi/modules/<string:module_name>", methods=["GET"])
def platform_vi_get_module(module_name: str):
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("VIEW_SERVICES")
    if denied:
        return denied

    session = _session_from_header()
    module = load_module_record(module_name, include_source=True, app_config=current_app.config)
    if not module:
        return jsonify({"error": "VI module not found"}), 404
    accessible_domains = _session_accessible_domains(session)
    if not _vi_module_visible_to_session(module, session, accessible_domains):
        return jsonify({"error": "VI module access denied"}), 403
    return jsonify({"module": _serialize_vi_module(module, include_source=True)}), 200


@main_bp.route("/platform/vi/modules/<string:module_name>", methods=["PUT"])
def platform_vi_update_module(module_name: str):
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        body = {}
    session = _session_from_header()
    accessible_domains = _session_accessible_domains(session)
    existing = load_module_record(module_name, include_source=True, app_config=current_app.config)
    if not existing:
        return jsonify({"error": "VI module not found"}), 404
    if not _vi_module_editable_by_session(existing, session):
        return jsonify({"error": "Only the module owner or a super admin can edit this module"}), 403

    try:
        record, source = _normalize_vi_module_body(body, existing=existing, session=session, accessible_domains=accessible_domains)
        updated = write_module_record(record, source, current_app.config)
        return jsonify({"module": _serialize_vi_module(updated, include_source=True)}), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.error(f"Failed to update VI module {module_name}: {exc}")
        return jsonify({"error": f"Failed to update VI module: {exc}"}), 500


@main_bp.route("/platform/vi/modules/<string:module_name>", methods=["DELETE"])
def platform_vi_delete_module(module_name: str):
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    session = _session_from_header()
    existing = load_module_record(module_name, include_source=False, app_config=current_app.config)
    if not existing:
        return jsonify({"error": "VI module not found"}), 404
    if not _vi_module_editable_by_session(existing, session):
        return jsonify({"error": "Only the module owner or a super admin can delete this module"}), 403
    deleted = delete_module_record(module_name, current_app.config)
    if not deleted:
        return jsonify({"error": "VI module not found"}), 404
    return jsonify({"message": f"Deleted VI module '{normalize_module_name(module_name)}'"}), 200


@main_bp.route("/platform/vi/modules/<string:module_name>/domains", methods=["POST"])
def platform_vi_assign_module_domain(module_name: str):
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    session = _session_from_header()
    accessible_domains = _session_accessible_domains(session)
    module = load_module_record(module_name, include_source=True, app_config=current_app.config)
    if not module:
        return jsonify({"error": "VI module not found"}), 404
    if not _vi_module_visible_to_session(module, session, accessible_domains):
        return jsonify({"error": "VI module access denied"}), 403
    if str(module.get("scope") or "").strip().lower() == "global":
        return jsonify({"module": _serialize_vi_module(module, include_source=True)}), 200

    body = request.get_json(silent=True) or {}
    domain_name = str(body.get("domain") or body.get("service_domain") or "").strip().lower()
    if not domain_name:
        return jsonify({"error": "domain is required"}), 400
    if accessible_domains and not _is_super_admin_session(session) and domain_name not in accessible_domains:
        return jsonify({"error": f"Domain '{domain_name}' is not available to the current user"}), 403

    next_domains = _normalize_domain_list((module.get("assigned_domains") or []) + [domain_name])
    next_owner_domains = _normalize_domain_list((module.get("owner_domains") or []) + [domain_name])
    updated = write_module_record(
        {
            **_module_source_payload(module),
            "assigned_domains": next_domains,
            "owner_domains": next_owner_domains,
        },
        str(module.get("source") or ""),
        current_app.config,
    )
    return jsonify({"module": _serialize_vi_module(updated, include_source=True)}), 200


@main_bp.route("/platform/vi/connection", methods=["GET"])
def platform_vi_connection():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied

    verun_root = _resolve_verun_root()
    vi_jar = _resolve_vi_jar_path(verun_root)
    source_dir = _resolve_vi_portal_source_dir()
    session_key = _vi_repl_session_key()
    repl_session = getattr(current_app, "vi_repl_sessions", {}).get(session_key)
    repl_active = bool(repl_session and repl_session.get("process") and repl_session["process"].poll() is None)
    terminal_session = getattr(current_app, "vi_terminal_sessions", {}).get(session_key)
    terminal_status = _vi_terminal_session_metadata(session_key, terminal_session)
    return jsonify(
        {
            "verun_root": str(verun_root) if verun_root else "",
            "vi_jar_path": str(vi_jar) if vi_jar else "",
            "vi_jar_exists": bool(vi_jar and vi_jar.is_file()),
            "source_dir": str(source_dir),
            "files_count": _count_vi_portal_files(source_dir),
            "repl_active": repl_active,
            "repl_prompt": str((repl_session or {}).get("prompt") or VI_REPL_PRIMARY_PROMPT),
            "terminal_active": bool(terminal_status.get("active")),
            "terminal_prompt": str(terminal_status.get("prompt") or VI_REPL_PRIMARY_PROMPT),
            "terminal_cols": int(terminal_status.get("cols") or VI_TERMINAL_DEFAULT_COLS),
            "terminal_rows": int(terminal_status.get("rows") or VI_TERMINAL_DEFAULT_ROWS),
            "terminal_session_key": str(terminal_status.get("sessionKey") or session_key),
        }
    ), 200


@main_bp.route("/platform/vi/connection", methods=["PUT"])
def platform_vi_update_connection():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    source_dir_value = str(body.get("source_dir") or body.get("sourceDir") or "").strip()
    if not source_dir_value:
        return jsonify({"error": "source_dir is required"}), 400

    try:
        source_dir = _normalize_vi_portal_source_dir(source_dir_value)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Failed to prepare source directory: {exc}"}), 500

    current_app.config["VI_PORTAL_SOURCE_DIR"] = str(source_dir)
    auth_data = _load_normalized_auth_data()
    auth_data["vi_portal_source_dir"] = str(source_dir)
    _save_normalized_auth_data(auth_data)

    verun_root = _resolve_verun_root()
    vi_jar = _resolve_vi_jar_path(verun_root)
    session_key = _vi_repl_session_key()
    repl_session = getattr(current_app, "vi_repl_sessions", {}).get(session_key)
    repl_active = bool(repl_session and repl_session.get("process") and repl_session["process"].poll() is None)
    terminal_session = getattr(current_app, "vi_terminal_sessions", {}).get(session_key)
    terminal_status = _vi_terminal_session_metadata(session_key, terminal_session)
    return jsonify(
        {
            "verun_root": str(verun_root) if verun_root else "",
            "vi_jar_path": str(vi_jar) if vi_jar else "",
            "vi_jar_exists": bool(vi_jar and vi_jar.is_file()),
            "source_dir": str(source_dir),
            "files_count": _count_vi_portal_files(source_dir),
            "repl_active": repl_active,
            "repl_prompt": str((repl_session or {}).get("prompt") or VI_REPL_PRIMARY_PROMPT),
            "terminal_active": bool(terminal_status.get("active")),
            "terminal_prompt": str(terminal_status.get("prompt") or VI_REPL_PRIMARY_PROMPT),
            "terminal_cols": int(terminal_status.get("cols") or VI_TERMINAL_DEFAULT_COLS),
            "terminal_rows": int(terminal_status.get("rows") or VI_TERMINAL_DEFAULT_ROWS),
            "terminal_session_key": str(terminal_status.get("sessionKey") or session_key),
        }
    ), 200


@main_bp.route("/platform/vi/workspace-env", methods=["GET"])
def platform_vi_workspace_env():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("VIEW_SERVICES")
    if denied:
        return denied

    source_dir = _resolve_vi_portal_source_dir()
    env_path = _vi_workspace_env_path(source_dir)
    return jsonify(
        {
            "source_dir": str(source_dir),
            "path": str(env_path),
            "content": _read_vi_workspace_env_text(source_dir),
        }
    ), 200


@main_bp.route("/platform/vi/workspace-env", methods=["PUT"])
def platform_vi_update_workspace_env():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    content = str(body.get("content") if "content" in body else body.get("env") or body.get("text") or "")
    source_dir = _resolve_vi_portal_source_dir()
    env_path = _write_vi_workspace_env_text(content, source_dir)
    return jsonify(
        {
            "source_dir": str(source_dir),
            "path": env_path,
            "content": _read_vi_workspace_env_text(source_dir),
        }
    ), 200


@main_bp.route("/platform/vi/directories", methods=["GET"])
def platform_vi_list_directories():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    path_value = str(request.args.get("path") or "").strip()
    try:
        return jsonify(_vi_portal_directory_listing(path_value)), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Failed to browse directories: {exc}"}), 500


@main_bp.route("/platform/vi/files", methods=["GET"])
def platform_vi_list_files():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("VIEW_SERVICES")
    if denied:
        return denied

    return jsonify({"files": _list_vi_portal_files()}), 200


@main_bp.route("/platform/vi/files", methods=["POST"])
def platform_vi_create_file():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    path_value = str(body.get("path") or body.get("name") or "").strip()
    content = str(body.get("content") or body.get("code") or "")
    if not path_value:
        return jsonify({"error": "File path is required"}), 400

    try:
        file_path, relative_path = _resolve_vi_portal_file_path(path_value)
        if file_path.exists():
            return jsonify({"error": f"File already exists: {relative_path}"}), 409
        return jsonify(_write_vi_portal_file(relative_path, content)), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/vi/files/<path:file_path>", methods=["GET"])
def platform_vi_get_file(file_path: str):
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("VIEW_SERVICES")
    if denied:
        return denied

    try:
        return jsonify(_read_vi_portal_file(file_path)), 200
    except FileNotFoundError:
        return jsonify({"error": f"File not found: {file_path}"}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@main_bp.route("/platform/vi/files/<path:file_path>", methods=["PUT"])
def platform_vi_update_file(file_path: str):
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    next_path_value = str(body.get("path") or body.get("name") or file_path).strip()
    content = str(body.get("content") or body.get("code") or "")

    try:
        current_full_path, current_rel_path = _resolve_vi_portal_file_path(file_path)
        if not current_full_path.exists():
            return jsonify({"error": f"File not found: {current_rel_path}"}), 404
        next_full_path, next_rel_path = _resolve_vi_portal_file_path(next_path_value, create_parent=True)
        if next_rel_path != current_rel_path and next_full_path.exists():
            return jsonify({"error": f"File already exists: {next_rel_path}"}), 409
        if next_rel_path != current_rel_path:
            next_full_path.write_text(content, encoding="utf-8")
            current_full_path.unlink()
        else:
            current_full_path.write_text(content, encoding="utf-8")
        return jsonify(_read_vi_portal_file(next_rel_path)), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/vi/files/<path:file_path>", methods=["DELETE"])
def platform_vi_delete_file(file_path: str):
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    try:
        deleted_path = _delete_vi_portal_file(file_path)
        return jsonify({"message": f"File '{deleted_path}' deleted"}), 200
    except FileNotFoundError:
        return jsonify({"error": f"File not found: {file_path}"}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/vi/files/<path:file_path>/run", methods=["POST"])
def platform_vi_run_file(file_path: str):
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    ok, result = _run_vi_portal_file(file_path)
    if not ok:
        status_code = 404 if "not found" in str((result or {}).get("error") or "").lower() else 400
        return jsonify(result if isinstance(result, dict) else {"error": "VI file execution failed"}), status_code
    return jsonify(result), 200


@main_bp.route("/platform/vi/validate", methods=["POST"])
def platform_vi_validate_source():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    source_value = str(
        body.get("source")
        if "source" in body
        else body.get("content")
        if "content" in body
        else body.get("code") or ""
    )
    path_value = str(body.get("path") or body.get("file") or "").strip()
    return jsonify(validate_versa_source(source_value, path_hint=path_value)), 200


@main_bp.route("/platform/lapis/validate", methods=["POST"])
def platform_lapis_validate():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    lapis_config = body.get("config")
    if not isinstance(lapis_config, dict):
        return jsonify({"error": "LAPIS config is required"}), 400
    # Keep upload validation deterministic and fast: schema, endpoint references,
    # and Versa syntax. Generation/runtime checks remain separate operations.
    detail = Config.validate_lapis_config_detailed(lapis_config, include_dry_run=False)
    issues = collect_lapis_validation_issues(detail)
    error_text = str(detail.get("error") or "").strip()
    return jsonify(
        {
            "ok": bool(detail.get("valid")),
            "error": detail.get("error"),
            "versaIssues": list(detail.get("versaIssues") or []),
            "issues": issues,
            "normalized": detail.get("normalized"),
            "dryRun": detail.get("dryRun"),
            "progressMessage": (
                "Validation passed."
                if bool(detail.get("valid"))
                else f"Validation failed: {error_text or 'review the reported issue and retry.'}"
            ),
            "validationState": {
                "attemptCount": 0,
                "nextStep": "continue",
            },
        }
    ), 200


@main_bp.route("/platform/lapis/repair", methods=["POST"])
def platform_lapis_repair():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    lapis_config = body.get("config")
    if not isinstance(lapis_config, dict):
        return jsonify({"error": "LAPIS config is required"}), 400

    settings = _platform_settings_with_defaults((_load_normalized_auth_data().get("settings") or {}))
    feature_flags = settings.get("featureFlags") if isinstance(settings.get("featureFlags"), dict) else {}
    if not feature_flag_enabled("lapisRecursiveAutoFix", feature_flags):
        return jsonify(
            {
                "ok": False,
                "error": "Recursive LAPIS auto-fix is disabled by platform feature flag.",
                "featureFlags": feature_flags,
                "finalStatus": "disabled",
                "progressMessage": "Recursive LAPIS auto-fix is currently disabled.",
            }
        ), 200

    max_attempts = max(int(body.get("maxAttempts") or 6), 1)
    result = repair_lapis_config_recursively(
        lapis_config,
        include_dry_run=True,
        max_attempts=max_attempts,
        allow_safe_schema_fix=feature_flag_enabled("lapisSafeSchemaAutoFix", feature_flags),
    )
    return jsonify({**result, "featureFlags": feature_flags}), 200


@main_bp.route("/platform/vi/terminal/session", methods=["GET"])
def platform_vi_terminal_status():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    session_key = _vi_terminal_session_key()
    terminal_session = getattr(current_app, "vi_terminal_sessions", {}).get(session_key)
    return jsonify(_vi_terminal_session_metadata(session_key, terminal_session)), 200


@main_bp.route("/platform/vi/terminal/session", methods=["POST"])
def platform_vi_terminal_start():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    reset = bool(body.get("reset"))
    cols = body.get("cols")
    rows = body.get("rows")
    if reset:
        _terminate_vi_terminal_session(_vi_terminal_session_key())
    ok, result = _ensure_vi_terminal_session(cols=cols, rows=rows)
    if not ok:
        return jsonify(result if isinstance(result, dict) else {"error": "Failed to start VI terminal"}), 400
    return jsonify(result), 200


@main_bp.route("/platform/vi/terminal/session", methods=["DELETE"])
def platform_vi_terminal_stop():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    session_key = _vi_terminal_session_key()
    _terminate_vi_terminal_session(session_key)
    return jsonify({"message": "VI terminal session closed", "active": False, "sessionKey": session_key}), 200


@main_bp.route("/platform/vi/terminal/run", methods=["POST"])
def platform_vi_terminal_run_file():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    path_value = str(body.get("path") or body.get("file") or "").strip()
    has_source = any(key in body for key in ("source", "content", "code"))
    source_value = str(
        body.get("source")
        if "source" in body
        else body.get("content")
        if "content" in body
        else body.get("code") or ""
    )
    if not path_value and not has_source:
        return jsonify({"error": "File path or source is required"}), 400

    try:
        ok, result = _run_vi_terminal_source(path_value, source_value) if has_source else _run_vi_terminal_file(path_value)
    except FileNotFoundError:
        return jsonify({"error": f"File not found: {path_value}"}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if not ok:
        status_code = 409 if "already running" in str((result or {}).get("error") or "").lower() else 400
        return jsonify(result if isinstance(result, dict) else {"error": "Failed to run VI file in terminal"}), status_code
    return jsonify(result), 200


@main_bp.route("/platform/vi/terminal/poll", methods=["GET"])
def platform_vi_terminal_poll():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    try:
        last_seq = max(0, int(request.args.get("lastSeq") or 0))
    except (TypeError, ValueError):
        last_seq = 0
    session_key = _vi_terminal_session_key()
    terminal_session = getattr(current_app, "vi_terminal_sessions", {}).get(session_key)
    return _jsonify_with_retry_after(_vi_terminal_poll_payload(session_key, terminal_session, last_seq))


@main_bp.route("/platform/vi/terminal/input", methods=["POST"])
def platform_vi_terminal_input():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    source = str(body.get("source") if "source" in body else body.get("data") or "")
    ok, result = _write_vi_terminal_input(source)
    if not ok:
        return jsonify(result if isinstance(result, dict) else {"error": "Failed to write to VI terminal"}), 400
    return jsonify(result), 200


@main_bp.route("/platform/vi/terminal/resize", methods=["POST"])
def platform_vi_terminal_resize():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    ok, result = _resize_vi_terminal_session(_vi_terminal_session_key(), body.get("cols"), body.get("rows"))
    if not ok:
        return jsonify(result if isinstance(result, dict) else {"error": "Failed to resize VI terminal"}), 400
    return jsonify(result), 200


@main_bp.route("/platform/vi/terminal/signal", methods=["POST"])
def platform_vi_terminal_signal():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    ok, result = _signal_vi_terminal_session(str(body.get("signal") or "SIGINT"))
    if not ok:
        return jsonify(result if isinstance(result, dict) else {"error": "Failed to signal VI terminal"}), 400
    return jsonify(result), 200


@main_bp.route("/platform/vi/repl/session", methods=["POST"])
def platform_vi_repl_start():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    ok, result = _ensure_vi_repl_session()
    if not ok:
        return jsonify(result if isinstance(result, dict) else {"error": "Failed to start VI REPL"}), 400
    return jsonify(result), 200


@main_bp.route("/platform/vi/repl/session", methods=["DELETE"])
def platform_vi_repl_stop():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    session_key = _vi_repl_session_key()
    _terminate_vi_repl_session(session_key)
    return jsonify({"message": "VI REPL session closed", "active": False}), 200


@main_bp.route("/platform/vi/repl/input", methods=["POST"])
def platform_vi_repl_input():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_platform_permission("MANAGE_SERVICES")
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    source = str(body.get("source") or body.get("code") or "")
    ok, result = _submit_vi_repl_input(source)
    if not ok:
        return jsonify(result if isinstance(result, dict) else {"error": "Failed to submit REPL input"}), 400
    return jsonify(result), 200


@sock.route("/platform/vi/terminal/ws")
def platform_vi_terminal_ws(ws):
    session = _session_from_request_token()
    if not session:
        ws.close(message="Authentication required")
        return
    if "MANAGE_SERVICES" not in _platform_permissions_for_role(_role_from_session(session)):
        ws.close(message="Insufficient platform permissions")
        return

    ok, result = _ensure_vi_terminal_session()
    if not ok:
        ws.send(json.dumps({"type": "error", "message": str((result or {}).get("error") or "Failed to start VI terminal")}))
        ws.close()
        return

    session_key = str(result.get("sessionKey") or _vi_terminal_session_key())
    terminal_session = getattr(current_app, "vi_terminal_sessions", {}).get(session_key)
    buffer_text, last_seq, _ = _vi_terminal_snapshot(terminal_session or {})
    ws.send(json.dumps({"type": "status", **_vi_terminal_session_metadata(session_key, terminal_session)}))
    if buffer_text:
        ws.send(json.dumps({"type": "output", "data": buffer_text}))

    while True:
        terminal_session = getattr(current_app, "vi_terminal_sessions", {}).get(session_key)
        if not terminal_session:
            ws.send(json.dumps({"type": "status", "active": False, "sessionKey": session_key}))
            return

        for seq, chunk in _pending_vi_terminal_chunks(terminal_session, last_seq):
            ws.send(json.dumps({"type": "output", "data": chunk}))
            last_seq = seq

        if not _vi_terminal_session_metadata(session_key, terminal_session).get("active", False):
            ws.send(json.dumps({"type": "status", **_vi_terminal_session_metadata(session_key, terminal_session)}))
            return

        try:
            incoming = ws.receive(timeout=0.01)
        except ConnectionClosed:
            return
        if incoming is None:
            continue
        if isinstance(incoming, bytes):
            incoming = incoming.decode("utf-8", errors="replace")
        try:
            payload = json.loads(str(incoming or ""))
        except json.JSONDecodeError:
            payload = {"type": "input", "data": str(incoming or "")}

        message_type = str(payload.get("type") or "input").strip().lower()
        if message_type == "input":
            ok, info = _write_vi_terminal_input(str(payload.get("data") or ""))
            if not ok:
                ws.send(json.dumps({"type": "error", "message": str((info or {}).get("error") or "Failed to write to VI terminal")}))
            continue
        if message_type == "resize":
            ok, info = _resize_vi_terminal_session(session_key, payload.get("cols"), payload.get("rows"))
            if ok:
                ws.send(json.dumps({"type": "status", **info}))
            else:
                ws.send(json.dumps({"type": "error", "message": str((info or {}).get("error") or "Failed to resize VI terminal")}))
            continue
        if message_type == "signal":
            ok, info = _signal_vi_terminal_session(str(payload.get("signal") or "SIGINT"))
            if ok:
                ws.send(json.dumps({"type": "status", **info}))
            else:
                ws.send(json.dumps({"type": "error", "message": str((info or {}).get("error") or "Failed to signal VI terminal")}))
            continue
        if message_type == "ping":
            ws.send(json.dumps({"type": "status", **_vi_terminal_session_metadata(session_key, terminal_session)}))
            continue
        ws.send(json.dumps({"type": "error", "message": f"Unsupported terminal message type: {message_type}"}))


@main_bp.route("/platform/verse/health", methods=["GET"])
def verse_health():
    probe = str(request.args.get("probe") or "").strip().lower() in {"1", "true", "yes"}
    if not (probe and _request_is_loopback()):
        denied = _frontend_auth_or_forbid()
        if denied:
            return denied
    try:
        session = _session_from_header() or {}
        payload = _verse_service().health(probe=probe)
        if session.get("username"):
            payload["settings"] = _verse_service().get_user_settings(session.get("username"))
        payload["prerequisites"] = _verse_prerequisite_status(session)
        return jsonify(payload), 200
    except Exception as exc:
        return jsonify({"provider": str(_runtime_cfg("AI_PROVIDER") or "openai"), "configured": False, "error": str(exc)}), 200


@main_bp.route("/platform/ai/config", methods=["GET"])
def get_ai_config():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    return jsonify(_ai_config_status(_session_from_header())), 200


@main_bp.route("/platform/ai/config", methods=["PUT"])
def update_ai_config():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_super_admin()
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    providers = body.get("providers") if isinstance(body.get("providers"), dict) else {}
    updates: dict[str, str] = {}
    try:
        if "defaultProvider" in body:
            selected = _sanitize_ai_config_text(body.get("defaultProvider"), field="Default provider", max_length=32).lower()
            if selected not in _AI_PROVIDER_SPECS:
                return jsonify({"error": "Unsupported AI provider"}), 400
            updates["AI_PROVIDER"] = selected

        for provider_id, raw_provider in providers.items():
            provider_id = str(provider_id or "").strip().lower()
            if provider_id not in _AI_PROVIDER_SPECS or not isinstance(raw_provider, dict):
                return jsonify({"error": f"Unsupported AI provider configuration: {provider_id or 'unknown'}"}), 400
            spec = _AI_PROVIDER_SPECS[provider_id]
            if "model" in raw_provider:
                model = _sanitize_ai_config_text(raw_provider.get("model"), field=f"{spec['label']} model", max_length=160)
                if not model:
                    return jsonify({"error": f"{spec['label']} model is required"}), 400
                updates[spec["modelConfig"]] = model
            remove_key = bool(raw_provider.get("removeApiKey"))
            if "apiKey" in raw_provider and remove_key:
                return jsonify({"error": f"Choose either replacing or removing the {spec['label']} API key"}), 400
            if "apiKey" in raw_provider:
                api_key = _sanitize_ai_config_text(raw_provider.get("apiKey"), field=f"{spec['label']} API key", max_length=10000)
                if not api_key:
                    return jsonify({"error": f"Use removeApiKey to clear the {spec['label']} API key"}), 400
                _validate_ai_key_assignment(provider_id, api_key)
                updates[spec["keyConfig"]] = api_key
            elif remove_key:
                updates[spec["keyConfig"]] = ""
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if not updates:
        return jsonify({"error": "No AI configuration changes provided"}), 400

    try:
        _persist_ai_env_values(updates)
        current_app.config.update(updates)
        current_app.ai_config_runtime_keys.update(updates.keys())
        persisted_path = _backend_env_local_path()
        persisted_mtime = persisted_path.stat().st_mtime_ns if persisted_path.exists() else None
        for key in updates:
            current_app.ai_config_runtime_mtimes[key] = persisted_mtime
        current_app.verse_service = None
        current_app.verse_service_signature = None
        return jsonify(_ai_config_status(_session_from_header())), 200
    except Exception:
        current_app.logger.exception("Failed to persist AI provider configuration")
        return jsonify({"error": "Failed to save AI configuration"}), 500


@main_bp.route("/platform/ai/config/test", methods=["POST"])
def test_ai_config():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_super_admin()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    provider_id = str(body.get("provider") or "").strip().lower()
    if provider_id not in _AI_PROVIDER_SPECS:
        return jsonify({"error": "Unsupported AI provider"}), 400
    spec = _AI_PROVIDER_SPECS[provider_id]
    provider_config = {
        "AI_PROVIDER": provider_id,
        "OPENAI_API_KEY": _runtime_cfg("OPENAI_API_KEY"),
        "OPENAI_MODEL": _runtime_cfg("OPENAI_MODEL"),
        "GOOGLE_API_KEY": _runtime_cfg("GOOGLE_API_KEY"),
        "GOOGLE_MODEL": _runtime_cfg("GOOGLE_MODEL"),
        "ANTHROPIC_API_KEY": _runtime_cfg("ANTHROPIC_API_KEY"),
        "ANTHROPIC_MODEL": _runtime_cfg("ANTHROPIC_MODEL"),
    }
    try:
        for field, config_key in (("apiKey", spec["keyConfig"]), ("model", spec["modelConfig"])):
            if field in body:
                value = _sanitize_ai_config_text(body[field], field=field, max_length=10000 if field == "apiKey" else 160)
                if not value:
                    return jsonify({"error": f"{field} is required"}), 400
                if field == "apiKey":
                    _validate_ai_key_assignment(provider_id, value)
                provider_config[config_key] = value
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if not str(provider_config.get(spec["keyConfig"]) or "").strip():
        return jsonify({"error": f"{spec['label']} is not configured"}), 400
    try:
        result = build_ai_provider(provider_config, provider_name=provider_id).healthcheck()
        return jsonify({"ok": True, "provider": provider_id, "model": str(result.model or spec["defaultModel"])}), 200
    except AIAuthenticationError as exc:
        return jsonify({"error": str(exc)}), 400
    except AIRateLimitError:
        return jsonify({"error": f"{spec['label']} is configured but rate limited or out of quota"}), 429
    except (AIConfigurationError, AIProviderError) as exc:
        return jsonify({"error": str(exc) or f"{spec['label']} connection test failed"}), 502
    except Exception:
        current_app.logger.exception("AI provider connection test failed for %s", provider_id)
        return jsonify({"error": f"{spec['label']} connection test failed"}), 502


@main_bp.route("/platform/verse/bootstrap", methods=["GET"])
def verse_bootstrap():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    session = _session_from_header() or {}
    try:
        payload = _verse_service().health(probe=False)
        payload["me"] = {
            "username": str(session.get("username") or "").strip(),
            "role": str(session.get("role") or "").strip(),
            "isSuperAdmin": bool(session.get("is_super_admin")),
        }
        payload["settings"] = _verse_service().get_user_settings(session.get("username"))
        payload["prerequisites"] = _verse_prerequisite_status(session)
        payload["agents"] = _verse_service().list_agents()
        return jsonify(payload), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/settings", methods=["GET"])
def get_verse_settings():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    session = _session_from_header() or {}
    try:
        return jsonify(
            {
                "settings": _verse_service().get_user_settings(session.get("username")),
                "prerequisites": _verse_prerequisite_status(session),
            }
        ), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/settings", methods=["PUT"])
def update_verse_settings():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    session = _session_from_header() or {}
    body = request.get_json(silent=True) or {}
    try:
        settings = _verse_service().update_user_settings(
            session.get("username"),
            collaboration_level=_verse_collaboration_level(body),
            proactive_mode_enabled=_verse_proactive_mode_enabled(body),
            agent_settings=_verse_agent_settings(body),
        )
        return jsonify({"settings": settings, "prerequisites": _verse_prerequisite_status(session)}), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/notifications", methods=["GET"])
def list_verse_notifications():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    session = _session_from_header() or {}
    username = _normalize_username(session.get("username")) or "anonymous"
    run_scheduler = str(request.args.get("run") or "1").strip().lower() not in {"0", "false", "no", "off"}
    force = str(request.args.get("force") or "").strip().lower() in {"1", "true", "yes", "on"}
    should_run_scheduler = run_scheduler
    deferred_reason = ""
    retry_after_ms = 0
    scheduler_degraded = False

    if run_scheduler and not force:
        scheduler_state = _resilience_state_snapshot(_RESILIENCE_BUCKET_VERSE_NOTIFICATIONS, username)
        retry_after_ms = max(
            _resilience_remaining_ms(scheduler_state, "pausedUntil"),
            _resilience_remaining_ms(scheduler_state, "nextAllowedAt"),
        )
        if retry_after_ms > 0:
            should_run_scheduler = False
            scheduler_degraded = bool(scheduler_state.get("degraded") or scheduler_state.get("lastError"))
            deferred_reason = str(scheduler_state.get("lastError") or "").strip() if scheduler_degraded else ""

    try:
        scheduler_ran = False
        if should_run_scheduler:
            scheduled_payload: dict[str, Any] = {}

            def _run_notification_scheduler() -> None:
                nonlocal scheduled_payload
                scheduled_payload = _verse_service().list_proactive_notifications(
                    session.get("username"),
                    run_scheduler=True,
                    force=force,
                )

            scheduler_ran = _run_with_proactive_leader_lock(current_app, _run_notification_scheduler)
            if scheduler_ran:
                payload = scheduled_payload
            else:
                # Another worker owns this tick. Read persisted notifications
                # without starting a second provider evaluation.
                should_run_scheduler = False
                deferred_reason = "Another worker is running the proactive scheduler"
                payload = _verse_service().list_proactive_notifications(
                    session.get("username"),
                    run_scheduler=False,
                    force=False,
                )
        else:
            payload = _verse_service().list_proactive_notifications(
                session.get("username"),
                run_scheduler=False,
                force=force,
            )
        if scheduler_ran and not force:
            _resilience_record_success(
                _RESILIENCE_BUCKET_VERSE_NOTIFICATIONS,
                username,
                next_allowed_ms=VERSE_NOTIFICATION_MIN_INTERVAL_MS,
            )
        payload = dict(payload or {})
        payload.setdefault("items", [])
        payload.setdefault("unreadCount", 0)
        payload.setdefault("emitted", [])
        payload.update(
            {
                "degraded": bool(run_scheduler and not scheduler_ran and scheduler_degraded),
                "schedulerRan": bool(scheduler_ran),
                "schedulerDeferred": bool(run_scheduler and not scheduler_ran),
                "retryAfterMs": int(retry_after_ms if run_scheduler and not scheduler_ran else 0),
                "reason": deferred_reason if run_scheduler and not scheduler_ran else "",
            }
        )
        return _jsonify_with_retry_after(payload)
    except Exception as exc:
        if run_scheduler and not force:
            current_app.logger.warning("Verse proactive notification scheduler failed; serving cached notifications", exc_info=True)
            failure_state = _resilience_record_failure(
                _RESILIENCE_BUCKET_VERSE_NOTIFICATIONS,
                username,
                error=str(exc),
                base_delay_ms=VERSE_NOTIFICATION_FAILURE_BASE_MS,
                max_delay_ms=VERSE_NOTIFICATION_FAILURE_MAX_MS,
            )
            try:
                payload = _verse_service().list_proactive_notifications(
                    session.get("username"),
                    run_scheduler=False,
                    force=False,
                )
            except Exception:
                return jsonify({"error": str(exc)}), 500
            payload = dict(payload or {})
            payload.setdefault("items", [])
            payload.setdefault("unreadCount", 0)
            payload.setdefault("emitted", [])
            payload.update(
                {
                    "degraded": True,
                    "schedulerRan": False,
                    "schedulerDeferred": True,
                    "retryAfterMs": int(failure_state.get("retryAfterMs") or 0),
                    "reason": str(exc),
                }
            )
            return _jsonify_with_retry_after(payload)
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/notifications/read", methods=["POST"])
def mark_verse_notifications_read():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    session = _session_from_header() or {}
    body = request.get_json(silent=True) or {}
    try:
        payload = _verse_service().mark_proactive_notifications_read(
            session.get("username"),
            notification_id=str(body.get("notificationId") or body.get("id") or "").strip(),
            thread_id=str(body.get("threadId") or "").strip(),
        )
        return jsonify(payload), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/issues/ignore", methods=["POST"])
def ignore_verse_issue():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    session = _session_from_header() or {}
    body = request.get_json(silent=True) or {}
    try:
        payload = _verse_service().ignore_proactive_issue(
            session.get("username"),
            issue_key=str(body.get("issueKey") or body.get("issue_key") or "").strip(),
            agent_id=str(body.get("agentId") or body.get("agent_id") or "").strip(),
            thread_id=str(body.get("threadId") or "").strip(),
        )
        return jsonify(payload), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/proactive/tick", methods=["POST"])
def tick_verse_proactive_runtime():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    session = _session_from_header() or {}
    body = request.get_json(silent=True) or {}
    force = str(body.get("force") or request.args.get("force") or "").strip().lower() in {"1", "true", "yes", "on"}
    try:
        result: dict[str, Any] = {}

        def _run_tick() -> None:
            nonlocal result
            result = _verse_service().run_due_proactive_evaluations(session.get("username"), force=force)

        if not _run_with_proactive_leader_lock(current_app, _run_tick):
            return jsonify({
                "evaluations": [],
                "emitted": [],
                "schedulerSkipped": True,
                "reason": "Another worker is running the proactive scheduler",
            }), 200
        return jsonify(result), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/agents", methods=["GET"])
def list_verse_agents():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    try:
        return jsonify({"agents": _verse_service().list_agents()}), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/agents/<string:agent_id>", methods=["PUT"])
def rename_verse_agent(agent_id):
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_super_admin()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    display_name = str(body.get("displayName") or body.get("name") or "").strip()
    try:
        agent = _verse_service().rename_agent(agent_id, display_name, (_session_from_header() or {}).get("username"))
        return jsonify({"agent": agent}), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/datasets", methods=["GET"])
def list_verse_datasets():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    session = _session_from_header() or {}
    try:
        return jsonify({"datasets": _verse_service().list_datasets(session.get("username"))}), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/datasets", methods=["POST"])
def create_verse_dataset():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    session = _session_from_header() or {}
    try:
        source_type = str(body.get("sourceType") or "").strip().lower()
        if source_type == "platform-context":
            dataset = _verse_service().create_dataset_from_platform_context(
                session.get("username"),
                title=str(body.get("title") or "").strip(),
                payload=body.get("payload") if isinstance(body.get("payload"), dict) else {},
                page_kind=str(body.get("pageKind") or "").strip(),
                notes=str(body.get("notes") or "").strip(),
            )
        else:
            dataset = _verse_service().create_dataset(
                session.get("username"),
                title=str(body.get("title") or "").strip(),
                raw_text=str(body.get("text") or body.get("content") or "").strip(),
                filename=str(body.get("filename") or "").strip(),
                format_hint=str(body.get("format") or "").strip(),
                page_kind=str(body.get("pageKind") or "").strip(),
                notes=str(body.get("notes") or "").strip(),
            )
        analysis = _verse_service().analyze_dataset(str(dataset.get("id") or dataset.get("datasetId") or ""), session.get("username"), {})
        return jsonify({"dataset": dataset, "analysis": analysis}), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/datasets/upload", methods=["POST"])
def upload_verse_dataset():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    session = _session_from_header() or {}
    upload = request.files.get("file")
    if upload is None:
        return jsonify({"error": "Dataset upload requires a file"}), 400
    filename = Path(str(upload.filename or "dataset-upload.bin")).name
    try:
        file_bytes = upload.read()
        text = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return jsonify({"error": "Only UTF-8 CSV, TSV, and JSON uploads are supported"}), 400
    try:
        dataset = _verse_service().create_dataset(
            session.get("username"),
            title=str(request.form.get("title") or "").strip(),
            raw_text=text,
            filename=filename,
            format_hint=str(request.form.get("format") or "").strip(),
            page_kind=str(request.form.get("pageKind") or "").strip(),
            notes=str(request.form.get("notes") or "").strip(),
            archive_bytes=file_bytes,
        )
        analysis = _verse_service().analyze_dataset(str(dataset.get("id") or dataset.get("datasetId") or ""), session.get("username"), {})
        return jsonify({"dataset": dataset, "analysis": analysis}), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/datasets/<string:dataset_id>", methods=["GET"])
def get_verse_dataset(dataset_id):
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    session = _session_from_header() or {}
    try:
        dataset = _verse_service().get_dataset(dataset_id, session.get("username"))
        if not dataset:
            return jsonify({"error": "Verse dataset was not found"}), 404
        return jsonify({"dataset": dataset}), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/datasets/<string:dataset_id>/analyze", methods=["POST"])
def analyze_verse_dataset(dataset_id):
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    session = _session_from_header() or {}
    body = request.get_json(silent=True) or {}
    try:
        return jsonify({"analysis": _verse_service().analyze_dataset(dataset_id, session.get("username"), body)}), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/threads", methods=["GET"])
def list_verse_threads():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    session = _session_from_header() or {}
    try:
        requested_scope = str(request.args.get("scope") or "").strip().lower()
        if requested_scope == "dock":
            scopes = {"dock"}
        elif requested_scope == "portal":
            scopes = {"portal"}
        else:
            scopes = {"portal", "dock"}
        return jsonify({"threads": _verse_service().list_threads(session.get("username"), scopes=scopes)}), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/threads", methods=["POST"])
def create_verse_thread():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    session = _session_from_header() or {}
    try:
        thread = _verse_service().create_thread(
            session.get("username"),
            title=str(body.get("title") or "").strip(),
            initial_message=str(body.get("initialMessage") or body.get("message") or "").strip(),
            provider_name=str(body.get("provider") or body.get("providerName") or "").strip(),
            collaboration_level=_verse_collaboration_level(body),
            thread_scope=str(body.get("threadScope") or body.get("scope") or "portal").strip() or "portal",
            context_key=str(body.get("contextKey") or "").strip(),
            source_pathname=str(body.get("sourcePathname") or body.get("pathname") or "").strip(),
            metadata=body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
        )
        return jsonify({"thread": thread}), 201
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/threads/resolve", methods=["POST"])
def resolve_verse_context_thread():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    session = _session_from_header() or {}
    body = request.get_json(silent=True) or {}
    try:
        thread = _verse_service().resolve_context_thread(
            session.get("username"),
            pathname=str(body.get("pathname") or body.get("sourcePathname") or "/").strip() or "/",
            provider_name=str(body.get("provider") or body.get("providerName") or "").strip(),
            collaboration_level=_verse_collaboration_level(body),
            metadata=body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
        )
        return jsonify({"thread": thread}), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/threads/<string:thread_id>", methods=["GET"])
def get_verse_thread(thread_id):
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    session = _session_from_header() or {}
    try:
        thread = _verse_service().get_thread(thread_id, session.get("username"))
        if not thread:
            return jsonify({"error": "Verse thread was not found"}), 404
        return jsonify({"thread": thread}), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/threads/<string:thread_id>", methods=["DELETE"])
def delete_verse_thread(thread_id):
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    session = _session_from_header() or {}
    try:
        _verse_service().delete_thread(session.get("username"), thread_id)
        return jsonify({"deleted": True}), 200
    except ValueError as exc:
        message = str(exc)
        return jsonify({"error": message}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/threads/<string:thread_id>/messages", methods=["POST"])
def send_verse_thread_message(thread_id):
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    session = _session_from_header() or {}
    screen, platform_context = _verse_request_context(body)
    platform_context["prerequisites"] = _verse_prerequisite_status(session)
    platform_context["collaborationLevel"] = _verse_collaboration_level(body) or _verse_service().get_user_settings(session.get("username")).get("collaborationLevel")
    try:
        thread = _verse_service().send_message(
            thread_id,
            session.get("username"),
            str(body.get("content") or body.get("message") or "").strip(),
            provider_name=str(body.get("provider") or body.get("providerName") or "").strip(),
            current_screen=screen,
            platform_context=platform_context,
            collaboration_level=_verse_collaboration_level(body),
        )
        return jsonify({"thread": thread}), 200
    except ValueError as exc:
        message = str(exc)
        return jsonify({"error": message}), 404 if "not found" in message.lower() else 400
    except AIConfigurationError as exc:
        return jsonify({"error": str(exc)}), 503
    except AIAuthenticationError as exc:
        return jsonify({"error": str(exc)}), 502
    except AIRateLimitError as exc:
        return jsonify({"error": str(exc)}), 429
    except AIProviderError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/assist", methods=["POST"])
def assist_with_verse():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    session = _session_from_header() or {}
    screen, platform_context = _verse_request_context(body)
    platform_context["prerequisites"] = _verse_prerequisite_status(session)
    platform_context["collaborationLevel"] = _verse_collaboration_level(body) or _verse_service().get_user_settings(session.get("username")).get("collaborationLevel")
    try:
        response = _verse_service().assist(
            session.get("username"),
            str(body.get("content") or body.get("message") or "").strip(),
            provider_name=str(body.get("provider") or body.get("providerName") or "").strip(),
            current_screen=screen,
            platform_context=platform_context,
            history=body.get("history") if isinstance(body.get("history"), list) else [],
            collaboration_level=_verse_collaboration_level(body),
        )
        return jsonify(response), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except AIConfigurationError as exc:
        return jsonify({"error": str(exc)}), 503
    except AIAuthenticationError as exc:
        return jsonify({"error": str(exc)}), 502
    except AIRateLimitError as exc:
        return jsonify({"error": str(exc)}), 429
    except AIProviderError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/threads/<string:thread_id>/invite", methods=["POST"])
def invite_verse_agent(thread_id):
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    session = _session_from_header() or {}
    try:
        thread = _verse_service().invite_agent(
            thread_id,
            session.get("username"),
            str(body.get("agentId") or body.get("agent") or "").strip(),
            reason=str(body.get("reason") or "").strip(),
            initiated_by="user",
        )
        return jsonify({"thread": thread}), 200
    except ValueError as exc:
        message = str(exc)
        return jsonify({"error": message}), 404 if "not found" in message.lower() else 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/threads/<string:thread_id>/synthesis", methods=["POST"])
def synthesize_verse_thread(thread_id):
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    session = _session_from_header() or {}
    body = request.get_json(silent=True) or {}
    screen, _platform_context = _verse_request_context(body)
    try:
        thread = _verse_service().synthesize_thread(
            thread_id,
            session.get("username"),
            provider_name=str(body.get("provider") or body.get("providerName") or "").strip(),
            current_screen=screen,
        )
        return jsonify({"thread": thread}), 200
    except ValueError as exc:
        message = str(exc)
        return jsonify({"error": message}), 404 if "not found" in message.lower() else 400
    except AIConfigurationError as exc:
        return jsonify({"error": str(exc)}), 503
    except AIAuthenticationError as exc:
        return jsonify({"error": str(exc)}), 502
    except AIRateLimitError as exc:
        return jsonify({"error": str(exc)}), 429
    except AIProviderError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/mind-share/preview", methods=["POST"])
def preview_verse_mind_share_write():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    session = _session_from_header() or {}
    try:
        return jsonify(_verse_service().preview_mind_share_write(session.get("username"), body)), 200
    except (ValueError, MindShareValidationError) as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/mind-share/apply", methods=["POST"])
def apply_verse_mind_share_write():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    session = _session_from_header() or {}
    try:
        return jsonify(_verse_service().apply_mind_share_write(session.get("username"), body)), 200
    except (ValueError, MindShareValidationError) as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/capabilities", methods=["GET"])
def list_platform_capability_catalog():
    client = str(request.args.get("client") or "").strip().lower()
    surface_id = str(request.args.get("surfaceId") or request.args.get("surface_id") or "").strip()
    executable_only = _normalize_verse_action_bool(request.args.get("executableOnly"), default=False)
    include_unavailable = _normalize_verse_action_bool(request.args.get("includeUnavailable"), default=True)
    session = _session_from_header() or {}
    try:
        capabilities = [
            _decorate_platform_capability(item, session)
            for item in list_platform_capabilities(
                client=client,
                surface_id=surface_id,
                executable_only=executable_only,
            )
        ]
        if not include_unavailable:
            capabilities = [item for item in capabilities if bool(item.get("allowed"))]
        return jsonify({"capabilities": capabilities}), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/capabilities/<path:capability_id>", methods=["GET"])
def show_platform_capability(capability_id: str):
    session = _session_from_header() or {}
    try:
        capability = get_platform_capability(capability_id)
        if capability is None:
            return jsonify({"error": "Platform capability not found"}), 404
        return jsonify(_decorate_platform_capability(capability, session)), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/actions/catalog", methods=["GET"])
def list_platform_action_catalog():
    client = str(request.args.get("client") or "").strip().lower()
    surface_id = str(request.args.get("surfaceId") or request.args.get("surface_id") or "").strip()
    executable_only = _normalize_verse_action_bool(request.args.get("executableOnly"), default=True)
    include_unavailable = _normalize_verse_action_bool(request.args.get("includeUnavailable"), default=True)
    session = _session_from_header() or {}
    try:
        actions = [
            _decorate_platform_capability(item, session)
            for item in list_platform_capabilities(
                client=client,
                surface_id=surface_id,
                executable_only=executable_only,
            )
        ]
        if not include_unavailable:
            actions = [item for item in actions if bool(item.get("allowed"))]
        return jsonify({"actions": actions}), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/actions/preview", methods=["POST"])
def preview_platform_action():
    body = request.get_json(silent=True) or {}
    session = _session_from_header() or {}
    try:
        payload, status = _preview_platform_action(body, session)
        return jsonify(payload), status
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/actions/execute", methods=["POST"])
def execute_platform_action():
    body = request.get_json(silent=True) or {}
    session = _session_from_header() or {}
    try:
        payload, status = _execute_platform_action(body, session)
        return jsonify(payload), status
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/actions/catalog", methods=["GET"])
def list_verse_action_catalog():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    session = _session_from_header() or {}
    try:
        actions = _verse_service().action_catalog()
        can_manage_services = "MANAGE_SERVICES" in set(session.get("permissions") or [])
        visible_actions = [
            item for item in actions
            if str(item.get("kind") or "") != "service-manager-action" or can_manage_services
        ]
        return jsonify({"actions": visible_actions}), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/actions/preview", methods=["POST"])
def preview_verse_action():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    artifact = body.get("artifact") if isinstance(body.get("artifact"), dict) else {}
    session = _session_from_header() or {}
    try:
        payload, status = _preview_platform_action({"artifact": artifact}, session)
        return jsonify(payload), status
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/verse/actions/execute", methods=["POST"])
def execute_verse_action():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    artifact = body.get("artifact") if isinstance(body.get("artifact"), dict) else {}
    session = _session_from_header() or {}
    try:
        payload, status = _execute_platform_action({"artifact": artifact}, session)
        return jsonify(payload), status
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/vdb/domains", methods=["GET"])
def list_vdb_domains():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_super_admin()
    if denied:
        return denied
    denied = _authorize_or_forbid("DATA_ACCESS")
    if denied:
        return denied
    try:
        _use_runtime_workspace()
        success, domains = current_app.vdb_client.list_domains()
        if not success:
            return jsonify({"error": "Failed to list VDB domains"}), 500
        return jsonify({"domains": domains if isinstance(domains, list) else []}), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/vdb/domains", methods=["POST"])
def create_vdb_domain():
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_super_admin()
    if denied:
        return denied
    denied = _authorize_or_forbid("WRITE")
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    domain_name = str(body.get("domain") or body.get("name") or "").strip()
    db_name = str(body.get("db") or body.get("database") or "main").strip() or "main"
    if not domain_name:
        return jsonify({"error": "domain is required"}), 400
    try:
        _use_runtime_workspace()
        ok_domain, domain_result = current_app.vdb_client.define_domain(domain_name)
        if not ok_domain:
            return jsonify({"error": f"Failed to define domain '{domain_name}': {domain_result}"}), 500
        if not current_app.vdb_client.use_domain(domain_name):
            return jsonify({"error": f"Domain '{domain_name}' created but switching failed"}), 500
        ok_db, db_result = current_app.vdb_client.define_database(db_name)
        if not ok_db:
            return jsonify({"error": f"Domain created, but database '{db_name}' define failed: {db_result}"}), 500
        current_app.vdb_client.use_database(db_name)
        _use_runtime_workspace()
        return jsonify({"domain": domain_name, "database": db_name}), 201
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@main_bp.route("/platform/users/<string:username>", methods=["DELETE"])
def delete_platform_user(username):
    denied = _frontend_auth_or_forbid()
    if denied:
        return denied
    denied = _require_super_admin()
    if denied:
        return denied

    target_username = _normalize_username(username)
    session = _session_from_header() or {}
    if _normalize_username(session.get("username")) == target_username:
        return jsonify({"error": "You cannot delete your own active account"}), 400

    data = _load_normalized_auth_data()
    target = _find_auth_user(data, target_username)
    if target and bool(target.get("is_super_admin", False)):
        return jsonify({"error": "Super admin account cannot be deleted"}), 400
    users = data.get("users", [])
    next_users = [u for u in users if _normalize_username(u.get("username")) != target_username]
    if len(next_users) == len(users):
        return jsonify({"error": "User not found"}), 404
    if not next_users:
        return jsonify({"error": "At least one account must remain"}), 400
    if not any(_normalize_platform_role(user.get("role")) == ROLE_ADMIN for user in next_users):
        return jsonify({"error": "At least one admin account must remain"}), 400

    data["users"] = next_users
    _save_normalized_auth_data(data)
    return jsonify({"message": f"User '{username}' deleted"}), 200
