from __future__ import annotations

from pathlib import Path
import threading

from .models import AgentDefinition, MindShareWriteEntry, normalize_confidence


class MindShareValidationError(ValueError):
    pass


class MindShareManager:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.lock = threading.RLock()

    def preview_write(
        self,
        agent: AgentDefinition,
        *,
        thread_id: str,
        file_name: str,
        content_type: str,
        basis: str,
        confidence: str,
        content: str,
    ) -> MindShareWriteEntry:
        normalized_file = str(file_name or "").strip()
        if not normalized_file:
            raise MindShareValidationError("mind-share target file is required")
        if normalized_file not in agent.mind_share_write_scope:
            raise MindShareValidationError(f"{agent.active_display_name} is not allowed to write to {normalized_file}")
        target = (self.root / normalized_file).resolve()
        if target.parent != self.root or not target.name.endswith(".md"):
            raise MindShareValidationError("Only existing markdown files inside mind-share are writable")
        if not target.exists():
            raise MindShareValidationError(f"mind-share target {normalized_file} does not exist")
        basis_text = str(basis or "").strip()
        content_text = str(content or "").strip()
        if not basis_text:
            raise MindShareValidationError("mind-share write basis is required")
        if not content_text:
            raise MindShareValidationError("mind-share write content is required")
        entry = MindShareWriteEntry(
            file_name=normalized_file,
            agent_id=agent.agent_id,
            agent_name=agent.name,
            agent_title=agent.title,
            agent_display_name=agent.active_display_name,
            thread_id=str(thread_id or "").strip(),
            confidence=normalize_confidence(confidence),
            basis=basis_text,
            content_type=str(content_type or "Observation").strip() or "Observation",
            content=content_text,
        )
        entry.preview = self.render_entry(entry)
        return entry

    def render_entry(self, entry: MindShareWriteEntry) -> str:
        content_label = str(entry.content_type or "Observation").strip().title()
        return (
            f"\n### {entry.timestamp} | {entry.agent_display_name} | {content_label} | {entry.confidence} confidence\n"
            f"Basis: {entry.basis}\n"
            f"Thread: {entry.thread_id}\n"
            f"Content Type: {entry.content_type}\n"
            f"Content:\n{entry.content.strip()}\n"
        )

    def apply_write(self, entry: MindShareWriteEntry) -> MindShareWriteEntry:
        target = (self.root / entry.file_name).resolve()
        rendered = entry.preview or self.render_entry(entry)
        with self.lock:
            current = target.read_text(encoding="utf-8") if target.exists() else ""
            updated = f"{current.rstrip()}\n{rendered}".rstrip() + "\n"
            target.write_text(updated, encoding="utf-8")
        entry.preview = rendered
        entry.applied = True
        return entry
