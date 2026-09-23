from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.vdb_bson import read_bson_value, write_bson_value
from config import Config


CORE_VI_MODULE_NAMES = {
    "vdb",
    "http",
    "email",
    "json_xml",
    "filer",
    "crypto",
    "jwt",
    "time",
    "datetime",
    "random",
}

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MODULE_STORE_FALLBACK_ROOT: Path | None = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _vdb_root() -> Path:
    configured = str(os.getenv("VERUN_VDB_ROOT") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (_repo_root() / "verun" / "vdb").resolve()


def _module_store_root() -> Path:
    """Return the module collection root, with a runtime fallback for read-only hosts."""
    global _MODULE_STORE_FALLBACK_ROOT
    if _MODULE_STORE_FALLBACK_ROOT is not None:
        return _MODULE_STORE_FALLBACK_ROOT
    configured = str(os.getenv("LIWIRO_VI_MODULE_STORE_DIR") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return _vdb_root() / "__data__" / "domains" / "default" / "dbs" / "main" / "collections" / "modules"


def _use_module_store_fallback() -> Path:
    global _MODULE_STORE_FALLBACK_ROOT
    fallback = Path(tempfile.gettempdir()) / "liwiro" / "vi-module-store"
    fallback.mkdir(parents=True, exist_ok=True)
    _MODULE_STORE_FALLBACK_ROOT = fallback.resolve()
    return _MODULE_STORE_FALLBACK_ROOT


def _vdb_modules_collection_dir() -> Path:
    return _module_store_root()


def _vdb_modules_data_dir() -> Path:
    return _vdb_modules_collection_dir() / "data"


def _vdb_modules_sys_dir() -> Path:
    return _vdb_modules_collection_dir() / "sys"


def _vdb_module_model_path() -> Path:
    return _vdb_modules_sys_dir() / "model.bson"


def _vdb_module_indexes_path() -> Path:
    return _vdb_modules_sys_dir() / "indexes.bson"


def _vdb_module_document_path(name: Any) -> Path:
    return _vdb_modules_data_dir() / f"{normalize_module_name(name)}.bson"


def default_custom_modules_dir() -> Path:
    return (_repo_root() / "verun" / "vi" / "custom_modules").resolve()


def custom_modules_dir(app_config: dict | None = None) -> Path:
    configured = ""
    if isinstance(app_config, dict):
        configured = str(app_config.get("VI_CUSTOM_MODULES_DIR") or "").strip()
    if not configured:
        configured = str(os.getenv("VI_CUSTOM_MODULES_DIR") or getattr(Config, "VI_CUSTOM_MODULES_DIR", "") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return default_custom_modules_dir()


def registry_path(app_config: dict | None = None) -> Path:
    return custom_modules_dir(app_config) / "registry.json"


def modules_source_dir(app_config: dict | None = None) -> Path:
    return custom_modules_dir(app_config) / "modules"


def normalize_module_name(name: Any) -> str:
    return str(name or "").strip().lower()


def validate_module_name(name: Any) -> str:
    normalized = normalize_module_name(name)
    if not normalized:
        raise ValueError("Module name is required")
    if not _IDENTIFIER_RE.fullmatch(normalized):
        raise ValueError("Module name must be a lowercase Versa identifier")
    if normalized in CORE_VI_MODULE_NAMES:
        raise ValueError(f"Module name '{normalized}' conflicts with a reserved VI core module")
    return normalized


def reserved_module_names() -> list[str]:
    return sorted(CORE_VI_MODULE_NAMES)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mediacloud_source() -> str:
    return """json_xml import *;
http import *;
crypto import *;
datetime import *;

func _trim(value) {
  return str(value ?? "").trim();
}

func _service_env() {
  return env ?? {};
}

func _config_value(runtimeConfig, key, fallback) {
  let cfg = runtimeConfig ?? {};
  let moduleCfg = module_config ?? {};
  let env = _service_env();
  return cfg[key] ?? moduleCfg[key] ?? env[key] ?? fallback;
}

func _config_text(runtimeConfig, key, fallback) {
  return _trim(_config_value(runtimeConfig, key, fallback));
}

func _default_provider(runtimeConfig) {
  let value = _config_text(runtimeConfig, "defaultProvider", _service_env().MEDIA_DEFAULT_PROVIDER ?? "cloudinary");
  if (value == "" || value != "cloudinary") {
    return "cloudinary";
  }
  return value;
}

func _cloudinary_ready(runtimeConfig) {
  return !(
    _config_text(runtimeConfig, "cloudName", _service_env().CLOUDINARY_CLOUD_NAME ?? "") == ""
    || _config_text(runtimeConfig, "apiKey", _service_env().CLOUDINARY_API_KEY ?? "") == ""
    || _config_text(runtimeConfig, "apiSecret", _service_env().CLOUDINARY_API_SECRET ?? "") == ""
  );
}

func providers(runtimeConfig) {
  return {
    cloudinary: {
      ready: _cloudinary_ready(runtimeConfig),
      folder: _config_text(runtimeConfig, "folder", _service_env().CLOUDINARY_FOLDER ?? "")
    }
  };
}

func status(runtimeConfig) {
  return {
    ok: true,
    defaultProvider: _default_provider(runtimeConfig),
    providers: providers(runtimeConfig)
  };
}

func _normalize_payload(payload) {
  let req = payload ?? {};
  let body = req.body ?? req ?? {};
  return {
    request: req,
    body: body,
    provider: _trim(req.provider ?? body.provider ?? _default_provider(req.config ?? {}))
  };
}

func _cloudinary_upload(payload) {
  let normalized = _normalize_payload(payload);
  let req = normalized.request;
  let body = normalized.body;
  let runtimeConfig = req.config ?? {};
  let cloudName = _config_text(runtimeConfig, "cloudName", _service_env().CLOUDINARY_CLOUD_NAME ?? "");
  let apiKey = _config_text(runtimeConfig, "apiKey", _service_env().CLOUDINARY_API_KEY ?? "");
  let apiSecret = _config_text(runtimeConfig, "apiSecret", _service_env().CLOUDINARY_API_SECRET ?? "");
  let folder = _trim(body.folder ?? req.folder ?? _config_value(runtimeConfig, "folder", _service_env().CLOUDINARY_FOLDER ?? ""));
  let publicId = _trim(body.publicId ?? req.publicId ?? "");
  let sourceUrl = _trim(body.sourceUrl ?? req.sourceUrl ?? "");
  let dataUri = _trim(body.dataUri ?? req.dataUri ?? "");
  let dataBase64 = _trim(body.dataBase64 ?? req.dataBase64 ?? "");
  let textBody = _trim(body.textBody ?? req.textBody ?? "");
  let filename = _trim(body.filename ?? req.filename ?? publicId ?? "cloudinary-upload.bin");
  let mimeType = _trim(body.mimeType ?? req.mimeType ?? "application/octet-stream");
  let fileValue = dataUri;
  if (fileValue == "" && dataBase64 != "") {
    fileValue = "data:" + mimeType + ";base64," + dataBase64;
  }
  if (fileValue == "" && textBody != "") {
    fileValue = "data:text/plain;base64," + crypto.base64_encode(textBody);
    if (mimeType == "application/octet-stream") {
      mimeType = "text/plain";
    }
  }
  if (fileValue == "") {
    fileValue = sourceUrl;
  }
  if (cloudName == "" || apiKey == "" || apiSecret == "") {
    return {ok: false, statusCode: 500, error: "Missing Cloudinary configuration", provider: "cloudinary"};
  }
  if (fileValue == "") {
    return {ok: false, statusCode: 400, error: "Provide sourceUrl, dataUri, dataBase64, or textBody", provider: "cloudinary"};
  }
  let form = {file: fileValue};
  if (folder != "") {
    form.folder = folder;
  }
  if (publicId != "") {
    form.public_id = publicId;
  }
  let uploadRes = http.post("https://api.cloudinary.com/v1_1/" + cloudName + "/auto/upload", {
    authBasic: {username: apiKey, password: apiSecret},
    form: form,
    timeoutSeconds: 90
  });
  let providerPayload = {};
  let bodyText = _trim(uploadRes.body ?? "");
  if (bodyText != "") {
    providerPayload = json_xml.parse_json(bodyText);
  }
  if (!(uploadRes.ok == true)) {
    return {ok: false, statusCode: uploadRes.status ?? 500, error: "Cloudinary upload failed", provider: "cloudinary", raw: uploadRes, providerResponse: providerPayload};
  }
  return {
    ok: true,
    statusCode: uploadRes.status ?? 200,
    provider: "cloudinary",
    filename: filename,
    mimeType: mimeType,
    providerAssetId: _trim(providerPayload.asset_id ?? ""),
    storageBucket: "",
    storagePath: _trim(providerPayload.public_id ?? publicId ?? ""),
    publicUrl: _trim(providerPayload.url ?? ""),
    secureUrl: _trim(providerPayload.secure_url ?? providerPayload.url ?? ""),
    sizeBytes: providerPayload.bytes ?? 0,
    providerResponse: providerPayload
  };
}

func upload(payload) {
  let provider = _normalize_payload(payload).provider;
  if (provider == "" || provider == "cloudinary") {
    return _cloudinary_upload(payload);
  }
  return {ok: false, statusCode: 400, error: "Unsupported media provider", provider: provider};
}
"""


def _default_registry_payload() -> dict:
    now = _iso_now()
    return {
        "version": 1,
        "modules": [
            {
                "name": "mediacloud",
                "title": "MediaCloud",
                "description": "Cloudinary media-storage adapter for Versa services and demos.",
                "scope": "global",
                "owner_username": "system",
                "owner_domains": [],
                "assigned_domains": [],
                "domain_restore": [],
                "config_schema": {
                    "defaultProvider": {"type": "string", "enum": ["cloudinary"]},
                    "cloudName": {"type": "string"},
                    "apiKey": {"type": "string"},
                    "apiSecret": {"type": "string"},
                    "folder": {"type": "string"},
                },
                "config_defaults": {"defaultProvider": "cloudinary"},
                "source_path": "modules/mediacloud.versa",
                "created_at": now,
                "updated_at": now,
            }
        ],
    }


def _ensure_seed_files(app_config: dict | None = None) -> None:
    root = custom_modules_dir(app_config)
    root.mkdir(parents=True, exist_ok=True)
    modules_dir = modules_source_dir(app_config)
    modules_dir.mkdir(parents=True, exist_ok=True)
    registry = registry_path(app_config)
    if not registry.exists():
        registry.write_text(json.dumps(_default_registry_payload(), indent=2), encoding="utf-8")
    mediacloud_path = modules_dir / "mediacloud.versa"
    if not mediacloud_path.exists():
        mediacloud_path.write_text(_mediacloud_source(), encoding="utf-8")


def _default_vdb_module_schema() -> dict[str, Any]:
    return {
        "_id": {"type": "string", "required": True, "unique": True},
        "name": {"type": "string", "required": True, "unique": True},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "scope": {"type": "string"},
        "owner_username": {"type": "string"},
        "owner_domains": {"type": "array"},
        "assigned_domains": {"type": "array"},
        "domain_restore": {"type": "array"},
        "service_domain": {"type": "string"},
        "config_schema": {"type": "object"},
        "config_defaults": {"type": "object"},
        "source": {"type": "string"},
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
        "created_by": {"type": "string"},
        "updated_by": {"type": "string"},
    }


def _seed_vdb_module_record() -> dict[str, Any]:
    now = _iso_now()
    return {
        "_id": "mediacloud",
        "name": "mediacloud",
        "title": "MediaCloud",
        "description": "Cloudinary media-storage adapter for Versa services and demos.",
        "scope": "global",
        "owner_username": "system",
        "owner_domains": [],
        "assigned_domains": [],
        "domain_restore": [],
        "service_domain": "services",
        "config_schema": {
            "defaultProvider": {"type": "string", "enum": ["cloudinary"]},
            "cloudName": {"type": "string"},
            "apiKey": {"type": "string"},
            "apiSecret": {"type": "string"},
            "folder": {"type": "string"},
        },
        "config_defaults": {"defaultProvider": "cloudinary"},
        "source": _mediacloud_source(),
        "created_at": now,
        "updated_at": now,
        "created_by": "system",
        "updated_by": "system",
    }


def _normalize_vdb_module_record(raw: dict[str, Any] | None) -> dict[str, Any]:
    record = raw if isinstance(raw, dict) else {}
    name = normalize_module_name(record.get("name") or record.get("_id"))
    scope = str(record.get("scope") or "domain").strip().lower()
    if scope not in {"domain", "global"}:
        scope = "domain"
    return {
        "name": name,
        "_id": name,
        "title": str(record.get("title") or name).strip() or name,
        "description": str(record.get("description") or "").strip(),
        "scope": scope,
        "owner_username": str(record.get("owner_username") or "").strip().lower(),
        "owner_domains": _normalize_domains(record.get("owner_domains")),
        "assigned_domains": _normalize_domains(record.get("assigned_domains")),
        "domain_restore": _normalize_domains(record.get("domain_restore")),
        "service_domain": str(record.get("service_domain") or record.get("serviceDomain") or "services").strip().lower(),
        "config_schema": record.get("config_schema") if isinstance(record.get("config_schema"), dict) else {},
        "config_defaults": record.get("config_defaults") if isinstance(record.get("config_defaults"), dict) else {},
        "source": str(record.get("source") or ""),
        "created_at": str(record.get("created_at") or _iso_now()),
        "updated_at": str(record.get("updated_at") or record.get("created_at") or _iso_now()),
        "created_by": str(record.get("created_by") or record.get("owner_username") or "").strip().lower(),
        "updated_by": str(record.get("updated_by") or record.get("owner_username") or "").strip().lower(),
    }


def _ensure_vdb_module_store() -> None:
    try:
        _ensure_vdb_module_store_at_current_root()
    except (OSError, PermissionError):
        # The control plane can run with a read-only checked-out Verun tree
        # (managed containers and validation workers do this routinely). Keep
        # module management functional by moving only this mutable registry to
        # an isolated runtime store; an explicitly configured store remains
        # authoritative and its errors are still surfaced.
        if str(os.getenv("LIWIRO_VI_MODULE_STORE_DIR") or "").strip():
            raise
        _use_module_store_fallback()
        _ensure_vdb_module_store_at_current_root()


def _ensure_vdb_module_store_at_current_root() -> None:
    _vdb_modules_data_dir().mkdir(parents=True, exist_ok=True)
    _vdb_modules_sys_dir().mkdir(parents=True, exist_ok=True)
    if not _vdb_module_model_path().exists():
        write_bson_value(_vdb_module_model_path(), _default_vdb_module_schema())
    if not _vdb_module_indexes_path().exists():
        write_bson_value(_vdb_module_indexes_path(), {})
    seed_path = _vdb_module_document_path("mediacloud")
    desired = _seed_vdb_module_record()
    current: dict[str, Any] = {}
    if seed_path.exists():
        try:
            payload = read_bson_value(seed_path)
            current = payload if isinstance(payload, dict) else {}
        except Exception:
            current = {}
    if (
        not seed_path.exists()
        or str(current.get("description") or "").strip() != str(desired.get("description") or "").strip()
        or current.get("config_schema") != desired.get("config_schema")
        or str(current.get("source") or "") != str(desired.get("source") or "")
    ):
        write_bson_value(seed_path, desired)


def _list_vdb_module_records() -> list[dict[str, Any]]:
    _ensure_vdb_module_store()
    out: list[dict[str, Any]] = []
    for candidate in sorted(_vdb_modules_data_dir().glob("*.bson")):
        try:
            payload = read_bson_value(candidate)
        except Exception:
            continue
        normalized = _normalize_vdb_module_record(payload if isinstance(payload, dict) else {})
        if normalized["name"]:
            out.append(normalized)
    return out


def _load_legacy_registry_records(include_source: bool = False, app_config: dict | None = None) -> list[dict[str, Any]]:
    _ensure_seed_files(app_config)
    path = registry_path(app_config)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = _default_registry_payload()
    raw_modules = data.get("modules") if isinstance(data, dict) else []
    normalized = []
    seen = set()
    for item in raw_modules if isinstance(raw_modules, list) else []:
        if not isinstance(item, dict):
            continue
        entry = _normalize_registry_entry(item)
        if not entry["name"] or entry["name"] in seen:
            continue
        seen.add(entry["name"])
        if include_source:
            try:
                source_file = _resolve_source_file(entry["source_path"], app_config)
                entry["source"] = source_file.read_text(encoding="utf-8") if source_file.exists() else ""
            except Exception:
                entry["source"] = ""
        normalized.append(entry)
    if "mediacloud" not in seen:
        seed = _normalize_registry_entry(_default_registry_payload()["modules"][0])
        if include_source:
            seed["source"] = _mediacloud_source()
        normalized.append(seed)
    return normalized


def _normalize_domains(raw_domains: Any) -> list[str]:
    values = raw_domains if isinstance(raw_domains, list) else [raw_domains]
    out: list[str] = []
    for value in values:
        text = str(value or "").strip().lower()
        if text and text not in out:
            out.append(text)
    return out


def _normalize_registry_entry(raw: dict[str, Any]) -> dict[str, Any]:
    name = normalize_module_name(raw.get("name"))
    source_path = str(raw.get("source_path") or f"modules/{name}.versa").strip() or f"modules/{name}.versa"
    scope = str(raw.get("scope") or "domain").strip().lower()
    if scope not in {"domain", "global"}:
        scope = "domain"
    return {
        "name": name,
        "title": str(raw.get("title") or name).strip() or name,
        "description": str(raw.get("description") or "").strip(),
        "scope": scope,
        "owner_username": str(raw.get("owner_username") or "").strip().lower(),
        "owner_domains": _normalize_domains(raw.get("owner_domains")),
        "assigned_domains": _normalize_domains(raw.get("assigned_domains")),
        "domain_restore": _normalize_domains(raw.get("domain_restore")),
        "config_schema": raw.get("config_schema") if isinstance(raw.get("config_schema"), dict) else {},
        "config_defaults": raw.get("config_defaults") if isinstance(raw.get("config_defaults"), dict) else {},
        "source_path": source_path,
        "created_at": str(raw.get("created_at") or _iso_now()),
        "updated_at": str(raw.get("updated_at") or raw.get("created_at") or _iso_now()),
    }


def load_module_registry(app_config: dict | None = None) -> dict[str, Any]:
    modules = list_module_records(include_source=False, app_config=app_config)
    payload_modules = []
    for entry in modules:
        payload_modules.append(
            {
                "name": entry.get("name"),
                "title": entry.get("title"),
                "description": entry.get("description"),
                "scope": entry.get("scope"),
                "owner_username": entry.get("owner_username"),
                "owner_domains": entry.get("owner_domains") or [],
                "assigned_domains": entry.get("assigned_domains") or [],
                "domain_restore": entry.get("domain_restore") or [],
                "service_domain": entry.get("service_domain") or "services",
                "config_schema": entry.get("config_schema") or {},
                "config_defaults": entry.get("config_defaults") or {},
                "created_at": entry.get("created_at"),
                "updated_at": entry.get("updated_at"),
                "created_by": entry.get("created_by"),
                "updated_by": entry.get("updated_by"),
            }
        )
    return {"version": 1, "modules": payload_modules}


def save_module_registry(data: dict[str, Any], app_config: dict | None = None) -> None:
    for item in (data or {}).get("modules") or []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "")
        write_module_record(item, source, app_config)


def _resolve_source_file(source_path: str, app_config: dict | None = None) -> Path:
    base = custom_modules_dir(app_config)
    resolved = (base / str(source_path or "").strip()).resolve()
    resolved.relative_to(base)
    return resolved


def list_module_records(include_source: bool = False, app_config: dict | None = None) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []

    for entry in _list_vdb_module_records():
        record = dict(entry)
        if not include_source:
            record.pop("source", None)
        name = str(record.get("name") or "").strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(record)

    for entry in _load_legacy_registry_records(include_source=include_source, app_config=app_config):
        name = str(entry.get("name") or "").strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(entry)

    out.sort(key=lambda item: (str(item.get("scope") or "") != "global", str(item.get("name") or "")))
    return out


def load_module_record(name: Any, include_source: bool = True, app_config: dict | None = None) -> dict[str, Any] | None:
    target = normalize_module_name(name)
    if not target:
        return None
    vdb_path = _vdb_module_document_path(target)
    if vdb_path.exists():
        try:
            payload = read_bson_value(vdb_path)
            record = _normalize_vdb_module_record(payload if isinstance(payload, dict) else {})
            if not include_source:
                record.pop("source", None)
            if record.get("name") == target:
                return record
        except Exception:
            pass
    for entry in _load_legacy_registry_records(include_source=include_source, app_config=app_config):
        if entry.get("name") == target:
            return entry
    return None


def write_module_record(record: dict[str, Any], source: str, app_config: dict | None = None) -> dict[str, Any]:
    name = validate_module_name(record.get("name"))
    now = _iso_now()
    existing = load_module_record(name, include_source=True, app_config=app_config) or {}
    normalized = _normalize_vdb_module_record(
        {
            **existing,
            **record,
            "_id": name,
            "name": name,
            "source": str(source or ""),
            "created_at": record.get("created_at") or existing.get("created_at") or now,
            "updated_at": now,
            "created_by": record.get("created_by") or existing.get("created_by") or record.get("owner_username") or existing.get("owner_username") or "",
            "updated_by": record.get("updated_by") or record.get("owner_username") or existing.get("owner_username") or "",
        }
    )
    _ensure_vdb_module_store()
    try:
        write_bson_value(_vdb_module_document_path(name), normalized)
    except (OSError, PermissionError):
        if str(os.getenv("LIWIRO_VI_MODULE_STORE_DIR") or "").strip():
            raise
        _use_module_store_fallback()
        _ensure_vdb_module_store()
        write_bson_value(_vdb_module_document_path(name), normalized)
    return normalized


def delete_module_record(name: Any, app_config: dict | None = None) -> bool:
    target = normalize_module_name(name)
    if not target:
        return False
    removed = False
    vdb_path = _vdb_module_document_path(target)
    if vdb_path.exists():
        vdb_path.unlink()
        removed = True
    legacy = load_module_record(target, include_source=False, app_config=app_config)
    if legacy and str(legacy.get("source_path") or "").strip():
        try:
            registry = _load_legacy_registry_records(include_source=False, app_config=app_config)
            kept = [item for item in registry if item.get("name") != target]
            _ensure_seed_files(app_config)
            registry_path(app_config).write_text(json.dumps({"version": 1, "modules": kept}, indent=2), encoding="utf-8")
            source_file = _resolve_source_file(str(legacy.get("source_path") or ""), app_config)
            if source_file.exists():
                source_file.unlink()
            removed = True
        except Exception:
            pass
    return removed
