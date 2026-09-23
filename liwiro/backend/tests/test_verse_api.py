# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import shutil
import sys
import tempfile
import time
import unittest
import io
from pathlib import Path
from unittest.mock import MagicMock, patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import _PROACTIVE_THREAD_LOCK, _persist_ai_env_values, _runtime_cfg, _run_with_proactive_leader_lock, _stop_verse_background_workers, _verse_proactive_scheduler_interval_seconds, create_app
from app.verse.providers.base import AIResponse
from app.verse.service import VerseService
from app.verse.store import VerseStore
from app.verse.models import VerseUserSettings


class _ApiProvider:
    def __init__(self):
        self.responses = [
            {
                "message": "Kalulu reviewed the API contract.",
                "summary": "Architecture review is underway.",
                "confidence": "High",
                "content_type": "analysis",
            }
        ]

    def generate(self, request):
        import json

        payload = dict(self.responses.pop(0) if self.responses else {
            "message": "Nzou synthesized the thread.",
            "summary": "Synthesis complete.",
            "confidence": "High",
            "content_type": "synthesis",
        })
        usage = payload.pop("_usage", {"input_tokens": 12, "output_tokens": 8})
        return AIResponse(
            text=json.dumps(payload),
            model="fake-model",
            provider="fake",
            usage=usage if isinstance(usage, dict) else {},
        )

    def healthcheck(self, request=None):
        return AIResponse(text='{"probe":"ok"}', model="fake-model", provider="fake")


class VerseApiTests(unittest.TestCase):
    def test_proactive_scheduler_interval_handles_malformed_and_unsafe_config(self):
        app = create_app()
        self.addCleanup(_stop_verse_background_workers, app)
        app.config["VERSE_PROACTIVE_SCHEDULER_INTERVAL_SECONDS"] = "not-a-number"
        self.assertEqual(_verse_proactive_scheduler_interval_seconds(app), 60)
        app.config["VERSE_PROACTIVE_SCHEDULER_INTERVAL_SECONDS"] = 1
        self.assertEqual(_verse_proactive_scheduler_interval_seconds(app), 10)
        app.config["VERSE_PROACTIVE_SCHEDULER_INTERVAL_SECONDS"] = 45
        self.assertEqual(_verse_proactive_scheduler_interval_seconds(app), 45)

    def test_proactive_leader_lock_does_not_swallow_evaluation_errors(self):
        app, _, _ = self._build_app()
        data_dir = tempfile.TemporaryDirectory()
        self.addCleanup(data_dir.cleanup)
        app.config["VERSE_DATA_DIR"] = data_dir.name
        with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
            _run_with_proactive_leader_lock(app, lambda: (_ for _ in ()).throw(RuntimeError("provider unavailable")))

    def test_proactive_leader_lock_uses_thread_fallback_without_fcntl(self):
        app, _, _ = self._build_app()
        calls = []
        with patch("app.main.fcntl", None):
            self.assertTrue(_run_with_proactive_leader_lock(app, lambda: calls.append("ran")))
            self.assertEqual(calls, ["ran"])
            _PROACTIVE_THREAD_LOCK.acquire()
            try:
                self.assertFalse(_run_with_proactive_leader_lock(app, lambda: calls.append("duplicate")))
            finally:
                _PROACTIVE_THREAD_LOCK.release()
        self.assertEqual(calls, ["ran"])

    def _build_app(self):
        with patch("app.main._initialize_vdb_runtime", return_value=(True, "ok")), \
             patch("app.main._reconcile_service_runtime_states", return_value=[]), \
             patch("app.main._autostart_services_if_enabled", return_value=None):
            app = create_app()
        app.testing = True
        app.vdb_client = MagicMock()
        app.vdb_client.async_authorize.return_value = True
        app.vdb_client.use_domain.return_value = True
        app.vdb_client.use_database.return_value = True
        app.process_manager = MagicMock()
        app.process_manager.stop_api_service.return_value = True
        app.process_manager.restart_service.return_value = (9123, 5501)

        verse_root_dir = tempfile.TemporaryDirectory()
        data_dir = tempfile.TemporaryDirectory()
        self.addCleanup(verse_root_dir.cleanup)
        self.addCleanup(data_dir.cleanup)
        self.addCleanup(_stop_verse_background_workers, app)
        shutil.copytree(REPO_ROOT / "verse", verse_root_dir.name, dirs_exist_ok=True)
        app.config["VERSE_ROOT"] = verse_root_dir.name
        app.config["VERSE_DATA_DIR"] = data_dir.name
        app.config["AI_PROVIDER"] = "google"
        app.config["GOOGLE_API_KEY"] = "test-key"
        app.config["GOOGLE_MODEL"] = "fake-model"
        app.config["ANTHROPIC_API_KEY"] = "anthropic-test-key"
        app.config["ANTHROPIC_MODEL"] = "claude-sonnet-4-6"
        app.config["OPENAI_API_KEY"] = "openai-test-key"
        app.config["OPENAI_MODEL"] = "gpt-5-mini"

        token = "user-token"
        app.auth_sessions[token] = {
            "username": "zulan",
            "role": "admin",
            "is_super_admin": False,
            "service_access": ["*"],
            "permissions_overrides": [],
            "liwiro_rbac": {},
            "permissions": ["VIEW_SERVICES", "MANAGE_SERVICES"],
        }
        super_token = "super-token"
        app.auth_sessions[super_token] = {
            "username": "root",
            "role": "admin",
            "is_super_admin": True,
            "service_access": ["*"],
            "permissions_overrides": [],
            "liwiro_rbac": {},
            "permissions": ["VIEW_SERVICES", "MANAGE_SERVICES"],
        }
        return app, token, super_token

    def _single_proactive_agent_settings(self, service: VerseService, enabled_agent_id: str, level: int = 2) -> dict[str, dict]:
        return {
            agent["id"]: {
                "proactivityEnabled": agent["id"] == enabled_agent_id,
                "proactivityLevel": level if agent["id"] == enabled_agent_id else 1,
            }
            for agent in service.list_agents()
        }

    def test_ai_config_status_is_authenticated_and_never_returns_keys(self):
        app, token, _ = self._build_app()
        client = app.test_client()

        denied = client.get("/platform/ai/config")
        response = client.get("/platform/ai/config", headers={"Authorization": f"Bearer {token}"})
        me_response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

        self.assertEqual(denied.status_code, 401)
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertFalse(payload["canManage"])
        self.assertEqual({item["id"] for item in payload["providers"]}, {"openai", "google", "anthropic"})
        self.assertNotIn("API_KEY", response.get_data(as_text=True))
        self.assertNotIn("test-key", response.get_data(as_text=True))
        self.assertEqual(me_response.status_code, 200)
        self.assertIn("configured", me_response.get_json()["aiConfig"])
        self.assertNotIn("providers", me_response.get_json()["aiConfig"])

    def test_ai_config_updates_are_super_admin_only_and_refresh_runtime(self):
        app, token, super_token = self._build_app()
        client = app.test_client()
        request_payload = {
            "defaultProvider": "anthropic",
            "providers": {
                "anthropic": {"model": "claude-test", "apiKey": "replacement-secret"},
                "google": {"model": "gemini-test", "removeApiKey": True},
            },
        }

        denied = client.put("/platform/ai/config", headers={"Authorization": f"Bearer {token}"}, json=request_payload)
        with patch("app.main._persist_ai_env_values") as persist:
            response = client.put("/platform/ai/config", headers={"Authorization": f"Bearer {super_token}"}, json=request_payload)

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(response.status_code, 200)
        persist.assert_called_once_with({
            "AI_PROVIDER": "anthropic",
            "ANTHROPIC_MODEL": "claude-test",
            "ANTHROPIC_API_KEY": "replacement-secret",
            "GOOGLE_MODEL": "gemini-test",
            "GOOGLE_API_KEY": "",
        })
        self.assertEqual(app.config["AI_PROVIDER"], "anthropic")
        self.assertTrue(response.get_json()["configured"])
        self.assertNotIn("replacement-secret", response.get_data(as_text=True))

    def test_ai_config_connection_test_uses_saved_provider_without_exposing_key(self):
        app, _, super_token = self._build_app()
        client = app.test_client()
        provider = _ApiProvider()

        with patch("app.main.build_ai_provider", return_value=provider) as build_provider:
            response = client.post(
                "/platform/ai/config/test",
                headers={"Authorization": f"Bearer {super_token}"},
                json={"provider": "anthropic"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True, "provider": "anthropic", "model": "fake-model"})
        self.assertEqual(build_provider.call_args.kwargs["provider_name"], "anthropic")

    def test_ai_config_can_test_draft_without_saving_or_returning_credentials(self):
        app, _, token = self._build_app()
        original = app.config["OPENAI_API_KEY"]
        with patch("app.main._runtime_cfg", side_effect=lambda key: app.config.get(key)), \
             patch("app.main.build_ai_provider", return_value=_ApiProvider()) as build:
            response = app.test_client().post("/platform/ai/config/test", headers={"Authorization": f"Bearer {token}"},
                                             json={"provider": "openai", "apiKey": "draft-secret", "model": "draft-model"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(build.call_args.args[0]["OPENAI_API_KEY"], "draft-secret")
        self.assertEqual(build.call_args.args[0]["OPENAI_MODEL"], "draft-model")
        self.assertEqual(app.config["OPENAI_API_KEY"], original)
        self.assertNotIn("draft-secret", response.get_data(as_text=True))

    def test_ai_config_rejects_a_key_saved_under_the_wrong_provider(self):
        app, _, token = self._build_app()
        response = app.test_client().put(
            "/platform/ai/config",
            headers={"Authorization": f"Bearer {token}"},
            json={"providers": {"openai": {"apiKey": "sk-ant-api03-wrong-provider"}}},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Anthropic API key", response.get_json()["error"])

    def test_ai_config_persistence_is_atomic_and_owner_only(self):
        env_dir = tempfile.TemporaryDirectory()
        self.addCleanup(env_dir.cleanup)
        env_path = Path(env_dir.name) / ".env.local"
        env_path.write_text('OPENAI_API_KEY="old"\nUNCHANGED=value\n', encoding="utf-8")

        with patch("app.main._backend_env_local_path", return_value=env_path):
            _persist_ai_env_values({"OPENAI_API_KEY": "new-secret", "GOOGLE_API_KEY": ""})

        content = env_path.read_text(encoding="utf-8")
        self.assertIn('OPENAI_API_KEY="new-secret"', content)
        self.assertIn('GOOGLE_API_KEY=""', content)
        self.assertIn("UNCHANGED=value", content)
        self.assertEqual(env_path.stat().st_mode & 0o777, 0o600)

        lock_path = env_path.with_name(f"{env_path.name}.lock")
        self.assertTrue(lock_path.exists())
        self.assertEqual(lock_path.stat().st_mode & 0o777, 0o600)

    def test_ai_config_endpoint_survives_runtime_reload(self):
        env_dir = tempfile.TemporaryDirectory()
        self.addCleanup(env_dir.cleanup)
        env_path = Path(env_dir.name) / ".env.local"
        app, _, super_token = self._build_app()
        client = app.test_client()
        payload = {
            "defaultProvider": "google",
            "providers": {"google": {"model": "gemini-persisted", "apiKey": "persisted-secret"}},
        }
        with patch("app.main._backend_env_local_path", return_value=env_path):
            response = client.put("/platform/ai/config", headers={"Authorization": f"Bearer {super_token}"}, json=payload)
            self.assertEqual(response.status_code, 200)
            app.config["AI_PROVIDER"] = "openai"
            app.config["GOOGLE_MODEL"] = "stale-model"
            app.config["GOOGLE_API_KEY"] = ""
            app.ai_config_runtime_keys.clear()
            reloaded = client.get("/platform/ai/config", headers={"Authorization": f"Bearer {super_token}"})

        self.assertEqual(reloaded.status_code, 200)
        status = reloaded.get_json()
        self.assertEqual(status["defaultProvider"], "google")
        google = next(item for item in status["providers"] if item["id"] == "google")
        self.assertEqual(google["model"], "gemini-persisted")
        self.assertTrue(google["configured"])
        self.assertNotIn("persisted-secret", reloaded.get_data(as_text=True))

    def test_runtime_ai_config_rereads_external_persisted_updates(self):
        env_dir = tempfile.TemporaryDirectory()
        self.addCleanup(env_dir.cleanup)
        env_path = Path(env_dir.name) / ".env.local"
        env_path.write_text('OPENAI_MODEL="first-model"\n', encoding="utf-8")

        app, _, _ = self._build_app()
        with patch("app.main._backend_env_local_path", return_value=env_path):
            with app.app_context():
                app.config["OPENAI_MODEL"] = "stale-model"
                app.ai_config_runtime_keys.add("OPENAI_MODEL")
                self.assertEqual(_runtime_cfg("OPENAI_MODEL"), "first-model")
                env_path.write_text('OPENAI_MODEL="second-model"\n', encoding="utf-8")
                self.assertEqual(_runtime_cfg("OPENAI_MODEL"), "second-model")

    def test_agents_route_returns_loaded_agents(self):
        app, token, _ = self._build_app()
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=_ApiProvider(),
        )
        with patch("app.main._verse_service", return_value=service):
            client = app.test_client()
            res = client.get("/platform/verse/agents", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data["agents"]), 5)
        analyst = next(item for item in data["agents"] if item["id"] == "liwiro-analyst")
        self.assertIn("skills", analyst)
        self.assertTrue(any(skill["title"] == "Metrics Interpretation" for skill in analyst["skills"]))
        self.assertIn("allowedInputs", analyst)
        self.assertIn("preferredOutputs", analyst)
        self.assertIn("abilitySummary", analyst)
        self.assertIn("sampleQuestions", analyst)

    def test_health_route_returns_provider_options(self):
        app, token, _ = self._build_app()
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={
                "AI_PROVIDER": "google",
                "GOOGLE_API_KEY": "test-key",
                "GOOGLE_MODEL": "fake-model",
                "OPENAI_API_KEY": "openai-test-key",
                "OPENAI_MODEL": "gpt-5-mini",
            },
            provider=_ApiProvider(),
        )
        with patch("app.main._verse_service", return_value=service):
            client = app.test_client()
            res = client.get("/platform/verse/health", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        providers = payload["providers"]
        self.assertEqual({item["id"] for item in providers}, {"google", "openai", "anthropic"})
        self.assertEqual(payload["settings"]["collaborationLevel"], "very collaborative")
        self.assertIn("prerequisites", payload)

    def test_bootstrap_route_returns_me_settings_and_agents(self):
        app, token, _ = self._build_app()
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=_ApiProvider(),
        )
        with patch("app.main._verse_service", return_value=service):
            client = app.test_client()
            res = client.get("/platform/verse/bootstrap", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertEqual(payload["me"]["username"], "zulan")
        self.assertIn("settings", payload)
        self.assertIn("agents", payload)
        self.assertIn("prerequisites", payload)

    def test_loopback_probe_health_route_works_without_liwiro_session(self):
        app, _, _ = self._build_app()
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=_ApiProvider(),
        )
        with patch("app.main._verse_service", return_value=service):
            client = app.test_client()
            res = client.get("/platform/verse/health?probe=1", environ_base={"REMOTE_ADDR": "127.0.0.1"})
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertTrue(payload["configured"])
        self.assertTrue(payload["probe"]["ok"])

    def test_thread_create_and_message_routes_work(self):
        app, token, _ = self._build_app()
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=_ApiProvider(),
        )
        with patch("app.main._verse_service", return_value=service):
            client = app.test_client()
            create_res = client.post("/platform/verse/threads", headers={"Authorization": f"Bearer {token}"}, json={})
            self.assertEqual(create_res.status_code, 201)
            thread_id = create_res.get_json()["thread"]["id"]
            message_res = client.post(
                f"/platform/verse/threads/{thread_id}/messages",
                headers={"Authorization": f"Bearer {token}"},
                json={"content": "Review my REST API design"},
            )
        self.assertEqual(message_res.status_code, 200)
        thread = message_res.get_json()["thread"]
        self.assertEqual(thread["activeAgentId"], "liwiro-architect")
        self.assertEqual(len(thread["messages"]), 2)
        self.assertEqual(thread["messages"][1]["usage"]["totalTokens"], 20)
        self.assertEqual(thread["collaborationLevel"], "very collaborative")
        self.assertEqual(thread["messages"][1]["inspectDetails"]["promptMode"], "bounded")
        self.assertEqual(thread["messages"][1]["inspectDetails"]["bootstrapFiles"], [])

    def test_message_route_exposes_liwiro_reference_context_report(self):
        app, token, _ = self._build_app()
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=_ApiProvider(),
        )
        with patch("app.main._verse_service", return_value=service):
            client = app.test_client()
            create_res = client.post("/platform/verse/threads", headers={"Authorization": f"Bearer {token}"}, json={})
            self.assertEqual(create_res.status_code, 201)
            thread_id = create_res.get_json()["thread"]["id"]
            message_res = client.post(
                f"/platform/verse/threads/{thread_id}/messages",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "content": "Use platform actions preview to prepare a service-builder LAPIS draft with linkedModel and crudOperation",
                    "context": {"pageKind": "service-builder", "pathname": "/service-builder"},
                },
            )
        self.assertEqual(message_res.status_code, 200)
        thread = message_res.get_json()["thread"]
        message = thread["messages"][1]
        inspect_details = message["inspectDetails"]
        entries = inspect_details["contextReport"]["entries"]

        self.assertTrue(
            any(
                entry.get("category") == "reference"
                and str(entry.get("source") or "").endswith("liwiro/verse/liwiro-platform-reference/reference.json")
                for entry in entries
            )
        )
        self.assertTrue(
            any(
                str(trace.get("source") or "").endswith("liwiro/verse/liwiro-platform-reference/reference.json")
                for trace in message["retrievalTrace"]
            )
        )

    def test_thread_message_can_answer_agent_ability_question_without_provider_output(self):
        app, token, _ = self._build_app()
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=_ApiProvider(),
        )
        with patch("app.main._verse_service", return_value=service):
            client = app.test_client()
            create_res = client.post("/platform/verse/threads", headers={"Authorization": f"Bearer {token}"}, json={})
            thread_id = create_res.get_json()["thread"]["id"]
            message_res = client.post(
                f"/platform/verse/threads/{thread_id}/messages",
                headers={"Authorization": f"Bearer {token}"},
                json={"content": "@Ananse what can you do and what skills are you best at?"},
            )
        self.assertEqual(message_res.status_code, 200)
        payload = message_res.get_json()["thread"]["messages"][-1]
        self.assertEqual(payload["agentDisplayName"], "Ananse")
        self.assertIn("Metrics Interpretation", payload["content"])
        self.assertEqual(payload["confidence"], "High")

    def test_settings_route_updates_collaboration_level(self):
        app, token, _ = self._build_app()
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=_ApiProvider(),
        )
        with patch("app.main._verse_service", return_value=service):
            client = app.test_client()
            res = client.put(
                "/platform/verse/settings",
                headers={"Authorization": f"Bearer {token}"},
                json={"collaborationLevel": "absolutely synergetic"},
            )
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertEqual(payload["settings"]["collaborationLevel"], "absolutely synergetic")

    def test_resolve_context_thread_reuses_page_chat(self):
        app, token, _ = self._build_app()
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=_ApiProvider(),
        )
        with patch("app.main._verse_service", return_value=service):
            client = app.test_client()
            first = client.post(
                "/platform/verse/threads/resolve",
                headers={"Authorization": f"Bearer {token}"},
                json={"pathname": "/service-builder", "collaborationLevel": "very collaborative"},
            )
            created = service.create_thread(
                "zulan",
                title="Page Chat",
                collaboration_level="very collaborative",
                thread_scope="dock",
                context_key="dock::/service-builder",
                source_pathname="/service-builder",
                metadata={"pathname": "/service-builder", "surface": "dock"},
            )
            second = client.post(
                "/platform/verse/threads/resolve",
                headers={"Authorization": f"Bearer {token}"},
                json={"pathname": "/service-builder"},
            )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertIsNone(first.get_json()["thread"])
        self.assertEqual(second.get_json()["thread"]["id"], created["id"])
        self.assertEqual(second.get_json()["thread"]["threadScope"], "dock")

    def test_threads_route_lists_portal_and_dock_threads_by_default(self):
        app, token, _ = self._build_app()
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=_ApiProvider(),
        )
        service.create_thread("zulan", title="Portal Thread", thread_scope="portal")
        service.create_thread("zulan", title="Dock Thread", thread_scope="dock")
        with patch("app.main._verse_service", return_value=service):
            client = app.test_client()
            res = client.get("/platform/verse/threads", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertEqual({item["threadScope"] for item in payload["threads"]}, {"portal", "dock"})

    def test_user_settings_save_retries_windows_style_replace_conflict(self):
        data_dir = tempfile.TemporaryDirectory()
        self.addCleanup(data_dir.cleanup)
        store = VerseStore(data_dir.name)
        original_replace = Path.replace
        attempts = {"count": 0}

        def flaky_replace(path_obj, target_obj):
            if str(path_obj).endswith(".tmp") and attempts["count"] == 0:
                attempts["count"] += 1
                raise PermissionError(32, "The process cannot access the file because it is being used by another process")
            return original_replace(path_obj, target_obj)

        with patch("app.vdb_bson.Path.replace", new=flaky_replace):
            payload = store.save_user_settings(
                VerseUserSettings(username="zulan", collaboration_level="absolutely synergetic")
            )

        self.assertEqual(payload["collaborationLevel"], "absolutely synergetic")
        self.assertEqual(store.load_user_settings("zulan").collaboration_level, "absolutely synergetic")
        self.assertEqual(attempts["count"], 1)

    def test_assist_route_returns_normalized_usage(self):
        app, token, _ = self._build_app()
        provider = _ApiProvider()
        provider.responses = [
            {
                "message": "Kalulu reviewed the request.",
                "confidence": "High",
                "_usage": {"promptTokenCount": 17, "candidatesTokenCount": 5, "totalTokenCount": 22},
            }
        ]
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=provider,
        )
        with patch("app.main._verse_service", return_value=service):
            client = app.test_client()
            res = client.post(
                "/platform/verse/assist",
                headers={"Authorization": f"Bearer {token}"},
                json={"content": "Review this design", "context": {"pathname": "/verse-ai", "screen": "/verse-ai"}},
            )
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertEqual(payload["usage"]["inputTokens"], 17)
        self.assertEqual(payload["usage"]["outputTokens"], 5)
        self.assertEqual(payload["usage"]["totalTokens"], 22)
        self.assertEqual(payload["inspectDetails"]["usage"]["totalTokens"], 22)

    def test_assist_route_promotes_structured_next_step_into_visible_message(self):
        app, token, _ = self._build_app()
        provider = _ApiProvider()
        provider.responses = [
            {
                "message": "I prepared the next step.",
                "confidence": "High",
                "next_step": "Open the prepared VDB query and run it in the VDB Portal to verify the result.",
                "artifact": {
                    "kind": "vdb-query",
                    "vdbQuery": "context",
                },
            }
        ]
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=provider,
        )
        with patch("app.main._verse_service", return_value=service):
            client = app.test_client()
            res = client.post(
                "/platform/verse/assist",
                headers={"Authorization": f"Bearer {token}"},
                json={"content": "prepare the vdb context query", "context": {"pathname": "/vdb-portal", "screen": "/vdb-portal"}},
            )
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertEqual(payload["message"], "Open the prepared VDB query and run it in the VDB Portal to verify the result.")
        self.assertEqual(payload["inspectDetails"]["nextStep"], "Open the prepared VDB query and run it in the VDB Portal to verify the result.")

    def test_assist_route_returns_visible_planning_content_for_mixed_design_build(self):
        app, token, _ = self._build_app()
        provider = _ApiProvider()
        provider.responses = [
            {
                "message": "Kalulu wants to confirm the workflow and storage shape before generating the Versa attendance system.",
                "confidence": "Medium",
                "response_mode": "planning",
                "planning": {
                    "currentGoal": "Turn the request into a validated implementation plan before generating artifacts.",
                    "missingDecisions": ["data shape for storage and records", "exact artifact/query/script shape"],
                    "nextStep": "Confirm the plan details or answer the missing decisions, then I can produce the build-ready artifact.",
                },
                "next_step": "Confirm the plan details or answer the missing decisions, then I can produce the build-ready artifact.",
            },
        ]
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=provider,
        )
        with patch("app.main._verse_service", return_value=service):
            client = app.test_client()
            res = client.post(
                "/platform/verse/assist",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "content": "lets create a versa menu driven cli application with vdb for storage to act as a fully designed ux employee check in check out system",
                    "context": {"pathname": "/services", "screen": "/services"},
                },
            )
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertEqual(payload["inspectDetails"]["responseMode"], "planning")
        self.assertIn("**Current Goal**", payload["message"])
        self.assertIn("**Missing Decisions**", payload["message"])
        self.assertIn("**Next Concrete Step**", payload["message"])

    def test_thread_routes_accept_anthropic_provider_selection(self):
        app, token, _ = self._build_app()
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={
                "AI_PROVIDER": "google",
                "GOOGLE_API_KEY": "test-key",
                "GOOGLE_MODEL": "fake-model",
                "ANTHROPIC_API_KEY": "anthropic-test-key",
                "ANTHROPIC_MODEL": "claude-sonnet-4-6",
                "OPENAI_API_KEY": "openai-test-key",
                "OPENAI_MODEL": "gpt-5-mini",
            },
            provider=_ApiProvider(),
        )
        with patch("app.main._verse_service", return_value=service):
            client = app.test_client()
            create_res = client.post(
                "/platform/verse/threads",
                headers={"Authorization": f"Bearer {token}"},
                json={"provider": "anthropic"},
            )
            self.assertEqual(create_res.status_code, 201)
            thread_id = create_res.get_json()["thread"]["id"]
            self.assertEqual(create_res.get_json()["thread"]["providerName"], "anthropic")
            message_res = client.post(
                f"/platform/verse/threads/{thread_id}/messages",
                headers={"Authorization": f"Bearer {token}"},
                json={"content": "Review this design", "provider": "anthropic"},
            )
        self.assertEqual(message_res.status_code, 200)
        thread = message_res.get_json()["thread"]
        self.assertEqual(thread["providerName"], "anthropic")

    def test_thread_routes_accept_openai_provider_selection(self):
        app, token, _ = self._build_app()
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={
                "AI_PROVIDER": "google",
                "GOOGLE_API_KEY": "test-key",
                "GOOGLE_MODEL": "fake-model",
                "ANTHROPIC_API_KEY": "anthropic-test-key",
                "ANTHROPIC_MODEL": "claude-sonnet-4-6",
                "OPENAI_API_KEY": "openai-test-key",
                "OPENAI_MODEL": "gpt-5-mini",
            },
            provider=_ApiProvider(),
        )
        with patch("app.main._verse_service", return_value=service):
            client = app.test_client()
            create_res = client.post(
                "/platform/verse/threads",
                headers={"Authorization": f"Bearer {token}"},
                json={"provider": "openai"},
            )
            self.assertEqual(create_res.status_code, 201)
            thread_id = create_res.get_json()["thread"]["id"]
            self.assertEqual(create_res.get_json()["thread"]["providerName"], "openai")
            message_res = client.post(
                f"/platform/verse/threads/{thread_id}/messages",
                headers={"Authorization": f"Bearer {token}"},
                json={"content": "Review this design", "provider": "openai"},
            )
        self.assertEqual(message_res.status_code, 200)
        thread = message_res.get_json()["thread"]
        self.assertEqual(thread["providerName"], "openai")

    def test_super_admin_can_rename_agent(self):
        app, _, super_token = self._build_app()
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=_ApiProvider(),
        )
        with patch("app.main._verse_service", return_value=service):
            client = app.test_client()
            res = client.put(
                "/platform/verse/agents/liwiro-architect",
                headers={"Authorization": f"Bearer {super_token}"},
                json={"displayName": "Builder"},
            )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["agent"]["displayName"], "Builder")

    def test_assist_route_returns_page_artifact(self):
        app, token, _ = self._build_app()
        provider = _ApiProvider()
        provider.responses = [
            {
                "message": "Kalulu drafted a VDB query for the current console.",
                "confidence": "High",
                "artifact": {
                    "kind": "vdb-query",
                    "vdbQuery": "read domains",
                },
            }
        ]
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=provider,
        )
        with patch("app.main._verse_service", return_value=service):
            client = app.test_client()
            res = client.post(
                "/platform/verse/assist",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "content": "Give me a query to inspect domains",
                    "context": {"pathname": "/vdb-portal", "pageKind": "vdb-portal", "screen": "vdb portal"},
                },
            )
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertEqual(payload["agent"]["id"], "liwiro-architect")
        self.assertEqual(payload["artifact"]["kind"], "vdb-query")
        self.assertEqual(payload["artifact"]["vdbQuery"], "read domains")

    def test_actions_catalog_includes_service_manager_when_user_can_manage_services(self):
        app, token, _ = self._build_app()
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=_ApiProvider(),
        )
        with patch("app.main._verse_service", return_value=service):
            client = app.test_client()
            res = client.get("/platform/verse/actions/catalog", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertIn("service-manager-action", {item["kind"] for item in payload["actions"]})

    def test_execute_service_manager_action_route_starts_service(self):
        app, token, _ = self._build_app()
        service_doc = {
            "apiName": "zshop-core",
            "processId": "8123",
            "status": "NOT_RUNNING",
            "lapis_config": {"metadata": {"apiName": "zshop-core"}},
            "service_access": ["*"],
        }
        app.vdb_client.read_documents.return_value = (True, [service_doc])
        app.vdb_client.update_document.return_value = (True, 1)
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=_ApiProvider(),
        )
        with patch("app.main._verse_service", return_value=service):
            client = app.test_client()
            res = client.post(
                "/platform/verse/actions/execute",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "artifact": {
                        "kind": "service-manager-action",
                        "serviceAction": {"action": "start", "processId": "8123"},
                    }
                },
            )
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["action"], "start")
        self.assertEqual(payload["service"]["apiName"], "zshop-core")
        app.process_manager.restart_service.assert_called_once()

    def test_dataset_routes_create_and_analyze_pasted_data(self):
        app, token, _ = self._build_app()
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=_ApiProvider(),
        )
        with patch("app.main._verse_service", return_value=service):
            client = app.test_client()
            create_res = client.post(
                "/platform/verse/datasets",
                headers={"Authorization": f"Bearer {token}"},
                json={"title": "Sales", "text": "month,revenue\nJan,120\nFeb,180\n"},
            )
            self.assertEqual(create_res.status_code, 201)
            payload = create_res.get_json()
            dataset_id = payload["dataset"]["id"]
            self.assertEqual(payload["analysis"]["chart"]["chartType"], "bar")

            analyze_res = client.post(
                f"/platform/verse/datasets/{dataset_id}/analyze",
                headers={"Authorization": f"Bearer {token}"},
                json={"chartType": "histogram", "metric": "revenue"},
            )
        self.assertEqual(analyze_res.status_code, 200)
        self.assertEqual(analyze_res.get_json()["analysis"]["chart"]["chartType"], "histogram")

    def test_dataset_upload_route_archives_file(self):
        app, token, _ = self._build_app()
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=_ApiProvider(),
        )
        with patch("app.main._verse_service", return_value=service):
            client = app.test_client()
            res = client.post(
                "/platform/verse/datasets/upload",
                headers={"Authorization": f"Bearer {token}"},
                data={"file": (io.BytesIO(b"segment,value\nA,12\nB,24\n"), "segments.csv")},
                content_type="multipart/form-data",
            )
        self.assertEqual(res.status_code, 201)
        payload = res.get_json()
        self.assertEqual(payload["dataset"]["source"]["sourceType"], "upload")
        self.assertTrue(payload["dataset"]["source"]["archivedPath"].endswith("segments.csv"))

    def test_vi_validate_route_returns_parser_payload(self):
        app, token, _ = self._build_app()
        with patch(
            "app.main.validate_versa_source",
            return_value={"ok": False, "error": "Unexpected token near line 2", "path": "scratch/test.versa"},
        ):
            client = app.test_client()
            res = client.post(
                "/platform/vi/validate",
                headers={"Authorization": f"Bearer {token}"},
                json={"source": "let p = ;", "path": "scratch/test.versa"},
            )
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["path"], "scratch/test.versa")
        self.assertIn("Unexpected token", payload["error"])

    def test_lapis_validate_route_returns_versa_issues(self):
        app, token, _ = self._build_app()
        detail = {
            "valid": False,
            "error": "Endpoint '/mad-libs' has invalid Versa syntax.",
            "normalized": {"metadata": {"apiName": "mad-libs"}},
            "versaIssues": [
                {
                    "endpointId": "play",
                    "endpointPath": "/mad-libs",
                    "path": "service-scripts/mad-libs/play.versa",
                    "error": "Unexpected token near line 3",
                }
            ],
        }
        with patch("app.main.Config.validate_lapis_config_detailed", return_value=detail):
            client = app.test_client()
            res = client.post(
                "/platform/lapis/validate",
                headers={"Authorization": f"Bearer {token}"},
                json={"config": {"metadata": {"apiName": "mad-libs"}, "endpoints": {}}},
            )
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], detail["error"])
        self.assertEqual(payload["normalized"]["metadata"]["apiName"], "mad-libs")
        self.assertEqual(payload["versaIssues"][0]["endpointId"], "play")
        self.assertEqual(payload["validationState"]["attemptCount"], 0)
        self.assertEqual(payload["validationState"]["nextStep"], "continue")

    def test_lapis_validate_route_has_no_retry_or_permission_gate(self):
        app, token, _ = self._build_app()
        detail = {
            "valid": False,
            "error": "Versa syntax validation timed out.",
            "normalized": {"metadata": {"apiName": "mad-libs"}},
            "versaIssues": [],
        }
        with patch("app.main.Config.validate_lapis_config_detailed", return_value=detail):
            client = app.test_client()
            res = client.post(
                "/platform/lapis/validate",
                headers={"Authorization": f"Bearer {token}"},
                json={"config": {"metadata": {"apiName": "mad-libs"}, "endpoints": {}}, "validationState": {"attemptCount": 1}},
            )
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertEqual(payload["validationState"]["attemptCount"], 0)
        self.assertEqual(payload["validationState"]["nextStep"], "continue")

    def test_platform_settings_route_exposes_feature_flags(self):
        app, token, _ = self._build_app()
        auth_data = {
            "settings": {
                "productionMode": True,
                "featureFlags": {
                    "lapisRecursiveAutoFix": False,
                },
            }
        }
        with patch("app.main._load_normalized_auth_data", return_value=auth_data):
            client = app.test_client()
            res = client.get("/platform/settings", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertIn("featureFlags", payload)
        self.assertIn("featureFlagDefinitions", payload)
        self.assertFalse(payload["featureFlags"]["lapisRecursiveAutoFix"])
        self.assertTrue(any(item["id"] == "verseActionProgressMessages" for item in payload["featureFlagDefinitions"]))

    def test_platform_settings_route_updates_feature_flags(self):
        app, _, super_token = self._build_app()
        store = {"settings": {"featureFlags": {"lapisRecursiveAutoFix": True}}}

        def _load():
            return store

        def _save(next_data):
            snapshot = dict(next_data)
            store.clear()
            store.update(snapshot)

        with patch("app.main._load_normalized_auth_data", side_effect=_load), patch("app.main._save_normalized_auth_data", side_effect=_save):
            client = app.test_client()
            res = client.put(
                "/platform/settings",
                headers={"Authorization": f"Bearer {super_token}"},
                json={"featureFlags": {"lapisRecursiveAutoFix": False, "vdbProgressMessages": False}},
            )

        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertFalse(payload["featureFlags"]["lapisRecursiveAutoFix"])
        self.assertFalse(payload["featureFlags"]["vdbProgressMessages"])
        self.assertIn("featureFlags", store["settings"])
        self.assertFalse(store["settings"]["featureFlags"]["lapisRecursiveAutoFix"])

    def test_lapis_repair_route_returns_structured_result(self):
        app, token, _ = self._build_app()
        auth_data = {"settings": {"featureFlags": {"lapisRecursiveAutoFix": True, "lapisSafeSchemaAutoFix": True}}}
        repair_result = {
            "ok": True,
            "error": "",
            "normalized": {"metadata": {"apiName": "RepairService"}},
            "dryRun": {"sandboxId": "sandbox-1"},
            "issues": [],
            "repairAttempts": [{"attempt": 1}],
            "appliedFixes": [{"code": "missing-comma-after-property"}],
            "attemptCount": 1,
            "repaired": True,
            "repairable": True,
            "finalStatus": "ready",
            "progressMessage": "Validation passed after deterministic repair.",
        }
        with patch("app.main._load_normalized_auth_data", return_value=auth_data), patch("app.main.repair_lapis_config_recursively", return_value=repair_result):
            client = app.test_client()
            res = client.post(
                "/platform/lapis/repair",
                headers={"Authorization": f"Bearer {token}"},
                json={"config": {"metadata": {"apiName": "RepairService"}, "endpoints": {}}},
            )
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["finalStatus"], "ready")
        self.assertTrue(payload["featureFlags"]["lapisRecursiveAutoFix"])

    def test_lapis_repair_route_respects_disabled_feature_flag(self):
        app, token, _ = self._build_app()
        auth_data = {"settings": {"featureFlags": {"lapisRecursiveAutoFix": False}}}
        with patch("app.main._load_normalized_auth_data", return_value=auth_data):
            client = app.test_client()
            res = client.post(
                "/platform/lapis/repair",
                headers={"Authorization": f"Bearer {token}"},
                json={"config": {"metadata": {"apiName": "RepairService"}, "endpoints": {}}},
            )
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["finalStatus"], "disabled")

    def test_settings_route_updates_proactive_configuration(self):
        app, token, _ = self._build_app()
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=_ApiProvider(),
        )
        with patch("app.main._verse_service", return_value=service):
            client = app.test_client()
            res = client.put(
                "/platform/verse/settings",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "collaborationLevel": "absolutely synergetic",
                    "proactiveModeEnabled": True,
                    "agents": {
                        "liwiro-architect": {"proactivityEnabled": True, "proactivityLevel": 6},
                        "liwiro-analyst": {"proactivityEnabled": False, "proactivityLevel": 2},
                    },
                },
            )
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()["settings"]
        self.assertTrue(payload["proactiveModeEnabled"])
        self.assertEqual(payload["agents"]["liwiro-architect"]["proactivityLevel"], 6)
        self.assertFalse(payload["agents"]["liwiro-analyst"]["proactivityEnabled"])

    def test_notifications_routes_support_read_flow(self):
        app, token, _ = self._build_app()
        provider = _ApiProvider()
        provider.responses = [
            {
                "shouldNotify": True,
                "issueKey": "api-drift",
                "title": "API drift",
                "summary": "The API contract no longer matches the current draft.",
                "message": "I found API drift between the current draft and the generated surface.",
                "confidence": "High",
                "severity": "high",
            }
        ]
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=provider,
        )
        service.update_user_settings(
            "zulan",
            proactive_mode_enabled=True,
            agent_settings=self._single_proactive_agent_settings(service, "liwiro-architect", level=6),
        )
        with patch("app.main._verse_service", return_value=service):
            client = app.test_client()
            notifications_res = client.get("/platform/verse/notifications?force=1", headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(notifications_res.status_code, 200)
            notifications_payload = notifications_res.get_json()
            self.assertEqual(len(notifications_payload["emitted"]), 1)
            thread_id = notifications_payload["items"][0]["threadId"]
            read_res = client.post(
                "/platform/verse/notifications/read",
                headers={"Authorization": f"Bearer {token}"},
                json={"threadId": thread_id},
            )
        self.assertEqual(read_res.status_code, 200)
        self.assertEqual(read_res.get_json()["unreadCount"], 0)

    def test_notifications_route_defers_scheduler_during_cooldown(self):
        app, token, _ = self._build_app()
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=_ApiProvider(),
        )
        app.resilience_state = {
            "verse_notifications": {
                "zulan": {
                    "nextAllowedAt": time.time() + 20,
                    "lastError": "",
                }
            }
        }

        with patch("app.main._verse_service", return_value=service), \
             patch.object(service, "run_due_proactive_evaluations", wraps=service.run_due_proactive_evaluations) as run_due:
            client = app.test_client()
            res = client.get("/platform/verse/notifications", headers={"Authorization": f"Bearer {token}"})

        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertFalse(payload["degraded"])
        self.assertTrue(payload["schedulerDeferred"])
        self.assertFalse(payload["schedulerRan"])
        self.assertGreater(payload["retryAfterMs"], 0)
        run_due.assert_not_called()

    def test_notifications_route_falls_back_to_cached_items_when_scheduler_fails(self):
        app, token, _ = self._build_app()
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=_ApiProvider(),
        )

        with patch("app.main._verse_service", return_value=service), \
             patch.object(service, "run_due_proactive_evaluations", side_effect=RuntimeError("provider down")):
            client = app.test_client()
            res = client.get("/platform/verse/notifications", headers={"Authorization": f"Bearer {token}"})

        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertTrue(payload["degraded"])
        self.assertTrue(payload["schedulerDeferred"])
        self.assertFalse(payload["schedulerRan"])
        self.assertGreater(payload["retryAfterMs"], 0)
        self.assertEqual(payload["reason"], "provider down")

    def test_notifications_route_reads_cached_items_when_another_worker_owns_scheduler_lock(self):
        app, token, _ = self._build_app()
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=_ApiProvider(),
        )

        with patch("app.main._verse_service", return_value=service), \
             patch("app.main._run_with_proactive_leader_lock", return_value=False), \
             patch.object(service, "run_due_proactive_evaluations", wraps=service.run_due_proactive_evaluations) as run_due:
            client = app.test_client()
            res = client.get("/platform/verse/notifications?force=1", headers={"Authorization": f"Bearer {token}"})

        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertTrue(payload["schedulerDeferred"])
        self.assertFalse(payload["schedulerRan"])
        self.assertIn("another worker", payload["reason"].lower())
        run_due.assert_not_called()

    def test_ignore_issue_route_suppresses_future_proactive_repeats(self):
        app, token, _ = self._build_app()
        provider = _ApiProvider()
        provider.responses = [
            {
                "shouldNotify": True,
                "issueKey": "compliance-gap",
                "title": "Compliance gap",
                "summary": "A policy control is missing.",
                "message": "I found a policy control gap that should be addressed.",
                "confidence": "High",
                "severity": "high",
            },
            {
                "shouldNotify": True,
                "issueKey": "compliance-gap",
                "title": "Compliance gap",
                "summary": "The same policy control is still missing.",
                "message": "Following up: the policy control gap still exists.",
                "confidence": "High",
                "severity": "high",
            },
        ]
        service = VerseService(
            verse_root=app.config["VERSE_ROOT"],
            data_dir=app.config["VERSE_DATA_DIR"],
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=provider,
        )
        service.update_user_settings(
            "zulan",
            proactive_mode_enabled=True,
            agent_settings=self._single_proactive_agent_settings(service, "liwiro-compliance-advisor", level=6),
        )
        with patch("app.main._verse_service", return_value=service):
            client = app.test_client()
            first = client.get("/platform/verse/notifications?force=1", headers={"Authorization": f"Bearer {token}"})
            first_payload = first.get_json()
            self.assertEqual(len(first_payload["emitted"]), 1)
            issue_key = first_payload["emitted"][0]["issueKey"]
            thread_id = first_payload["emitted"][0]["threadId"]
            ignore_res = client.post(
                "/platform/verse/issues/ignore",
                headers={"Authorization": f"Bearer {token}"},
                json={"issueKey": issue_key, "agentId": "liwiro-compliance-advisor", "threadId": thread_id},
            )
            self.assertEqual(ignore_res.status_code, 200)
            second = client.get("/platform/verse/notifications?force=1", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.get_json()["emitted"], [])


if __name__ == "__main__":
    unittest.main()
