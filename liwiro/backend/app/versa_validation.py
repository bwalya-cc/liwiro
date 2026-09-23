# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[3]
_VI_TARGET_DIR = _REPO_ROOT / "verun" / "vi" / "target"
_CUSTOM_MODULES_DIR = _REPO_ROOT / "verun" / "vi" / "custom_modules" / "modules"
_GENERIC_VERSA_PATHS = {
    "scratch/playground.versa",
    "scratch/unsaved.versa",
    "scratch/verse-draft.versa",
    "scratch/draft.versa",
    "scratch/script.versa",
    "playground.versa",
    "unsaved.versa",
    "draft.versa",
}
_CORE_OPTIONAL_MODULES = {"vdb", "http", "email", "json_xml", "filer", "crypto", "jwt", "time", "datetime", "random"}
_MODULE_IMPORT_LINE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s+import\s+(?:\*|\{[^;]*\})\s*;\s*$")
_MODULE_NAMESPACE_IMPORT_LINE_RE = re.compile(r"^\s*import\s+([A-Za-z_][A-Za-z0-9_]*)\s*;\s*$")
_DECLARED_IDENTIFIER_RE = re.compile(r"\b(?:let|var|const|func|class)\s+([A-Za-z_][A-Za-z0-9_]*)")
_KNOWN_SCRIPT_RUNTIME_IDENTIFIERS = {"params", "service", "request", "response", "context", "auth", "env"}


def _slugify_versa_stem(*values: Any, default: str = "verse-draft") -> str:
    for value in values:
        text = str(value or "").strip().lower()
        if not text:
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
        if slug:
            return slug[:64].strip("-") or default
    return default


def _normalize_versa_relpath(path_value: str) -> str:
    candidate = Path(str(path_value or "").strip().replace("\\", "/"))
    if not str(candidate) or candidate.is_absolute():
        raise ValueError("Invalid file path")
    parts = [part for part in candidate.parts if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        raise ValueError("Invalid file path")
    normalized = Path(*parts)
    suffix = normalized.suffix.lower()
    if not suffix:
        normalized = normalized.with_suffix(".versa")
    elif suffix != ".versa":
        normalized = normalized.with_suffix(".versa")
    return normalized.as_posix()


def suggest_versa_relpath(path_value: str = "", *, title: str = "", user_text: str = "") -> str:
    raw_path = str(path_value or "").strip()
    if raw_path:
        try:
            normalized = _normalize_versa_relpath(raw_path)
            if normalized.lower() not in _GENERIC_VERSA_PATHS:
                return normalized
        except ValueError:
            pass
    stem = _slugify_versa_stem(title, user_text, default="verse-draft")
    return f"scratch/{stem}.versa"


def _resolve_vi_validation_classpath() -> str:
    candidates = [
        _VI_TARGET_DIR / "vi-1.0.0-jar-with-dependencies.jar",
        _VI_TARGET_DIR / "vi-1.0.0.jar",
        _VI_TARGET_DIR / "classes",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return ""


def _known_versa_module_names() -> set[str]:
    names = set(_CORE_OPTIONAL_MODULES)
    if _CUSTOM_MODULES_DIR.exists():
        for path in _CUSTOM_MODULES_DIR.glob("*.versa"):
            names.add(path.stem.lower())
    return names


def _strip_versa_comments_and_strings(source: str) -> str:
    out: list[str] = []
    quote = ""
    escape = False
    comment = False
    for ch in str(source or ""):
        if comment:
            if ch == "\n":
                comment = False
                out.append("\n")
            else:
                out.append(" ")
            continue
        if quote:
            if escape:
                escape = False
                out.append(" ")
                continue
            if ch == "\\":
                escape = True
                out.append(" ")
                continue
            if ch == quote:
                quote = ""
                out.append(" ")
                continue
            out.append("\n" if ch == "\n" else " ")
            continue
        if ch == "#":
            comment = True
            out.append(" ")
            continue
        if ch in {"'", "\"", "`"}:
            quote = ch
            out.append(" ")
            continue
        out.append(ch)
    return "".join(out)


def _top_level_module_import_issues(source: str, known_modules: set[str]) -> tuple[set[str], list[str]]:
    imported: set[str] = set()
    issues: list[str] = []
    seen_code = False
    for line_number, raw in enumerate(str(source or "").splitlines(), start=1):
        trimmed = str(raw or "").strip()
        if not trimmed or trimmed.startswith("#") or trimmed.startswith("//"):
            continue
        module_match = _MODULE_IMPORT_LINE_RE.match(raw)
        if module_match:
            module = str(module_match.group(1) or "").strip().lower()
            if module in known_modules:
                if seen_code:
                    issues.append(f"Module imports must appear at the top of the file/script: {module} (line {line_number}).")
                imported.add(module)
                continue
        namespace_match = _MODULE_NAMESPACE_IMPORT_LINE_RE.match(raw)
        if namespace_match:
            module = str(namespace_match.group(1) or "").strip().lower()
            if module in known_modules:
                if seen_code:
                    issues.append(f"Module imports must appear at the top of the file/script: {module} (line {line_number}).")
                imported.add(module)
                continue
        seen_code = True
    return imported, issues


def _runtime_surface_issues(source: str) -> list[str]:
    text = str(source or "")
    if not text.strip():
        return []
    known_modules = _known_versa_module_names()
    imported, issues = _top_level_module_import_issues(text, known_modules)
    scrubbed = _strip_versa_comments_and_strings(text)
    declared_names = {match.group(1).lower() for match in _DECLARED_IDENTIFIER_RE.finditer(scrubbed)}
    for module in sorted(known_modules):
        if module in imported or module in declared_names:
            continue
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(module)}\s*\.", scrubbed):
            issues.append(
                f"Module '{module}' is used as a namespace but not imported. Add '{module} import *;' or 'import {module};' at the top of the file before executable code."
            )
    deduped: list[str] = []
    seen: set[str] = set()
    for issue in issues:
        if issue not in seen:
            seen.add(issue)
            deduped.append(issue)
    return deduped


def _is_known_runtime_name_error(message: str) -> bool:
    raw = str(message or "").strip()
    match = re.search(r"Undefined variable:\s*([A-Za-z_][A-Za-z0-9_]*)", raw)
    if not match:
        return False
    return str(match.group(1) or "").strip().lower() in _KNOWN_SCRIPT_RUNTIME_IDENTIFIERS


def validate_versa_source(source: str, *, path_hint: str = "") -> dict[str, Any]:
    text = str(source or "")
    if not text.strip():
        return {"ok": False, "error": "Versa source is required.", "path": suggest_versa_relpath(path_hint)}

    classpath = _resolve_vi_validation_classpath()
    if not classpath:
        return {
            "ok": False,
            "error": "VI parser runtime is not available. Build verun/vi before validating Versa source.",
            "path": suggest_versa_relpath(path_hint),
        }

    requested_path = suggest_versa_relpath(path_hint)
    tmp_path = None
    try:
        stem = Path(requested_path).stem or "verse-validate"
        with tempfile.NamedTemporaryFile("w", suffix=f"-{stem}.versa", delete=False, encoding="utf-8") as handle:
            tmp_path = handle.name
            handle.write(text)

        proc = subprocess.run(
            ["java", "-cp", classpath, "verun.runtime.Main", tmp_path, "--parse-only", "--msg-only"],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env={**os.environ},
        )
        if proc.returncode == 0:
            runtime_issues = _runtime_surface_issues(text)
            if runtime_issues:
                return {"ok": False, "error": runtime_issues[0], "issues": runtime_issues, "path": requested_path}
            return {"ok": True, "error": "", "path": requested_path}

        message = str(proc.stderr or proc.stdout or "Versa syntax validation failed.").strip()
        if _is_known_runtime_name_error(message):
            runtime_issues = _runtime_surface_issues(text)
            if runtime_issues:
                return {"ok": False, "error": runtime_issues[0], "issues": runtime_issues, "path": requested_path}
            return {"ok": True, "error": "", "path": requested_path, "warning": message[-4000:]}
        return {"ok": False, "error": message[-4000:], "path": requested_path}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Versa syntax validation timed out.", "path": requested_path}
    except Exception as exc:
        return {"ok": False, "error": f"Versa syntax validation failed: {exc}", "path": requested_path}
    finally:
        if tmp_path:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass


def validate_lapis_versa_scripts(config: dict[str, Any]) -> list[dict[str, str]]:
    metadata = config.get("metadata") if isinstance(config.get("metadata"), dict) else {}
    api_name = str(metadata.get("apiName") or "").strip()
    issues: list[dict[str, str]] = []
    endpoints = config.get("endpoints") if isinstance(config.get("endpoints"), dict) else {}
    for endpoint_id, endpoint in endpoints.items():
        if not isinstance(endpoint, dict):
            continue
        if str(endpoint.get("operationType") or "").strip().lower() != "script":
            continue
        script_text = str(endpoint.get("versaScript") or "")
        if not script_text.strip():
            continue
        route_path = str(endpoint.get("path") or endpoint_id or "").strip() or str(endpoint_id or "endpoint")
        path_hint = suggest_versa_relpath(
            f"service-scripts/{api_name or 'service'}/{endpoint_id or 'endpoint'}.versa",
            title=route_path,
            user_text=api_name,
        )
        result = validate_versa_source(script_text, path_hint=path_hint)
        if result.get("ok"):
            continue
        issues.append(
            {
                "endpointId": str(endpoint_id),
                "endpointPath": route_path,
                "path": str(result.get("path") or path_hint),
                "error": str(result.get("error") or "Versa syntax validation failed."),
            }
        )
    return issues
