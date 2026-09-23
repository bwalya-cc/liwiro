"""Sanitized service capability summaries shared across backend surfaces."""

from __future__ import annotations

import json
from typing import Any

_MEDIA_PROVIDER_SPECS = (
    {
        "id": "cloudinary",
        "label": "Cloudinary",
        "env_keys": (
            "CLOUDINARY_CLOUD_NAME",
            "CLOUDINARY_API_KEY",
            "CLOUDINARY_API_SECRET",
            "CLOUDINARY_FOLDER",
        ),
        "required_env_keys": (
            "CLOUDINARY_CLOUD_NAME",
            "CLOUDINARY_API_KEY",
            "CLOUDINARY_API_SECRET",
        ),
        "path_hints": ("/cloudinary",),
        "script_markers": (
            "api.cloudinary.com/v1_1/",
            "/auto/upload",
        ),
        "input_modes": ("sourceUrl", "dataUri", "dataBase64", "textBody"),
    },
)


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def normalize_config_env(raw_env: Any) -> dict[str, Any]:
    if not isinstance(raw_env, dict):
        return {}
    normalized: dict[str, Any] = {}
    for key, value in raw_env.items():
        env_key = str(key or "").strip().upper()
        if not env_key:
            continue
        if isinstance(value, (str, int, float, bool)):
            normalized[env_key] = value
        elif value is None:
            normalized[env_key] = ""
        else:
            normalized[env_key] = json.dumps(value)
    return normalized


def _is_placeholder_env_value(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return True
    placeholder_markers = (
        "replace-with",
        "replace_me",
        "replace-me",
        "changeme",
        "change-me",
        "<",
        ">",
    )
    return any(marker in text for marker in placeholder_markers)


def _normalize_provider_id(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def summarize_media_capabilities(lapis_config: Any) -> dict[str, Any]:
    cfg = lapis_config if isinstance(lapis_config, dict) else {}
    metadata = cfg.get("metadata") if isinstance(cfg.get("metadata"), dict) else {}
    endpoints = cfg.get("endpoints") if isinstance(cfg.get("endpoints"), dict) else {}
    env = normalize_config_env(metadata.get("env"))

    default_provider = _normalize_provider_id(env.get("MEDIA_DEFAULT_PROVIDER"))
    asset_collection = str(env.get("MEDIA_ASSET_COLLECTION") or "media_assets").strip() or "media_assets"
    providers: list[dict[str, Any]] = []
    input_modes: list[str] = []

    for spec in _MEDIA_PROVIDER_SPECS:
        matched_routes: list[dict[str, str]] = []
        for endpoint_id, endpoint in endpoints.items():
            endpoint_cfg = endpoint if isinstance(endpoint, dict) else {}
            path = str(endpoint_cfg.get("path") or "").strip()
            path_lower = path.lower()
            script_lower = str(endpoint_cfg.get("versaScript") or "").strip().lower()
            if not any(hint in path_lower for hint in spec["path_hints"]) and not any(
                marker in script_lower for marker in spec["script_markers"]
            ):
                continue
            matched_routes.append(
                {
                    "id": str(endpoint_id or "").strip(),
                    "method": str(endpoint_cfg.get("method") or "GET").strip().upper() or "GET",
                    "path": path or "/",
                }
            )

        env_keys_present = [key for key in spec["env_keys"] if key in env]
        ready = all(not _is_placeholder_env_value(env.get(key)) for key in spec["required_env_keys"])
        enabled = bool(matched_routes or env_keys_present or default_provider == spec["id"])
        if not enabled:
            continue

        providers.append(
            {
                "id": spec["id"],
                "label": spec["label"],
                "ready": ready,
                "default": default_provider == spec["id"],
                "envKeys": env_keys_present,
                "routes": matched_routes,
                "inputModes": list(spec["input_modes"]),
            }
        )
        input_modes.extend(spec["input_modes"])

    return {
        "enabled": bool(providers),
        "assetCollection": asset_collection,
        "defaultProvider": default_provider,
        "providers": providers,
        "serviceEnvKeys": sorted(env.keys()),
        "inputModes": _dedupe_preserve_order(input_modes),
        "jsonRequestOnly": bool(providers),
    }
