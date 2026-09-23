from __future__ import annotations

import json
import re
from typing import Any


_SCRIPT_POSITION_RE = re.compile(
    r"(?:Script error\s*\(line\s*(?P<line>\d+),\s*column\s*(?P<column>\d+)\)|line\s*(?P<line2>\d+)\s*:\s*(?P<column2>\d+))",
    re.IGNORECASE,
)
_SCRIPT_PREVIEW_RE = re.compile(r"preview:\s*(?P<preview>[^\n]+)", re.IGNORECASE)


def _json_clone(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _json_signature(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except Exception:
        return ""


def _structured_issue(
    *,
    issue_type: str,
    message: str,
    endpoint_id: str = "",
    endpoint_path: str = "",
    path: str = "",
    line: int | None = None,
    column: int | None = None,
    preview_text: str = "",
    repairable: bool = False,
    code: str = "",
) -> dict[str, Any]:
    return {
        "type": str(issue_type or "").strip() or "validation",
        "message": str(message or "").strip() or "Validation failed.",
        "endpointId": str(endpoint_id or "").strip(),
        "endpointPath": str(endpoint_path or "").strip(),
        "path": str(path or "").strip(),
        "line": int(line) if isinstance(line, int) and line > 0 else None,
        "column": int(column) if isinstance(column, int) and column > 0 else None,
        "previewText": str(preview_text or "").strip(),
        "repairable": bool(repairable),
        "code": str(code or "").strip(),
    }


def _line_column_from_error(text: str) -> tuple[int | None, int | None]:
    match = _SCRIPT_POSITION_RE.search(str(text or ""))
    if not match:
        return None, None
    line = match.group("line") or match.group("line2")
    column = match.group("column") or match.group("column2")
    try:
        return int(line) if line else None, int(column) if column else None
    except Exception:
        return None, None


def _extract_nested_error(payload: Any) -> str:
    if isinstance(payload, dict):
        details = payload.get("details")
        detail_error = str((details or {}).get("error") or "").strip() if isinstance(details, dict) else ""
        if detail_error:
            return detail_error
        direct = str(payload.get("error") or "").strip()
        if direct:
            return direct
    return str(payload or "").strip()


def _preview_text_from_error(text: str) -> str:
    match = _SCRIPT_PREVIEW_RE.search(str(text or ""))
    if not match:
        return ""
    return str(match.group("preview") or "").strip()


def _parse_route_error_payload(raw_text: str) -> Any:
    text = str(raw_text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        return text


def collect_lapis_validation_issues(detail: dict[str, Any] | None) -> list[dict[str, Any]]:
    payload = dict(detail or {})
    issues: list[dict[str, Any]] = []

    for item in list(payload.get("versaIssues") or []):
        if not isinstance(item, dict):
            continue
        error_text = str(item.get("error") or "Versa syntax validation failed.").strip()
        line, column = _line_column_from_error(error_text)
        preview_text = _preview_text_from_error(error_text)
        repairable = "expected ',' after property" in error_text.lower()
        issues.append(
            _structured_issue(
                issue_type="versa-script",
                message=error_text,
                endpoint_id=str(item.get("endpointId") or ""),
                endpoint_path=str(item.get("endpointPath") or ""),
                path=str(item.get("path") or ""),
                line=line,
                column=column,
                preview_text=preview_text,
                repairable=repairable,
                code="missing-comma-after-property" if repairable else "",
            )
        )

    dry_run = payload.get("dryRun") if isinstance(payload.get("dryRun"), dict) else {}
    for item in list(dry_run.get("endpointResults") or []):
        if not isinstance(item, dict) or bool(item.get("ok", True)):
            continue
        endpoint_id = str(item.get("endpointId") or "").strip()
        route = str(item.get("route") or "").strip()
        parsed_payload = _parse_route_error_payload(str(item.get("error") or ""))
        error_text = _extract_nested_error(parsed_payload)
        if not error_text:
            error_text = str(item.get("error") or "Dry-run endpoint validation failed.").strip()
        line, column = _line_column_from_error(error_text)
        preview_text = _preview_text_from_error(error_text)
        repairable = "expected ',' after property" in error_text.lower()
        issues.append(
            _structured_issue(
                issue_type="dry-run-route",
                message=error_text,
                endpoint_id=endpoint_id,
                endpoint_path=route,
                line=line,
                column=column,
                preview_text=preview_text,
                repairable=repairable,
                code="missing-comma-after-property" if repairable else "",
            )
        )

    if issues:
        return issues

    error_text = str(payload.get("error") or "").strip()
    if error_text:
        issues.append(_structured_issue(issue_type="config", message=error_text))
    return issues


def _apply_missing_comma_after_property(
    script_text: str,
    *,
    line: int | None = None,
    preview_text: str = "",
) -> tuple[str, dict[str, Any] | None]:
    lines = str(script_text or "").splitlines()
    if not lines:
        return str(script_text or ""), None

    candidate_indexes: list[int] = []
    preview = str(preview_text or "").strip()
    normalized_preview = preview.rstrip(";").rstrip(",").strip()
    if normalized_preview:
        for index, raw_line in enumerate(lines):
            normalized_line = str(raw_line or "").strip().rstrip(";").rstrip(",").strip()
            if normalized_line == normalized_preview:
                candidate_indexes.append(index)
    if isinstance(line, int) and line > 0 and line <= len(lines):
        candidate_indexes.append(line - 1)
    candidate_indexes.extend(index for index in range(len(lines) - 1, -1, -1) if index not in candidate_indexes)

    for index in candidate_indexes:
        raw_line = lines[index]
        stripped = raw_line.strip()
        if not stripped or stripped.startswith(("#", "//")):
            continue
        if stripped.endswith(","):
            continue
        if stripped in {"{", "}", "};", "]", "];"}:
            continue
        if stripped.endswith("{") or stripped.endswith("["):
            continue
        updated = raw_line.rstrip()
        if updated.endswith(";"):
            updated = updated[:-1].rstrip()
        updated = f"{updated},"
        lines[index] = updated
        return "\n".join(lines), {
            "type": "versa-script",
            "code": "missing-comma-after-property",
            "message": "Added a trailing comma to a Versa object property before revalidation.",
            "line": index + 1,
        }
    return str(script_text or ""), None


def _apply_issue_repairs(config: dict[str, Any], issues: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    working = _json_clone(config or {})
    endpoints = working.get("endpoints") if isinstance(working.get("endpoints"), dict) else {}
    applied: list[dict[str, Any]] = []

    for issue in issues:
        if not isinstance(issue, dict) or not issue.get("repairable"):
            continue
        endpoint_id = str(issue.get("endpointId") or "").strip()
        if not endpoint_id or not isinstance(endpoints.get(endpoint_id), dict):
            continue
        if str(issue.get("code") or "").strip() != "missing-comma-after-property":
            continue
        endpoint = dict(endpoints.get(endpoint_id) or {})
        next_script, fix = _apply_missing_comma_after_property(
            str(endpoint.get("versaScript") or ""),
            line=issue.get("line") if isinstance(issue.get("line"), int) else None,
            preview_text=str(issue.get("previewText") or ""),
        )
        if not fix or next_script == str(endpoint.get("versaScript") or ""):
            continue
        endpoint["versaScript"] = next_script
        endpoints[endpoint_id] = endpoint
        applied.append(
            {
                **fix,
                "endpointId": endpoint_id,
                "endpointPath": str(issue.get("endpointPath") or ""),
            }
        )

    if applied:
        working["endpoints"] = endpoints
    return working, applied


def repair_lapis_config_recursively(
    config: dict[str, Any] | None,
    *,
    include_dry_run: bool = True,
    max_attempts: int = 6,
    allow_safe_schema_fix: bool = True,
) -> dict[str, Any]:
    from config import Config

    current = _json_clone(config or {})
    applied_fixes: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    last_detail: dict[str, Any] | None = None

    for attempt in range(1, max(max_attempts, 1) + 1):
        detail = Config.validate_lapis_config_detailed(current, include_dry_run=include_dry_run)
        last_detail = dict(detail or {})
        issues = collect_lapis_validation_issues(last_detail)
        if bool(last_detail.get("valid")):
            return {
                "ok": True,
                "error": "",
                "normalized": last_detail.get("normalized") if isinstance(last_detail.get("normalized"), dict) else current,
                "dryRun": last_detail.get("dryRun"),
                "issues": [],
                "repairAttempts": attempts,
                "appliedFixes": applied_fixes,
                "attemptCount": attempt - 1,
                "repaired": bool(applied_fixes),
                "repairable": True,
                "finalStatus": "ready",
                "progressMessage": "Validation passed after deterministic repair.",
            }

        next_config = current
        round_fixes: list[dict[str, Any]] = []
        current_signature = _json_signature(current)

        normalized = last_detail.get("normalized") if isinstance(last_detail.get("normalized"), dict) else None
        if allow_safe_schema_fix and isinstance(normalized, dict):
            normalized_signature = _json_signature(normalized)
            if normalized_signature and normalized_signature != current_signature:
                next_config = _json_clone(normalized)
                round_fixes.append(
                    {
                        "type": "config",
                        "code": "safe-schema-normalization",
                        "message": "Applied safe LAPIS schema normalization before revalidation.",
                    }
                )

        repaired_config, issue_fixes = _apply_issue_repairs(next_config, issues)
        if issue_fixes:
            next_config = repaired_config
            round_fixes.extend(issue_fixes)

        attempts.append(
            {
                "attempt": attempt,
                "error": str(last_detail.get("error") or "").strip(),
                "issues": issues,
                "appliedFixes": round_fixes,
                "progressMessage": (
                    "Applied deterministic fixes and revalidating."
                    if round_fixes
                    else "Validation failed and no deterministic fix was available."
                ),
            }
        )

        if not round_fixes or _json_signature(next_config) == current_signature:
            return {
                "ok": False,
                "error": str(last_detail.get("error") or "").strip() or "Validation failed.",
                "normalized": normalized if isinstance(normalized, dict) else current,
                "dryRun": last_detail.get("dryRun"),
                "issues": issues,
                "repairAttempts": attempts,
                "appliedFixes": applied_fixes,
                "attemptCount": attempt,
                "repaired": bool(applied_fixes),
                "repairable": bool(any(bool(item.get("repairable")) for item in issues)),
                "finalStatus": "needs-manual-fix",
                "progressMessage": "No deterministic repair remained. Manual fixes are still required.",
            }

        applied_fixes.extend(round_fixes)
        current = next_config

    normalized = last_detail.get("normalized") if isinstance((last_detail or {}).get("normalized"), dict) else current
    issues = collect_lapis_validation_issues(last_detail or {})
    return {
        "ok": False,
        "error": str((last_detail or {}).get("error") or "").strip() or "Validation failed after exhausting repair attempts.",
        "normalized": normalized,
        "dryRun": (last_detail or {}).get("dryRun"),
        "issues": issues,
        "repairAttempts": attempts,
        "appliedFixes": applied_fixes,
        "attemptCount": len(attempts),
        "repaired": bool(applied_fixes),
        "repairable": bool(any(bool(item.get("repairable")) for item in issues)),
        "finalStatus": "needs-manual-fix",
        "progressMessage": "Validation still failed after exhausting deterministic repair attempts.",
    }
