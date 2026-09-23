from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any
import json
import re

from .models import (
    AgentDefinition,
    ContextLibraryEntry,
    PromptContextEntry,
    PromptContextReport,
    RetrievalTraceEntry,
    SkillDefinition,
    VerseScaffold,
)
from .providers.base import AIContextBlock
from .routing import tokenize


_REPO_ROOT = Path(__file__).resolve().parents[4]
_DOC_ROOT = _REPO_ROOT / "docs"
_VI_WIKI_ROOT = _REPO_ROOT / "verun" / "vi" / "versa-wiki"
_LIWIRO_REFERENCE_ROOT = _REPO_ROOT / "liwiro" / "verse" / "liwiro-platform-reference"
_SHARED_DOCS_PATH = _REPO_ROOT / "liwiro" / "verse" / "context" / "reference" / "ai-operation-reference.json"

_MANUAL_SPECS = {
    "liwiro-platform-reference": {
        "label": "Liwiro Platform Reference",
        "path": _LIWIRO_REFERENCE_ROOT / "reference.json",
        "wiki": "",
    },
    "verse-chat": {
        "label": "Verse Chat Manual",
        "path": _DOC_ROOT / "liwiro" / "verse-chat.md",
        "wiki": "/wiki/verse-manual",
    },
    "versa-canonical-reference": {
        "label": "Versa Canonical Reference",
        "path": _VI_WIKI_ROOT / "versa-reference.json",
        "wiki": "/wiki/versa-wiki",
    },
    "versa-runtime": {
        "label": "VI Runtime and REPL",
        "path": _DOC_ROOT / "verun" / "versa" / "runtime-cli-repl.md",
        "wiki": "/wiki/vi-portal-manual",
    },
    "vql-reference": {
        "label": "VQL Reference",
        "path": _DOC_ROOT / "verun" / "vdb" / "vql-reference.md",
        "wiki": "/wiki/vql-reference",
    },
    "vdb-usage": {
        "label": "VDB Usage Guide",
        "path": _DOC_ROOT / "verun" / "vdb" / "usage-guide.md",
        "wiki": "/wiki/verun-vdb-manual",
    },
}

_VERSA_IMPORT_RE = re.compile(
    r"(?m)^\s*(?:import\s+([A-Za-z_./-][A-Za-z0-9_./-]*)\s*;|([A-Za-z_./-][A-Za-z0-9_./-]*)\s+import\s+(?:\*|\{[^}]*\})\s*;)"
)
_VERSA_UNDOCUMENTED_CONSTRUCT_PATTERNS = (
    ("async", "No shared-corpus or canonical Versa guidance was found for async/await style flows."),
    ("await", "No shared-corpus or canonical Versa guidance was found for async/await style flows."),
    ("yield", "No shared-corpus or canonical Versa guidance was found for generator/yield syntax."),
    ("decorator", "No shared-corpus or canonical Versa guidance was found for decorators."),
    ("@", "No shared-corpus or canonical Versa guidance was found for decorator-style syntax."),
    ("switch", "No shared-corpus or canonical Versa guidance was found for switch statements."),
    ("enum", "No shared-corpus or canonical Versa guidance was found for enum declarations."),
    ("interface", "No shared-corpus or canonical Versa guidance was found for interface declarations."),
    ("promise", "No shared-corpus or canonical Versa guidance was found for Promise-style APIs."),
)

_CONTEXT_CHAR_LIMITS = {
    "bootstrap": 2400,
    "agent-profile": 1600,
    "guardrails": 1200,
    "thread-rules": 1200,
    "thread": 1200,
    "skill": 700,
    "mind-share": 1600,
    "reference": 3000,
    "manual": 2400,
    "validator": 1400,
    "learning": 720,
    "platform": 1800,
}


@lru_cache(maxsize=None)
def _read_manual_text(path_str: str) -> str:
    path = Path(path_str)
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=1)
def _load_shared_docs() -> list[dict[str, Any]]:
    if not _SHARED_DOCS_PATH.exists():
        return []
    try:
        payload = json.loads(_SHARED_DOCS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    docs = [item for item in payload if isinstance(item, dict)]
    docs.sort(key=lambda item: int(item.get("order") or 0))
    return docs


@lru_cache(maxsize=1)
def _read_versa_reference_payload() -> dict[str, Any]:
    raw = _read_manual_text(str(_MANUAL_SPECS["versa-canonical-reference"]["path"]))
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


@lru_cache(maxsize=1)
def _read_liwiro_reference_payload() -> dict[str, Any]:
    raw = _read_manual_text(str(_MANUAL_SPECS["liwiro-platform-reference"]["path"]))
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalize_text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    out: list[str] = []
    for item in list(value or []):
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out


def _compact_code_lines(lines: Any, limit: int = 8) -> str:
    collected = [str(line).rstrip() for line in list(lines or []) if str(line).strip()]
    if limit > 0 and len(collected) > limit:
        collected = collected[:limit] + ["..."]
    return "\n".join(collected).strip()


def _verse_section_lookup(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for raw in list(payload.get("sections") or []):
        if not isinstance(raw, dict):
            continue
        section_id = str(raw.get("id") or "").strip()
        if section_id:
            out[section_id] = raw
    return out


def _verse_section_search_text(section: dict[str, Any]) -> str:
    parts: list[str] = [
        str(section.get("id") or ""),
        str(section.get("title") or ""),
        str(section.get("summary") or ""),
        " ".join(_normalize_text_list(section.get("tags"))),
        " ".join(_normalize_text_list(section.get("constructs"))),
        " ".join(_normalize_text_list(section.get("queryHints"))),
        " ".join(_normalize_text_list(section.get("syntaxPatterns"))),
        " ".join(_normalize_text_list(section.get("rules"))),
    ]
    for error in list(section.get("errors") or []):
        if not isinstance(error, dict):
            continue
        parts.extend(
            [
                str(error.get("errorContains") or ""),
                str(error.get("meaning") or ""),
                " ".join(_normalize_text_list(error.get("fix"))),
            ]
        )
    for example_group in ("validExamples", "invalidExamples"):
        for example in list(section.get(example_group) or []):
            if not isinstance(example, dict):
                continue
            parts.extend(
                [
                    str(example.get("title") or ""),
                    " ".join(_normalize_text_list(example.get("notes"))),
                    " ".join(_normalize_text_list(example.get("code"))),
                ]
            )
    for table in list(section.get("tables") or []):
        if not isinstance(table, dict):
            continue
        parts.append(str(table.get("title") or ""))
        parts.extend(_normalize_text_list(table.get("columns")))
        for row in list(table.get("rows") or []):
            parts.extend(_normalize_text_list(row))
    return "\n".join(part for part in parts if part).strip()


def _doc_search_text(doc: dict[str, Any]) -> str:
    parts = [
        str(doc.get("slug") or ""),
        str(doc.get("title") or ""),
        str(doc.get("summary") or ""),
        str(doc.get("subsystem") or ""),
        " ".join(_normalize_text_list(doc.get("tags"))),
        " ".join(_normalize_text_list(doc.get("agentGoals"))),
        " ".join(_normalize_text_list(doc.get("prerequisites"))),
        " ".join(_normalize_text_list(doc.get("requiredWorkflows"))),
        " ".join(_normalize_text_list(doc.get("guardrails"))),
        " ".join(_normalize_text_list(doc.get("antiPatterns"))),
        " ".join(_normalize_text_list(doc.get("examples_good"))),
        " ".join(_normalize_text_list(doc.get("examples_bad"))),
        " ".join(_normalize_text_list(doc.get("failure_modes"))),
    ]
    return "\n".join(part for part in parts if part).strip()

def _verse_reference_known_modules(payload: dict[str, Any]) -> set[str]:
    modules = {
        str(item).strip()
        for item in list(((payload.get("coverage") or {}).get("documentedModules") or []))
        if str(item).strip()
    }
    lookup = _verse_section_lookup(payload)
    imports_section = lookup.get("imports-and-modules") or {}
    for table in list(imports_section.get("tables") or []):
        if not isinstance(table, dict):
            continue
        columns = [str(column).strip().lower() for column in list(table.get("columns") or [])]
        module_idx = columns.index("module") if "module" in columns else -1
        if module_idx < 0:
            continue
        for row in list(table.get("rows") or []):
            if not isinstance(row, list) or module_idx >= len(row):
                continue
            text = str(row[module_idx] or "").strip()
            if text:
                modules.add(text)
    return modules


def _text_matches_any(text: str, values: list[str]) -> bool:
    haystack = str(text or "").lower()
    for value in values:
        needle = str(value or "").strip().lower()
        if needle and needle in haystack:
            return True
    return False


def _select_versa_sections(
    *,
    query: str,
    source_text: str = "",
    validator_issues: list[str] | None = None,
    limit: int = 5,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = _read_versa_reference_payload()
    if not payload:
        return [], {}
    lookup = _verse_section_lookup(payload)
    retrieval = payload.get("retrieval") if isinstance(payload.get("retrieval"), dict) else {}
    selected_ids: list[str] = []
    seen_ids: set[str] = set()

    def add_section(section_id: str) -> None:
        normalized = str(section_id or "").strip()
        if not normalized or normalized not in lookup or normalized in seen_ids:
            return
        seen_ids.add(normalized)
        selected_ids.append(normalized)

    for section_id in _normalize_text_list(retrieval.get("requiredSectionIds")):
        add_section(section_id)

    combined_text = "\n".join(
        part
        for part in [
            str(query or "").strip(),
            str(source_text or "").strip(),
            " ".join(_normalize_text_list(validator_issues)),
        ]
        if part
    )
    candidate_scores: dict[str, float] = {}
    for rule in list(retrieval.get("constructRules") or []):
        if not isinstance(rule, dict):
            continue
        if _text_matches_any(combined_text, _normalize_text_list(rule.get("matchAny"))):
            for section_id in _normalize_text_list(rule.get("sectionIds")):
                if section_id in lookup:
                    candidate_scores[section_id] = candidate_scores.get(section_id, 0.0) + 2.0

    for section_id, section in lookup.items():
        score = _score_text(combined_text, _verse_section_search_text(section))
        if score > 0:
            candidate_scores[section_id] = candidate_scores.get(section_id, 0.0) + score
    ranked_sections = sorted(candidate_scores.items(), key=lambda item: item[1], reverse=True)
    for section_id, _ in ranked_sections:
        add_section(section_id)
        if len(selected_ids) >= max(limit, 1):
            break

    for section_id in _normalize_text_list(retrieval.get("defaultSectionIds"))[: max(limit, 1)]:
        add_section(section_id)
        if len(selected_ids) >= max(limit, 1):
            break

    return [lookup[section_id] for section_id in selected_ids[: max(limit, 1)]], payload


def _detect_versa_reference_gaps(
    payload: dict[str, Any],
    *,
    query: str,
    source_text: str = "",
    validator_issues: list[str] | None = None,
) -> list[str]:
    combined_text = "\n".join(
        part
        for part in [
            str(query or "").strip(),
            str(source_text or "").strip(),
            " ".join(_normalize_text_list(validator_issues)),
        ]
        if part
    )
    combined_lower = combined_text.lower()
    gaps: list[str] = []
    known_modules = _verse_reference_known_modules(payload)
    for match in _VERSA_IMPORT_RE.finditer(source_text or ""):
        module_name = str(match.group(1) or match.group(2) or "").strip()
        if not module_name or "/" in module_name:
            continue
        if module_name not in known_modules:
            gaps.append(f"No canonical Versa module entry was found for import '{module_name}'.")
    for needle, message in _VERSA_UNDOCUMENTED_CONSTRUCT_PATTERNS:
        if needle in combined_lower:
            gaps.append(message)
    normalized: list[str] = []
    seen: set[str] = set()
    for item in gaps:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            normalized.append(text)
    return normalized


def _render_versa_workflow(payload: dict[str, Any]) -> str:
    agent_usage = payload.get("agentUsage") if isinstance(payload.get("agentUsage"), dict) else {}
    lines = [
        f"{str(payload.get('title') or 'Versa Reference').strip()} ({str(payload.get('version') or '').strip()})",
        str(payload.get("summary") or "").strip(),
        "",
        "Priority Rules:",
        *[f"- {item}" for item in _normalize_text_list(agent_usage.get("priorityRules"))],
        "",
        "Generation Checklist:",
        *[f"- {item}" for item in _normalize_text_list(agent_usage.get("generationChecklist"))],
    ]
    workflow = _normalize_text_list(agent_usage.get("sourceConstructionWorkflow"))
    if workflow:
        lines.extend(["", "Whole-Script Workflow:", *[f"- {item}" for item in workflow]])
    return "\n".join(line for line in lines if line.strip()).strip()


def _render_versa_section(section: dict[str, Any]) -> str:
    lines: list[str] = [
        str(section.get("title") or "Versa Section").strip(),
        str(section.get("summary") or "").strip(),
    ]
    constructs = _normalize_text_list(section.get("constructs"))
    if constructs:
        lines.append(f"Constructs: {', '.join(constructs)}")
    syntax_patterns = _normalize_text_list(section.get("syntaxPatterns"))
    if syntax_patterns:
        lines.extend(["Syntax Patterns:", *[f"- {item}" for item in syntax_patterns]])
    rules = _normalize_text_list(section.get("rules"))
    if rules:
        lines.extend(["Rules:", *[f"- {item}" for item in rules]])
    tables = list(section.get("tables") or [])
    if tables:
        for table in tables[:3]:
            if not isinstance(table, dict):
                continue
            title = str(table.get("title") or "Reference Table").strip()
            lines.append(title)
            columns = _normalize_text_list(table.get("columns"))
            if columns:
                lines.append(f"Columns: {', '.join(columns)}")
            for row in list(table.get("rows") or [])[:8]:
                values = _normalize_text_list(row)
                if values:
                    lines.append(f"- {' | '.join(values)}")
    valid_examples = list(section.get("validExamples") or [])
    if valid_examples:
        first = valid_examples[0] if isinstance(valid_examples[0], dict) else {}
        code = _compact_code_lines(first.get("code"), limit=8)
        if code:
            lines.extend(["Valid Example:", code])
    invalid_examples = list(section.get("invalidExamples") or [])
    if invalid_examples:
        first_bad = invalid_examples[0] if isinstance(invalid_examples[0], dict) else {}
        code = _compact_code_lines(first_bad.get("code"), limit=6)
        if code:
            lines.extend(["Invalid Example:", code])
    errors = list(section.get("errors") or [])
    if errors:
        lines.append("Relevant Parser Mappings:")
        for error in errors[:3]:
            if not isinstance(error, dict):
                continue
            error_contains = str(error.get("errorContains") or "").strip()
            meaning = str(error.get("meaning") or "").strip()
            fix = "; ".join(_normalize_text_list(error.get("fix")))
            detail = " | ".join(item for item in [error_contains, meaning, fix] if item)
            if detail:
                lines.append(f"- {detail}")
    return "\n".join(line for line in lines if line.strip()).strip()


def build_versa_reference_context(
    *,
    query: str,
    source_text: str = "",
    validator_issues: list[str] | None = None,
    limit: int = 5,
) -> tuple[list[AIContextBlock], list[str]]:
    sections, payload = _select_versa_sections(
        query=query,
        source_text=source_text,
        validator_issues=validator_issues,
        limit=limit,
    )
    if not payload:
        return [], []
    source = _MANUAL_SPECS["versa-canonical-reference"]["path"].as_posix()
    wiki = str(_MANUAL_SPECS["versa-canonical-reference"]["wiki"])
    blocks: list[AIContextBlock] = [
        AIContextBlock(
            label="Versa Authoring Workflow",
            source=source,
            reason="Canonical Versa authoring and repair workflow",
            content=_render_versa_workflow(payload),
        )
    ]
    for section in sections:
        blocks.append(
            AIContextBlock(
                label=f"Versa Reference: {str(section.get('title') or 'Section').strip()}",
                source=source,
                reason=f"Relevant Versa syntax context selected from {wiki}",
                content=_render_versa_section(section),
            )
        )
    for doc in _select_shared_docs(" ".join([query, source_text, " ".join(_normalize_text_list(validator_issues))]), page_kind="versa", limit=min(max(limit - 1, 1), 3)):
        blocks.append(
            AIContextBlock(
                label=f"Versa Reference: {str(doc.get('title') or 'Versa').strip()}",
                source=str(_SHARED_DOCS_PATH.as_posix()),
                reason=f"Shared-corpus Versa workflow context from {_shared_wiki_href(doc)}",
                content=_doc_markdown(doc),
            )
        )
    gaps = _detect_versa_reference_gaps(
        payload,
        query=query,
        source_text=source_text,
        validator_issues=validator_issues,
    )
    for gap in _shared_doc_versa_gaps(query=query, source_text=source_text, validator_issues=validator_issues):
        if gap not in gaps:
            gaps.append(gap)
    if gaps:
        missing_policy = _normalize_text_list(((payload.get("agentUsage") or {}).get("missingInfoPolicy") or []))
        gap_lines = ["Documentation gaps detected:", *[f"- {item}" for item in gaps]]
        if missing_policy:
            gap_lines.extend(["", "Missing-Info Policy:", *[f"- {item}" for item in missing_policy]])
        blocks.append(
            AIContextBlock(
                label="Versa Reference Gaps",
                source=source,
                reason="The canonical Versa reference does not fully cover every requested construct",
                content="\n".join(gap_lines).strip(),
            )
        )
    return blocks, gaps


def _liwiro_section_lookup(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for raw in list(payload.get("sections") or []):
        if not isinstance(raw, dict):
            continue
        section_id = str(raw.get("id") or "").strip()
        if section_id:
            out[section_id] = raw
    return out


def _liwiro_section_search_text(section: dict[str, Any]) -> str:
    parts: list[str] = [
        str(section.get("id") or ""),
        str(section.get("title") or ""),
        str(section.get("summary") or ""),
        " ".join(_normalize_text_list(section.get("tags"))),
        " ".join(_normalize_text_list(section.get("constructs"))),
        " ".join(_normalize_text_list(section.get("queryHints"))),
        " ".join(_normalize_text_list(section.get("rules"))),
    ]
    for table in list(section.get("tables") or []):
        if not isinstance(table, dict):
            continue
        parts.append(str(table.get("title") or ""))
        parts.extend(_normalize_text_list(table.get("columns")))
        for row in list(table.get("rows") or []):
            parts.extend(_normalize_text_list(row))
    for example in list(section.get("validExamples") or []):
        if not isinstance(example, dict):
            continue
        parts.extend(
            [
                str(example.get("title") or ""),
                " ".join(_normalize_text_list(example.get("notes"))),
                " ".join(_normalize_text_list(example.get("code"))),
            ]
        )
    return "\n".join(part for part in parts if part).strip()


def _select_liwiro_sections(
    *,
    query: str,
    page_kind: str = "",
    limit: int = 5,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = _read_liwiro_reference_payload()
    if not payload:
        return [], {}
    lookup = _liwiro_section_lookup(payload)
    retrieval = payload.get("retrieval") if isinstance(payload.get("retrieval"), dict) else {}
    selected_ids: list[str] = []
    seen_ids: set[str] = set()

    def add_section(section_id: str) -> None:
        normalized = str(section_id or "").strip()
        if not normalized or normalized not in lookup or normalized in seen_ids:
            return
        seen_ids.add(normalized)
        selected_ids.append(normalized)

    for section_id in _normalize_text_list(retrieval.get("requiredSectionIds")):
        add_section(section_id)

    combined_text = "\n".join(
        part for part in [str(query or "").strip(), str(page_kind or "").replace("-", " ").strip()] if part
    )
    candidate_scores: dict[str, float] = {}
    for rule in list(retrieval.get("constructRules") or []):
        if not isinstance(rule, dict):
            continue
        if _text_matches_any(combined_text, _normalize_text_list(rule.get("matchAny"))):
            for section_id in _normalize_text_list(rule.get("sectionIds")):
                if section_id in lookup:
                    candidate_scores[section_id] = candidate_scores.get(section_id, 0.0) + 2.0

    for section_id, section in lookup.items():
        score = _score_text(combined_text, _liwiro_section_search_text(section))
        if score > 0:
            candidate_scores[section_id] = candidate_scores.get(section_id, 0.0) + score
    ranked_sections = sorted(candidate_scores.items(), key=lambda item: item[1], reverse=True)
    for section_id, _score in ranked_sections:
        add_section(section_id)
        if len(selected_ids) >= max(limit, 1):
            break

    for section_id in _normalize_text_list(retrieval.get("defaultSectionIds"))[: max(limit, 1)]:
        add_section(section_id)
        if len(selected_ids) >= max(limit, 1):
            break

    return [lookup[section_id] for section_id in selected_ids[: max(limit, 1)]], payload


def _render_liwiro_workflow(payload: dict[str, Any]) -> str:
    agent_usage = payload.get("agentUsage") if isinstance(payload.get("agentUsage"), dict) else {}
    lines = [
        f"{str(payload.get('title') or 'Liwiro Platform Reference').strip()} ({str(payload.get('version') or '').strip()})",
        str(payload.get("summary") or "").strip(),
        "",
        "Priority Rules:",
        *[f"- {item}" for item in _normalize_text_list(agent_usage.get("priorityRules"))],
        "",
        "Action Checklist:",
        *[f"- {item}" for item in _normalize_text_list(agent_usage.get("actionChecklist"))],
    ]
    workflow = _normalize_text_list(agent_usage.get("sourceConstructionWorkflow"))
    if workflow:
        lines.extend(["", "Decision Workflow:", *[f"- {item}" for item in workflow]])
    return "\n".join(line for line in lines if line.strip()).strip()


def _render_liwiro_section(section: dict[str, Any]) -> str:
    lines: list[str] = [
        str(section.get("title") or "Liwiro Section").strip(),
        str(section.get("summary") or "").strip(),
    ]
    constructs = _normalize_text_list(section.get("constructs"))
    if constructs:
        lines.append(f"Constructs: {', '.join(constructs)}")
    query_hints = _normalize_text_list(section.get("queryHints"))
    if query_hints:
        lines.append(f"Query Hints: {', '.join(query_hints[:8])}")
    rules = _normalize_text_list(section.get("rules"))
    if rules:
        lines.extend(["Rules:", *[f"- {item}" for item in rules]])
    tables = list(section.get("tables") or [])
    if tables:
        for table in tables[:3]:
            if not isinstance(table, dict):
                continue
            title = str(table.get("title") or "Reference Table").strip()
            lines.append(title)
            columns = _normalize_text_list(table.get("columns"))
            if columns:
                lines.append(f"Columns: {', '.join(columns)}")
            for row in list(table.get("rows") or [])[:8]:
                values = _normalize_text_list(row)
                if values:
                    lines.append(f"- {' | '.join(values)}")
    valid_examples = list(section.get("validExamples") or [])
    if valid_examples:
        first = valid_examples[0] if isinstance(valid_examples[0], dict) else {}
        code = _compact_code_lines(first.get("code"), limit=8)
        if code:
            lines.extend(["Example:", code])
    return "\n".join(line for line in lines if line.strip()).strip()


def build_liwiro_reference_context(
    *,
    query: str,
    page_kind: str = "",
    limit: int = 6,
) -> list[AIContextBlock]:
    sections, payload = _select_liwiro_sections(query=query, page_kind=page_kind, limit=limit)
    if not payload:
        return []
    source = _MANUAL_SPECS["liwiro-platform-reference"]["path"].as_posix()
    blocks: list[AIContextBlock] = [
        AIContextBlock(
            label="Liwiro Workflow",
            source=source,
            reason="Canonical Liwiro control-plane workflow and action guidance",
            content=_render_liwiro_workflow(payload),
        )
    ]
    for section in sections:
        blocks.append(
            AIContextBlock(
                label=f"Liwiro Reference: {str(section.get('title') or 'Section').strip()}",
                source=source,
                reason="Relevant Liwiro platform and LAPIS context",
                content=_render_liwiro_section(section),
            )
        )
    return blocks


def _lapis_reference_summary() -> str:
    return "\n".join(
        [
            "LAPIS validity rules:",
            "- Top-level sections must include metadata, auth, models, and endpoints.",
            "- metadata.apiName, metadata.basePath, metadata.version, and metadata.rateLimiting are required.",
            "- metadata.basePath must start with '/'.",
            "- metadata.version must use semantic versioning like 1.0.0.",
            "- auth.enabled, auth.isAuthService, auth.keyManagement, and auth.customEndpoints.enabled must be valid booleans/values.",
            "- Every model must define name, collection, and fields.",
            "- Every model field must define id, name, type, and required.",
            "- Every endpoint must define method, path, and operationType.",
            "- CRUD endpoints require crudOperation and linkedModel.",
            "- Custom endpoints require readable VDB command syntax in vqlQuery.",
            "- Script endpoints require non-empty versaScript.",
            "- Endpoints that reference a linked model must reference a model that exists in models.",
            "- For a concrete service draft, at least one model and one endpoint should exist before presenting it as ready.",
            "Guide users to /wiki/lapis-reference and /wiki/service-builder-manual for the operator-facing explanation.",
        ]
    )


def _needs_liwiro_reference(query: str, page_kind: str = "") -> bool:
    text = str(query or "").lower()
    page = str(page_kind or "").strip().lower()
    if page in {"service-builder", "service-manager", "vdb-portal", "vi-portal"}:
        return True
    terms = (
        "liwiro",
        "lapis",
        "service builder",
        "service manager",
        "generate service",
        "generated service",
        "manager state",
        "platform action",
        "action catalog",
        "action preview",
        "action execute",
        "capability",
        "capabilities",
        "capability id",
        "platform/lapis/validate",
        "platform/vdb",
        "platform/vi",
        "vdb portal",
        "vi portal",
        "auth keys",
        "vdb credentials",
        "unix socket",
        "named pipe",
        "transport",
    )
    return any(term in text for term in terms)


def _needs_verse_manual(query: str, page_kind: str = "") -> bool:
    text = str(query or "").lower()
    page = str(page_kind or "").strip().lower()
    if page in {"verse-ai", "general"} and any(term in text for term in ("verse", "agent", "handoff", "mind-share", "thread", "provider")):
        return True
    return any(term in text for term in ("verse chat", "verse agent", "mind-share", "handoff", "thread summary", "context report"))


def _manual_candidates(query: str, page_kind: str = "") -> list[dict[str, str]]:
    text = str(query or "").lower()
    page = str(page_kind or "").strip().lower()
    out: list[dict[str, str]] = []
    if _needs_liwiro_reference(query, page):
        liwiro_blocks = build_liwiro_reference_context(query=query, page_kind=page, limit=6)
        out.append(
            {
                "label": _MANUAL_SPECS["liwiro-platform-reference"]["label"],
                "source": _MANUAL_SPECS["liwiro-platform-reference"]["path"].as_posix(),
                "wiki": str(_MANUAL_SPECS["liwiro-platform-reference"]["wiki"]),
                "category": "reference",
                "content": "\n\n".join(block.content for block in liwiro_blocks if str(block.content or "").strip()),
            }
        )
    if page in {"service-builder", "service-manager"} or any(term in text for term in ("lapis", "endpoint", "crud", "microservice", "model", "linkedmodel", "operationtype", "vqlquery", "versascript")):
        out.append(
            {
                "label": "LAPIS Validation Rules",
                "source": "validator",
                "wiki": "/wiki/lapis-reference",
                "category": "validator",
                "content": _lapis_reference_summary(),
            }
        )
    if _needs_verse_manual(query, page):
        out.append(
            {
                "label": "Verse Chat Manual",
                "source": _MANUAL_SPECS["verse-chat"]["path"].as_posix(),
                "wiki": _MANUAL_SPECS["verse-chat"]["wiki"],
                "category": "manual",
                "content": _read_manual_text(str(_MANUAL_SPECS["verse-chat"]["path"])),
            }
        )
    if page == "vi-portal" or any(term in text for term in ("versa", "vi portal", "vi repl", ".versa", "syntax", "comment", "module")):
        versa_blocks, _ = build_versa_reference_context(query=query, limit=5)
        out.append(
            {
                "label": _MANUAL_SPECS["versa-canonical-reference"]["label"],
                "source": _MANUAL_SPECS["versa-canonical-reference"]["path"].as_posix(),
                "wiki": _MANUAL_SPECS["versa-canonical-reference"]["wiki"],
                "category": "reference",
                "content": "\n\n".join(block.content for block in versa_blocks if str(block.content or "").strip()),
            }
        )
    if page == "vi-portal" or any(term in text for term in ("repl", "terminal", "run script", "run file")):
        out.append(
            {
                "label": _MANUAL_SPECS["versa-runtime"]["label"],
                "source": _MANUAL_SPECS["versa-runtime"]["path"].as_posix(),
                "wiki": _MANUAL_SPECS["versa-runtime"]["wiki"],
                "category": "manual",
                "content": _read_manual_text(str(_MANUAL_SPECS["versa-runtime"]["path"])),
            }
        )
    if page == "vdb-portal" or any(term in text for term in ("vdb", "vql", "query", "collection", "domain", "database", "tumi", "rbac")):
        for key in ("vql-reference", "vdb-usage"):
            out.append(
                {
                    "label": _MANUAL_SPECS[key]["label"],
                    "source": _MANUAL_SPECS[key]["path"].as_posix(),
                    "wiki": _MANUAL_SPECS[key]["wiki"],
                    "category": "manual",
                    "content": _read_manual_text(str(_MANUAL_SPECS[key]["path"])),
                }
            )
    for doc in _select_shared_docs(query, page_kind=page, limit=5):
        content = _doc_markdown(doc)
        if not content:
            continue
        out.append(
            {
                "label": str(doc.get("title") or "Knowledge Page").strip(),
                "source": str(_SHARED_DOCS_PATH.as_posix()),
                "wiki": _shared_wiki_href(doc),
                "category": "manual",
                "content": content,
            }
        )
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in out:
        source = str(item.get("source") or "").strip()
        if not source or source in seen:
            continue
        seen.add(source)
        deduped.append(item)
    return [item for item in deduped if str(item.get("content") or "").strip()]

def _score_text(query: str, candidate: str) -> float:
    query_tokens = set(tokenize(query))
    if not query_tokens:
        return 0.0
    candidate_tokens = set(tokenize(candidate))
    if not candidate_tokens:
        return 0.0
    matched = query_tokens & candidate_tokens
    return len(matched) / max(len(query_tokens), 1)


def _doc_markdown(doc: dict[str, Any]) -> str:
    def bullets(title: str, values: Any) -> list[str]:
        items = _normalize_text_list(values)
        if not items:
            return []
        return [title, *[f"- {item}" for item in items], ""]

    return "\n".join(
        line
        for line in [
            f"# {str(doc.get('title') or 'Document').strip()}",
            "",
            str(doc.get("summary") or "").strip(),
            "",
            *bullets("Audience:", [str(doc.get("audience") or "").strip()]),
            *bullets("Agent Goals:", doc.get("agentGoals")),
            *bullets("Prerequisites:", doc.get("prerequisites")),
            *bullets("Required Workflows:", doc.get("requiredWorkflows")),
            *bullets("Guardrails:", doc.get("guardrails")),
            *bullets("Anti-Patterns:", doc.get("antiPatterns")),
            *bullets("Good Examples:", doc.get("examples_good")),
            *bullets("Bad Examples:", doc.get("examples_bad")),
            *bullets("Failure Modes:", doc.get("failure_modes")),
        ]
        if str(line).strip()
    ).strip()


def _shared_wiki_href(doc: dict[str, Any]) -> str:
    slug = str(doc.get("slug") or "").strip()
    return f"/wiki/{slug}" if slug else ""


def _select_shared_docs(query: str, *, page_kind: str = "", limit: int = 4) -> list[dict[str, Any]]:
    docs = _load_shared_docs()
    if not docs:
        return []
    scored: list[tuple[float, dict[str, Any]]] = []
    query_text = " ".join(part for part in [query, page_kind] if str(part or "").strip())
    for doc in docs:
        score = _score_text(query_text, _doc_search_text(doc))
        if page_kind and page_kind in _normalize_text_list(doc.get("tags")):
            score += 0.2
        if page_kind and page_kind == str(doc.get("subsystem") or "").strip().lower():
            score += 0.2
        if score > 0:
            scored.append((score, doc))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [doc for _, doc in scored[:limit]]


def _shared_doc_known_versa_modules() -> set[str]:
    modules = {"json_xml", "vdb", "http", "email", "crypto", "jwt", "time", "datetime", "random", "filer"}
    for doc in _load_shared_docs():
        if str(doc.get("slug") or "").strip() == "versa-reference":
            modules.update(token for token in _normalize_text_list(doc.get("tags")) if token.isidentifier())
    return modules


def _shared_doc_versa_gaps(*, query: str, source_text: str = "", validator_issues: list[str] | None = None) -> list[str]:
    combined = "\n".join(part for part in [query, source_text, " ".join(_normalize_text_list(validator_issues))] if str(part).strip())
    gaps: list[str] = []
    known_modules = _shared_doc_known_versa_modules()
    for match in _VERSA_IMPORT_RE.finditer(source_text or ""):
        module_name = str(match.group(1) or match.group(2) or "").strip()
        if module_name and "/" not in module_name and module_name not in known_modules:
            gaps.append(f"No shared-corpus Versa module entry was found for import '{module_name}'.")
    lowered = combined.lower()
    for needle, message in _VERSA_UNDOCUMENTED_CONSTRUCT_PATTERNS:
        if needle in lowered:
            gaps.append(message)
    deduped: list[str] = []
    seen: set[str] = set()
    for gap in gaps:
        if gap not in seen:
            seen.add(gap)
            deduped.append(gap)
    return deduped

def select_skills(scaffold: VerseScaffold, agent: AgentDefinition, query: str, limit: int = 3) -> list[SkillDefinition]:
    scored: list[tuple[float, SkillDefinition]] = []
    for skill in scaffold.skills.values():
        text = " ".join(
            [
                skill.title,
                skill.purpose,
                " ".join(skill.inputs),
                " ".join(skill.output_format),
                " ".join(skill.failure_conditions),
            ]
        )
        score = _score_text(query, text)
        if skill.best_suited_agent.strip().lower() == agent.name.strip().lower():
            score += 0.4
        if score > 0:
            scored.append((score, skill))
    return [skill for _, skill in sorted(scored, key=lambda item: item[0], reverse=True)[:limit]]


def select_mind_share_documents(scaffold: VerseScaffold, agent: AgentDefinition, query: str, limit: int = 4) -> list[tuple[str, float]]:
    scored: list[tuple[str, float]] = []
    for file_name in agent.mind_share_read_scope:
        doc = scaffold.mind_share_documents.get(file_name)
        if not doc:
            continue
        score = _score_text(query, f"{file_name} {doc.content}")
        if file_name == "thread-summaries.md":
            score += 0.1
        scored.append((file_name, score))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:limit]


def select_learning_records(records: list[dict[str, Any]], query: str, page_kind: str = "", limit: int = 3) -> list[tuple[dict[str, Any], float]]:
    scored: list[tuple[dict[str, Any], float]] = []
    for raw in list(records or []):
        if not isinstance(raw, dict):
            continue
        text = " ".join(
            [
                str(raw.get("category") or ""),
                str(raw.get("issue") or ""),
                str(raw.get("resolution") or ""),
                str(raw.get("pageKind") or raw.get("page_kind") or ""),
                " ".join(str(item) for item in list(raw.get("tags") or [])),
            ]
        )
        score = _score_text(query, text)
        if page_kind and str(raw.get("pageKind") or raw.get("page_kind") or "").strip().lower() == str(page_kind).strip().lower():
            score += 0.15
        if score > 0:
            scored.append((raw, score))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:limit]


def _trim_context_content(content: str, *, limit: int) -> tuple[str, bool]:
    text = str(content or "").strip()
    if not text:
        return "", False
    if limit <= 0 or len(text) <= limit:
        return text, False
    return f"{text[: max(limit - 4, 1)].rstrip()}\n...", True


def _render_agent_prompt_profile(agent: AgentDefinition, prompt_mode: str = "full") -> str:
    contract = dict(agent.contract or {})
    lines = [
        f"Active specialist: {agent.active_display_name} ({agent.title})",
        f"Mission: {agent.mission}",
        f"Core responsibilities: {'; '.join(agent.core_responsibilities[:5])}",
        f"Decision style: {'; '.join(agent.decision_style[:4])}",
    ]
    if agent.primary_users:
        lines.append(f"Primary users: {'; '.join(agent.primary_users[:5])}")
    if contract.get("owns"):
        lines.append(f"Owns: {'; '.join(str(item) for item in list(contract.get('owns') or [])[:6])}")
    if prompt_mode == "minimal":
        if agent.preferred_outputs:
            lines.append(f"Preferred outputs: {'; '.join(agent.preferred_outputs[:4])}")
        if contract.get("artifactKindsAllowed"):
            lines.append(
                f"Allowed artifact kinds: {'; '.join(str(item) for item in list(contract.get('artifactKindsAllowed') or [])[:4])}"
            )
        if contract.get("requiredEvidence"):
            lines.append(f"Required evidence: {'; '.join(str(item) for item in list(contract.get('requiredEvidence') or [])[:4])}")
        if agent.do_not:
            lines.append(f"Do not: {'; '.join(agent.do_not[:4])}")
        return "\n".join(line for line in lines if line.strip()).strip()
    if agent.allowed_inputs:
        lines.append(f"Allowed inputs: {'; '.join(agent.allowed_inputs[:6])}")
    if agent.collaboration_rules:
        lines.append(f"Collaboration rules: {'; '.join(agent.collaboration_rules[:5])}")
    if contract.get("supports"):
        lines.append(f"Supports: {'; '.join(str(item) for item in list(contract.get('supports') or [])[:5])}")
    if contract.get("artifactKindsAllowed"):
        lines.append(
            f"Allowed artifact kinds: {'; '.join(str(item) for item in list(contract.get('artifactKindsAllowed') or [])[:5])}"
        )
    if contract.get("requiredEvidence"):
        lines.append(f"Required evidence: {'; '.join(str(item) for item in list(contract.get('requiredEvidence') or [])[:5])}")
    if contract.get("forbiddenAssumptions"):
        lines.append(
            f"Forbidden assumptions: {'; '.join(str(item) for item in list(contract.get('forbiddenAssumptions') or [])[:5])}"
        )
    if agent.mind_share_read_scope:
        lines.append(f"mind-share read scope: {', '.join(agent.mind_share_read_scope[:6])}")
    if agent.mind_share_write_scope:
        lines.append(f"mind-share write scope: {', '.join(agent.mind_share_write_scope[:6])}")
    if agent.preferred_outputs:
        lines.append(f"Preferred outputs: {'; '.join(agent.preferred_outputs[:5])}")
    if agent.success_criteria:
        lines.append(f"Success criteria: {agent.success_criteria}")
    if agent.do_not:
        lines.append(f"Do not: {'; '.join(agent.do_not[:5])}")
    return "\n".join(line for line in lines if line.strip()).strip()


def _render_thread_delta(messages: list[dict[str, Any]] | None, *, limit: int = 6) -> str:
    lines: list[str] = []
    for raw in list(messages or [])[-max(limit, 1) :]:
        if not isinstance(raw, dict):
            continue
        role = str(raw.get("role") or "").strip().lower()
        if role == "system":
            continue
        content = " ".join(str(raw.get("content") or "").strip().split())
        if not content:
            continue
        if len(content) > 220:
            content = f"{content[:217].rstrip()}..."
        speaker = "User" if role == "user" else str(raw.get("agent_display_name") or raw.get("agentDisplayName") or raw.get("agent_name") or "Agent").strip()
        lines.append(f"- {speaker}: {content}")
    if not lines:
        return ""
    return "\n".join(["Recent thread delta:", *lines]).strip()


def _bootstrap_file_names(
    *,
    scaffold: VerseScaffold,
    prompt_mode: str,
    thread_summary: str,
    thread_messages: list[dict[str, Any]] | None,
    platform_context: dict[str, Any] | None,
) -> list[str]:
    del scaffold, prompt_mode, thread_summary, thread_messages, platform_context
    return []


def _promptable_platform_context(platform_context: dict[str, Any] | None) -> dict[str, Any]:
    context = dict(platform_context or {})
    filtered: dict[str, Any] = {}
    for key, value in context.items():
        text_key = str(key or "").strip()
        if not text_key or text_key.startswith("_"):
            continue
        text_value = str(value or "").strip()
        if not text_value:
            continue
        filtered[text_key] = text_value
    return filtered


def _trim_context_text(value: Any, *, limit: int = 240) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: max(limit - 3, 0)].rstrip()}..."


def _render_named_context_block(title: str, payload: dict[str, Any], *, field_limit: int = 220) -> str:
    lines: list[str] = [f"{title}:"]
    for key, value in payload.items():
        key_text = str(key or "").strip()
        if not key_text:
            continue
        if isinstance(value, list):
            rendered_items = [_trim_context_text(item, limit=field_limit) for item in value if _trim_context_text(item, limit=field_limit)]
            if rendered_items:
                lines.append(f"- {key_text}: {', '.join(rendered_items[:6])}")
            continue
        if isinstance(value, dict):
            nested = ", ".join(
                f"{nested_key}={_trim_context_text(nested_value, limit=max(field_limit // 2, 60))}"
                for nested_key, nested_value in list(value.items())[:8]
                if str(nested_key or "").strip() and str(nested_value or "").strip()
            )
            if nested:
                lines.append(f"- {key_text}: {nested}")
            continue
        value_text = _trim_context_text(value, limit=field_limit)
        if value_text:
            lines.append(f"- {key_text}: {value_text}")
    return "\n".join(lines).strip()


def _render_custom_platform_context(platform_context: dict[str, Any] | None) -> str:
    context = dict(platform_context or {})
    if not context:
        return ""

    lines: list[str] = []
    pathname = _trim_context_text(context.get("pathname"), limit=160)
    screen = _trim_context_text(context.get("screen"), limit=160)
    page_kind = _trim_context_text(context.get("pageKind"), limit=80)
    if pathname or screen or page_kind:
        lines.append(
            "Surface: "
            + "; ".join(
                part
                for part in (
                    f"path={pathname}" if pathname else "",
                    f"screen={screen}" if screen else "",
                    f"pageKind={page_kind}" if page_kind else "",
                )
                if part
            )
        )

    for title, key in (("Focus", "focus"), ("Selection", "selection"), ("Entity", "entity"), ("Metrics", "metrics")):
        payload = context.get(key)
        if isinstance(payload, dict) and payload:
            rendered = _render_named_context_block(title, payload, field_limit=180 if key != "metrics" else 120)
            if rendered:
                lines.append(rendered)

    page_summary = _trim_context_text(context.get("pageSummary"), limit=800)
    if page_summary:
        lines.append(f"Page Summary:\n{page_summary}")

    available_actions = context.get("availableActions")
    if isinstance(available_actions, list) and available_actions:
        action_lines: list[str] = []
        for action in available_actions[:6]:
            if not isinstance(action, dict):
                continue
            label = _trim_context_text(action.get("label") or action.get("id"), limit=120)
            description = _trim_context_text(action.get("description") or action.get("targetPath"), limit=180)
            if label:
                action_lines.append(f"- {label}" + (f": {description}" if description else ""))
        if action_lines:
            lines.append("\n".join(["Available Actions:", *action_lines]))

    records = context.get("records")
    if isinstance(records, list) and records:
        record_lines: list[str] = []
        for item in records[:6]:
            if not isinstance(item, dict):
                continue
            compact = ", ".join(
                f"{key}={_trim_context_text(value, limit=90)}"
                for key, value in list(item.items())[:8]
                if str(key or "").strip() and str(value or "").strip()
            )
            if compact:
                record_lines.append(f"- {compact}")
        if record_lines:
            lines.append("\n".join(["Records:", *record_lines]))

    leftover_scalars = {}
    for key, value in context.items():
        if key in {
            "pathname",
            "screen",
            "pageKind",
            "focus",
            "selection",
            "entity",
            "metrics",
            "availableActions",
            "pageSummary",
            "records",
            "selectedContextFileIds",
        }:
            continue
        if isinstance(value, (dict, list)):
            continue
        value_text = _trim_context_text(value, limit=180)
        if value_text:
            leftover_scalars[str(key)] = value_text
    if leftover_scalars:
        rendered = _render_named_context_block("Context Notes", leftover_scalars, field_limit=180)
        if rendered:
            lines.append(rendered)

    return "\n\n".join(line for line in lines if line).strip()


def build_prompt_context_bundle(
    scaffold: VerseScaffold,
    agent: AgentDefinition,
    query: str,
    thread_summary: str,
    platform_context: dict[str, Any] | None = None,
    learning_records: list[dict[str, Any]] | None = None,
    *,
    prompt_mode: str = "full",
    thread_messages: list[dict[str, Any]] | None = None,
    handoff_context: bool = False,
    synthesis_mode: bool = False,
) -> tuple[list[AIContextBlock], list[dict[str, Any]], dict[str, Any]]:
    normalized_mode = "minimal" if str(prompt_mode or "").strip().lower() == "minimal" else "bounded"
    traces: list[RetrievalTraceEntry] = []
    blocks: list[AIContextBlock] = []
    report_entries: list[PromptContextEntry] = []
    truncation_warnings: list[str] = []
    page_kind = str((platform_context or {}).get("pageKind") or "").strip().lower()
    def add_block(
        *,
        label: str,
        source: str,
        reason: str,
        content: str,
        category: str,
        trace: bool = False,
        trace_source: str = "",
        score: float = 0.0,
    ) -> None:
        limit = _CONTEXT_CHAR_LIMITS.get(category, 1200)
        trimmed, truncated = _trim_context_content(content, limit=limit)
        if not trimmed:
            return
        blocks.append(AIContextBlock(label=label, source=source, reason=reason, content=trimmed))
        report_entries.append(
            PromptContextEntry(
                label=label,
                source=source,
                reason=reason,
                category=category,
                chars=len(trimmed),
                prompt_mode=normalized_mode,
                truncated=truncated,
            )
        )
        if truncated:
            truncation_warnings.append(f"{label} was truncated to keep prompt assembly bounded.")
        if trace:
            traces.append(
                RetrievalTraceEntry(
                    source=trace_source or source,
                    reason=reason,
                    score=score,
                    excerpt=trimmed[:240],
                )
            )

    add_block(
        label=f"Agent Profile: {agent.active_display_name}",
        source=agent.source_path,
        reason="Current Verse specialist identity and remit",
        content=_render_agent_prompt_profile(agent, normalized_mode),
        category="agent-profile",
    )

    if normalized_mode != "minimal":
        add_block(
            label="Guardrails",
            source="liwiro/verse/mind-share/guardrails.md",
            reason="Universal Verse write and reasoning rules",
            content=scaffold.guardrails_markdown,
            category="guardrails",
        )
        add_block(
            label="Thread Behavior",
            source="liwiro/verse/router/thread-behavior.md",
            reason="Defines visible handoffs and synthesis behavior",
            content=scaffold.thread_behavior_markdown,
            category="thread-rules",
        )

    if thread_summary.strip():
        add_block(
            label="Current Thread Summary",
            source="thread.summary",
            reason="Carry forward established thread state",
            content=thread_summary.strip(),
            category="thread",
            trace=True,
            score=0.8,
        )

    thread_delta = _render_thread_delta(thread_messages, limit=4 if normalized_mode == "minimal" else 8)
    if thread_delta:
        add_block(
            label="Recent Thread Delta",
            source="thread.delta",
            reason="Recent thread context for continuity",
            content=thread_delta,
            category="thread",
        )

    skill_limit = 1 if normalized_mode == "minimal" else 2
    for skill in select_skills(scaffold, agent, query, limit=skill_limit):
        summary = "\n".join(
            [
                f"Title: {skill.title}",
                f"Purpose: {skill.purpose}",
                f"Procedure: {'; '.join(skill.procedure)}",
                f"Output Format: {'; '.join(skill.output_format)}",
            ]
        ).strip()
        add_block(
            label=f"Skill: {skill.title}",
            source=skill.source_path,
            reason=f"Relevant specialist procedure for {agent.active_display_name}",
            content=summary,
            category="skill",
            trace=True,
            score=0.7,
        )

    mind_share_limit = 1 if normalized_mode == "minimal" else 2
    for file_name, score in select_mind_share_documents(scaffold, agent, query, limit=mind_share_limit):
        doc = scaffold.mind_share_documents[file_name]
        add_block(
            label=f"mind-share: {file_name}",
            source=doc.path,
            reason=f"Within {agent.active_display_name}'s read scope and relevant to the request",
            content=doc.content,
            category="mind-share",
            trace=True,
            trace_source=file_name,
            score=score,
        )

    desired_artifact_kind = str((platform_context or {}).get("desiredArtifactKind") or "").strip()
    if desired_artifact_kind:
        checklist: list[str] = []
        if desired_artifact_kind == "vi-script":
            checklist = ["Versa syntax reference", "runtime-safe module usage", "validator-ready source"]
        elif desired_artifact_kind == "vdb-query":
            checklist = ["portal-safe JSON object", "domain or collection target", "supported VDB command shape"]
        elif desired_artifact_kind == "service-builder-lapis":
            checklist = ["at least one model", "at least one endpoint", "builder-valid LAPIS config"]
        if checklist:
            add_block(
                label="Evidence Checklist",
                source="verse-orchestrator",
                reason="Artifact-target-aware evidence requirements",
                content="\n".join(["Validate against this checklist before returning an artifact:", *[f"- {item}" for item in checklist]]),
                category="reference",
                trace=True,
                score=0.88,
            )

    manual_limit = 1 if normalized_mode == "minimal" else 2
    for manual in _manual_candidates(query, page_kind)[:manual_limit]:
        content = str(manual.get("content") or "").strip()
        if not content:
            continue
        source = str(manual.get("source") or "").strip()
        wiki = str(manual.get("wiki") or "").strip()
        category = str(manual.get("category") or ("reference" if source.endswith(".json") else "manual")).strip().lower()
        if category not in _CONTEXT_CHAR_LIMITS:
            category = "manual"
        reason = (
            f"Relevant structured reference context for {agent.active_display_name}"
            if category == "reference"
            else f"Relevant operator manual context for {agent.active_display_name}"
        )
        add_block(
            label=str(manual.get("label") or "Manual"),
            source=source,
            reason=reason,
            content=content,
            category=category,
            trace=True,
            trace_source=wiki or source,
            score=0.72,
        )

    learning_limit = 1 if normalized_mode == "minimal" else 2
    for record, score in select_learning_records(list(learning_records or []), query, page_kind, limit=learning_limit):
        content = "\n".join(
            [
                f"Category: {record.get('category')}",
                f"Issue: {record.get('issue')}",
                f"Resolution: {record.get('resolution')}",
                f"Tags: {', '.join(str(item) for item in list(record.get('tags') or []))}",
            ]
        ).strip()
        add_block(
            label="Operational Learning",
            source="verse-learning",
            reason="Previous validated lesson from an earlier Verse failure or correction",
            content=content,
            category="learning",
            trace=True,
            score=score,
        )

    rendered_context = _render_custom_platform_context(platform_context)
    if rendered_context:
        add_block(
            label="Page Context",
            source="platform",
            reason="Bounded custom context attached by the active Liwiro page",
            content=rendered_context,
            category="platform",
            trace=True,
            score=0.6,
        )

    report = PromptContextReport(
        prompt_mode=normalized_mode,
        page_kind=page_kind,
        handoff_context=handoff_context,
        synthesis_mode=synthesis_mode,
        bootstrap_files=[],
        approximate_chars=sum(entry.chars for entry in report_entries),
        total_blocks=len(blocks),
        entries=report_entries,
        truncation_warnings=truncation_warnings,
    )
    return blocks, [trace.to_dict() for trace in traces], report.to_dict()


def build_context_bundle(
    scaffold: VerseScaffold,
    agent: AgentDefinition,
    query: str,
    thread_summary: str,
    platform_context: dict[str, Any] | None = None,
    learning_records: list[dict[str, Any]] | None = None,
) -> tuple[list[AIContextBlock], list[dict[str, Any]]]:
    blocks, traces, _report = build_prompt_context_bundle(
        scaffold,
        agent,
        query,
        thread_summary,
        platform_context,
        learning_records=learning_records,
        prompt_mode="bounded",
    )
    return blocks, traces


def build_context_file_index(scaffold: VerseScaffold) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for item in scaffold.context_library.values():
        entries.append(
            {
                "fileId": item.file_id,
                "title": item.title,
                "kind": item.kind,
                "summary": item.summary,
                "keywords": list(item.keywords),
                "domains": list(item.domains),
                "artifactKinds": list(item.artifact_kinds),
                "capabilityIds": list(item.capability_ids),
                "agentIds": list(item.agent_ids),
                "pageKinds": list(item.page_kinds),
                "selectionHints": list(item.selection_hints),
                "priority": int(item.priority or 0),
            }
        )
    entries.sort(key=lambda item: (int(item.get("priority") or 0), len(item.get("summary") or "")), reverse=True)
    return entries


def select_context_entries(
    scaffold: VerseScaffold,
    query: str,
    *,
    lead_agent_id: str = "",
    capability_id: str = "",
    page_kind: str = "",
    limit: int = 8,
) -> list[ContextLibraryEntry]:
    scored: list[tuple[float, ContextLibraryEntry]] = []
    for entry in scaffold.context_library.values():
        search_text = " ".join(
            [
                entry.title,
                entry.summary,
                " ".join(entry.keywords),
                " ".join(entry.domains),
                " ".join(entry.selection_hints),
                " ".join(entry.capability_ids),
                " ".join(entry.agent_ids),
                " ".join(entry.page_kinds),
            ]
        )
        score = _score_text(query, search_text)
        if capability_id and capability_id in entry.capability_ids:
            score += 0.45
        if lead_agent_id and lead_agent_id in entry.agent_ids:
            score += 0.2
        if page_kind and page_kind in entry.page_kinds:
            score += 0.18
        if score > 0 or entry.priority >= 9:
            score += min(max(entry.priority, 0), 10) / 100.0
            scored.append((score, entry))
    scored.sort(key=lambda item: item[0], reverse=True)
    selected: list[ContextLibraryEntry] = []
    seen: set[str] = set()
    for _, entry in scored:
        if entry.file_id in seen:
            continue
        selected.append(entry)
        seen.add(entry.file_id)
        if len(selected) >= limit:
            break
    return selected


def build_generation_context_bundle(
    scaffold: VerseScaffold,
    lead_agent: AgentDefinition,
    query: str,
    thread_summary: str,
    *,
    capability: dict[str, Any] | None = None,
    supporting_agents: list[AgentDefinition] | None = None,
    context_entries: list[ContextLibraryEntry] | None = None,
    platform_context: dict[str, Any] | None = None,
    learning_records: list[dict[str, Any]] | None = None,
    prompt_mode: str = "full",
    thread_messages: list[dict[str, Any]] | None = None,
    handoff_context: bool = False,
    synthesis_mode: bool = False,
) -> tuple[list[AIContextBlock], list[dict[str, Any]], dict[str, Any]]:
    blocks, traces, report = build_prompt_context_bundle(
        scaffold,
        lead_agent,
        query,
        thread_summary,
        platform_context=platform_context,
        learning_records=learning_records,
        prompt_mode=prompt_mode,
        thread_messages=thread_messages,
        handoff_context=handoff_context,
        synthesis_mode=synthesis_mode,
    )

    normalized_mode = str(report.get("promptMode") or prompt_mode or "full").strip().lower()

    def add_generated_block(
        *,
        label: str,
        source: str,
        reason: str,
        content: str,
        category: str = "reference",
        trace_source: str = "",
        score: float = 0.0,
    ) -> None:
        limit = _CONTEXT_CHAR_LIMITS.get(category, 1200)
        trimmed, truncated = _trim_context_content(content, limit=limit)
        if not trimmed:
            return
        blocks.append(AIContextBlock(label=label, source=source, reason=reason, content=trimmed))
        traces.append(
            RetrievalTraceEntry(
                source=trace_source or source,
                reason=reason,
                score=score,
                excerpt=trimmed[:240],
            ).to_dict()
        )
        report_entries = list(report.get("entries") or [])
        report_entries.append(
            PromptContextEntry(
                label=label,
                source=source,
                reason=reason,
                category=category,
                chars=len(trimmed),
                prompt_mode=normalized_mode,
                truncated=truncated,
            ).to_dict()
        )
        report["entries"] = report_entries
        report["approximateChars"] = int(report.get("approximateChars") or 0) + len(trimmed)
        report["totalBlocks"] = len(blocks)
        if truncated:
            warnings = list(report.get("truncationWarnings") or [])
            warnings.append(f"{label} was truncated to keep prompt assembly bounded.")
            report["truncationWarnings"] = warnings

    add_generated_block(
        label=f"Lead Agent Contract: {lead_agent.active_display_name}",
        source=lead_agent.source_path,
        reason="Selected lead agent persona, remit, and contract",
        content="\n".join(
            [
                f"Name: {lead_agent.active_display_name}",
                f"Title: {lead_agent.title}",
                f"Mission: {lead_agent.mission}",
                f"Responsibilities: {'; '.join(lead_agent.core_responsibilities)}",
                f"Preferred Outputs: {'; '.join(lead_agent.preferred_outputs)}",
                f"Contract: {json.dumps(lead_agent.contract or {}, ensure_ascii=True)}",
            ]
        ),
        category="agent-profile",
        score=0.95,
    )

    contributors = [agent for agent in list(supporting_agents or []) if isinstance(agent, AgentDefinition)]
    if contributors:
        add_generated_block(
            label="Supporting Agents",
            source="verse-team",
            reason="Selected collaborative team for this turn",
            content="\n".join(
                [f"- {agent.active_display_name}: {agent.mission or '; '.join(agent.core_responsibilities[:2])}" for agent in contributors]
            ),
            category="agent-profile",
            score=0.74,
        )

    if isinstance(capability, dict) and capability:
        add_generated_block(
            label=f"Capability: {str(capability.get('title') or capability.get('id') or 'Capability').strip()}",
            source="verse-capabilities",
            reason="Selected capability contract for this turn",
            content=json.dumps(capability, ensure_ascii=True, indent=2),
            category="reference",
            score=0.92,
        )

    for entry in list(context_entries or []):
        add_generated_block(
            label=f"Context File: {entry.title}",
            source=entry.source_path,
            reason=f"Selected specialized context file ({entry.kind})",
            content=entry.content,
            category="reference",
            trace_source=entry.file_id,
            score=0.8 + min(max(entry.priority, 0), 10) / 100.0,
        )

    return blocks, traces, report
