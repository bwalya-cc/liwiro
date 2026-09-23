from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any
import json
import re

from .models import (
    AgentDefinition,
    AgentDisplayProfile,
    BootstrapDocument,
    ContextLibraryEntry,
    HandoffRule,
    MindShareDocument,
    SkillDefinition,
    VerseScaffold,
    slugify,
)


_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_KV_RE = re.compile(r"^- \*\*(.+?):\*\*\s*(.+?)\s*$")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _section_map(markdown: str) -> dict[str, str]:
    text = str(markdown or "")
    matches = list(_SECTION_RE.finditer(text))
    if not matches:
        return {}
    out: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        out[match.group(1).strip()] = text[start:end].strip()
    return out


def _bullets(section_text: str) -> list[str]:
    items: list[str] = []
    for raw_line in str(section_text or "").splitlines():
        line = raw_line.strip()
        if line.startswith("- "):
            value = line[2:].strip()
            if value:
                items.append(value)
    return items


def _kv_bullets(section_text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw_line in str(section_text or "").splitlines():
        line = raw_line.strip()
        match = _KV_RE.match(line)
        if not match:
            continue
        out[match.group(1).strip()] = match.group(2).strip()
    return out


def _first_paragraph(section_text: str) -> str:
    parts = [line.strip() for line in str(section_text or "").splitlines() if line.strip()]
    return " ".join(parts)


def _parse_simple_frontmatter(markdown: str) -> tuple[dict[str, Any], str]:
    text = str(markdown or "")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text.strip()
    raw = str(match.group(1) or "")
    body = str(match.group(2) or "").strip()
    data: dict[str, Any] = {}
    current_key = ""
    for raw_line in raw.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if re.match(r"^[A-Za-z0-9_-]+\s*:", line):
            key, value = line.split(":", 1)
            current_key = key.strip()
            scalar = value.strip()
            if scalar:
                data[current_key] = scalar
            else:
                data[current_key] = []
            continue
        if line.lstrip().startswith("- ") and current_key:
            bucket = data.setdefault(current_key, [])
            if not isinstance(bucket, list):
                bucket = [str(bucket)]
                data[current_key] = bucket
            bucket.append(line.strip()[2:].strip())
    return data, body


def _style_token(suggestion: str) -> str:
    from .models import STYLE_TOKEN_MAP

    return STYLE_TOKEN_MAP.get(str(suggestion or "").strip().lower(), "slate")


def _normalize_alias_lookup(agents: dict[str, AgentDefinition]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for agent_id, agent in agents.items():
        for alias in agent.aliases():
            key = alias.strip().lower()
            if key and key not in lookup:
                lookup[key] = agent_id
    return lookup


def _resolve_agent_id(name: str, alias_lookup: dict[str, str]) -> str:
    key = str(name or "").strip().lower()
    return alias_lookup.get(key, slugify(key))


class VerseContentLoader:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self._cache_key: tuple[tuple[str, int], ...] | None = None
        self._cached: VerseScaffold | None = None

    def load(self, profiles: dict[str, AgentDisplayProfile] | None = None) -> VerseScaffold:
        cache_key = self._compute_cache_key()
        if self._cached is not None and cache_key == self._cache_key:
            return self._apply_profiles(self._cached, profiles or {})

        agents = self._load_agents()
        skills = self._load_skills()
        alias_lookup = _normalize_alias_lookup(agents)
        routing_markdown = _read_text(self.root / "router" / "agent-routing.md")
        handoff_markdown = _read_text(self.root / "router" / "handoff-rules.md")
        thread_behavior_markdown = _read_text(self.root / "router" / "thread-behavior.md")
        route_keywords, context_biases = self._load_routing_rules(routing_markdown, alias_lookup)
        handoff_rules = self._load_handoff_rules(handoff_markdown, alias_lookup)
        mind_share_documents = self._load_mind_share()
        bootstrap_documents = self._load_bootstrap()
        context_library = self._load_context_library()
        guardrails_markdown = mind_share_documents.get("guardrails.md", MindShareDocument("guardrails.md", "", "")).content
        output_templates_markdown = mind_share_documents.get("output-templates.md", MindShareDocument("output-templates.md", "", "")).content
        scaffold = VerseScaffold(
            agents=agents,
            skills=skills,
            routing_markdown=routing_markdown,
            handoff_markdown=handoff_markdown,
            thread_behavior_markdown=thread_behavior_markdown,
            route_keywords=route_keywords,
            context_biases=context_biases,
            handoff_rules=handoff_rules,
            mind_share_documents=mind_share_documents,
            bootstrap_documents=bootstrap_documents,
            context_library=context_library,
            guardrails_markdown=guardrails_markdown,
            output_templates_markdown=output_templates_markdown,
        )
        self._cache_key = cache_key
        self._cached = scaffold
        return self._apply_profiles(scaffold, profiles or {})

    def _compute_cache_key(self) -> tuple[tuple[str, int], ...]:
        files = sorted(path for path in self.root.rglob("*.md") if path.is_file())
        # A workspace can be replaced while a background request is reading it
        # (for example during deploys or test temporary-directory cleanup).
        # Treat files that disappear between discovery and stat as transient
        # rather than failing the entire Verse request.
        entries: list[tuple[str, int]] = []
        for path in files:
            try:
                entries.append((str(path), path.stat().st_mtime_ns))
            except FileNotFoundError:
                continue
            except OSError:
                continue
        return tuple(entries)

    def _load_agents(self) -> dict[str, AgentDefinition]:
        out: dict[str, AgentDefinition] = {}
        contracts = self._load_agent_contracts()
        for path in sorted((self.root / "agents").glob("*.persona.md")):
            markdown = _read_text(path)
            sections = _section_map(markdown)
            identity = _kv_bullets(sections.get("Agent Identity", ""))
            title = str(identity.get("Title") or path.stem.replace(".persona", "").replace("-", " ").title()).strip()
            name = str(identity.get("Name") or slugify(title).title()).strip()
            agent_id = path.name.replace(".persona.md", "")
            contract = dict(contracts.get(agent_id) or {})
            out[agent_id] = AgentDefinition(
                agent_id=agent_id,
                title=title,
                name=name,
                theme=str(identity.get("Theme") or ""),
                archetype=str(identity.get("Archetype") or ""),
                temperament=str(identity.get("Temperament") or ""),
                style_color_suggestion=str(identity.get("Style Color Suggestion") or ""),
                style_token=_style_token(identity.get("Style Color Suggestion") or ""),
                mission=_first_paragraph(sections.get("Mission", "")),
                primary_users=_bullets(sections.get("Primary Users", "")),
                core_responsibilities=_bullets(sections.get("Core Responsibilities", "")),
                decision_style=_bullets(sections.get("Decision Style", "")),
                allowed_inputs=_bullets(sections.get("Allowed Inputs", "")),
                preferred_outputs=_bullets(sections.get("Preferred Outputs", "")),
                collaboration_rules=_bullets(sections.get("Collaboration Rules", "")),
                mind_share_read_scope=_bullets(sections.get("mind-share Read Scope", "")),
                mind_share_write_scope=_bullets(sections.get("mind-share Write Scope", "")),
                do_not=_bullets(sections.get("Do Not", "")),
                success_criteria=_first_paragraph(sections.get("Success Criteria", "")),
                source_path=str(path),
                raw_markdown=markdown,
                display_name=name,
                contract=contract,
            )
        return out

    def _load_agent_contracts(self) -> dict[str, dict]:
        path = self.root / "agents" / "contracts.json"
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(payload, dict):
            return {}
        return {str(key): dict(value) for key, value in payload.items() if isinstance(value, dict)}

    def _load_skills(self) -> dict[str, SkillDefinition]:
        out: dict[str, SkillDefinition] = {}
        for path in sorted((self.root / "skills").glob("*.skill.md")):
            markdown = _read_text(path)
            sections = _section_map(markdown)
            heading = markdown.splitlines()[0].replace("# Skill:", "").strip()
            skill_id = path.name.replace(".skill.md", "")
            out[skill_id] = SkillDefinition(
                skill_id=skill_id,
                title=heading or path.stem.replace(".skill", "").replace("-", " ").title(),
                purpose=_first_paragraph(sections.get("Purpose", "")),
                best_suited_agent=_first_paragraph(sections.get("Best-Suited Agent", "")),
                inputs=_bullets(sections.get("Inputs", "")),
                procedure=_bullets(sections.get("Procedure", "")),
                output_format=_bullets(sections.get("Output Format", "")),
                failure_conditions=_bullets(sections.get("Failure Conditions", "")),
                quality_bar=_first_paragraph(sections.get("Quality Bar", "")),
                source_path=str(path),
                raw_markdown=markdown,
            )
        return out

    def _load_routing_rules(self, markdown: str, alias_lookup: dict[str, str]) -> tuple[dict[str, list[str]], list[tuple[list[str], str]]]:
        route_keywords: dict[str, list[str]] = {}
        lines = str(markdown or "").splitlines()
        index = 0
        while index < len(lines):
            line = lines[index].strip()
            if line.startswith("### Route to ") and " when the user asks about:" in line:
                header = line.replace("### Route to ", "", 1).replace(" when the user asks about:", "").strip()
                agent_name = header.split("(", 1)[0].strip()
                agent_id = _resolve_agent_id(agent_name, alias_lookup)
                index += 1
                keywords: list[str] = []
                while index < len(lines):
                    current = lines[index].strip()
                    if current.startswith("### ") or current.startswith("## "):
                        break
                    if current.startswith("- "):
                        keywords.append(current[2:].strip().lower())
                    index += 1
                route_keywords[agent_id] = keywords
                continue
            index += 1

        context_biases: list[tuple[list[str], str]] = []
        context_section = _section_map(markdown).get("Context-Based Overrides", "")
        for line in _bullets(context_section):
            match = re.search(r"bias toward \*\*(.+?)\*\*", line)
            if not match:
                continue
            agent_id = _resolve_agent_id(match.group(1), alias_lookup)
            prefix = line.split(", bias toward", 1)[0]
            keywords = [token for token in re.findall(r"[a-z0-9]+", prefix.lower()) if token not in {"if", "the", "user", "is", "on", "an", "a", "or", "screen", "toward", "bias"}]
            if keywords:
                context_biases.append((keywords, agent_id))
        return route_keywords, context_biases

    def _load_handoff_rules(self, markdown: str, alias_lookup: dict[str, str]) -> list[HandoffRule]:
        rules: list[HandoffRule] = []
        lines = str(markdown or "").splitlines()
        index = 0
        while index < len(lines):
            line = lines[index].strip()
            if line.startswith("### ") and " → " in line:
                header = line.replace("### ", "", 1).strip()
                left, right = [item.strip() for item in header.split("→", 1)]
                source = _resolve_agent_id(left, alias_lookup)
                target = _resolve_agent_id(right, alias_lookup)
                index += 1
                triggers: list[str] = []
                while index < len(lines):
                    current = lines[index].strip()
                    if current.startswith("### ") or current.startswith("## "):
                        break
                    if current.startswith("- "):
                        triggers.append(current[2:].strip().lower())
                    index += 1
                rules.append(HandoffRule(source_agent_id=source, target_agent_id=target, triggers=triggers))
                continue
            index += 1
        return rules

    def _load_mind_share(self) -> dict[str, MindShareDocument]:
        out: dict[str, MindShareDocument] = {}
        for path in sorted((self.root / "mind-share").glob("*.md")):
            out[path.name] = MindShareDocument(
                file_name=path.name,
                path=str(path),
                content=_read_text(path),
            )
        return out

    def _load_bootstrap(self) -> dict[str, BootstrapDocument]:
        out: dict[str, BootstrapDocument] = {}
        bootstrap_root = self.root / "bootstrap"
        if not bootstrap_root.exists():
            return out
        for path in sorted(bootstrap_root.glob("*.md")):
            markdown = _read_text(path)
            title = markdown.splitlines()[0].replace("#", "").strip() if markdown else path.stem.replace("-", " ").title()
            out[path.name] = BootstrapDocument(
                file_name=path.name,
                path=str(path),
                title=title,
                content=markdown,
            )
        return out

    def _load_context_library(self) -> dict[str, ContextLibraryEntry]:
        out: dict[str, ContextLibraryEntry] = {}
        context_root = self.root / "context"
        if not context_root.exists():
            return out
        for path in sorted(context_root.rglob("*.md")):
            if not path.is_file():
                continue
            raw = _read_text(path)
            metadata, body = _parse_simple_frontmatter(raw)
            file_id = str(metadata.get("id") or path.relative_to(context_root).as_posix().replace(".md", "")).strip()
            title = str(metadata.get("title") or path.stem.replace("-", " ").title()).strip()
            kind = str(metadata.get("type") or path.parent.name).strip()
            summary = str(metadata.get("summary") or _first_paragraph(body)).strip()
            priority_raw = str(metadata.get("priority") or "0").strip()
            try:
                priority = int(priority_raw)
            except Exception:
                priority = 0

            def _list_value(key: str) -> list[str]:
                value = metadata.get(key)
                if isinstance(value, list):
                    return [str(item or "").strip() for item in value if str(item or "").strip()]
                text = str(value or "").strip()
                return [text] if text else []

            out[file_id] = ContextLibraryEntry(
                file_id=file_id,
                title=title,
                kind=kind,
                summary=summary,
                keywords=_list_value("tags"),
                domains=_list_value("domains"),
                artifact_kinds=_list_value("appliesToArtifacts"),
                capability_ids=_list_value("appliesToCapabilities"),
                agent_ids=_list_value("appliesToAgents"),
                page_kinds=_list_value("appliesToPages"),
                selection_hints=_list_value("selectionHints"),
                priority=priority,
                source_path=str(path),
                content=body,
            )
        return out

    def _apply_profiles(self, scaffold: VerseScaffold, profiles: dict[str, AgentDisplayProfile]) -> VerseScaffold:
        if not profiles:
            return scaffold
        updated_agents: dict[str, AgentDefinition] = {}
        for agent_id, agent in scaffold.agents.items():
            profile = profiles.get(agent_id)
            if profile and str(profile.display_name or "").strip():
                updated_agents[agent_id] = replace(agent, display_name=str(profile.display_name).strip())
            else:
                updated_agents[agent_id] = agent
        return replace(scaffold, agents=updated_agents)
