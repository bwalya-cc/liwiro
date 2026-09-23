from __future__ import annotations

import difflib
import re

from .models import AgentDefinition, RoutedAgentDecision, VerseScaffold, normalize_request_mode


_TOKEN_RE = re.compile(r"[a-z0-9_]+")
_MENTION_RE = re.compile(r"@([a-z0-9][a-z0-9_-]*)", re.IGNORECASE)
_EXPLAIN_TERMS = {"explain", "what", "why", "help", "review", "understand"}
_PLAN_TERMS = {"plan", "formalize", "design", "designed", "architect", "approach", "spec"}
_BUILD_TERMS = {"build", "create", "generate", "write", "implement", "scaffold", "make"}
_OPERATE_TERMS = {"start", "stop", "delete", "restart", "deploy", "run"}
_ANALYZE_TERMS = {"analyze", "analysis", "dashboard", "metrics", "trends", "compare"}
_MIXED_DOMAIN_TERMS = {"versa", "vdb", "ux", "cli", "storage", "api", "service"}


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(str(text or "").lower())


class VerseRouter:
    def __init__(self, scaffold: VerseScaffold):
        self.scaffold = scaffold

    @staticmethod
    def _normalize_alias(value: str) -> str:
        return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())

    def resolve_explicit_agent(self, text: str) -> RoutedAgentDecision | None:
        lowered = str(text or "").lower()
        candidates: list[tuple[int, AgentDefinition, str]] = []
        for agent in self.scaffold.agents.values():
            for alias in agent.aliases():
                marker = f"@{alias.lower()}"
                if marker in lowered:
                    candidates.append((len(alias), agent, alias))
        if not candidates:
            return None
        _, agent, alias = sorted(candidates, key=lambda item: item[0], reverse=True)[0]
        return RoutedAgentDecision(
            agent_id=agent.agent_id,
            source="explicit_mention",
            reason=f"User explicitly invoked @{alias}",
            matched_terms=[alias],
        )

    def resolve_unknown_mention(self, text: str) -> RoutedAgentDecision | None:
        mentions = [str(match.group(1) or "").strip() for match in _MENTION_RE.finditer(str(text or ""))]
        if not mentions:
            return None

        alias_entries: list[tuple[str, str, AgentDefinition]] = []
        for agent in self.scaffold.agents.values():
            for alias in agent.aliases():
                normalized = self._normalize_alias(alias)
                if normalized:
                    alias_entries.append((normalized, alias, agent))

        if not alias_entries:
            return None

        for mention in mentions:
            mention_normalized = self._normalize_alias(mention)
            if not mention_normalized:
                continue
            if any(mention_normalized == normalized for normalized, _, _ in alias_entries):
                continue
            ranked: list[tuple[float, str, AgentDefinition]] = []
            for normalized, alias, agent in alias_entries:
                score = difflib.SequenceMatcher(None, mention_normalized, normalized).ratio()
                if mention_normalized in normalized or normalized in mention_normalized:
                    score = max(score, 0.84)
                ranked.append((score, alias, agent))
            ranked.sort(key=lambda item: item[0], reverse=True)
            if not ranked or ranked[0][0] < 0.62:
                continue
            suggested_alias = ranked[0][1]
            suggested_agent = ranked[0][2]
            lead_agent = self.scaffold.agents.get("liwiro-architect") or next(iter(self.scaffold.agents.values()))
            teammates = ", ".join(
                f"@{agent.active_display_name}"
                for agent in self.scaffold.agents.values()
                if agent.agent_id != lead_agent.agent_id
            )
            return RoutedAgentDecision(
                agent_id=lead_agent.agent_id,
                source="unknown_mention",
                reason=(
                    f"User addressed unknown teammate @{mention}. "
                    f"It may be a misspelling of @{suggested_alias}. "
                    f"As lead agent, acknowledge the misspelling possibility and mention the available teammates: {teammates}."
                ),
                request_mode=self.classify_request_mode(text),
                matched_terms=[mention, suggested_alias],
                routing_evidence=[
                    {"kind": "unknown-mention", "value": mention, "score": ranked[0][0]},
                    {"kind": "suggested-alias", "value": suggested_alias, "score": ranked[0][0]},
                ],
            )
        return None

    def classify_request_mode(self, text: str, page_kind: str = "") -> str:
        lowered = str(text or "").lower()
        tokens = set(tokenize(lowered))
        explain_score = len(tokens & _EXPLAIN_TERMS)
        plan_score = len(tokens & _PLAN_TERMS)
        build_score = len(tokens & _BUILD_TERMS)
        operate_score = len(tokens & _OPERATE_TERMS)
        analyze_score = len(tokens & _ANALYZE_TERMS)
        domain_mix_score = len(tokens & _MIXED_DOMAIN_TERMS)

        if analyze_score >= max(plan_score, build_score, operate_score, explain_score) and analyze_score > 0:
            return "analyze"
        if operate_score > 0 and operate_score >= max(plan_score, build_score, explain_score):
            return "operate"
        if plan_score > 0 and build_score == 0:
            return "plan" if "design" not in tokens else "design"
        if build_score > 0 and plan_score == 0:
            return "build"
        if plan_score > 0 and build_score > 0:
            return "mixed-design-build"
        if build_score > 0 and domain_mix_score >= 3:
            return "mixed-design-build"
        if build_score > 0 and ("designed" in tokens or "ux" in tokens):
            return "mixed-design-build"
        if "design" in tokens:
            return "design"
        if page_kind == "ananse-workbench":
            return "analyze"
        return "explain"

    def route(
        self,
        text: str,
        current_screen: str = "",
        active_agent_id: str = "",
        *,
        page_kind: str = "",
        desired_artifact_kind: str = "",
    ) -> RoutedAgentDecision:
        request_mode = self.classify_request_mode(text, page_kind=page_kind)
        explicit = self.resolve_explicit_agent(text)
        if explicit:
            explicit.request_mode = request_mode
            explicit.routing_evidence.append({"kind": "request-mode", "value": request_mode, "score": 1.0})
            return explicit
        unknown_mention = self.resolve_unknown_mention(text)
        if unknown_mention:
            unknown_mention.request_mode = request_mode
            unknown_mention.routing_evidence.append({"kind": "request-mode", "value": request_mode, "score": 1.0})
            return unknown_mention
        if desired_artifact_kind == "ananse-analysis":
            return RoutedAgentDecision(
                agent_id="liwiro-analyst",
                source="artifact_target",
                reason="Requested artifact kind maps directly to Ananse analysis",
                request_mode=request_mode,
                matched_terms=[desired_artifact_kind],
                routing_evidence=[{"kind": "artifact-kind", "value": desired_artifact_kind, "score": 1.0}],
            )
        if desired_artifact_kind in {"service-builder-lapis", "service-manager-action", "vi-script", "vdb-query"}:
            return RoutedAgentDecision(
                agent_id="liwiro-architect",
                source="artifact_target",
                reason="Requested artifact kind maps directly to Kalulu's implementation remit",
                request_mode=request_mode,
                matched_terms=[desired_artifact_kind],
                routing_evidence=[{"kind": "artifact-kind", "value": desired_artifact_kind, "score": 1.0}],
            )
        tokens = tokenize(text)
        scores: dict[str, tuple[int, list[str]]] = {}
        for agent_id, keywords in self.scaffold.route_keywords.items():
            matched = [keyword for keyword in keywords if keyword in tokens or keyword in str(text or "").lower()]
            if matched:
                scores[agent_id] = (len(matched), matched)
        if scores:
            agent_id, (score, matched) = sorted(scores.items(), key=lambda item: (item[1][0], item[0]), reverse=True)[0]
            return RoutedAgentDecision(
                agent_id=agent_id,
                source="routing_keywords",
                reason=f"Matched {score} routing keyword(s)",
                request_mode=request_mode,
                matched_terms=matched,
                routing_evidence=[
                    {"kind": "request-mode", "value": request_mode, "score": 1.0},
                    *({"kind": "keyword", "value": term, "score": 0.7} for term in matched),
                ],
            )
        screen_text = str(current_screen or "").lower()
        for keywords, agent_id in self.scaffold.context_biases:
            if any(keyword in screen_text for keyword in keywords):
                return RoutedAgentDecision(
                    agent_id=agent_id,
                    source="screen_context",
                    reason=f"Screen context biased routing toward {self.scaffold.agents.get(agent_id).active_display_name if self.scaffold.agents.get(agent_id) else agent_id}",
                    request_mode=request_mode,
                    matched_terms=list(keywords),
                    routing_evidence=[
                        {"kind": "request-mode", "value": request_mode, "score": 1.0},
                        *({"kind": "screen-keyword", "value": term, "score": 0.55} for term in keywords),
                    ],
                )
        if str(active_agent_id or "").strip() and active_agent_id in self.scaffold.agents and request_mode in {"explain", "plan"}:
            agent = self.scaffold.agents[active_agent_id]
            return RoutedAgentDecision(
                agent_id=agent.agent_id,
                source="thread_active_agent",
                reason=f"Continuing with the active specialist {agent.active_display_name}",
                request_mode=request_mode,
                routing_evidence=[{"kind": "active-agent", "value": agent.agent_id, "score": 0.45}],
            )
        default_agent = self.scaffold.agents.get("liwiro-architect")
        if default_agent:
            return RoutedAgentDecision(
                agent_id=default_agent.agent_id,
                source="default_architect",
                reason=f"No specialist was explicitly addressed, so Verse started with {default_agent.active_display_name}",
                request_mode=request_mode,
                routing_evidence=[{"kind": "request-mode", "value": request_mode, "score": 1.0}],
            )
        fallback = self.scaffold.agents.get("liwiro-architect") or next(iter(self.scaffold.agents.values()))
        return RoutedAgentDecision(
            agent_id=fallback.agent_id,
            source="fallback",
            reason="The request was ambiguous, so Verse chose the default architectural specialist",
            request_mode=normalize_request_mode(request_mode),
            routing_evidence=[{"kind": "request-mode", "value": request_mode, "score": 1.0}],
        )

    def allowed_handoff_targets(self, source_agent_id: str) -> set[str]:
        return {
            rule.target_agent_id
            for rule in self.scaffold.handoff_rules
            if rule.source_agent_id == source_agent_id
        }

    def normalize_handoff_target(self, source_agent_id: str, raw_target: str) -> str:
        target = str(raw_target or "").strip().lower()
        if not target:
            return ""
        for agent_id, agent in self.scaffold.agents.items():
            aliases = {alias.lower() for alias in agent.aliases()}
            if target in aliases or target == agent_id.lower():
                if agent_id in self.allowed_handoff_targets(source_agent_id):
                    return agent_id
        return ""
