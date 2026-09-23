from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
import re


CONFIDENCE_VALUES = {"High", "Medium", "Low", "Blocked"}
REQUEST_MODE_VALUES = {"explain", "plan", "design", "build", "operate", "analyze", "mixed-design-build"}
HANDOFF_STATUS_VALUES = {"lead", "invited", "responded", "synthesized", "closed", "blocked"}
DEFAULT_VERSE_THREAD_TITLE = "Hello, Chat"
VERSE_COLLABORATION_LEVELS = ("collaborative", "very collaborative", "absolutely synergetic")
DEFAULT_VERSE_COLLABORATION_LEVEL = "very collaborative"
VERSE_PROMPT_MODES = ("bounded", "full", "minimal")
DEFAULT_PROACTIVITY_LEVEL = 2
PROACTIVITY_LEVEL_MIN = 1
PROACTIVITY_LEVEL_MAX = 6
THREAD_ORIGIN_VALUES = {"user", "proactive"}
DEFAULT_THREAD_ORIGIN = "user"
PROACTIVE_NOTIFICATION_STATES = {"new", "reminded", "read", "ignored"}
DEFAULT_PROACTIVE_NOTIFICATION_STATE = "new"

STYLE_TOKEN_MAP = {
    "deep blue": "blue",
    "teal": "teal",
    "amber": "amber",
    "violet": "violet",
    "silver-gray": "slate",
    "silver gray": "slate",
}


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def normalize_confidence(value: str | None) -> str:
    text = str(value or "").strip().title()
    return text if text in CONFIDENCE_VALUES else "Medium"


def normalize_request_mode(value: Any, default: str = "explain") -> str:
    text = str(value or "").strip().lower()
    fallback = str(default or "explain").strip().lower()
    if fallback not in REQUEST_MODE_VALUES:
        fallback = "explain"
    return text if text in REQUEST_MODE_VALUES else fallback


def normalize_handoff_status(value: Any, default: str = "invited") -> str:
    text = str(value or "").strip().lower()
    fallback = str(default or "invited").strip().lower()
    if fallback not in HANDOFF_STATUS_VALUES:
        fallback = "invited"
    return text if text in HANDOFF_STATUS_VALUES else fallback


def normalize_collaboration_level(value: str | None) -> str:
    text = str(value or "").strip().lower()
    return text if text in VERSE_COLLABORATION_LEVELS else DEFAULT_VERSE_COLLABORATION_LEVEL


def normalize_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if not text:
        return bool(default)
    return text in {"1", "true", "yes", "on"}


def normalize_proactivity_level(value: Any) -> int:
    try:
        number = int(value)
    except Exception:
        number = DEFAULT_PROACTIVITY_LEVEL
    return max(PROACTIVITY_LEVEL_MIN, min(PROACTIVITY_LEVEL_MAX, number))


def normalize_thread_origin(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in THREAD_ORIGIN_VALUES else DEFAULT_THREAD_ORIGIN


def normalize_prompt_mode(value: Any, default: str = "full") -> str:
    fallback = str(default or "full").strip().lower()
    if fallback not in VERSE_PROMPT_MODES:
        fallback = "full"
    text = str(value or "").strip().lower()
    return text if text in VERSE_PROMPT_MODES else fallback


def normalize_notification_state(value: Any, default: str = DEFAULT_PROACTIVE_NOTIFICATION_STATE) -> str:
    fallback = str(default or DEFAULT_PROACTIVE_NOTIFICATION_STATE).strip().lower()
    if fallback not in PROACTIVE_NOTIFICATION_STATES:
        fallback = DEFAULT_PROACTIVE_NOTIFICATION_STATE
    text = str(value or "").strip().lower()
    return text if text in PROACTIVE_NOTIFICATION_STATES else fallback


def normalize_issue_key(value: Any, fallback: Any = "") -> str:
    candidate = slugify(str(value or "").strip())
    if candidate:
        return candidate
    return slugify(str(fallback or "").strip())


def default_agent_proactivity_settings() -> dict[str, Any]:
    return {
        "proactivity_enabled": True,
        "proactivity_level": DEFAULT_PROACTIVITY_LEVEL,
    }


def normalize_agent_proactivity_settings(raw: Any) -> dict[str, Any]:
    item = dict(raw or {}) if isinstance(raw, dict) else {}
    defaults = default_agent_proactivity_settings()
    return {
        "proactivity_enabled": normalize_bool(
            item.get("proactivity_enabled") if "proactivity_enabled" in item else item.get("proactivityEnabled"),
            defaults["proactivity_enabled"],
        ),
        "proactivity_level": normalize_proactivity_level(
            item.get("proactivity_level") if "proactivity_level" in item else item.get("proactivityLevel")
        ),
    }


def default_thread_title(message: str) -> str:
    text = " ".join(str(message or "").strip().split())
    if not text:
        return DEFAULT_VERSE_THREAD_TITLE
    if len(text) <= 72:
        return text
    return f"{text[:69].rstrip()}..."


def is_placeholder_thread_title(title: str | None) -> bool:
    text = str(title or "").strip().lower()
    return text in {"", "untitled thread", "new verse thread", DEFAULT_VERSE_THREAD_TITLE.lower()}


@dataclass
class AgentDisplayProfile:
    agent_id: str
    display_name: str
    renamed_by: str = ""
    updated_at: str = field(default_factory=iso_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentDefinition:
    agent_id: str
    title: str
    name: str
    theme: str = ""
    archetype: str = ""
    temperament: str = ""
    style_color_suggestion: str = ""
    style_token: str = "slate"
    mission: str = ""
    primary_users: list[str] = field(default_factory=list)
    core_responsibilities: list[str] = field(default_factory=list)
    decision_style: list[str] = field(default_factory=list)
    allowed_inputs: list[str] = field(default_factory=list)
    preferred_outputs: list[str] = field(default_factory=list)
    collaboration_rules: list[str] = field(default_factory=list)
    mind_share_read_scope: list[str] = field(default_factory=list)
    mind_share_write_scope: list[str] = field(default_factory=list)
    do_not: list[str] = field(default_factory=list)
    success_criteria: str = ""
    source_path: str = ""
    raw_markdown: str = ""
    display_name: str = ""
    contract: dict[str, Any] = field(default_factory=dict)

    @property
    def active_display_name(self) -> str:
        return str(self.display_name or self.name or self.title).strip()

    def aliases(self) -> list[str]:
        values = [
            self.title,
            self.name,
            self.active_display_name,
            self.agent_id,
            self.agent_id.replace("-", " "),
        ]
        out: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if text and text.lower() not in {item.lower() for item in out}:
                out.append(text)
        return out

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SkillDefinition:
    skill_id: str
    title: str
    purpose: str = ""
    best_suited_agent: str = ""
    inputs: list[str] = field(default_factory=list)
    procedure: list[str] = field(default_factory=list)
    output_format: list[str] = field(default_factory=list)
    failure_conditions: list[str] = field(default_factory=list)
    quality_bar: str = ""
    source_path: str = ""
    raw_markdown: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HandoffRule:
    source_agent_id: str
    target_agent_id: str
    triggers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MindShareDocument:
    file_name: str
    path: str
    content: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BootstrapDocument:
    file_name: str
    path: str
    title: str
    content: str


@dataclass
class ContextLibraryEntry:
    file_id: str
    title: str
    kind: str
    summary: str = ""
    keywords: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    artifact_kinds: list[str] = field(default_factory=list)
    capability_ids: list[str] = field(default_factory=list)
    agent_ids: list[str] = field(default_factory=list)
    page_kinds: list[str] = field(default_factory=list)
    selection_hints: list[str] = field(default_factory=list)
    priority: int = 0
    source_path: str = ""
    content: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievalTraceEntry:
    source: str
    reason: str
    score: float = 0.0
    excerpt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RoutedAgentDecision:
    agent_id: str
    source: str
    reason: str
    request_mode: str = "explain"
    matched_terms: list[str] = field(default_factory=list)
    routing_evidence: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["request_mode"] = normalize_request_mode(self.request_mode)
        return payload


@dataclass
class AgentHandoff:
    source_agent_id: str
    target_agent_id: str
    reason: str
    initiated_by: str = "agent"
    status: str = "invited"
    why_invited: str = ""
    review_focus: str = ""
    expected_decision: str = ""
    created_at: str = field(default_factory=iso_now)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = normalize_handoff_status(self.status)
        return payload


@dataclass
class MindShareWriteEntry:
    file_name: str
    agent_id: str
    agent_name: str
    agent_title: str
    agent_display_name: str
    thread_id: str
    confidence: str
    basis: str
    content_type: str
    content: str
    timestamp: str = field(default_factory=iso_now)
    preview: str = ""
    applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VerseLearningRecord:
    record_id: str
    category: str
    source: str
    issue: str
    resolution: str
    page_kind: str = ""
    artifact_kind: str = ""
    agent_id: str = ""
    thread_id: str = ""
    username: str = ""
    trigger_pattern: str = ""
    wrong_behavior: str = ""
    correct_behavior: str = ""
    enforcement_rule: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=iso_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PromptContextEntry:
    label: str
    source: str
    reason: str
    category: str
    chars: int = 0
    prompt_mode: str = "full"
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["prompt_mode"] = normalize_prompt_mode(self.prompt_mode)
        return payload


@dataclass
class PromptContextReport:
    prompt_mode: str = "full"
    page_kind: str = ""
    handoff_context: bool = False
    synthesis_mode: bool = False
    bootstrap_files: list[str] = field(default_factory=list)
    approximate_chars: int = 0
    total_blocks: int = 0
    entries: list[PromptContextEntry] = field(default_factory=list)
    truncation_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "promptMode": normalize_prompt_mode(self.prompt_mode),
            "pageKind": str(self.page_kind or "").strip(),
            "handoffContext": bool(self.handoff_context),
            "synthesisMode": bool(self.synthesis_mode),
            "bootstrapFiles": list(self.bootstrap_files),
            "approximateChars": int(self.approximate_chars),
            "totalBlocks": int(self.total_blocks),
            "entries": [entry.to_dict() for entry in self.entries],
            "truncationWarnings": list(self.truncation_warnings),
        }


@dataclass
class VerseMessage:
    message_id: str
    role: str
    content: str
    created_at: str = field(default_factory=iso_now)
    user_display_name: str = ""
    agent_id: str = ""
    agent_name: str = ""
    agent_title: str = ""
    agent_display_name: str = ""
    style_token: str = "slate"
    content_type: str = "message"
    confidence: str = ""
    retrieval_trace: list[dict[str, Any]] = field(default_factory=list)
    artifact: dict[str, Any] | None = None
    primary_card: dict[str, Any] | None = None
    supporting_blocks: list[dict[str, Any]] = field(default_factory=list)
    contributors: list[dict[str, Any]] = field(default_factory=list)
    visualization: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
    inspect_details: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VerseDatasetSource:
    source_type: str
    format: str = ""
    filename: str = ""
    archived_name: str = ""
    archived_path: str = ""
    page_kind: str = ""
    created_at: str = field(default_factory=iso_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VerseDataset:
    dataset_id: str
    owner_username: str
    title: str
    source: dict[str, Any]
    columns: list[dict[str, Any]]
    rows: list[dict[str, Any]]
    created_at: str = field(default_factory=iso_now)
    updated_at: str = field(default_factory=iso_now)
    summary: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["row_count"] = len(self.rows)
        payload["column_count"] = len(self.columns)
        return payload


@dataclass
class VerseChartSpec:
    chart_type: str
    data: list[dict[str, Any]]
    title: str = ""
    description: str = ""
    intent: str = ""
    confidence: str = "Medium"
    status: str = "ready"
    fallback_reason: str = ""
    x_key: str = ""
    y_keys: list[str] = field(default_factory=list)
    value_key: str = ""
    series_key: str = ""
    table_columns: list[str] = field(default_factory=list)
    category_order: list[str] = field(default_factory=list)
    anomaly_points: list[dict[str, Any]] = field(default_factory=list)
    bins: list[dict[str, Any]] = field(default_factory=list)
    stacked: bool = False
    horizontal: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "chartType": self.chart_type,
            "data": list(self.data),
            "title": self.title,
            "description": self.description,
            "intent": self.intent,
            "confidence": self.confidence,
            "status": self.status,
            "fallbackReason": self.fallback_reason,
            "xKey": self.x_key,
            "yKeys": list(self.y_keys),
            "valueKey": self.value_key,
            "seriesKey": self.series_key,
            "tableColumns": list(self.table_columns),
            "categoryOrder": list(self.category_order),
            "anomalyPoints": list(self.anomaly_points),
            "bins": list(self.bins),
            "stacked": self.stacked,
            "horizontal": self.horizontal,
        }


@dataclass
class VerseAnalysisFinding:
    title: str
    description: str
    severity: str = "info"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VerseAnalysisResult:
    dataset_id: str
    title: str
    description: str = ""
    chart: dict[str, Any] = field(default_factory=dict)
    intent: str = ""
    confidence: str = "Medium"
    alternate_chart_types: list[str] = field(default_factory=list)
    metrics: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    insight_notes: list[str] = field(default_factory=list)
    detected_patterns: list[dict[str, Any]] = field(default_factory=list)
    uncertainty_notes: list[str] = field(default_factory=list)
    table_preview: list[dict[str, Any]] = field(default_factory=list)
    controls: dict[str, Any] = field(default_factory=dict)
    dataset: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "datasetId": self.dataset_id,
            "title": self.title,
            "description": self.description,
            "chart": dict(self.chart),
            "intent": self.intent,
            "confidence": self.confidence,
            "alternateChartTypes": list(self.alternate_chart_types),
            "metrics": list(self.metrics),
            "findings": list(self.findings),
            "insightNotes": list(self.insight_notes),
            "detectedPatterns": list(self.detected_patterns),
            "uncertaintyNotes": list(self.uncertainty_notes),
            "tablePreview": list(self.table_preview),
            "controls": dict(self.controls),
            "dataset": dict(self.dataset),
        }


@dataclass
class VerseWorkbenchState:
    dataset_id: str
    chart_type: str = ""
    dimension: str = ""
    metric: str = ""
    compare_by: str = ""
    aggregation: str = ""
    filters: list[dict[str, Any]] = field(default_factory=list)
    limit: int = 12

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VerseSynthesisResult:
    agent_id: str
    agent_display_name: str
    content: str
    created_at: str = field(default_factory=iso_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VerseUserSettings:
    username: str
    collaboration_level: str = DEFAULT_VERSE_COLLABORATION_LEVEL
    proactive_mode_enabled: bool = False
    agent_settings: dict[str, dict[str, Any]] = field(default_factory=dict)
    updated_at: str = field(default_factory=iso_now)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["collaboration_level"] = normalize_collaboration_level(self.collaboration_level)
        payload["proactive_mode_enabled"] = bool(self.proactive_mode_enabled)
        payload["agent_settings"] = {
            str(agent_id or "").strip(): normalize_agent_proactivity_settings(settings)
            for agent_id, settings in dict(self.agent_settings or {}).items()
            if str(agent_id or "").strip()
        }
        return payload


@dataclass
class VerseProactiveIssueRecord:
    issue_id: str
    username: str
    agent_id: str
    issue_key: str
    title: str
    thread_id: str = ""
    ignored: bool = False
    status: str = "active"
    last_evaluated_at: str = ""
    last_notified_at: str = ""
    user_replied_at: str = ""
    created_at: str = field(default_factory=iso_now)
    updated_at: str = field(default_factory=iso_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VerseNotificationRecord:
    notification_id: str
    username: str
    thread_id: str
    agent_id: str
    issue_key: str
    title: str
    body: str
    status: str = "new"
    unread: bool = True
    ignored: bool = False
    created_at: str = field(default_factory=iso_now)
    updated_at: str = field(default_factory=iso_now)
    last_notified_at: str = field(default_factory=iso_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VerseProactiveScheduleState:
    username: str
    agent_id: str
    last_evaluated_at: str = ""
    next_scheduled_at: str = ""
    updated_at: str = field(default_factory=iso_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VerseThreadState:
    thread_id: str
    owner_username: str
    title: str
    created_at: str = field(default_factory=iso_now)
    updated_at: str = field(default_factory=iso_now)
    provider_name: str = ""
    provider_model: str = ""
    active_agent_id: str = ""
    participants: list[str] = field(default_factory=list)
    invited_agents: list[str] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    handoffs: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    summary_updated_at: str = ""
    synthesis: dict[str, Any] | None = None
    mind_share_writes: list[dict[str, Any]] = field(default_factory=list)
    collaboration_level: str = DEFAULT_VERSE_COLLABORATION_LEVEL
    thread_scope: str = "portal"
    context_key: str = ""
    source_pathname: str = ""
    request_mode: str = "explain"
    routing_evidence: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "VerseThreadState":
        data = dict(payload or {})
        return cls(
            thread_id=str(data.get("thread_id") or data.get("id") or ""),
            owner_username=str(data.get("owner_username") or data.get("ownerUsername") or ""),
            title=str(data.get("title") or DEFAULT_VERSE_THREAD_TITLE),
            created_at=str(data.get("created_at") or data.get("createdAt") or iso_now()),
            updated_at=str(data.get("updated_at") or data.get("updatedAt") or iso_now()),
            provider_name=str(data.get("provider_name") or data.get("providerName") or ""),
            provider_model=str(data.get("provider_model") or data.get("providerModel") or ""),
            active_agent_id=str(data.get("active_agent_id") or data.get("activeAgentId") or ""),
            participants=list(data.get("participants") or []),
            invited_agents=list(data.get("invited_agents") or data.get("invitedAgents") or []),
            messages=list(data.get("messages") or []),
            handoffs=list(data.get("handoffs") or []),
            summary=str(data.get("summary") or ""),
            summary_updated_at=str(data.get("summary_updated_at") or data.get("summaryUpdatedAt") or ""),
            synthesis=data.get("synthesis"),
            mind_share_writes=list(data.get("mind_share_writes") or data.get("mindShareWrites") or []),
            collaboration_level=normalize_collaboration_level(data.get("collaboration_level") or data.get("collaborationLevel")),
            thread_scope=str(data.get("thread_scope") or data.get("threadScope") or "portal").strip() or "portal",
            context_key=str(data.get("context_key") or data.get("contextKey") or "").strip(),
            source_pathname=str(data.get("source_pathname") or data.get("sourcePathname") or "").strip(),
            request_mode=normalize_request_mode(data.get("request_mode") or data.get("requestMode")),
            routing_evidence=list(data.get("routing_evidence") or data.get("routingEvidence") or []),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class VerseScaffold:
    agents: dict[str, AgentDefinition]
    skills: dict[str, SkillDefinition]
    routing_markdown: str
    handoff_markdown: str
    thread_behavior_markdown: str
    route_keywords: dict[str, list[str]]
    context_biases: list[tuple[list[str], str]]
    handoff_rules: list[HandoffRule]
    mind_share_documents: dict[str, MindShareDocument]
    bootstrap_documents: dict[str, BootstrapDocument]
    context_library: dict[str, ContextLibraryEntry]
    guardrails_markdown: str
    output_templates_markdown: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "agents": {key: value.to_dict() for key, value in self.agents.items()},
            "skills": {key: value.to_dict() for key, value in self.skills.items()},
            "routing_markdown": self.routing_markdown,
            "handoff_markdown": self.handoff_markdown,
            "thread_behavior_markdown": self.thread_behavior_markdown,
            "route_keywords": self.route_keywords,
            "context_biases": self.context_biases,
            "handoff_rules": [rule.to_dict() for rule in self.handoff_rules],
            "mind_share_documents": {key: value.to_dict() for key, value in self.mind_share_documents.items()},
            "bootstrap_documents": {key: value.to_dict() for key, value in self.bootstrap_documents.items()},
            "context_library": {key: value.to_dict() for key, value in self.context_library.items()},
            "guardrails_markdown": self.guardrails_markdown,
            "output_templates_markdown": self.output_templates_markdown,
        }
