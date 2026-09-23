from __future__ import annotations

import os
from typing import Any


FEATURE_FLAG_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "lapisRecursiveAutoFix",
        "group": "lapis",
        "title": "Recursive LAPIS Auto-Fix",
        "description": "Allow Liwiro to apply deterministic LAPIS and Versa repairs during upload validation.",
        "default": True,
        "envKey": "LIWIRO_FF_LAPIS_RECURSIVE_AUTO_FIX",
    },
    {
        "id": "lapisSafeSchemaAutoFix",
        "group": "lapis",
        "title": "Safe Schema Auto-Fix",
        "description": "Allow Liwiro to normalize safe LAPIS config shape issues before revalidation.",
        "default": True,
        "envKey": "LIWIRO_FF_LAPIS_SAFE_SCHEMA_AUTO_FIX",
    },
    {
        "id": "unifiedOperationStatus",
        "group": "ux",
        "title": "Unified Operation Status",
        "description": "Show shared in-progress, success, and error status feedback for long-running portal actions.",
        "default": True,
        "envKey": "LIWIRO_FF_UNIFIED_OPERATION_STATUS",
    },
    {
        "id": "transientSuccessFeedback",
        "group": "ux",
        "title": "Transient Success Feedback",
        "description": "Show short-lived success confirmations after completed operations.",
        "default": True,
        "envKey": "LIWIRO_FF_TRANSIENT_SUCCESS_FEEDBACK",
    },
    {
        "id": "serviceBatchProgressMessages",
        "group": "services",
        "title": "Service Batch Progress Messages",
        "description": "Show item-by-item progress updates for batch service operations and LAPIS batch generation.",
        "default": True,
        "envKey": "LIWIRO_FF_SERVICE_BATCH_PROGRESS_MESSAGES",
    },
    {
        "id": "viProgressMessages",
        "group": "vi",
        "title": "VI Portal Progress Messages",
        "description": "Show explicit operation progress inside VI Portal actions.",
        "default": True,
        "envKey": "LIWIRO_FF_VI_PROGRESS_MESSAGES",
    },
    {
        "id": "vdbProgressMessages",
        "group": "vdb",
        "title": "VDB Portal Progress Messages",
        "description": "Show explicit operation progress inside VDB Portal actions.",
        "default": True,
        "envKey": "LIWIRO_FF_VDB_PROGRESS_MESSAGES",
    },
    {
        "id": "verseActionProgressMessages",
        "group": "verse",
        "title": "Verse Action Progress Messages",
        "description": "Show explicit progress states while Verse sends messages or executes prepared actions.",
        "default": True,
        "envKey": "LIWIRO_FF_VERSE_ACTION_PROGRESS_MESSAGES",
    },
    {
        "id": "settingsProgressMessages",
        "group": "settings",
        "title": "Settings Progress Messages",
        "description": "Show explicit progress states while loading or saving settings and platform controls.",
        "default": True,
        "envKey": "LIWIRO_FF_SETTINGS_PROGRESS_MESSAGES",
    },
)


_FEATURE_FLAG_BY_ID = {str(item["id"]): dict(item) for item in FEATURE_FLAG_DEFINITIONS}


def _env_override_bool(env_key: str) -> bool | None:
    raw = os.getenv(str(env_key or "").strip())
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def feature_flag_definitions() -> list[dict[str, Any]]:
    return [dict(item) for item in FEATURE_FLAG_DEFINITIONS]


def feature_flags_with_defaults(raw_flags: dict[str, Any] | None = None) -> dict[str, bool]:
    source = dict(raw_flags or {})
    resolved: dict[str, bool] = {}
    for item in FEATURE_FLAG_DEFINITIONS:
        flag_id = str(item.get("id") or "").strip()
        env_key = str(item.get("envKey") or "").strip()
        default = bool(item.get("default"))
        value = bool(source.get(flag_id, default))
        env_override = _env_override_bool(env_key)
        if env_override is not None:
            value = env_override
        resolved[flag_id] = value
    return resolved


def feature_flag_enabled(flag_id: str, raw_flags: dict[str, Any] | None = None) -> bool:
    normalized_id = str(flag_id or "").strip()
    if normalized_id not in _FEATURE_FLAG_BY_ID:
        return False
    return bool(feature_flags_with_defaults(raw_flags).get(normalized_id, False))

