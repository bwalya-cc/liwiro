# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from config import Config, normalize_vdb_named_pipe_path
from utils.auth_helpers import normalize_username


ROLE_VIEWER = "viewer"
ROLE_SERVICE_MANAGER = "service_manager"
ROLE_ADMIN = "admin"
WILDCARD_SERVICE_ACCESS = "*"

_AUTH_CACHE = {"path": None, "mtime_ns": None, "data": None}
_NORMALIZED_AUTH_CACHE = {"path": None, "mtime_ns": None, "data": None}
_DEFAULT_PLATFORM_SETTINGS = {
    "productionMode": False,
    "startServicesOnStartup": False,
    "autoRefreshServiceStatus": True,
    "deleteDataWithServiceByDefault": True,
    "startServicesAfterGenerationByDefault": True,
    "retryFailedBatchOpsByDefault": True,
}


def auth_file_path() -> Path:
    return Path(Config.LIWIRO_AUTH_PATH)


def load_auth_file() -> dict:
    path = auth_file_path()
    path_key = str(path.resolve())
    try:
        stat = path.stat()
        mtime_ns = stat.st_mtime_ns
    except FileNotFoundError:
        _AUTH_CACHE["path"] = path_key
        _AUTH_CACHE["mtime_ns"] = None
        _AUTH_CACHE["data"] = {}
        return {}

    if (
        _AUTH_CACHE.get("path") == path_key
        and _AUTH_CACHE.get("mtime_ns") == mtime_ns
        and isinstance(_AUTH_CACHE.get("data"), dict)
    ):
        return copy.deepcopy(_AUTH_CACHE["data"])

    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        out = data if isinstance(data, dict) else {}
        _AUTH_CACHE["path"] = path_key
        _AUTH_CACHE["mtime_ns"] = mtime_ns
        _AUTH_CACHE["data"] = copy.deepcopy(out)
        return out
    except Exception:
        return {}


def save_auth_file(data: dict) -> None:
    path = auth_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    try:
        stat = path.stat()
        _AUTH_CACHE["path"] = str(path.resolve())
        _AUTH_CACHE["mtime_ns"] = stat.st_mtime_ns
        _AUTH_CACHE["data"] = copy.deepcopy(data if isinstance(data, dict) else {})
    except Exception:
        _AUTH_CACHE["path"] = None
        _AUTH_CACHE["mtime_ns"] = None
        _AUTH_CACHE["data"] = None
    _NORMALIZED_AUTH_CACHE["path"] = None
    _NORMALIZED_AUTH_CACHE["mtime_ns"] = None
    _NORMALIZED_AUTH_CACHE["data"] = None


def normalize_platform_role(role_value) -> str:
    role = str(role_value or "").strip().lower().replace("-", "_")
    if role in {"manager", ROLE_SERVICE_MANAGER}:
        return ROLE_SERVICE_MANAGER
    if role in {"admin", "super_admin", "superadmin"}:
        return ROLE_ADMIN
    return ROLE_VIEWER


def normalize_service_access(raw_access) -> list[str]:
    if raw_access is None:
        return []
    values = raw_access if isinstance(raw_access, list) else [raw_access]
    normalized = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        if text not in normalized:
            normalized.append(text)
    return normalized


def normalize_user_permissions(raw_permissions) -> list[dict]:
    if not isinstance(raw_permissions, list):
        return []
    normalized = []
    for entry in raw_permissions:
        if not isinstance(entry, dict):
            continue
        perm_type = str(entry.get("type") or "").strip().upper()
        if not perm_type:
            continue
        raw_effect = str(
            entry.get("effect")
            or entry.get("mode")
            or entry.get("action")
            or "ALLOW"
        ).strip().upper()
        effect = "DENY" if raw_effect in {"DENY", "REMOVE", "REVOKE", "BLOCK", "EXCLUDE"} else "ALLOW"
        item = {"type": perm_type, "effect": effect}
        for key in ("service", "endpoint", "model", "targetService"):
            value = str(entry.get(key) or "").strip()
            if value:
                item[key] = value
        normalized.append(item)
    return normalized


def normalize_liwiro_rbac(raw_rbac, is_super_admin: bool = False) -> dict:
    value = raw_rbac if isinstance(raw_rbac, dict) else {}
    default_role = "LIWIRO_SUPER_ADMIN" if is_super_admin else "LIWIRO_USER"
    role = str(value.get("role") or default_role).strip() or default_role
    abilities_raw = value.get("abilities")
    abilities = abilities_raw if isinstance(abilities_raw, list) else []
    normalized_abilities = []
    for item in abilities:
        text = str(item or "").strip().upper()
        if text and text not in normalized_abilities:
            normalized_abilities.append(text)
    if not normalized_abilities and is_super_admin:
        normalized_abilities = [
            "MANAGE_LIWIRO_USERS",
            "MANAGE_LIWIRO_SERVICES",
            "MANAGE_VDB_DOMAINS",
            "MANAGE_PLATFORM_SETTINGS",
        ]
    if not normalized_abilities and not is_super_admin:
        normalized_abilities = ["VIEW_SERVICES"]
    return {"role": role, "abilities": normalized_abilities}


def normalize_auth_data(data: dict) -> dict:
    auth_data = dict(data or {})
    auth_data.pop("vdb_password", None)
    auth_data.pop("vdb_super_admin_password", None)
    auth_data["vdb_named_pipe_path"] = normalize_vdb_named_pipe_path(auth_data.get("vdb_named_pipe_path"))
    users = auth_data.get("users")
    if not isinstance(users, list):
        users = []
    normalized_users = []
    for entry in users:
        if not isinstance(entry, dict):
            continue
        username = normalize_username(entry.get("username"))
        password_hash = str(entry.get("password_hash") or "").strip()
        if not username or not password_hash:
            continue
        role = normalize_platform_role(entry.get("role"))
        has_explicit_access = "service_access" in entry or "serviceAccess" in entry
        service_access = normalize_service_access(entry.get("service_access") or entry.get("serviceAccess"))
        if not has_explicit_access:
            service_access = [WILDCARD_SERVICE_ACCESS]
        if role == ROLE_ADMIN and WILDCARD_SERVICE_ACCESS not in service_access:
            service_access = [WILDCARD_SERVICE_ACCESS]
        is_super_admin = bool(entry.get("is_super_admin", False))
        normalized_users.append(
            {
                "username": username,
                "password_hash": password_hash,
                "role": role,
                "service_access": service_access,
                "permissions": normalize_user_permissions(entry.get("permissions")),
                "liwiro_rbac": normalize_liwiro_rbac(entry.get("liwiro_rbac"), is_super_admin=is_super_admin),
                "is_super_admin": is_super_admin,
                "created_at": entry.get("created_at") or datetime.now(timezone.utc).isoformat(),
            }
        )

    if normalized_users and not any(bool(user.get("is_super_admin")) for user in normalized_users):
        first_admin_index = None
        for idx, user in enumerate(normalized_users):
            if normalize_platform_role(user.get("role")) == ROLE_ADMIN:
                first_admin_index = idx
                break
        if first_admin_index is None:
            first_admin_index = 0
        normalized_users[first_admin_index]["is_super_admin"] = True

    auth_data["users"] = normalized_users
    auth_data.setdefault("settings", dict(_DEFAULT_PLATFORM_SETTINGS))
    for key, default_value in _DEFAULT_PLATFORM_SETTINGS.items():
        if key not in auth_data["settings"]:
            auth_data["settings"][key] = default_value
    return auth_data


def load_normalized_auth_data() -> dict:
    raw = load_auth_file()
    cache_path = _AUTH_CACHE.get("path")
    cache_mtime_ns = _AUTH_CACHE.get("mtime_ns")
    if (
        _NORMALIZED_AUTH_CACHE.get("path") == cache_path
        and _NORMALIZED_AUTH_CACHE.get("mtime_ns") == cache_mtime_ns
        and isinstance(_NORMALIZED_AUTH_CACHE.get("data"), dict)
    ):
        return copy.deepcopy(_NORMALIZED_AUTH_CACHE["data"])

    normalized = normalize_auth_data(raw)
    _NORMALIZED_AUTH_CACHE["path"] = cache_path
    _NORMALIZED_AUTH_CACHE["mtime_ns"] = cache_mtime_ns
    _NORMALIZED_AUTH_CACHE["data"] = copy.deepcopy(normalized)
    return normalized


def save_normalized_auth_data(data: dict) -> dict:
    normalized = normalize_auth_data(data)
    normalized.pop("vdb_password", None)
    normalized.pop("vdb_super_admin_password", None)
    save_auth_file(normalized)
    _NORMALIZED_AUTH_CACHE["path"] = _AUTH_CACHE.get("path")
    _NORMALIZED_AUTH_CACHE["mtime_ns"] = _AUTH_CACHE.get("mtime_ns")
    _NORMALIZED_AUTH_CACHE["data"] = copy.deepcopy(normalized)
    return normalized


def find_auth_user(auth_data: dict, username: str):
    normalized = normalize_auth_data(auth_data)
    target = normalize_username(username)
    if not target:
        return None
    for user in normalized.get("users", []):
        if normalize_username(user.get("username")) == target:
            return user
    return None
