from __future__ import annotations

import copy
from pathlib import Path
import threading
import uuid

from app.vdb_bson import read_bson_value, write_bson_value

from .models import (
    AgentDisplayProfile,
    VerseLearningRecord,
    VerseNotificationRecord,
    VerseProactiveIssueRecord,
    VerseProactiveScheduleState,
    VerseThreadState,
    VerseUserSettings,
    default_agent_proactivity_settings,
    default_thread_title,
    iso_now,
    normalize_agent_proactivity_settings,
    normalize_bool,
    normalize_collaboration_level,
    normalize_issue_key,
    normalize_notification_state,
    normalize_proactivity_level,
    normalize_thread_origin,
)


class VerseStore:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir).resolve()
        self.threads_dir = self.data_dir / "threads"
        self.datasets_dir = self.data_dir / "datasets"
        self.dataset_archives_dir = self.data_dir / "dataset_archives"
        self.agent_profiles_path = self.data_dir / "agent_profiles.bson"
        self.learning_records_path = self.data_dir / "learning_records.bson"
        self.user_settings_path = self.data_dir / "user_settings.bson"
        self.proactive_notifications_path = self.data_dir / "proactive_notifications.bson"
        self.proactive_issue_memory_path = self.data_dir / "proactive_issue_memory.bson"
        self.proactive_schedule_path = self.data_dir / "proactive_schedule_state.bson"
        self.lock = threading.RLock()
        self._payload_cache: dict[str, tuple[int, object]] = {}
        self._thread_cache: dict[str, tuple[int, VerseThreadState]] = {}
        self._dataset_cache: dict[str, tuple[int, dict]] = {}
        self._ensure_runtime_layout()

    def _ensure_runtime_layout(self) -> None:
        self.threads_dir.mkdir(parents=True, exist_ok=True)
        self.datasets_dir.mkdir(parents=True, exist_ok=True)
        self.dataset_archives_dir.mkdir(parents=True, exist_ok=True)
        if not self.agent_profiles_path.exists():
            write_bson_value(self.agent_profiles_path, {})
        if not self.learning_records_path.exists():
            write_bson_value(self.learning_records_path, [])
        if not self.user_settings_path.exists():
            write_bson_value(self.user_settings_path, {})
        if not self.proactive_notifications_path.exists():
            write_bson_value(self.proactive_notifications_path, [])
        if not self.proactive_issue_memory_path.exists():
            write_bson_value(self.proactive_issue_memory_path, [])
        if not self.proactive_schedule_path.exists():
            write_bson_value(self.proactive_schedule_path, {})

    def _thread_path(self, thread_id: str) -> Path:
        return self.threads_dir / f"{thread_id}.bson"

    def _dataset_path(self, dataset_id: str) -> Path:
        return self.datasets_dir / f"{dataset_id}.bson"

    def _path_mtime_ns(self, path: Path) -> int:
        try:
            return path.stat().st_mtime_ns
        except OSError:
            return -1

    def _read_payload_cached(self, path: Path, default):
        cache_key = str(path)
        if not path.exists():
            value = default() if callable(default) else default
            return copy.deepcopy(value)
        mtime_ns = self._path_mtime_ns(path)
        cached = self._payload_cache.get(cache_key)
        if cached and cached[0] == mtime_ns:
            return copy.deepcopy(cached[1])
        payload = read_bson_value(path)
        self._payload_cache[cache_key] = (mtime_ns, copy.deepcopy(payload))
        return copy.deepcopy(payload)

    def _write_payload_cached(self, path: Path, payload) -> None:
        write_bson_value(path, payload)
        self._payload_cache[str(path)] = (self._path_mtime_ns(path), copy.deepcopy(payload))

    def _load_thread_cached(self, path: Path, *, clone: bool = True) -> VerseThreadState | None:
        if not path.exists():
            return None
        thread_id = path.stem
        mtime_ns = self._path_mtime_ns(path)
        cached = self._thread_cache.get(thread_id)
        if cached and cached[0] == mtime_ns:
            return copy.deepcopy(cached[1]) if clone else cached[1]
        payload = read_bson_value(path)
        if not isinstance(payload, dict):
            return None
        thread = VerseThreadState.from_dict(payload)
        self._thread_cache[thread_id] = (mtime_ns, copy.deepcopy(thread))
        return thread if clone else self._thread_cache[thread_id][1]

    def _write_thread_cached(self, thread: VerseThreadState) -> None:
        path = self._thread_path(thread.thread_id)
        payload = thread.to_dict()
        write_bson_value(path, payload)
        self._thread_cache[thread.thread_id] = (self._path_mtime_ns(path), copy.deepcopy(thread))

    def _drop_thread_cached(self, thread_id: str) -> None:
        self._thread_cache.pop(str(thread_id or "").strip(), None)

    def _load_dataset_cached(self, path: Path, *, clone: bool = True) -> dict | None:
        if not path.exists():
            return None
        dataset_id = path.stem
        mtime_ns = self._path_mtime_ns(path)
        cached = self._dataset_cache.get(dataset_id)
        if cached and cached[0] == mtime_ns:
            return copy.deepcopy(cached[1]) if clone else cached[1]
        payload = read_bson_value(path)
        if not isinstance(payload, dict):
            return None
        self._dataset_cache[dataset_id] = (mtime_ns, copy.deepcopy(payload))
        return payload if clone else self._dataset_cache[dataset_id][1]

    def _write_dataset_cached(self, dataset_id: str, payload: dict) -> None:
        path = self._dataset_path(dataset_id)
        write_bson_value(path, payload)
        self._dataset_cache[str(dataset_id or "").strip()] = (self._path_mtime_ns(path), copy.deepcopy(payload))

    def list_threads(self, owner_username: str, *, scopes: set[str] | None = None) -> list[dict]:
        threads: list[dict] = []
        allowed_scopes = {str(item or "").strip() for item in set(scopes or {"portal", "dock"}) if str(item or "").strip()}
        with self.lock:
            for path in sorted(self.threads_dir.glob("*.bson")):
                try:
                    thread = self._load_thread_cached(path, clone=False)
                except Exception:
                    continue
                if thread is None:
                    continue
                if thread.owner_username != str(owner_username or "").strip():
                    continue
                if allowed_scopes and str(thread.thread_scope or "portal").strip() not in allowed_scopes:
                    continue
                threads.append(self.serialize_thread(thread, include_messages=False))
        return sorted(threads, key=lambda item: item.get("updatedAt") or "", reverse=True)

    def create_thread(
        self,
        owner_username: str,
        title: str = "",
        initial_message: str = "",
        provider_name: str = "",
        provider_model: str = "",
        *,
        collaboration_level: str = "",
        thread_scope: str = "portal",
        context_key: str = "",
        source_pathname: str = "",
        metadata: dict | None = None,
    ) -> dict:
        thread_id = uuid.uuid4().hex
        created = VerseThreadState(
            thread_id=thread_id,
            owner_username=str(owner_username or "").strip(),
            title=str(title or "").strip() or default_thread_title(""),
            provider_name=str(provider_name or "").strip(),
            provider_model=str(provider_model or "").strip(),
            collaboration_level=normalize_collaboration_level(collaboration_level),
            thread_scope=str(thread_scope or "portal").strip() or "portal",
            context_key=str(context_key or "").strip(),
            source_pathname=str(source_pathname or "").strip(),
            metadata=dict(metadata or {}),
        )
        self.save_thread(created)
        return self.serialize_thread(created)

    def load_thread(self, thread_id: str) -> VerseThreadState | None:
        with self.lock:
            return self._load_thread_cached(self._thread_path(thread_id))

    def list_datasets(self, owner_username: str) -> list[dict]:
        datasets: list[dict] = []
        with self.lock:
            for path in sorted(self.datasets_dir.glob("*.bson")):
                try:
                    payload = self._load_dataset_cached(path, clone=False)
                except Exception:
                    continue
                if payload is None:
                    continue
                if str(payload.get("owner_username") or payload.get("ownerUsername") or "").strip() != str(owner_username or "").strip():
                    continue
                datasets.append(self.serialize_dataset(payload))
        return sorted(datasets, key=lambda item: item.get("updatedAt") or "", reverse=True)

    def load_dataset(self, dataset_id: str) -> dict | None:
        with self.lock:
            return self._load_dataset_cached(self._dataset_path(dataset_id))

    def save_dataset(self, dataset: dict) -> dict:
        with self.lock:
            payload = dict(dataset or {})
            payload["updated_at"] = iso_now()
            dataset_id = str(payload.get("dataset_id") or payload.get("id") or uuid.uuid4().hex)
            self._write_dataset_cached(dataset_id, payload)
        return self.serialize_dataset(payload)

    def write_dataset_archive(self, dataset_id: str, filename: str, content: bytes) -> dict:
        safe_name = Path(str(filename or "dataset-upload.bin")).name or "dataset-upload.bin"
        archive_name = f"{dataset_id}-{safe_name}"
        archive_path = self.dataset_archives_dir / archive_name
        archive_path.write_bytes(content)
        return {
            "archived_name": archive_name,
            "archived_path": str(archive_path),
        }

    def save_thread(self, thread: VerseThreadState) -> dict:
        with self.lock:
            thread.updated_at = iso_now()
            self._write_thread_cached(thread)
        return self.serialize_thread(thread)

    def thread_summary(self, thread_id: str) -> dict | None:
        with self.lock:
            thread = self._load_thread_cached(self._thread_path(thread_id), clone=False)
        if not thread:
            return None
        return self.serialize_thread(thread, include_messages=False)

    def delete_thread(self, username: str, thread_id: str) -> bool:
        normalized_username = str(username or "").strip()
        normalized_thread = str(thread_id or "").strip()
        if not normalized_username or not normalized_thread:
            return False
        deleted = False
        with self.lock:
            path = self._thread_path(normalized_thread)
            if path.exists():
                path.unlink()
                self._drop_thread_cached(normalized_thread)
                deleted = True
            # Best-effort cleanup keeps delete resilient even if proactive memory is malformed.
            try:
                notifications = self._read_payload_cached(self.proactive_notifications_path, list)
                if isinstance(notifications, list):
                    filtered_notifications = [
                        item
                        for item in notifications
                        if (
                            str(item.get("thread_id") or item.get("threadId") or "").strip() != normalized_thread
                            or str(item.get("username") or "").strip() != normalized_username
                        )
                    ]
                    if len(filtered_notifications) != len(notifications):
                        self._write_payload_cached(self.proactive_notifications_path, filtered_notifications)
            except Exception:
                pass
            try:
                issues = self._read_payload_cached(self.proactive_issue_memory_path, list)
                if isinstance(issues, list):
                    filtered_issues = [
                        item
                        for item in issues
                        if (
                            str(item.get("thread_id") or item.get("threadId") or "").strip() != normalized_thread
                            or str(item.get("username") or "").strip() != normalized_username
                        )
                    ]
                    if len(filtered_issues) != len(issues):
                        self._write_payload_cached(self.proactive_issue_memory_path, filtered_issues)
            except Exception:
                pass
        return deleted

    def resolve_thread_by_context(
        self,
        owner_username: str,
        *,
        thread_scope: str,
        context_key: str,
    ) -> VerseThreadState | None:
        scope = str(thread_scope or "").strip()
        key = str(context_key or "").strip()
        if not scope or not key:
            return None
        with self.lock:
            for path in sorted(self.threads_dir.glob("*.bson")):
                try:
                    thread = self._load_thread_cached(path, clone=False)
                except Exception:
                    continue
                if thread is None:
                    continue
                if thread.owner_username != str(owner_username or "").strip():
                    continue
                if str(thread.thread_scope or "").strip() != scope:
                    continue
                if str(thread.context_key or "").strip() != key:
                    continue
                return thread
        return None

    def load_user_settings(self, username: str) -> VerseUserSettings:
        normalized_username = str(username or "").strip()
        if not normalized_username:
            return VerseUserSettings(username="")
        with self.lock:
            payload = self._read_payload_cached(self.user_settings_path, dict)
        raw = payload.get(normalized_username) if isinstance(payload, dict) else {}
        if not isinstance(raw, dict):
            raw = {}
        raw_agent_settings = raw.get("agent_settings") or raw.get("agentSettings") or raw.get("agents") or {}
        return VerseUserSettings(
            username=normalized_username,
            collaboration_level=normalize_collaboration_level(raw.get("collaboration_level") or raw.get("collaborationLevel")),
            proactive_mode_enabled=normalize_bool(raw.get("proactive_mode_enabled") if "proactive_mode_enabled" in raw else raw.get("proactiveModeEnabled")),
            agent_settings={
                str(agent_id or "").strip(): normalize_agent_proactivity_settings(settings)
                for agent_id, settings in dict(raw_agent_settings or {}).items()
                if str(agent_id or "").strip()
            },
            updated_at=str(raw.get("updated_at") or raw.get("updatedAt") or iso_now()),
        )

    def save_user_settings(self, settings: VerseUserSettings) -> dict:
        with self.lock:
            payload = self._read_payload_cached(self.user_settings_path, dict)
            if not isinstance(payload, dict):
                payload = {}
            settings.updated_at = iso_now()
            payload[str(settings.username or "").strip()] = settings.to_dict()
            self._write_payload_cached(self.user_settings_path, payload)
        return self.serialize_user_settings(settings)

    def list_known_usernames(self) -> list[str]:
        usernames: set[str] = set()
        with self.lock:
            payload = self._read_payload_cached(self.user_settings_path, dict)
            if isinstance(payload, dict):
                usernames.update(str(key or "").strip() for key in payload.keys() if str(key or "").strip())
            for path in self.threads_dir.glob("*.bson"):
                try:
                    thread = self._load_thread_cached(path, clone=False)
                except Exception:
                    continue
                if thread is None:
                    continue
                username = str(thread.owner_username or "").strip()
                if username:
                    usernames.add(username)
        return sorted(usernames)

    def load_schedule_state(self, username: str, agent_id: str) -> VerseProactiveScheduleState:
        normalized_username = str(username or "").strip()
        normalized_agent = str(agent_id or "").strip()
        with self.lock:
            payload = self._read_payload_cached(self.proactive_schedule_path, dict)
        entry = (((payload or {}) if isinstance(payload, dict) else {}).get(normalized_username) or {}).get(normalized_agent) if normalized_username and normalized_agent else {}
        if not isinstance(entry, dict):
            entry = {}
        return VerseProactiveScheduleState(
            username=normalized_username,
            agent_id=normalized_agent,
            last_evaluated_at=str(entry.get("last_evaluated_at") or entry.get("lastEvaluatedAt") or ""),
            next_scheduled_at=str(entry.get("next_scheduled_at") or entry.get("nextScheduledAt") or ""),
            updated_at=str(entry.get("updated_at") or entry.get("updatedAt") or iso_now()),
        )

    def save_schedule_state(self, state: VerseProactiveScheduleState) -> dict:
        with self.lock:
            payload = self._read_payload_cached(self.proactive_schedule_path, dict)
            if not isinstance(payload, dict):
                payload = {}
            state.updated_at = iso_now()
            user_bucket = payload.setdefault(str(state.username or "").strip(), {})
            if not isinstance(user_bucket, dict):
                user_bucket = {}
                payload[str(state.username or "").strip()] = user_bucket
            user_bucket[str(state.agent_id or "").strip()] = state.to_dict()
            self._write_payload_cached(self.proactive_schedule_path, payload)
        return self.serialize_schedule_state(state)

    def list_schedule_states(self, username: str) -> list[dict]:
        normalized_username = str(username or "").strip()
        with self.lock:
            payload = self._read_payload_cached(self.proactive_schedule_path, dict)
        bucket = payload.get(normalized_username) if isinstance(payload, dict) else {}
        rows: list[dict] = []
        for agent_id, entry in dict(bucket or {}).items():
            if not isinstance(entry, dict) or not str(agent_id or "").strip():
                continue
            rows.append(self.serialize_schedule_state({"agent_id": agent_id, **entry}))
        return sorted(rows, key=lambda item: str(item.get("agentId") or ""))

    def list_notifications(self, username: str) -> list[dict]:
        normalized_username = str(username or "").strip()
        with self.lock:
            payload = self._read_payload_cached(self.proactive_notifications_path, list)
        rows = []
        for item in payload if isinstance(payload, list) else []:
            if not isinstance(item, dict):
                continue
            if str(item.get("username") or "").strip() != normalized_username:
                continue
            rows.append(self.serialize_notification(item))
        return sorted(rows, key=lambda item: item.get("updatedAt") or item.get("createdAt") or "", reverse=True)

    def save_notification(self, notification: VerseNotificationRecord | dict) -> dict:
        item = notification.to_dict() if isinstance(notification, VerseNotificationRecord) else dict(notification or {})
        normalized_id = str(item.get("notification_id") or item.get("notificationId") or uuid.uuid4().hex)
        with self.lock:
            payload = self._read_payload_cached(self.proactive_notifications_path, list)
            if not isinstance(payload, list):
                payload = []
            normalized = {
                "notification_id": normalized_id,
                "username": str(item.get("username") or "").strip(),
                "thread_id": str(item.get("thread_id") or item.get("threadId") or "").strip(),
                "agent_id": str(item.get("agent_id") or item.get("agentId") or "").strip(),
                "issue_key": normalize_issue_key(item.get("issue_key") or item.get("issueKey"), item.get("title")),
                "title": str(item.get("title") or "").strip(),
                "body": str(item.get("body") or "").strip(),
                "status": normalize_notification_state(item.get("status") or "new"),
                "unread": normalize_bool(item.get("unread"), True),
                "ignored": normalize_bool(item.get("ignored"), False),
                "created_at": str(item.get("created_at") or item.get("createdAt") or iso_now()),
                "updated_at": iso_now(),
                "last_notified_at": str(item.get("last_notified_at") or item.get("lastNotifiedAt") or iso_now()),
                "metadata": dict(item.get("metadata") or {}),
            }
            replaced = False
            for index, existing in enumerate(payload):
                if isinstance(existing, dict) and str(existing.get("notification_id") or existing.get("notificationId") or "").strip() == normalized_id:
                    payload[index] = normalized
                    replaced = True
                    break
            if not replaced:
                payload.append(normalized)
            self._write_payload_cached(self.proactive_notifications_path, payload)
        return self.serialize_notification(normalized)

    def mark_notification_read(self, username: str, notification_id: str = "", thread_id: str = "") -> list[dict]:
        normalized_username = str(username or "").strip()
        target_notification = str(notification_id or "").strip()
        target_thread = str(thread_id or "").strip()
        touched: list[dict] = []
        with self.lock:
            payload = self._read_payload_cached(self.proactive_notifications_path, list)
            if not isinstance(payload, list):
                payload = []
            changed = False
            for item in payload:
                if not isinstance(item, dict):
                    continue
                if str(item.get("username") or "").strip() != normalized_username:
                    continue
                if target_notification and str(item.get("notification_id") or item.get("notificationId") or "").strip() != target_notification:
                    continue
                if target_thread and str(item.get("thread_id") or item.get("threadId") or "").strip() != target_thread:
                    continue
                if item.get("unread"):
                    item["unread"] = False
                    item["updated_at"] = iso_now()
                    changed = True
                touched.append(self.serialize_notification(item))
            if changed:
                self._write_payload_cached(self.proactive_notifications_path, payload)
        return touched

    def find_issue_record(self, username: str, agent_id: str, issue_key: str) -> dict | None:
        normalized_username = str(username or "").strip()
        normalized_agent = str(agent_id or "").strip()
        normalized_key = normalize_issue_key(issue_key)
        with self.lock:
            payload = self._read_payload_cached(self.proactive_issue_memory_path, list)
        for item in payload if isinstance(payload, list) else []:
            if not isinstance(item, dict):
                continue
            if str(item.get("username") or "").strip() != normalized_username:
                continue
            if str(item.get("agent_id") or item.get("agentId") or "").strip() != normalized_agent:
                continue
            if normalize_issue_key(item.get("issue_key") or item.get("issueKey")) != normalized_key:
                continue
            return self.serialize_issue_record(item)
        return None

    def find_issue_record_by_thread(self, username: str, thread_id: str) -> dict | None:
        normalized_username = str(username or "").strip()
        normalized_thread_id = str(thread_id or "").strip()
        if not normalized_username or not normalized_thread_id:
            return None
        with self.lock:
            payload = self._read_payload_cached(self.proactive_issue_memory_path, list)
        for item in payload if isinstance(payload, list) else []:
            if not isinstance(item, dict):
                continue
            if str(item.get("username") or "").strip() != normalized_username:
                continue
            if str(item.get("thread_id") or item.get("threadId") or "").strip() != normalized_thread_id:
                continue
            return self.serialize_issue_record(item)
        return None

    def list_issue_records(self, username: str, agent_id: str = "") -> list[dict]:
        normalized_username = str(username or "").strip()
        normalized_agent = str(agent_id or "").strip()
        with self.lock:
            payload = self._read_payload_cached(self.proactive_issue_memory_path, list)
        rows: list[dict] = []
        for item in payload if isinstance(payload, list) else []:
            if not isinstance(item, dict):
                continue
            if str(item.get("username") or "").strip() != normalized_username:
                continue
            if normalized_agent and str(item.get("agent_id") or item.get("agentId") or "").strip() != normalized_agent:
                continue
            rows.append(self.serialize_issue_record(item))
        return sorted(rows, key=lambda item: item.get("updatedAt") or item.get("createdAt") or "", reverse=True)

    def save_issue_record(self, record: VerseProactiveIssueRecord | dict) -> dict:
        item = record.to_dict() if isinstance(record, VerseProactiveIssueRecord) else dict(record or {})
        normalized_id = str(item.get("issue_id") or item.get("issueId") or uuid.uuid4().hex)
        with self.lock:
            payload = self._read_payload_cached(self.proactive_issue_memory_path, list)
            if not isinstance(payload, list):
                payload = []
            normalized = {
                "issue_id": normalized_id,
                "username": str(item.get("username") or "").strip(),
                "agent_id": str(item.get("agent_id") or item.get("agentId") or "").strip(),
                "issue_key": normalize_issue_key(item.get("issue_key") or item.get("issueKey"), item.get("title")),
                "title": str(item.get("title") or "").strip(),
                "thread_id": str(item.get("thread_id") or item.get("threadId") or "").strip(),
                "ignored": normalize_bool(item.get("ignored"), False),
                "status": str(item.get("status") or "active").strip() or "active",
                "last_evaluated_at": str(item.get("last_evaluated_at") or item.get("lastEvaluatedAt") or ""),
                "last_notified_at": str(item.get("last_notified_at") or item.get("lastNotifiedAt") or ""),
                "user_replied_at": str(item.get("user_replied_at") or item.get("userRepliedAt") or ""),
                "created_at": str(item.get("created_at") or item.get("createdAt") or iso_now()),
                "updated_at": iso_now(),
                "metadata": dict(item.get("metadata") or {}),
            }
            replaced = False
            for index, existing in enumerate(payload):
                if isinstance(existing, dict) and str(existing.get("issue_id") or existing.get("issueId") or "").strip() == normalized_id:
                    payload[index] = normalized
                    replaced = True
                    break
            if not replaced:
                payload.append(normalized)
            self._write_payload_cached(self.proactive_issue_memory_path, payload)
        return self.serialize_issue_record(normalized)

    def mark_issue_ignored(self, username: str, issue_key: str, *, agent_id: str = "", thread_id: str = "") -> dict | None:
        normalized_username = str(username or "").strip()
        normalized_key = normalize_issue_key(issue_key)
        normalized_agent = str(agent_id or "").strip()
        normalized_thread_id = str(thread_id or "").strip()
        with self.lock:
            payload = self._read_payload_cached(self.proactive_issue_memory_path, list)
            if not isinstance(payload, list):
                payload = []
            updated = None
            for item in payload:
                if not isinstance(item, dict):
                    continue
                if str(item.get("username") or "").strip() != normalized_username:
                    continue
                if normalized_agent and str(item.get("agent_id") or item.get("agentId") or "").strip() != normalized_agent:
                    continue
                if normalized_thread_id and str(item.get("thread_id") or item.get("threadId") or "").strip() != normalized_thread_id:
                    continue
                if normalize_issue_key(item.get("issue_key") or item.get("issueKey")) != normalized_key:
                    continue
                item["ignored"] = True
                item["status"] = "ignored"
                item["updated_at"] = iso_now()
                updated = self.serialize_issue_record(item)
            if updated is not None:
                self._write_payload_cached(self.proactive_issue_memory_path, payload)
        return updated

    def mark_issue_user_replied(
        self,
        username: str,
        *,
        issue_key: str = "",
        agent_id: str = "",
        thread_id: str = "",
        reply_preview: str = "",
        explicit_follow_up_requested: bool = False,
    ) -> dict | None:
        normalized_username = str(username or "").strip()
        normalized_key = normalize_issue_key(issue_key)
        normalized_agent = str(agent_id or "").strip()
        normalized_thread_id = str(thread_id or "").strip()
        updated = None
        with self.lock:
            payload = self._read_payload_cached(self.proactive_issue_memory_path, list)
            if not isinstance(payload, list):
                payload = []
            for item in payload:
                if not isinstance(item, dict):
                    continue
                if str(item.get("username") or "").strip() != normalized_username:
                    continue
                if normalized_agent and str(item.get("agent_id") or item.get("agentId") or "").strip() != normalized_agent:
                    continue
                if normalized_thread_id and str(item.get("thread_id") or item.get("threadId") or "").strip() != normalized_thread_id:
                    continue
                if normalized_key and normalize_issue_key(item.get("issue_key") or item.get("issueKey")) != normalized_key:
                    continue
                metadata = dict(item.get("metadata") or {})
                if reply_preview:
                    metadata["lastUserReplyPreview"] = str(reply_preview or "").strip()
                if explicit_follow_up_requested:
                    metadata["explicitFollowUpRequested"] = True
                item["metadata"] = metadata
                item["user_replied_at"] = iso_now()
                item["updated_at"] = iso_now()
                if str(item.get("status") or "").strip().lower() != "ignored":
                    item["status"] = "acknowledged"
                updated = self.serialize_issue_record(item)
            if updated is not None:
                self._write_payload_cached(self.proactive_issue_memory_path, payload)
        return updated

    def mark_notifications_ignored(
        self,
        username: str,
        *,
        issue_key: str = "",
        agent_id: str = "",
        thread_id: str = "",
    ) -> list[dict]:
        normalized_username = str(username or "").strip()
        normalized_key = normalize_issue_key(issue_key)
        normalized_agent = str(agent_id or "").strip()
        normalized_thread_id = str(thread_id or "").strip()
        touched: list[dict] = []
        with self.lock:
            payload = self._read_payload_cached(self.proactive_notifications_path, list)
            if not isinstance(payload, list):
                payload = []
            changed = False
            for item in payload:
                if not isinstance(item, dict):
                    continue
                if str(item.get("username") or "").strip() != normalized_username:
                    continue
                if normalized_agent and str(item.get("agent_id") or item.get("agentId") or "").strip() != normalized_agent:
                    continue
                if normalized_thread_id and str(item.get("thread_id") or item.get("threadId") or "").strip() != normalized_thread_id:
                    continue
                if normalized_key and normalize_issue_key(item.get("issue_key") or item.get("issueKey")) != normalized_key:
                    continue
                item["ignored"] = True
                item["unread"] = False
                item["status"] = "ignored"
                item["updated_at"] = iso_now()
                touched.append(self.serialize_notification(item))
                changed = True
            if changed:
                self._write_payload_cached(self.proactive_notifications_path, payload)
        return touched

    def load_agent_profiles(self) -> dict[str, AgentDisplayProfile]:
        with self.lock:
            payload = self._read_payload_cached(self.agent_profiles_path, dict)
        if not isinstance(payload, dict):
            return {}
        profiles: dict[str, AgentDisplayProfile] = {}
        for agent_id, raw in payload.items():
            if not isinstance(raw, dict):
                continue
            profiles[str(agent_id)] = AgentDisplayProfile(
                agent_id=str(agent_id),
                display_name=str(raw.get("display_name") or raw.get("displayName") or "").strip(),
                renamed_by=str(raw.get("renamed_by") or raw.get("renamedBy") or "").strip(),
                updated_at=str(raw.get("updated_at") or raw.get("updatedAt") or iso_now()),
            )
        return profiles

    def save_agent_profile(self, profile: AgentDisplayProfile) -> AgentDisplayProfile:
        with self.lock:
            payload = self._read_payload_cached(self.agent_profiles_path, dict)
            if not isinstance(payload, dict):
                payload = {}
            payload[profile.agent_id] = profile.to_dict()
            self._write_payload_cached(self.agent_profiles_path, payload)
        return profile

    def list_learning_records(self) -> list[dict]:
        with self.lock:
            payload = self._read_payload_cached(self.learning_records_path, list)
        if not isinstance(payload, list):
            return []
        records: list[dict] = []
        for raw in payload:
            if not isinstance(raw, dict):
                continue
            records.append(self._serialize_learning_record(raw))
        return sorted(records, key=lambda item: item.get("createdAt") or "", reverse=True)

    def save_learning_record(self, record: VerseLearningRecord | dict) -> dict:
        raw_record = record.to_dict() if isinstance(record, VerseLearningRecord) else dict(record or {})
        issue = str(raw_record.get("issue") or "").strip()
        resolution = str(raw_record.get("resolution") or "").strip()
        category = str(raw_record.get("category") or "").strip()
        if not issue or not resolution or not category:
            raise ValueError("Learning record category, issue, and resolution are required")
        with self.lock:
            payload = self._read_payload_cached(self.learning_records_path, list)
            if not isinstance(payload, list):
                payload = []
            normalized = {
                "record_id": str(raw_record.get("record_id") or raw_record.get("recordId") or uuid.uuid4().hex),
                "category": category,
                "source": str(raw_record.get("source") or "").strip(),
                "issue": issue,
                "resolution": resolution,
                "page_kind": str(raw_record.get("page_kind") or raw_record.get("pageKind") or "").strip(),
                "artifact_kind": str(raw_record.get("artifact_kind") or raw_record.get("artifactKind") or "").strip(),
                "agent_id": str(raw_record.get("agent_id") or raw_record.get("agentId") or "").strip(),
                "thread_id": str(raw_record.get("thread_id") or raw_record.get("threadId") or "").strip(),
                "username": str(raw_record.get("username") or "").strip(),
                "trigger_pattern": str(raw_record.get("trigger_pattern") or raw_record.get("triggerPattern") or "").strip(),
                "wrong_behavior": str(raw_record.get("wrong_behavior") or raw_record.get("wrongBehavior") or "").strip(),
                "correct_behavior": str(raw_record.get("correct_behavior") or raw_record.get("correctBehavior") or "").strip(),
                "enforcement_rule": str(raw_record.get("enforcement_rule") or raw_record.get("enforcementRule") or "").strip(),
                "tags": [str(item).strip() for item in list(raw_record.get("tags") or []) if str(item).strip()],
                "created_at": str(raw_record.get("created_at") or raw_record.get("createdAt") or iso_now()),
            }
            dedupe_key = (
                normalized["category"].lower(),
                normalized["issue"].lower(),
                normalized["resolution"].lower(),
                normalized["artifact_kind"].lower(),
                normalized["page_kind"].lower(),
            )
            for existing in payload:
                if not isinstance(existing, dict):
                    continue
                existing_key = (
                    str(existing.get("category") or "").strip().lower(),
                    str(existing.get("issue") or "").strip().lower(),
                    str(existing.get("resolution") or "").strip().lower(),
                    str(existing.get("artifact_kind") or existing.get("artifactKind") or "").strip().lower(),
                    str(existing.get("page_kind") or existing.get("pageKind") or "").strip().lower(),
                )
                if existing_key == dedupe_key:
                    existing["tags"] = sorted(
                        {
                            *[str(item).strip() for item in list(existing.get("tags") or []) if str(item).strip()],
                            *normalized["tags"],
                        }
                    )
                    if normalized["thread_id"]:
                        existing["thread_id"] = normalized["thread_id"]
                    if normalized["agent_id"]:
                        existing["agent_id"] = normalized["agent_id"]
                    if normalized["username"]:
                        existing["username"] = normalized["username"]
                    if normalized["source"]:
                        existing["source"] = normalized["source"]
                    for key in ("trigger_pattern", "wrong_behavior", "correct_behavior", "enforcement_rule"):
                        if normalized[key]:
                            existing[key] = normalized[key]
                    existing["created_at"] = iso_now()
                    self._write_payload_cached(self.learning_records_path, payload)
                    return self._serialize_learning_record(existing)
            payload.append(normalized)
            self._write_payload_cached(self.learning_records_path, payload)
        return self._serialize_learning_record(normalized)

    def serialize_thread(self, thread: VerseThreadState, include_messages: bool = True) -> dict:
        metadata = dict(thread.metadata or {})
        thread_origin = normalize_thread_origin(metadata.get("threadOrigin") or metadata.get("thread_origin"))
        proactive_agent_id = str(metadata.get("proactiveAgentId") or metadata.get("proactive_agent_id") or "").strip()
        issue_key = normalize_issue_key(metadata.get("issueKey") or metadata.get("issue_key"))
        notification_state = normalize_notification_state(
            metadata.get("notificationState") or metadata.get("notification_state"),
            default="read" if thread_origin == "user" else "new",
        )
        last_notified_at = str(metadata.get("lastNotifiedAt") or metadata.get("last_notified_at") or "").strip()
        data = {
            "id": thread.thread_id,
            "threadId": thread.thread_id,
            "ownerUsername": thread.owner_username,
            "title": thread.title,
            "createdAt": thread.created_at,
            "updatedAt": thread.updated_at,
            "providerName": thread.provider_name,
            "providerModel": thread.provider_model,
            "activeAgentId": thread.active_agent_id,
            "participants": list(thread.participants),
            "invitedAgents": list(thread.invited_agents),
            "summary": thread.summary,
            "summaryUpdatedAt": thread.summary_updated_at,
            "synthesis": self._serialize_synthesis(thread.synthesis),
            "handoffs": [self._serialize_handoff(item) for item in thread.handoffs],
            "mindShareWrites": [self._serialize_mind_share_write(item) for item in thread.mind_share_writes],
            "collaborationLevel": normalize_collaboration_level(thread.collaboration_level),
            "threadScope": str(thread.thread_scope or "portal").strip() or "portal",
            "contextKey": str(thread.context_key or "").strip(),
            "sourcePathname": str(thread.source_pathname or "").strip(),
            "requestMode": str(thread.request_mode or "").strip(),
            "routingEvidence": list(thread.routing_evidence or []),
            "metadata": metadata,
            "threadOrigin": thread_origin,
            "proactiveAgentId": proactive_agent_id,
            "issueKey": issue_key,
            "notificationState": notification_state,
            "lastNotifiedAt": last_notified_at,
        }
        if include_messages:
            data["messages"] = [self._serialize_message(item) for item in thread.messages]
        else:
            data["messageCount"] = len(thread.messages)
            data["lastMessageAt"] = str((thread.messages[-1] or {}).get("created_at") or "") if thread.messages else ""
        return data

    def serialize_user_settings(self, settings: VerseUserSettings | dict) -> dict:
        item = settings.to_dict() if isinstance(settings, VerseUserSettings) else dict(settings or {})
        raw_agent_settings = dict(item.get("agent_settings") or item.get("agentSettings") or item.get("agents") or {})
        serialized_agents = {
            str(agent_id or "").strip(): {
                "proactivityEnabled": normalize_agent_proactivity_settings(raw_settings)["proactivity_enabled"],
                "proactivityLevel": normalize_agent_proactivity_settings(raw_settings)["proactivity_level"],
            }
            for agent_id, raw_settings in raw_agent_settings.items()
            if str(agent_id or "").strip()
        }
        return {
            "username": str(item.get("username") or "").strip(),
            "collaborationLevel": normalize_collaboration_level(item.get("collaboration_level") or item.get("collaborationLevel")),
            "proactiveModeEnabled": normalize_bool(item.get("proactive_mode_enabled") if "proactive_mode_enabled" in item else item.get("proactiveModeEnabled")),
            "agentSettings": serialized_agents,
            "agents": serialized_agents,
            "updatedAt": str(item.get("updated_at") or item.get("updatedAt") or ""),
        }

    def serialize_schedule_state(self, state: VerseProactiveScheduleState | dict) -> dict:
        item = state.to_dict() if isinstance(state, VerseProactiveScheduleState) else dict(state or {})
        return {
            "username": str(item.get("username") or "").strip(),
            "agentId": str(item.get("agent_id") or item.get("agentId") or "").strip(),
            "lastEvaluatedAt": str(item.get("last_evaluated_at") or item.get("lastEvaluatedAt") or ""),
            "nextScheduledAt": str(item.get("next_scheduled_at") or item.get("nextScheduledAt") or ""),
            "updatedAt": str(item.get("updated_at") or item.get("updatedAt") or ""),
        }

    def serialize_notification(self, notification: VerseNotificationRecord | dict) -> dict:
        item = notification.to_dict() if isinstance(notification, VerseNotificationRecord) else dict(notification or {})
        return {
            "id": str(item.get("notification_id") or item.get("notificationId") or ""),
            "notificationId": str(item.get("notification_id") or item.get("notificationId") or ""),
            "username": str(item.get("username") or "").strip(),
            "threadId": str(item.get("thread_id") or item.get("threadId") or "").strip(),
            "agentId": str(item.get("agent_id") or item.get("agentId") or "").strip(),
            "issueKey": normalize_issue_key(item.get("issue_key") or item.get("issueKey")),
            "title": str(item.get("title") or "").strip(),
            "body": str(item.get("body") or "").strip(),
            "status": normalize_notification_state(item.get("status") or "new"),
            "unread": normalize_bool(item.get("unread"), True),
            "ignored": normalize_bool(item.get("ignored"), False),
            "createdAt": str(item.get("created_at") or item.get("createdAt") or ""),
            "updatedAt": str(item.get("updated_at") or item.get("updatedAt") or ""),
            "lastNotifiedAt": str(item.get("last_notified_at") or item.get("lastNotifiedAt") or ""),
            "metadata": dict(item.get("metadata") or {}),
        }

    def serialize_issue_record(self, record: VerseProactiveIssueRecord | dict) -> dict:
        item = record.to_dict() if isinstance(record, VerseProactiveIssueRecord) else dict(record or {})
        return {
            "id": str(item.get("issue_id") or item.get("issueId") or ""),
            "issueId": str(item.get("issue_id") or item.get("issueId") or ""),
            "username": str(item.get("username") or "").strip(),
            "agentId": str(item.get("agent_id") or item.get("agentId") or "").strip(),
            "issueKey": normalize_issue_key(item.get("issue_key") or item.get("issueKey")),
            "title": str(item.get("title") or "").strip(),
            "threadId": str(item.get("thread_id") or item.get("threadId") or "").strip(),
            "ignored": normalize_bool(item.get("ignored"), False),
            "status": str(item.get("status") or "active").strip() or "active",
            "lastEvaluatedAt": str(item.get("last_evaluated_at") or item.get("lastEvaluatedAt") or ""),
            "lastNotifiedAt": str(item.get("last_notified_at") or item.get("lastNotifiedAt") or ""),
            "userRepliedAt": str(item.get("user_replied_at") or item.get("userRepliedAt") or ""),
            "createdAt": str(item.get("created_at") or item.get("createdAt") or ""),
            "updatedAt": str(item.get("updated_at") or item.get("updatedAt") or ""),
            "metadata": dict(item.get("metadata") or {}),
        }

    def _serialize_message(self, raw: dict) -> dict:
        item = dict(raw or {})
        metadata = dict(item.get("metadata") or {})
        return {
            "id": str(item.get("message_id") or item.get("messageId") or ""),
            "role": str(item.get("role") or ""),
            "content": str(item.get("content") or ""),
            "createdAt": str(item.get("created_at") or item.get("createdAt") or ""),
            "userDisplayName": str(
                item.get("user_display_name")
                or item.get("userDisplayName")
                or metadata.get("userDisplayName")
                or metadata.get("user_display_name")
                or ""
            ),
            "agentId": str(item.get("agent_id") or item.get("agentId") or ""),
            "agentName": str(item.get("agent_name") or item.get("agentName") or ""),
            "agentTitle": str(item.get("agent_title") or item.get("agentTitle") or ""),
            "agentDisplayName": str(item.get("agent_display_name") or item.get("agentDisplayName") or ""),
            "styleToken": str(item.get("style_token") or item.get("styleToken") or "slate"),
            "contentType": str(item.get("content_type") or item.get("contentType") or "message"),
            "confidence": str(item.get("confidence") or ""),
            "retrievalTrace": list(item.get("retrieval_trace") or item.get("retrievalTrace") or []),
            "artifact": item.get("artifact") if isinstance(item.get("artifact"), dict) else None,
            "primaryCard": item.get("primary_card") if isinstance(item.get("primary_card"), dict) else (item.get("primaryCard") if isinstance(item.get("primaryCard"), dict) else None),
            "supportingBlocks": list(item.get("supporting_blocks") or item.get("supportingBlocks") or []),
            "contributors": list(item.get("contributors") or []),
            "visualization": item.get("visualization") if isinstance(item.get("visualization"), dict) else None,
            "usage": dict(item.get("usage") or {}) if isinstance(item.get("usage"), dict) else None,
            "inspectDetails": dict(item.get("inspect_details") or item.get("inspectDetails") or {}),
            "metadata": metadata,
            "threadOrigin": normalize_thread_origin(metadata.get("threadOrigin") or metadata.get("thread_origin")),
            "proactiveAgentId": str(metadata.get("proactiveAgentId") or metadata.get("proactive_agent_id") or "").strip(),
            "issueKey": normalize_issue_key(metadata.get("issueKey") or metadata.get("issue_key")),
            "notificationState": normalize_notification_state(
                metadata.get("notificationState") or metadata.get("notification_state"),
                default="read",
            ),
        }

    def _serialize_handoff(self, raw: dict) -> dict:
        item = dict(raw or {})
        return {
            "sourceAgentId": str(item.get("source_agent_id") or item.get("sourceAgentId") or ""),
            "targetAgentId": str(item.get("target_agent_id") or item.get("targetAgentId") or ""),
            "reason": str(item.get("reason") or ""),
            "initiatedBy": str(item.get("initiated_by") or item.get("initiatedBy") or ""),
            "status": str(item.get("status") or ""),
            "whyInvited": str(item.get("why_invited") or item.get("whyInvited") or ""),
            "reviewFocus": str(item.get("review_focus") or item.get("reviewFocus") or ""),
            "expectedDecision": str(item.get("expected_decision") or item.get("expectedDecision") or ""),
            "createdAt": str(item.get("created_at") or item.get("createdAt") or ""),
        }

    def _serialize_mind_share_write(self, raw: dict) -> dict:
        item = dict(raw or {})
        return {
            "file": str(item.get("file_name") or item.get("file") or ""),
            "agentId": str(item.get("agent_id") or item.get("agentId") or ""),
            "agentName": str(item.get("agent_name") or item.get("agentName") or ""),
            "agentTitle": str(item.get("agent_title") or item.get("agentTitle") or ""),
            "agentDisplayName": str(item.get("agent_display_name") or item.get("agentDisplayName") or ""),
            "threadId": str(item.get("thread_id") or item.get("threadId") or ""),
            "confidence": str(item.get("confidence") or ""),
            "basis": str(item.get("basis") or ""),
            "contentType": str(item.get("content_type") or item.get("contentType") or ""),
            "content": str(item.get("content") or ""),
            "timestamp": str(item.get("timestamp") or ""),
            "preview": str(item.get("preview") or ""),
            "applied": bool(item.get("applied")),
        }

    def _serialize_synthesis(self, raw: dict | None) -> dict | None:
        if not isinstance(raw, dict):
            return None
        item = dict(raw)
        return {
            "agentId": str(item.get("agent_id") or item.get("agentId") or ""),
            "agentDisplayName": str(item.get("agent_display_name") or item.get("agentDisplayName") or ""),
            "content": str(item.get("content") or ""),
            "createdAt": str(item.get("created_at") or item.get("createdAt") or ""),
        }

    def _serialize_learning_record(self, raw: dict) -> dict:
        item = dict(raw or {})
        return {
            "id": str(item.get("record_id") or item.get("recordId") or ""),
            "recordId": str(item.get("record_id") or item.get("recordId") or ""),
            "category": str(item.get("category") or ""),
            "source": str(item.get("source") or ""),
            "issue": str(item.get("issue") or ""),
            "resolution": str(item.get("resolution") or ""),
            "pageKind": str(item.get("page_kind") or item.get("pageKind") or ""),
            "artifactKind": str(item.get("artifact_kind") or item.get("artifactKind") or ""),
            "agentId": str(item.get("agent_id") or item.get("agentId") or ""),
            "threadId": str(item.get("thread_id") or item.get("threadId") or ""),
            "username": str(item.get("username") or ""),
            "triggerPattern": str(item.get("trigger_pattern") or item.get("triggerPattern") or ""),
            "wrongBehavior": str(item.get("wrong_behavior") or item.get("wrongBehavior") or ""),
            "correctBehavior": str(item.get("correct_behavior") or item.get("correctBehavior") or ""),
            "enforcementRule": str(item.get("enforcement_rule") or item.get("enforcementRule") or ""),
            "tags": [str(value).strip() for value in list(item.get("tags") or []) if str(value).strip()],
            "createdAt": str(item.get("created_at") or item.get("createdAt") or ""),
        }

    def serialize_dataset(self, raw: dict, include_rows: bool = False) -> dict:
        item = dict(raw or {})
        source = dict(item.get("source") or {})
        data = {
            "id": str(item.get("dataset_id") or item.get("id") or ""),
            "datasetId": str(item.get("dataset_id") or item.get("id") or ""),
            "ownerUsername": str(item.get("owner_username") or item.get("ownerUsername") or ""),
            "title": str(item.get("title") or "Dataset"),
            "createdAt": str(item.get("created_at") or item.get("createdAt") or ""),
            "updatedAt": str(item.get("updated_at") or item.get("updatedAt") or ""),
            "rowCount": int(item.get("row_count") or len(item.get("rows") or [])),
            "columnCount": int(item.get("column_count") or len(item.get("columns") or [])),
            "columns": list(item.get("columns") or []),
            "summary": dict(item.get("summary") or {}),
            "notes": str(item.get("notes") or ""),
            "source": {
                "sourceType": str(source.get("source_type") or source.get("sourceType") or ""),
                "format": str(source.get("format") or ""),
                "filename": str(source.get("filename") or ""),
                "archivedName": str(source.get("archived_name") or source.get("archivedName") or ""),
                "archivedPath": str(source.get("archived_path") or source.get("archivedPath") or ""),
                "pageKind": str(source.get("page_kind") or source.get("pageKind") or ""),
                "createdAt": str(source.get("created_at") or source.get("createdAt") or ""),
            },
        }
        if include_rows:
            data["rows"] = list(item.get("rows") or [])
        else:
            data["previewRows"] = list(item.get("rows") or [])[:12]
        return data
