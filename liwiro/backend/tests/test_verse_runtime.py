# Copyright (c) 2026 Bwalya Cameron Chishimba
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.verse.loaders import VerseContentLoader
from app.verse.providers.base import AIConfigurationError, AIResponse
from app.verse.providers.factory import build_ai_provider
from app.verse.providers.google import GoogleGeminiProvider
from app.verse.providers.openai import OpenAIResponsesProvider
from app.verse.retrieval import _manual_candidates, build_liwiro_reference_context, build_prompt_context_bundle, build_versa_reference_context
from app.verse.routing import VerseRouter
from app.verse.service import VerseService, _canonicalize_vdb_artifact_query
from app.verse import store as verse_store_module


class _SequenceProvider:
    def __init__(self, responses):
        self.responses = list(responses)

    def generate(self, request):
        payload = self.responses.pop(0)
        if isinstance(payload, dict):
            text = json.dumps(payload)
        else:
            text = str(payload)
        return AIResponse(text=text, model="fake-model", provider="fake")

    def healthcheck(self, request=None):
        return AIResponse(text='{"probe":"ok"}', model="fake-model", provider="fake")


class _RecordingProvider(_SequenceProvider):
    def __init__(self, responses):
        super().__init__(responses)
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return super().generate(request)


class VerseRuntimeTests(unittest.TestCase):
    def test_vdb_artifact_normalization_requires_readable_commands(self):
        self.assertEqual(_canonicalize_vdb_artifact_query("read users"), "read users")
        self.assertEqual(_canonicalize_vdb_artifact_query("read collection orders"), "read collection orders")
        for value in ({"action": "context"}, {"context": {}}, [], "", '{"action":"context"}'):
            self.assertIsNone(_canonicalize_vdb_artifact_query(value))

    def setUp(self):
        self.verse_root_dir = tempfile.TemporaryDirectory()
        self.data_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.verse_root_dir.cleanup)
        self.addCleanup(self.data_dir.cleanup)
        shutil.copytree(REPO_ROOT / "verse", self.verse_root_dir.name, dirs_exist_ok=True)
        self.verse_root = Path(self.verse_root_dir.name)
        self.store_dir = Path(self.data_dir.name) / "verse-store"

    def _service(self, responses):
        return VerseService(
            verse_root=self.verse_root,
            data_dir=self.store_dir,
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=_SequenceProvider(responses),
        )

    def _single_proactive_agent_settings(self, service: VerseService, enabled_agent_id: str, level: int = 2) -> dict[str, dict]:
        return {
            agent["id"]: {
                "proactivityEnabled": agent["id"] == enabled_agent_id,
                "proactivityLevel": level if agent["id"] == enabled_agent_id else 1,
            }
            for agent in service.list_agents()
        }

    def test_loader_reads_agents_skills_and_router_rules(self):
        loader = VerseContentLoader(self.verse_root)
        scaffold = loader.load({})
        self.assertEqual(len(scaffold.agents), 5)
        self.assertIn("liwiro-architect", scaffold.agents)
        self.assertIn("liwiro-analyst", scaffold.route_keywords)
        self.assertTrue(any(rule.target_agent_id == "liwiro-reliability-advisor" for rule in scaffold.handoff_rules))
        self.assertIn("api-design-review", scaffold.skills)
        self.assertIn("AGENTS.md", scaffold.bootstrap_documents)
        self.assertIn("TOOLS.md", scaffold.bootstrap_documents)
        self.assertIn("artifactKindsAllowed", scaffold.agents["liwiro-architect"].contract)
        self.assertIn("domains/versa-vdb-employee-cli", scaffold.context_library)

    def test_agent_list_uses_canonical_importance_order(self):
        service = self._service([])
        agents = service.list_agents()
        self.assertEqual(
            [agent["id"] for agent in agents],
            [
                "liwiro-architect",
                "liwiro-analyst",
                "liwiro-reliability-advisor",
                "liwiro-compliance-advisor",
                "liwiro-documentation-advisor",
            ],
        )
        analyst = next(item for item in agents if item["id"] == "liwiro-analyst")
        self.assertTrue(any(skill["title"] == "Metrics Interpretation" for skill in analyst["skills"]))
        self.assertTrue(analyst["abilitySummary"])

    def test_versa_queries_use_canonical_vi_wiki_reference(self):
        manuals = _manual_candidates("write a versa script with modules", page_kind="vi-portal")
        sources = {str(item.get("source") or "") for item in manuals}

        self.assertTrue(any(source.endswith("liwiro/verse/context/reference/ai-operation-reference.json") for source in sources))
        self.assertTrue(any(str(item.get("wiki") or "").startswith("/wiki/") for item in manuals))

    def test_versa_reference_context_selects_sections_for_full_script(self):
        blocks, gaps = build_versa_reference_context(
            query="write a versa script that imports mediacloud and loops over animals",
            source_text=(
                "import mediacloud;\n"
                "let animals = [\"lion\", \"zebra\"];\n"
                "for (animal in animals) {\n"
                "  print(`Animal: {animal}`);\n"
                "}\n"
            ),
            validator_issues=["Expected ';' after variable declaration"],
            limit=6,
        )
        labels = {block.label for block in blocks}
        combined = "\n".join(block.content for block in blocks)

        self.assertIn("Versa Authoring Workflow", labels)
        self.assertTrue(any("Versa Reference:" in label for label in labels))
        self.assertIn("Required Workflows:", combined)
        self.assertIn("Guardrails:", combined)
        self.assertTrue(any("mediacloud" in gap for gap in gaps))

    def test_versa_reference_context_reports_unknown_module_gaps(self):
        blocks, gaps = build_versa_reference_context(
            query="write a versa script",
            source_text="import mysterycloud;\nlet ok = true;\nprint(ok);\n",
            validator_issues=[],
            limit=4,
        )
        self.assertTrue(any("mysterycloud" in gap for gap in gaps))
        self.assertTrue(any(block.label == "Versa Reference Gaps" for block in blocks))

    def test_liwiro_reference_context_selects_lapis_and_capability_sections(self):
        blocks = build_liwiro_reference_context(
            query="Use platform actions preview to prepare a service-builder LAPIS draft with linkedModel and crudOperation",
            page_kind="service-builder",
            limit=5,
        )
        labels = {block.label for block in blocks}
        combined = "\n".join(block.content for block in blocks)

        self.assertIn("Liwiro Workflow", labels)
        self.assertTrue(any("Capability Registry And Staged Action Flow" in label for label in labels))
        self.assertTrue(any("LAPIS Contract Core" in label for label in labels))
        self.assertIn("service.builder.generate", combined)
        self.assertIn("crudOperation", combined)

    def test_prompt_context_bundle_uses_bounded_mode_without_bootstrap_files(self):
        service = self._service([])
        scaffold = service._scaffold()
        agent = scaffold.agents["liwiro-architect"]

        blocks, traces, report = build_prompt_context_bundle(
            scaffold,
            agent,
            "Review this REST API design",
            "",
            {"pageKind": "service-builder", "screen": "/service-builder"},
            learning_records=[],
            prompt_mode="bounded",
            thread_messages=[{"role": "user", "content": "Review this REST API design"}],
        )

        self.assertGreater(len(blocks), 0)
        self.assertEqual(report["promptMode"], "bounded")
        self.assertEqual(report["bootstrapFiles"], [])
        self.assertTrue(any(entry["category"] == "platform" for entry in report["entries"]))
        self.assertTrue(any(trace["source"] == "platform" for trace in traces))

    def test_prompt_context_bundle_includes_liwiro_reference_for_service_builder_queries(self):
        service = self._service([])
        scaffold = service._scaffold()
        agent = scaffold.agents["liwiro-architect"]

        _blocks, traces, report = build_prompt_context_bundle(
            scaffold,
            agent,
            "Create a Builder-ready LAPIS service draft and use capability ids for the action flow",
            "",
            {"pageKind": "service-builder", "screen": "/service-builder"},
            learning_records=[],
            prompt_mode="bounded",
            thread_messages=[{"role": "user", "content": "Create a Builder-ready LAPIS service draft"}],
        )

        self.assertTrue(
            any(
                str(entry.get("source") or "").endswith("liwiro/verse/liwiro-platform-reference/reference.json")
                and str(entry.get("category") or "") == "reference"
                for entry in report["entries"]
            )
        )
        self.assertTrue(
            any(str(trace.get("source") or "").endswith("liwiro/verse/liwiro-platform-reference/reference.json") for trace in traces)
        )

    def test_send_message_routes_to_architect_and_persists_thread(self):
        service = self._service(
            [
                {
                    "message": "Kalulu reviewed the API boundary and authentication design.",
                    "summary": "Architecture review in progress.",
                    "confidence": "High",
                    "content_type": "analysis",
                }
            ]
        )
        thread = service.create_thread("zulan")
        updated = service.send_message(thread["id"], "zulan", "Review my REST API design for authentication")
        self.assertEqual(updated["activeAgentId"], "liwiro-architect")
        self.assertEqual(len(updated["messages"]), 2)
        self.assertEqual(updated["messages"][1]["agentDisplayName"], "Kalulu")
        self.assertEqual(updated["summary"], "Architecture review in progress.")
        self.assertEqual(updated["title"], "Architecture review in progress.")
        self.assertEqual(updated["messages"][1]["inspectDetails"]["promptMode"], "bounded")
        self.assertEqual(updated["messages"][1]["inspectDetails"]["bootstrapFiles"], [])

    def test_handoff_follow_up_uses_minimal_prompt_mode(self):
        provider = _RecordingProvider(
            [
                {
                    "message": "Kalulu wants Ntiili to add a reliability angle.",
                    "summary": "Initial design review completed.",
                    "confidence": "High",
                    "content_type": "analysis",
                    "handoff": {"agent": "Ntiili", "reason": "Need a reliability-focused rollout view."},
                },
                {
                    "message": "Ntiili added the reliability and rollout perspective.",
                    "summary": "Architecture and reliability view combined.",
                    "confidence": "High",
                    "content_type": "analysis",
                },
            ]
        )
        service = VerseService(
            verse_root=self.verse_root,
            data_dir=self.store_dir,
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=provider,
        )
        thread = service.create_thread("zulan")
        updated = service.send_message(thread["id"], "zulan", "Design the service and include rollout reliability considerations, and loop in Ntiili")

        self.assertEqual(len(provider.requests), 2)
        first_message = updated["messages"][1]
        second_message = updated["messages"][3]
        self.assertEqual(first_message["inspectDetails"]["promptMode"], "bounded")
        self.assertEqual(second_message["inspectDetails"]["promptMode"], "minimal")
        self.assertEqual(first_message["inspectDetails"]["bootstrapFiles"], [])
        self.assertEqual(second_message["inspectDetails"]["bootstrapFiles"], [])
        self.assertEqual(len(second_message["inspectDetails"]["handoffChain"]), 1)

    def test_thread_reply_uses_structured_next_step_when_message_is_generic(self):
        service = self._service(
            [
                {
                    "message": "I prepared the next step.",
                    "summary": "Prepared the next step.",
                    "confidence": "High",
                    "next_step": "Open the VI draft and run the attendance flow in VI Portal.",
                    "artifact": {
                        "kind": "vi-script",
                        "path": "attendance_checkin.versa",
                        "versaSource": "print(\"ok\");",
                    },
                }
            ]
        )
        thread = service.create_thread("zulan")
        updated = service.send_message(thread["id"], "zulan", "Build a Versa attendance CLI prototype")
        self.assertEqual(
            updated["messages"][-1]["content"],
            "Open the VI draft and run the attendance flow in VI Portal.",
        )

    def test_send_message_persists_user_display_name(self):
        service = self._service(
            [
                {
                    "message": "Kalulu answered the thread.",
                    "summary": "Thread updated.",
                    "confidence": "High",
                    "content_type": "analysis",
                }
            ]
        )
        thread = service.create_thread("zulan")
        updated = service.send_message(thread["id"], "zulan", "Review this design")
        self.assertEqual(updated["messages"][0]["userDisplayName"], "zulan")

    def test_follow_up_can_reuse_prior_artifact_for_program_card_request(self):
        service = self._service(
            [
                {
                    "message": "Kalulu prepared the service draft.",
                    "summary": "Draft prepared.",
                    "confidence": "High",
                    "artifact": {
                        "kind": "service-builder-lapis",
                        "lapisConfig": {
                            "metadata": {"apiName": "AttendanceService", "basePath": "/api/attendance", "version": "1.0.0"},
                            "models": {
                                "employees": {
                                    "name": "Employees",
                                    "fields": {"username": {"type": "string", "required": True}},
                                }
                            },
                            "endpoints": {},
                        },
                    },
                },
                {
                    "message": "Here is the card again.",
                    "summary": "Reused the prepared draft.",
                    "confidence": "High",
                },
                {
                    "message": "Here is the card again.",
                    "summary": "Reused the prepared draft.",
                    "confidence": "High",
                },
            ]
        )
        thread = service.create_thread("zulan")
        first = service.send_message(thread["id"], "zulan", "Create the attendance service")
        updated = service.send_message(first["id"], "zulan", "give me the program card")
        self.assertEqual(updated["messages"][-1]["artifact"]["kind"], "service-builder-lapis")
        self.assertEqual(updated["messages"][-1]["artifact"]["lapisConfig"]["metadata"]["apiName"], "AttendanceService")

    def test_new_threads_start_with_hello_chat_placeholder(self):
        service = self._service([])
        thread = service.create_thread("zulan", initial_message="Build me a service")
        self.assertEqual(thread["title"], "Hello, Chat")

    def test_new_thread_defaults_to_architect_when_no_agent_is_named(self):
        service = self._service(
            [
                {
                    "message": "Kalulu is taking the first pass before any specialist handoff.",
                    "summary": "Kalulu handled the initial response.",
                    "confidence": "High",
                    "content_type": "analysis",
                }
            ]
        )
        thread = service.create_thread("zulan")
        updated = service.send_message(thread["id"], "zulan", "Check rollout risk and compliance exposure")
        self.assertEqual(updated["activeAgentId"], "liwiro-architect")
        self.assertEqual(updated["messages"][1]["agentDisplayName"], "Kalulu")

    def test_thread_can_persist_anthropic_provider(self):
        service = self._service(
            [
                {
                    "message": "Anthropic handled this response.",
                    "summary": "Anthropic provider selection persisted.",
                    "confidence": "High",
                    "content_type": "analysis",
                }
            ]
        )
        service.provider_config["ANTHROPIC_API_KEY"] = "test-anthropic-key"
        service.provider_config["ANTHROPIC_MODEL"] = "claude-sonnet-4-6"
        thread = service.create_thread("zulan", provider_name="anthropic")
        self.assertEqual(thread["providerName"], "anthropic")
        updated = service.send_message(thread["id"], "zulan", "Review this design", provider_name="anthropic")
        self.assertEqual(updated["providerName"], "anthropic")
        self.assertEqual(updated["providerModel"], "claude-sonnet-4-6")

    def test_thread_can_persist_openai_provider(self):
        service = self._service(
            [
                {
                    "message": "OpenAI handled this response.",
                    "summary": "OpenAI provider selection persisted.",
                    "confidence": "High",
                    "content_type": "analysis",
                }
            ]
        )
        service.provider_config["OPENAI_API_KEY"] = "test-openai-key"
        service.provider_config["OPENAI_MODEL"] = "gpt-5-mini"
        thread = service.create_thread("zulan", provider_name="openai")
        self.assertEqual(thread["providerName"], "openai")
        updated = service.send_message(thread["id"], "zulan", "Review this design", provider_name="openai")
        self.assertEqual(updated["providerName"], "openai")
        self.assertEqual(updated["providerModel"], "gpt-5-mini")

    def test_renamed_agent_can_be_invoked_explicitly(self):
        service = self._service(
            [
                {
                    "message": "Kalulu is responding under the renamed display name.",
                    "summary": "Explicit rename routing works.",
                    "confidence": "Medium",
                    "content_type": "analysis",
                }
            ]
        )
        service.rename_agent("liwiro-architect", "Builder", "root")
        thread = service.create_thread("zulan")
        updated = service.send_message(thread["id"], "zulan", "@Builder help me split this service")
        self.assertEqual(updated["activeAgentId"], "liwiro-architect")
        self.assertEqual(updated["messages"][1]["agentDisplayName"], "Builder")

    def test_unknown_agent_mention_routes_to_lead_with_misspelling_hint(self):
        service = self._service([])
        router = VerseRouter(service._scaffold())
        decision = router.route("@Doge what do you think?")
        self.assertEqual(decision.agent_id, "liwiro-architect")
        self.assertEqual(decision.source, "unknown_mention")
        self.assertIn("@Dage", decision.reason)
        self.assertIn("@Ananse", decision.reason)

    def test_router_uses_keyword_matches_before_default_architect(self):
        service = self._service([])
        router = VerseRouter(service._scaffold())
        decision = router.route("Analyze dashboard trends and compare revenue performance")
        self.assertEqual(decision.agent_id, "liwiro-analyst")
        self.assertEqual(decision.source, "routing_keywords")

    def test_router_classifies_mixed_design_build_requests(self):
        service = self._service([])
        router = VerseRouter(service._scaffold())
        decision = router.route(
            "Create a Versa menu-driven CLI with VDB storage and fully designed UX for employee check in and check out",
            current_screen="/services",
            page_kind="service-manager",
            desired_artifact_kind="vi-script",
        )
        self.assertEqual(decision.request_mode, "mixed-design-build")
        self.assertEqual(decision.agent_id, "liwiro-architect")

    def test_active_agent_continuity_is_overridden_when_new_turn_changes_domain(self):
        service = self._service([])
        router = VerseRouter(service._scaffold())
        decision = router.route(
            "Analyze dashboard trends and compare revenue performance",
            active_agent_id="liwiro-architect",
        )
        self.assertEqual(decision.agent_id, "liwiro-analyst")
        self.assertNotEqual(decision.source, "thread_active_agent")

    def test_mixed_design_build_request_returns_planning_response_before_artifact(self):
        service = self._service(
            [
                {
                    "message": "Kalulu wants to define the attendance workflow and VDB record shape before generating the Versa draft.",
                    "summary": "Planning response prepared before artifact generation.",
                    "confidence": "Medium",
                    "response_mode": "planning",
                    "content_type": "plan",
                    "planning": {
                        "currentGoal": "Turn the request into a validated implementation plan before generating artifacts.",
                        "assumptions": ["Use plan-first orchestration before any runnable draft."],
                        "missingDecisions": ["data shape for storage and records", "exact artifact/query/script shape"],
                        "recommendedApproach": ["Define the menu flow and employee lifecycle first.", "Validate the VDB storage/query shape before scripting."],
                        "specialistConsults": ["Nzou for UX framing"],
                        "nextStep": "Confirm the plan details or answer the missing decisions, then I can produce the build-ready artifact.",
                    },
                    "next_step": "Confirm the plan details or answer the missing decisions, then I can produce the build-ready artifact.",
                },
            ]
        )
        thread = service.create_thread("zulan")
        updated = service.send_message(
            thread["id"],
            "zulan",
            "Create a Versa menu-driven CLI with VDB storage and fully designed UX for employee check in and check out",
            current_screen="/services",
        )
        last_message = updated["messages"][-1]
        self.assertEqual(last_message["contentType"], "plan")
        self.assertIsNone(last_message["artifact"])
        self.assertEqual(updated["requestMode"], "mixed-design-build")
        self.assertTrue(updated["metadata"]["planState"]["awaitingConfirmation"])
        self.assertIn("**Current Goal**", last_message["content"])
        self.assertIn("**Missing Decisions**", last_message["content"])
        self.assertIn("**Next Concrete Step**", last_message["content"])
        self.assertNotEqual(last_message["content"].strip(), "I prepared the next step.")

    def test_assist_mixed_design_build_request_returns_planning_gate(self):
        service = self._service(
            [
                {
                    "message": "Kalulu wants to confirm the workflow and storage model before writing the Versa implementation.",
                    "confidence": "Medium",
                    "response_mode": "planning",
                    "planning": {
                        "currentGoal": "Turn the request into a validated implementation plan before generating artifacts.",
                        "missingDecisions": ["data shape for storage and records"],
                        "nextStep": "Confirm the plan details or answer the missing decisions, then I can produce the build-ready artifact.",
                    },
                    "next_step": "Confirm the plan details or answer the missing decisions, then I can produce the build-ready artifact.",
                },
            ]
        )
        payload = service.assist(
            "zulan",
            "Create a Versa menu-driven CLI with VDB storage and fully designed UX for employee check in and check out",
            current_screen="/services",
        )
        self.assertEqual(payload["inspectDetails"]["responseMode"], "planning")
        self.assertIsNone(payload["artifact"])
        self.assertIn("**Current Goal**", payload["message"])
        self.assertIn("**Next Concrete Step**", payload["message"])

    def test_confirmation_phrase_advances_past_plan_gate(self):
        service = self._service(
            [
                {
                    "message": "Kalulu wants to confirm the workflow before generating the draft.",
                    "summary": "Planning response prepared before artifact generation.",
                    "confidence": "Medium",
                    "response_mode": "planning",
                    "content_type": "plan",
                    "planning": {
                        "currentGoal": "Turn the request into a validated implementation plan before generating artifacts.",
                        "missingDecisions": ["data shape for storage and records"],
                        "nextStep": "Confirm the plan details or answer the missing decisions, then I can produce the build-ready artifact.",
                    },
                    "next_step": "Confirm the plan details or answer the missing decisions, then I can produce the build-ready artifact.",
                },
                {
                    "message": "Kalulu prepared the validated draft path.",
                    "summary": "Draft ready for review.",
                    "confidence": "High",
                    "content_type": "analysis",
                    "artifact": {
                        "kind": "vi-script",
                        "path": "attendance_checkin.versa",
                        "versaSource": "print(\"ok\");",
                    },
                }
            ]
        )
        thread = service.create_thread("zulan")
        first = service.send_message(
            thread["id"],
            "zulan",
            "Create a Versa menu-driven CLI with VDB storage and fully designed UX for employee check in and check out",
            current_screen="/services",
        )
        self.assertEqual(first["messages"][-1]["contentType"], "plan")

        second = service.send_message(first["id"], "zulan", "yes lets proceed", current_screen="/services")
        self.assertNotEqual(second["messages"][-1]["contentType"], "plan")
        self.assertEqual(second["messages"][-1]["inspectDetails"]["responseMode"], "artifact")
        self.assertFalse(second["metadata"]["planState"]["awaitingConfirmation"])

    def test_simple_versa_request_recovers_direct_artifact_and_skips_planning_handoff(self):
        service = self._service(
            [
                {
                    "message": "Kalulu wants to confirm the exact outcome before drafting the script.",
                    "confidence": "Medium",
                    "response_mode": "planning",
                    "content_type": "plan",
                    "planning": {
                        "currentGoal": "Confirm the final script behavior before drafting.",
                        "missingDecisions": ["exact greeting behavior"],
                        "nextStep": "Confirm the exact outcome you want next so the draft can be tightened into a concrete action.",
                    },
                    "handoff": {"agent": "Ananse", "reason": "Add another perspective before drafting."},
                },
                {
                    "message": "Kalulu prepared the greeting script.",
                    "confidence": "High",
                    "artifact": {
                        "kind": "vi-script",
                        "title": "Greeting Prompt",
                        "path": "scratch/greet_user.versa",
                        "versaSource": 'let name = input("What is your name? ");\nprint("Hello, " + name + "!");',
                    },
                },
            ]
        )
        thread = service.create_thread("zulan")

        with patch("app.verse.service.validate_versa_source", return_value={"ok": True, "error": "", "path": "scratch/greet_user.versa"}):
            updated = service.send_message(
                thread["id"],
                "zulan",
                "can you write me a versa source file that just asks the user for their name and prints a greeting",
                current_screen="/verse-ai",
                platform_context={"pathname": "/verse-ai"},
            )

        self.assertEqual(len(updated["messages"]), 2)
        last_message = updated["messages"][-1]
        self.assertEqual(last_message["agentDisplayName"], "Kalulu")
        self.assertEqual(last_message["inspectDetails"]["responseMode"], "artifact")
        self.assertEqual(last_message["inspectDetails"]["handoffChain"], [])
        self.assertEqual(last_message["artifact"]["kind"], "vi-script")
        self.assertEqual(last_message["artifact"]["path"], "scratch/greet_user.versa")
        self.assertEqual(last_message["artifact"]["status"], "validated")
        self.assertNotIn("Confirm the exact outcome you want next", last_message["content"])

    def test_pending_plan_follow_up_is_provider_generated_not_local_template(self):
        service = self._service(
            [
                {
                    "message": "Kalulu wants to confirm the workflow before generating the draft.",
                    "summary": "Planning response prepared before artifact generation.",
                    "confidence": "Medium",
                    "response_mode": "planning",
                    "content_type": "plan",
                    "planning": {
                        "currentGoal": "Turn the request into a validated implementation plan before generating artifacts.",
                        "missingDecisions": ["data shape for storage and records"],
                        "nextStep": "Confirm the plan details or answer the missing decisions, then I can produce the build-ready artifact.",
                    },
                    "next_step": "Confirm the plan details or answer the missing decisions, then I can produce the build-ready artifact.",
                },
                {
                    "message": "Kalulu greets the user and briefly reminds them the attendance workflow is still waiting for confirmation.",
                    "summary": "Plan still awaiting confirmation.",
                    "confidence": "Medium",
                    "response_mode": "planning",
                    "content_type": "plan",
                    "planning": {
                        "currentGoal": "Turn the request into a validated implementation plan before generating artifacts.",
                        "missingDecisions": ["data shape for storage and records"],
                        "nextStep": "Confirm the workflow if you want me to build it, or ask for a different direction.",
                    },
                    "next_step": "Confirm the workflow if you want me to build it, or ask for a different direction.",
                },
            ]
        )
        thread = service.create_thread("zulan")
        first = service.send_message(
            thread["id"],
            "zulan",
            "Create a Versa menu-driven CLI with VDB storage and fully designed UX for employee check in and check out",
            current_screen="/services",
        )
        second = service.send_message(first["id"], "zulan", "hi", current_screen="/services")
        self.assertIn("greets the user", second["messages"][-1]["content"])
        self.assertNotIn("I already have the plan staged", second["messages"][-1]["content"])

    def test_learning_record_serializes_enforcement_details(self):
        service = self._service([])
        saved = service._capture_learning_record(
            category="wrong-output-failure",
            source="test",
            issue="Verse returned an invalid artifact.",
            resolution="Return a planning response when the request is under-specified.",
            page_kind="vi-portal",
            artifact_kind="vi-script",
            trigger_pattern="menu-driven cli",
            wrong_behavior="Returned runnable code too early.",
            correct_behavior="Gate on planning first.",
            enforcement_rule="mixed-design-build => planning",
        )
        self.assertEqual(saved["triggerPattern"], "menu-driven cli")
        self.assertEqual(saved["enforcementRule"], "mixed-design-build => planning")

    def test_local_route_selects_context_files_without_collaborators(self):
        service = self._service([])
        scaffold = service._scaffold()
        routed = service._route_turn_with_index(
            scaffold,
            username="zulan",
            user_text="Build a Versa employee attendance CLI with VDB",
            current_screen="/services",
            page_kind="service-manager",
            desired_kind="vi-script",
        )
        self.assertEqual(routed["leadAgentId"], "liwiro-architect")
        self.assertEqual(routed["supportingAgentIds"], [])
        self.assertIn("domains/versa-vdb-employee-cli", routed["contextFileIds"])
        self.assertEqual(routed["inspect"]["selection"], "local-router")

    def test_assist_can_return_primary_card_supporting_blocks_and_contributors(self):
        service = self._service(
            [
                {
                    "message": "Ananse prepared the analysis summary.",
                    "confidence": "High",
                    "capabilityId": "ananse-analysis",
                    "contributors": [{"agentId": "liwiro-documentation-advisor", "displayName": "Nzou", "role": "summary"}],
                    "primaryCard": {"type": "chart-card", "title": "Attendance Trend", "description": "Shift punctuality by day."},
                    "supportingBlocks": [{"type": "checklist", "title": "Follow-ups", "items": ["Review late arrivals", "Inspect shift anomalies"]}],
                    "artifact": {"kind": "ananse-analysis", "datasetId": "attendance-dataset", "analysis": {"datasetId": "attendance-dataset"}},
                    "visualization": {
                        "title": "Attendance Trend",
                        "type": "bar-chart",
                        "description": "Shift punctuality by day.",
                        "chart": {"chartType": "bar-chart", "data": [{"day": "Mon", "value": 4}]},
                        "metrics": [{"label": "Late arrivals", "value": 4}],
                    },
                },
            ]
        )
        payload = service.assist("zulan", "Analyze attendance patterns", current_screen="/ananse-workbench")
        self.assertEqual(payload["primaryCard"]["type"], "chart-card")
        self.assertEqual(payload["supportingBlocks"][0]["type"], "checklist")
        self.assertEqual(payload["contributors"][0]["displayName"], "Nzou")

    def test_valid_mind_share_write_is_appended(self):
        service = self._service(
            [
                {
                    "message": "Nzou documented the durable outcome.",
                    "summary": "Documented thread outcome.",
                    "confidence": "High",
                    "content_type": "summary",
                    "mind_share_writes": [
                        {
                            "file": "thread-summaries.md",
                            "content_type": "Summary",
                            "basis": "thread outcome and design discussion",
                            "confidence": "High",
                            "content": "The service boundary decision was recorded for future retrieval.",
                        }
                    ],
                }
            ]
        )
        thread = service.create_thread("zulan")
        updated = service.send_message(thread["id"], "zulan", "@Nzou record this architecture outcome")
        self.assertEqual(len(updated["mindShareWrites"]), 1)
        self.assertIn("thread-summaries.md", updated["mindShareWrites"][0]["file"])
        content = (self.verse_root / "mind-share" / "thread-summaries.md").read_text(encoding="utf-8")
        self.assertIn("The service boundary decision was recorded for future retrieval.", content)

    def test_valid_handoff_triggers_second_agent_response(self):
        service = self._service(
            [
                {
                    "message": "Kalulu sees architecture and reliability overlap.",
                    "summary": "Architecture review identified a runtime risk.",
                    "confidence": "High",
                    "content_type": "analysis",
                    "handoff": {
                        "agent": "Ntiili",
                        "reason": "Retry and timeout concerns need reliability review.",
                    },
                },
                {
                    "message": "Ntiili recommends explicit retries, observability, and rollback checks.",
                    "summary": "Reliability concerns are now captured.",
                    "confidence": "High",
                    "content_type": "analysis",
                },
            ]
        )
        thread = service.create_thread("zulan")
        updated = service.send_message(thread["id"], "zulan", "Design the billing API and check retry safety")
        self.assertEqual(updated["activeAgentId"], "liwiro-reliability-advisor")
        self.assertEqual(len(updated["messages"]), 4)
        self.assertEqual(updated["messages"][1]["agentDisplayName"], "Kalulu")
        self.assertEqual(updated["messages"][3]["agentDisplayName"], "Ntiili")
        self.assertEqual(len(updated["handoffs"]), 1)

    def test_explicit_invite_route_generates_specialist_reply(self):
        service = self._service(
            [
                {
                    "message": "Ananse added the stock velocity metrics to watch first.",
                    "summary": "Ananse contributed specialist metrics guidance.",
                    "confidence": "High",
                    "content_type": "analysis",
                }
            ]
        )
        thread = service.create_thread("zulan")
        updated = service.invite_agent(thread["id"], "zulan", "liwiro-analyst", reason="Assess stock metrics")
        self.assertGreaterEqual(len(updated["messages"]), 2)
        self.assertEqual(updated["messages"][1]["agentDisplayName"], "Ananse")

    def test_failed_invited_specialist_still_emits_visible_blocked_reply(self):
        service = self._service(
            [
                {
                    "message": "Kalulu sees architecture and reliability overlap.",
                    "summary": "Architecture review identified a runtime risk.",
                    "confidence": "High",
                    "content_type": "analysis",
                    "handoff": {
                        "agent": "Ntiili",
                        "reason": "Retry and timeout concerns need reliability review.",
                    },
                }
            ]
        )
        thread = service.create_thread("zulan")
        with patch.object(service, "_generate_for_agent") as generate_mock:
            generate_mock.side_effect = [
                {
                    "message": {
                        "id": "primary-message",
                        "role": "agent",
                        "content": "Kalulu sees architecture and reliability overlap.",
                        "agentDisplayName": "Kalulu",
                        "artifact": None,
                    },
                    "summary": "Architecture review identified a runtime risk.",
                    "mind_share_writes": [],
                    "handoffs": [],
                    "handoff_target": "liwiro-reliability-advisor",
                    "handoff_reason": "Retry and timeout concerns need reliability review.",
                },
                RuntimeError("provider timeout"),
            ]
            updated = service.send_message(thread["id"], "zulan", "Design the billing API and check retry safety")

        self.assertEqual(updated["messages"][-1]["role"], "agent")
        self.assertEqual(updated["messages"][-1]["agentDisplayName"], "Ntiili")
        self.assertEqual(updated["messages"][-1]["confidence"], "Blocked")
        self.assertIn("provider timeout", updated["messages"][-1]["content"])

    def test_list_threads_defaults_to_portal_and_dock_scopes(self):
        service = self._service([])
        portal_thread = service.create_thread("zulan", title="Portal Thread", thread_scope="portal")
        dock_thread = service.create_thread("zulan", title="Dock Thread", thread_scope="dock")

        listed = service.list_threads("zulan")

        self.assertEqual({item["id"] for item in listed}, {portal_thread["id"], dock_thread["id"]})

    def test_store_thread_cache_reuses_parsed_thread_between_reads(self):
        service = self._service([])
        thread = service.create_thread("zulan", title="Cached Thread")
        fresh_store = verse_store_module.VerseStore(self.store_dir)

        with patch.object(verse_store_module, "read_bson_value", wraps=verse_store_module.read_bson_value) as read_mock:
            first = fresh_store.load_thread(thread["id"])
            second = fresh_store.load_thread(thread["id"])

        self.assertEqual(read_mock.call_count, 1)
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(first.thread_id, second.thread_id)
        self.assertIsNot(first, second)

    def test_store_notification_cache_reuses_payload_between_reads(self):
        service = self._service([])
        service.store.save_notification(
            {
                "username": "zulan",
                "agent_id": "liwiro-architect",
                "title": "Cached notification",
                "body": "Watch the service queue.",
            }
        )
        fresh_store = verse_store_module.VerseStore(self.store_dir)

        with patch.object(verse_store_module, "read_bson_value", wraps=verse_store_module.read_bson_value) as read_mock:
            first = fresh_store.list_notifications("zulan")
            second = fresh_store.list_notifications("zulan")

        self.assertEqual(read_mock.call_count, 1)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["title"], second[0]["title"])

    def test_list_proactive_notifications_batches_agent_and_thread_enrichment(self):
        service = self._service([])
        first_thread = service.create_thread("zulan", title="First proactive thread")
        second_thread = service.create_thread("zulan", title="Second proactive thread")
        service.store.save_notification(
            {
                "username": "zulan",
                "thread_id": first_thread["id"],
                "agent_id": "liwiro-architect",
                "title": "First issue",
                "body": "First body",
            }
        )
        service.store.save_notification(
            {
                "username": "zulan",
                "thread_id": second_thread["id"],
                "agent_id": "liwiro-architect",
                "title": "Second issue",
                "body": "Second body",
            }
        )

        with patch.object(service, "list_agents", wraps=service.list_agents) as list_agents_mock, patch.object(
            service.store,
            "thread_summary",
            wraps=service.store.thread_summary,
        ) as thread_summary_mock:
            payload = service.list_proactive_notifications("zulan", run_scheduler=False)

        self.assertEqual(list_agents_mock.call_count, 1)
        self.assertEqual(thread_summary_mock.call_count, 2)
        self.assertEqual(len(payload["items"]), 2)

    def test_assist_can_return_service_builder_artifact(self):
        service = self._service(
            [
                {
                    "message": "Kalulu prepared a complete LAPIS draft for the current service.",
                    "confidence": "High",
                    "artifact": {
                        "kind": "service-builder-lapis",
                        "modePreference": "structured",
                        "lapisConfig": {
                            "metadata": {"apiName": "BillingService", "basePath": "/api/billing", "version": "1.0.0"},
                            "auth": {"enabled": True},
                            "models": {},
                            "sharedModules": {},
                            "modules": [],
                            "endpoints": {},
                        },
                    },
                }
            ]
        )
        response = service.assist(
            "zulan",
            "Create a billing service config",
            current_screen="/service-builder",
            platform_context={"pathname": "/service-builder", "pageKind": "service-builder"},
        )
        self.assertEqual(response["agent"]["id"], "liwiro-architect")
        self.assertEqual(response["artifact"]["kind"], "service-builder-lapis")
        self.assertEqual(response["artifact"]["lapisConfig"]["metadata"]["apiName"], "BillingService")
        self.assertTrue(
            any(
                str(trace.get("source") or "").endswith("liwiro/verse/liwiro-platform-reference/reference.json")
                for trace in response["retrievalTrace"]
            )
        )

    def test_assist_normalizes_crud_aliases_in_service_builder_artifact(self):
        service = self._service(
            [
                {
                    "message": "Kalulu prepared the service draft for the fashion-house project workspace.",
                    "confidence": "High",
                    "artifact": {
                        "kind": "service-builder-lapis",
                        "title": "Fashion House Project Management Service",
                        "lapisConfig": {
                            "metadata": {"apiName": "fashion-project-service", "basePath": "/api/fashion-project", "version": "1.0.0"},
                            "auth": {"enabled": False},
                            "models": {
                                "projects": {
                                    "name": "Projects",
                                    "collection": "projects",
                                    "fields": {
                                        "name": {"type": "string", "required": True},
                                        "status": {"type": "string"},
                                    },
                                }
                            },
                            "sharedModules": {},
                            "modules": [],
                            "endpoints": {
                                "listProjects": {
                                    "method": "GET",
                                    "path": "/projects",
                                    "operationType": "crud",
                                    "crudOperation": "READ_MANY",
                                    "linkedModel": "projects",
                                }
                            },
                        },
                    },
                }
            ]
        )
        response = service.assist(
            "zulan",
            "project management service for a fashion house",
            current_screen="/service-builder",
            platform_context={"pathname": "/service-builder", "pageKind": "service-builder"},
        )
        endpoint = response["artifact"]["lapisConfig"]["endpoints"]["listProjects"]
        self.assertEqual(response["artifact"]["status"], "validated")
        self.assertEqual(endpoint["crudOperation"], "read")

    def test_assist_hydrates_incomplete_service_builder_artifact(self):
        service = self._service(
            [
                {
                    "message": "Kalulu prepared a budget tracker service draft.",
                    "confidence": "High",
                    "artifact": {
                        "kind": "service-builder-lapis",
                        "title": "Budget Tracker API Definition",
                        "lapisConfig": {
                            "models": {},
                            "endpoints": {},
                        },
                    },
                },
                {
                    "message": "I repaired the service draft so it is ready for the builder.",
                    "confidence": "High",
                    "artifact": {
                        "kind": "service-builder-lapis",
                        "title": "Budget Tracker API Definition",
                        "lapisConfig": {
                            "metadata": {"apiName": "budget-tracker-api", "basePath": "/api/budget-tracker", "version": "1.0.0"},
                            "auth": {"enabled": False},
                            "models": {
                                "transactions": {
                                    "name": "Transactions",
                                    "collection": "transactions",
                                    "fields": {
                                        "amount": {"id": "amount", "name": "amount", "type": "number", "required": True},
                                    },
                                },
                            },
                            "sharedModules": {},
                            "modules": [],
                            "endpoints": {
                                "list_transactions": {
                                    "method": "GET",
                                    "path": "/transactions",
                                    "operationType": "crud",
                                    "crudOperation": "read",
                                    "linkedModel": "transactions",
                                },
                            },
                        },
                    },
                }
            ]
        )
        response = service.assist(
            "zulan",
            "build a simple microservice backend for budget tracker app",
            current_screen="/service-builder",
            platform_context={"pathname": "/service-builder", "pageKind": "service-builder"},
        )
        metadata = response["artifact"]["lapisConfig"]["metadata"]
        self.assertEqual(response["artifact"]["applyLabel"], "Open in Service Builder")
        self.assertEqual(response["artifact"]["executeLabel"], "Create Service")
        self.assertEqual(response["artifact"]["status"], "repaired")
        self.assertEqual(metadata["apiName"], "budget-tracker-api")
        self.assertEqual(metadata["basePath"], "/api/budget-tracker")
        self.assertEqual(metadata["version"], "1.0.0")
        self.assertTrue(response["artifact"]["lapisConfig"]["models"])
        self.assertTrue(response["artifact"]["lapisConfig"]["endpoints"])

    def test_assist_retries_for_missing_versa_artifact(self):
        service = self._service(
            [
                {
                    "message": "Kalulu described the ledger approach but forgot the draft.",
                    "confidence": "Medium",
                },
                {
                    "message": "I prepared a Versa ledger draft for VCMTE.HIVE.",
                    "confidence": "High",
                    "artifact": {
                        "kind": "vi-script",
                        "path": "scratch/vcmte_hive_blockchain.versa",
                        "versaSource": 'let ledger_name = "VCMTE.HIVE";\nprint(ledger_name);',
                    },
                },
            ]
        )
        response = service.assist(
            "zulan",
            "create an example blockchain implementation in versa for sharing untemperable trafic data for a platform called VCMTE.HIVE",
            current_screen="/verse-ai",
            platform_context={"pathname": "/verse-ai"},
        )
        self.assertEqual(response["artifact"]["kind"], "vi-script")
        self.assertEqual(response["artifact"]["targetPage"], "/vi-portal")
        self.assertIn("vcmte_hive_blockchain.versa", response["artifact"]["path"])
        self.assertIn('VCMTE.HIVE', response["artifact"]["versaSource"])

    def test_assist_simple_versa_request_forces_artifact_instead_of_planning(self):
        service = self._service(
            [
                {
                    "message": "Kalulu wants to confirm the exact outcome before writing the script.",
                    "confidence": "Medium",
                    "response_mode": "planning",
                    "planning": {
                        "currentGoal": "Confirm the final script behavior before drafting.",
                        "missingDecisions": ["exact greeting behavior"],
                        "nextStep": "Confirm the exact outcome you want next so the draft can be tightened into a concrete action.",
                    },
                },
                {
                    "message": "Kalulu prepared the greeting script.",
                    "confidence": "High",
                    "artifact": {
                        "kind": "vi-script",
                        "title": "Greeting Prompt",
                        "path": "scratch/greet_user.versa",
                        "versaSource": 'let name = input("What is your name? ");\nprint("Hello, " + name + "!");',
                    },
                },
            ]
        )
        with patch("app.verse.service.validate_versa_source", return_value={"ok": True, "error": "", "path": "scratch/greet_user.versa"}):
            response = service.assist(
                "zulan",
                "write a versa source file that just asks the user for their name and prints a greeting",
                current_screen="/verse-ai",
                platform_context={"pathname": "/verse-ai"},
            )

        self.assertEqual(response["inspectDetails"]["responseMode"], "artifact")
        self.assertEqual(response["artifact"]["kind"], "vi-script")
        self.assertEqual(response["artifact"]["path"], "scratch/greet_user.versa")
        self.assertNotIn("**Current Goal**", response["message"])

    def test_assist_recovers_wrong_service_artifact_for_ephemeral_cli_request(self):
        service = self._service(
            [
                {
                    "message": "Kalulu prepared a service draft for the game.",
                    "confidence": "Medium",
                    "artifact": {
                        "kind": "service-builder-lapis",
                        "lapisConfig": {
                            "metadata": {"apiName": "mad-libs-service", "basePath": "/api/mad-libs", "version": "1.0.0"},
                            "auth": {"enabled": False},
                            "models": {},
                            "sharedModules": {},
                            "modules": [],
                            "endpoints": {},
                        },
                    },
                },
                {
                    "message": "I prepared the ephemeral Versa game draft for VI.",
                    "confidence": "High",
                    "artifact": {
                        "kind": "vi-script",
                        "path": "scratch/mad_libs_game.versa",
                        "versaSource": 'let noun = "zebra";\nprint("Welcome to Mad Libs");\nprint(noun);',
                    },
                },
            ]
        )
        response = service.assist(
            "zulan",
            "lets create an ephemeral cli based game",
            current_screen="/verse-ai",
            platform_context={"pathname": "/verse-ai"},
        )
        self.assertEqual(response["artifact"]["kind"], "vi-script")
        self.assertEqual(response["artifact"]["targetPage"], "/vi-portal")
        self.assertIn("mad_libs_game.versa", response["artifact"]["path"])

    def test_assist_keeps_cross_page_versa_artifact_from_service_builder_request(self):
        service = self._service(
            [
                {
                    "message": "Kalulu prepared the Versa game draft for VI.",
                    "confidence": "High",
                    "artifact": {
                        "kind": "vi-script",
                        "path": "scratch/mad_libs.versa",
                        "versaSource": 'let adjective = "wild";\nprint(adjective);',
                    },
                }
            ]
        )
        response = service.assist(
            "zulan",
            "a versa script based game",
            current_screen="/service-builder",
            platform_context={"pathname": "/service-builder", "pageKind": "service-builder"},
        )
        self.assertEqual(response["artifact"]["kind"], "vi-script")
        self.assertEqual(response["artifact"]["targetPage"], "/vi-portal")

    def test_assist_repairs_versa_comment_syntax_before_presenting_artifact(self):
        service = self._service(
            [
                {
                    "message": "Kalulu prepared the traffic ledger draft.",
                    "confidence": "High",
                    "artifact": {
                        "kind": "vi-script",
                        "path": "examples/blockchain/zcmte_hive.versa",
                        "versaSource": 'let network = "ZCMTE.HIVE";\n// invalid comment style\nprint(network);',
                    },
                }
            ]
        )
        response = service.assist(
            "zulan",
            "create a blockchain example in versa for traffic data in Zambia",
            current_screen="/vi-portal",
            platform_context={"pathname": "/vi-portal", "pageKind": "vi-portal"},
        )
        self.assertEqual(response["artifact"]["status"], "validated")
        self.assertIn("# invalid comment style", response["artifact"]["versaSource"])
        self.assertNotIn("// invalid comment style", response["artifact"]["versaSource"])

    def test_assist_assigns_saveable_path_and_save_execute_label_for_vi_script(self):
        service = self._service(
            [
                {
                    "message": "Kalulu prepared the Mad Libs draft for VI.",
                    "confidence": "High",
                    "artifact": {
                        "kind": "vi-script",
                        "title": "Mad Libs CLI Game",
                        "path": "",
                        "versaSource": 'let noun = "zebra";\nprint(noun);',
                    },
                }
            ]
        )
        with patch("app.verse.service.validate_versa_source", return_value={"ok": True, "error": "", "path": "scratch/mad-libs-cli-game.versa"}):
            response = service.assist(
                "zulan",
                "create a mad libs cli game in versa",
                current_screen="/vi-portal",
                platform_context={"pathname": "/vi-portal", "pageKind": "vi-portal"},
            )
        artifact = response["artifact"]
        self.assertEqual(artifact["kind"], "vi-script")
        self.assertEqual(artifact["path"], "scratch/mad-libs-cli-game.versa")
        self.assertEqual(artifact["applyLabel"], "")
        self.assertEqual(artifact["executeLabel"], "Run")
        self.assertEqual(artifact["saveExecuteLabel"], "Save and Run")

    def test_assist_keeps_retrying_versa_until_parser_valid(self):
        service = self._service(
            [
                {
                    "message": "Kalulu prepared the first draft.",
                    "confidence": "High",
                    "artifact": {
                        "kind": "vi-script",
                        "path": "scratch/animal-mad-libs.versa",
                        "versaSource": 'let story = f"bad";',
                    },
                },
                {
                    "message": "Kalulu rewrote the draft.",
                    "confidence": "High",
                    "artifact": {
                        "kind": "vi-script",
                        "path": "scratch/animal-mad-libs.versa",
                        "versaSource": 'let story = f"still bad";',
                    },
                },
                {
                    "message": "Kalulu repaired the script and validated it.",
                    "confidence": "High",
                    "artifact": {
                        "kind": "vi-script",
                        "path": "scratch/animal-mad-libs.versa",
                        "versaSource": 'let adjective = "wild";\nlet animal = "zebra";\nlet story = "The " + adjective + " " + animal + "!";\nprint(story);',
                    },
                },
            ]
        )
        with patch(
            "app.verse.service.validate_versa_source",
            side_effect=[
                {"ok": False, "error": "Unexpected token", "path": "scratch/animal-mad-libs.versa"},
                {"ok": False, "error": "Unexpected token", "path": "scratch/animal-mad-libs.versa"},
                {"ok": True, "error": "", "path": "scratch/animal-mad-libs.versa"},
            ],
        ):
            response = service.assist(
                "zulan",
                "hey lets create a versa script mad libs game about animals",
                current_screen="/vi-portal",
                platform_context={"pathname": "/vi-portal", "pageKind": "vi-portal"},
            )
        self.assertEqual(response["artifact"]["kind"], "vi-script")
        self.assertEqual(response["artifact"]["status"], "repaired")
        self.assertTrue(response["artifact"]["validation"]["valid"])
        self.assertIn('let story = "The " + adjective + " " + animal + "!";', response["artifact"]["versaSource"])

    def test_assist_blocks_invalid_versa_script_when_parser_rejects_it(self):
        service = self._service(
            [
                {
                    "message": "Kalulu prepared the draft.",
                    "confidence": "High",
                    "artifact": {
                        "kind": "vi-script",
                        "path": "scratch/bad-script.versa",
                        "versaSource": "let p = ;",
                    },
                },
                *[
                    {
                        "message": "Kalulu retried the draft, but the parser still rejected it.",
                        "confidence": "High",
                        "artifact": {
                            "kind": "vi-script",
                            "path": "scratch/bad-script.versa",
                            "versaSource": "let p = ;",
                        },
                    }
                    for _ in range(2)
                ],
            ]
        )
        with patch.object(VerseService, "_invalid_artifact_retry_budget", return_value=2), patch(
            "app.verse.service.validate_versa_source",
            return_value={"ok": False, "error": "Unexpected token near line 1", "path": "scratch/bad-script.versa"},
        ):
            response = service.assist(
                "zulan",
                "create a broken versa script",
                current_screen="/vi-portal",
                platform_context={"pathname": "/vi-portal", "pageKind": "vi-portal"},
        )
        self.assertEqual(response["artifact"]["kind"], "vi-script")
        self.assertEqual(response["artifact"]["status"], "blocked")
        self.assertIn("Unexpected token", response["artifact"]["validation"]["issues"][0])
        details = response["artifact"]["validation"].get("details") or []
        self.assertEqual(details[0]["path"], "scratch/bad-script.versa")
        self.assertEqual(details[0]["errorLines"], [1])

    def test_assist_repairs_noncanonical_versa_function_keyword_before_validation(self):
        service = self._service(
            [
                {
                    "message": "Kalulu prepared the draft.",
                    "confidence": "High",
                    "artifact": {
                        "kind": "vi-script",
                        "path": "scratch/function-keyword.versa",
                        "versaSource": 'fn greet(name) {\n  print("Hello, " + name);\n}\ngreet("Zulan");',
                    },
                }
            ]
        )
        with patch("app.verse.service.validate_versa_source", return_value={"ok": True, "error": "", "path": "scratch/function-keyword.versa"}) as validate_mock:
            response = service.assist(
                "zulan",
                "create a versa greeting script",
                current_screen="/vi-portal",
                platform_context={"pathname": "/vi-portal", "pageKind": "vi-portal"},
            )

        self.assertEqual(response["artifact"]["status"], "validated")
        self.assertIn("func greet(name)", response["artifact"]["versaSource"])
        self.assertNotIn("fn greet", response["artifact"]["versaSource"])
        self.assertIn("func greet(name)", validate_mock.call_args.args[0])

    def test_follow_up_revalidates_reused_versa_artifact_before_returning(self):
        service = self._service(
            [
                {
                    "message": "Kalulu prepared the first draft.",
                    "confidence": "High",
                    "artifact": {
                        "kind": "vi-script",
                        "path": "scratch/legacy-script.versa",
                        "versaSource": 'let value = "ok";\nprint(value);',
                    },
                },
                {
                    "message": "Here is the card again.",
                    "confidence": "High",
                },
            ]
        )
        thread = service.create_thread("zulan")
        first = service.send_message(thread["id"], "zulan", "create a versa script", current_screen="/vi-portal")
        stored_thread = service.store.load_thread(first["id"])
        stored_thread.messages[-1]["artifact"] = {
            "kind": "vi-script",
            "path": "scratch/legacy-script.versa",
            "versaSource": 'let value = "ok";\nprint(value);',
        }
        service.store.save_thread(stored_thread)

        with patch("app.verse.service.validate_versa_source", return_value={"ok": True, "error": "", "path": "scratch/legacy-script.versa"}) as validate_mock:
            updated = service.send_message(first["id"], "zulan", "give me the program card", current_screen="/vi-portal")

        self.assertTrue(validate_mock.called)
        self.assertEqual(updated["messages"][-1]["artifact"]["kind"], "vi-script")
        self.assertEqual(updated["messages"][-1]["artifact"]["status"], "validated")
        self.assertTrue(updated["messages"][-1]["artifact"]["validation"]["valid"])

    def test_vi_script_retry_budget_is_ten(self):
        service = self._service([])
        self.assertEqual(service._invalid_artifact_retry_budget("vi-script"), 10)

    def test_user_correction_creates_learning_record(self):
        service = self._service(
            [
                {
                    "message": "Kalulu corrected the draft.",
                    "summary": "Correction applied.",
                    "confidence": "High",
                    "content_type": "analysis",
                }
            ]
        )
        thread = service.create_thread("zulan")
        service.send_message(thread["id"], "zulan", "single line comments in versa are # and not //", current_screen="/vi-portal")
        learning_records = service.store.list_learning_records()
        self.assertTrue(any("single-line comments" in record["issue"].lower() for record in learning_records))

    def test_thread_message_repair_reasoning_leak_in_visible_chat(self):
        service = self._service(
            [
                {
                    "message": "\" and JSON format.*\n\n*   *One more thing*: The user said \"fill me in\". I should explain the design.\n*   Single service: `inventory-api`.\n*   State: Managed via a simple map for now.\n*   Operations: CRUD plus stock updates.",
                    "summary": "Inventory API design overview.",
                    "confidence": "Medium",
                    "content_type": "analysis",
                }
            ]
        )
        thread = service.create_thread("zulan")
        updated = service.send_message(thread["id"], "zulan", "fill me in")
        reply = updated["messages"][1]["content"]
        self.assertNotIn("The user said", reply)
        self.assertNotIn("I should explain", reply)
        self.assertIn("inventory-api", reply)

    def test_thread_message_hides_raw_structured_blob_and_keeps_artifact(self):
        service = self._service(
            [
                {
                    "message": "{\"metadata\":{\"apiName\":\"ZShop\"}}",
                    "summary": "Prepared a service draft for zshop.",
                    "confidence": "High",
                    "content_type": "analysis",
                    "artifact": {
                        "kind": "service-builder-lapis",
                        "lapisConfig": {
                            "metadata": {"apiName": "ZShop", "basePath": "/api/zshop", "version": "1.0.0"},
                            "auth": {"enabled": False},
                            "models": {},
                            "sharedModules": {},
                            "modules": [],
                            "endpoints": {},
                        },
                    },
                }
            ]
        )
        thread = service.create_thread("zulan")
        updated = service.send_message(thread["id"], "zulan", "Create the zshop service")
        reply = updated["messages"][1]
        self.assertNotIn("{\"metadata\"", reply["content"])
        self.assertEqual(reply["artifact"]["kind"], "service-builder-lapis")
        self.assertIn("service draft", reply["content"].lower())

    def test_create_dataset_and_analysis_support_multiple_chart_types(self):
        service = self._service([])
        dataset = service.create_dataset(
            "zulan",
            title="Revenue by region",
            raw_text="date,region,revenue\n2026-01-01,North,120\n2026-01-01,South,90\n2026-02-01,North,160\n2026-02-01,South,110\n",
            filename="revenue.csv",
        )
        self.assertEqual(dataset["rowCount"], 4)
        self.assertEqual(dataset["source"]["format"], "csv")

        line_analysis = service.analyze_dataset(
            dataset["id"],
            "zulan",
            {"chartType": "line", "dimension": "date", "metric": "revenue", "compareBy": "region", "aggregation": "sum"},
        )
        self.assertEqual(line_analysis["chart"]["chartType"], "line")
        self.assertIn("bar", line_analysis["alternateChartTypes"])

        grouped_analysis = service.analyze_dataset(
            dataset["id"],
            "zulan",
            {"chartType": "grouped-bar", "dimension": "date", "metric": "revenue", "compareBy": "region", "aggregation": "sum"},
        )
        self.assertEqual(grouped_analysis["chart"]["chartType"], "grouped-bar")
        self.assertTrue(grouped_analysis["chart"]["data"])
        self.assertIn("confidence", grouped_analysis)
        self.assertIn("presets", grouped_analysis["controls"])

    def test_analysis_falls_back_when_requested_chart_cannot_render_safely(self):
        service = self._service([])
        dataset = service.create_dataset(
            "zulan",
            title="Sparse revenue",
            raw_text="segment,revenue\nNorth,120\nSouth,180\n",
            filename="sparse.csv",
        )
        analysis = service.analyze_dataset(
            dataset["id"],
            "zulan",
            {"chartType": "line", "dimension": "segment", "metric": "revenue"},
        )
        self.assertEqual(analysis["chart"]["status"], "fallback")
        self.assertIn(analysis["chart"]["chartType"], {"table", "metric-list"})
        self.assertTrue(analysis["chart"]["fallbackReason"])

    def test_assist_answers_ability_queries_with_local_profile_payload(self):
        service = self._service([])
        response = service.assist("zulan", "@Ananse what can you do and what skills are you best at?", current_screen="/verse-ai", platform_context={"pathname": "/verse-ai"})
        self.assertEqual(response["agent"]["id"], "liwiro-analyst")
        self.assertIn("Metrics Interpretation", response["message"])
        self.assertEqual(response["provider"]["id"], "local")

    def test_uploaded_dataset_archives_original_file(self):
        service = self._service([])
        dataset = service.create_dataset(
            "zulan",
            title="Simple upload",
            raw_text='[{"day":"Mon","hits":20},{"day":"Tue","hits":32}]',
            filename="traffic.json",
            format_hint="json",
            archive_bytes=b'[{"day":"Mon","hits":20},{"day":"Tue","hits":32}]',
        )
        archived_path = Path(dataset["source"]["archivedPath"])
        self.assertTrue(archived_path.exists())
        self.assertEqual(dataset["source"]["sourceType"], "upload")

    def test_assist_keeps_general_page_artifacts_for_navigation(self):
        service = self._service(
            [
                {
                    "message": "Kalulu prepared a service draft and kept the config out of the chat body.",
                    "confidence": "High",
                    "artifact": {
                        "kind": "service-builder-lapis",
                        "lapisConfig": {
                            "metadata": {"apiName": "BillingService", "basePath": "/api/billing", "version": "1.0.0"},
                            "auth": {"enabled": True},
                            "models": {},
                            "sharedModules": {},
                            "modules": [],
                            "endpoints": {},
                        },
                    },
                }
            ]
        )
        response = service.assist("zulan", "Create a billing service config", current_screen="/verse-ai", platform_context={"pathname": "/verse-ai"})
        self.assertEqual(response["artifact"]["kind"], "service-builder-lapis")
        self.assertEqual(response["artifact"]["targetPage"], "/service-builder")

    def test_assist_can_return_service_manager_artifact(self):
        service = self._service(
            [
                {
                    "message": "Kalulu prepared a stop action for zshop-core.",
                    "confidence": "High",
                    "artifact": {
                        "kind": "service-manager-action",
                        "serviceAction": {
                            "action": "stop",
                            "processId": "8123",
                            "serviceName": "zshop-core",
                        },
                    },
                }
            ]
        )
        response = service.assist(
            "zulan",
            "Stop zshop-core for me",
            current_screen="/services",
            platform_context={"pathname": "/services", "pageKind": "service-manager"},
        )
        self.assertEqual(response["artifact"]["kind"], "service-manager-action")
        self.assertEqual(response["artifact"]["executionMode"], "server")
        self.assertEqual(response["artifact"]["targetPage"], "/services")
        self.assertEqual(response["artifact"]["serviceAction"]["action"], "stop")

    def test_assist_drops_page_mismatched_artifacts(self):
        service = self._service(
            [
                {
                    "message": "Kalulu answered naturally without a page artifact.",
                    "confidence": "Medium",
                    "artifact": {
                        "kind": "vdb-query",
                        "vdbQuery": "read domains",
                    },
                }
            ]
        )
        response = service.assist(
            "zulan",
            "Help with this service design",
            current_screen="/service-builder",
            platform_context={"pathname": "/service-builder", "pageKind": "service-builder"},
        )
        self.assertIsNone(response["artifact"])

    def test_google_provider_factory_requires_api_key(self):
        with self.assertRaises(AIConfigurationError):
            build_ai_provider({"AI_PROVIDER": "google", "GOOGLE_API_KEY": "", "GOOGLE_MODEL": "gemini-3-flash-preview"})

    def test_anthropic_provider_factory_requires_api_key(self):
        with self.assertRaises(AIConfigurationError):
            build_ai_provider({"AI_PROVIDER": "anthropic"})

    def test_anthropic_provider_factory_builds_configured_provider(self):
        provider = build_ai_provider({
            "AI_PROVIDER": "anthropic",
            "ANTHROPIC_API_KEY": "test-key",
            "ANTHROPIC_MODEL": "claude-test",
        })

        self.assertEqual(provider.capabilities().provider, "anthropic")
        self.assertEqual(provider.model, "claude-test")

    def test_openai_provider_factory_requires_api_key(self):
        with self.assertRaises(AIConfigurationError):
            build_ai_provider({"AI_PROVIDER": "openai", "OPENAI_API_KEY": "", "OPENAI_MODEL": "gpt-5-mini"})

    def test_google_provider_posts_expected_payload(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {"parts": [{"text": '{"message":"ok"}'}]},
                }
            ],
            "usageMetadata": {"promptTokenCount": 12},
        }
        with patch("app.verse.providers.google.requests.post", return_value=response) as post:
            provider = GoogleGeminiProvider(api_key="abc", model="gemini-3-flash-preview")
            result = provider.generate(
                request=type(
                    "Req",
                    (),
                    {
                        "system_instruction": "Test instruction",
                        "context_blocks": [],
                        "messages": [type("Msg", (), {"role": "user", "content": "hello"})()],
                        "structured_output_schema": {"type": "object"},
                        "model": "gemini-3-flash-preview",
                        "temperature": 0.1,
                        "max_output_tokens": 128,
                    },
                )()
            )
        self.assertEqual(result.provider, "google")
        self.assertEqual(result.usage["promptTokenCount"], 12)
        call = post.call_args
        self.assertIn("generateContent", call.args[0])
        self.assertEqual(call.kwargs["json"]["generationConfig"]["maxOutputTokens"], 128)
        self.assertEqual(call.kwargs["json"]["contents"][0]["parts"][0]["text"], "hello")

    def test_openai_provider_posts_expected_payload(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "model": "gpt-5-mini",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": '{"message":"ok"}'}],
                }
            ],
            "usage": {"input_tokens": 12, "output_tokens": 8},
        }
        with patch("app.verse.providers.openai.requests.post", return_value=response) as post:
            provider = OpenAIResponsesProvider(api_key="abc", model="gpt-5-mini")
            result = provider.generate(
                request=type(
                    "Req",
                    (),
                    {
                        "system_instruction": "Test instruction",
                        "context_blocks": [],
                        "messages": [type("Msg", (), {"role": "user", "content": "hello"})()],
                        "structured_output_schema": {"type": "object"},
                        "model": "gpt-5-mini",
                        "temperature": 0.1,
                        "max_output_tokens": 128,
                    },
                )()
            )
        self.assertEqual(result.provider, "openai")
        self.assertEqual(result.usage["input_tokens"], 12)
        call = post.call_args
        self.assertEqual(call.args[0], "https://api.openai.com/v1/responses")
        self.assertGreaterEqual(call.kwargs["json"]["max_output_tokens"], 4096)
        self.assertEqual(call.kwargs["json"]["reasoning"]["effort"], "low")
        self.assertEqual(call.kwargs["json"]["input"][0]["content"][0]["type"], "input_text")
        self.assertEqual(call.kwargs["json"]["input"][0]["content"][0]["text"], "hello")
        self.assertEqual(call.kwargs["json"]["text"]["format"]["type"], "json_schema")
        self.assertNotIn("temperature", call.kwargs["json"])

    def test_openai_provider_replays_assistant_history_as_output_text(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "model": "gpt-5-mini",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": '{"message":"ok"}'}],
                }
            ],
            "usage": {"input_tokens": 12, "output_tokens": 8},
        }
        with patch("app.verse.providers.openai.requests.post", return_value=response) as post:
            provider = OpenAIResponsesProvider(api_key="abc", model="gpt-5-mini")
            provider.generate(
                request=type(
                    "Req",
                    (),
                    {
                        "system_instruction": "Test instruction",
                        "context_blocks": [],
                        "messages": [
                            type("Msg", (), {"role": "user", "content": "Write a versa greeting script"})(),
                            type("Msg", (), {"role": "assistant", "content": '{"message":"I prepared the script."}'})(),
                            type("Msg", (), {"role": "user", "content": "Open it in VI Portal"})(),
                        ],
                        "structured_output_schema": {"type": "object"},
                        "model": "gpt-5-mini",
                        "temperature": 0.1,
                        "max_output_tokens": 128,
                    },
                )()
            )
        payload_messages = post.call_args.kwargs["json"]["input"]
        self.assertEqual(payload_messages[0]["role"], "user")
        self.assertEqual(payload_messages[0]["content"][0]["type"], "input_text")
        self.assertEqual(payload_messages[1]["role"], "assistant")
        self.assertEqual(payload_messages[1]["content"][0]["type"], "output_text")
        self.assertEqual(payload_messages[2]["role"], "user")
        self.assertEqual(payload_messages[2]["content"][0]["type"], "input_text")

    def test_proactive_schedule_slots_are_evenly_spaced_from_midnight(self):
        service = self._service([])
        base = datetime(2026, 3, 29, 5, 30, tzinfo=timezone.utc)
        slots = service._schedule_slots_for_day(base, 3)
        self.assertEqual(
            [slot.isoformat() for slot in slots],
            [
                "2026-03-29T00:00:00+00:00",
                "2026-03-29T08:00:00+00:00",
                "2026-03-29T16:00:00+00:00",
            ],
        )
        self.assertEqual(service._next_scheduled_run(base, 3).isoformat(), "2026-03-29T08:00:00+00:00")

    def test_global_proactive_off_prevents_due_evaluations(self):
        service = self._service(
            [
                {
                    "shouldNotify": True,
                    "issueKey": "runtime-health",
                    "title": "Runtime health",
                    "summary": "A runtime issue needs attention.",
                    "message": "I found a runtime health issue.",
                    "confidence": "High",
                    "severity": "high",
                }
            ]
        )
        service.update_user_settings(
            "zulan",
            proactive_mode_enabled=False,
            agent_settings=self._single_proactive_agent_settings(service, "liwiro-architect", level=6),
        )
        result = service.run_due_proactive_evaluations("zulan", force=True, now=datetime(2026, 3, 29, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(result["emitted"], [])
        self.assertEqual(service.list_proactive_notifications("zulan", run_scheduler=False)["items"], [])

    def test_recover_missed_proactive_evaluations_scans_known_users_once(self):
        service = self._service(
            [
                {
                    "shouldNotify": True,
                    "issueKey": "startup-recovery",
                    "title": "Startup recovery",
                    "summary": "A missed proactive slot should be recovered after startup.",
                    "message": "I recovered a proactive finding that was missed while the app was offline.",
                    "confidence": "High",
                    "severity": "high",
                }
            ]
        )
        service.update_user_settings(
            "zulan",
            proactive_mode_enabled=True,
            agent_settings=self._single_proactive_agent_settings(service, "liwiro-architect", level=6),
        )

        first = service.recover_missed_proactive_evaluations(now=datetime(2026, 3, 29, 0, 0, tzinfo=timezone.utc))
        second = service.recover_missed_proactive_evaluations(now=datetime(2026, 3, 29, 0, 0, tzinfo=timezone.utc))

        self.assertEqual(len(first["emitted"]), 1)
        self.assertEqual(second["emitted"], [])
        notifications = service.list_proactive_notifications("zulan", run_scheduler=False)
        self.assertEqual(notifications["unreadCount"], 1)

    def test_proactive_scheduler_reuses_platform_context_and_learning_records_within_run(self):
        provider = _RecordingProvider(
            [
                {
                    "shouldNotify": False,
                    "message": "No issue is worth surfacing right now.",
                },
                {
                    "shouldNotify": False,
                    "message": "No follow-up issue is worth surfacing right now.",
                },
            ]
        )
        platform_calls = {"count": 0}

        def platform_loader(username: str) -> dict:
            platform_calls["count"] += 1
            return {"username": username, "services": [{"apiName": "accounts-api", "status": "RUNNING"}]}

        service = VerseService(
            verse_root=self.verse_root,
            data_dir=self.store_dir,
            provider_config={"AI_PROVIDER": "google", "GOOGLE_API_KEY": "test-key", "GOOGLE_MODEL": "fake-model"},
            provider=provider,
            platform_context_loader=platform_loader,
        )
        enabled_agents = {"liwiro-architect", "liwiro-analyst"}
        service.update_user_settings(
            "zulan",
            proactive_mode_enabled=True,
            agent_settings={
                agent["id"]: {
                    "proactivityEnabled": agent["id"] in enabled_agents,
                    "proactivityLevel": 6 if agent["id"] in enabled_agents else 1,
                }
                for agent in service.list_agents()
            },
        )

        learning_calls = {"count": 0}
        original_list_learning_records = service.store.list_learning_records

        def counted_learning_records():
            learning_calls["count"] += 1
            return original_list_learning_records()

        with patch.object(service.store, "list_learning_records", side_effect=counted_learning_records):
            result = service.run_due_proactive_evaluations("zulan", force=True, now=datetime(2026, 3, 29, 0, 0, tzinfo=timezone.utc))

        self.assertEqual(platform_calls["count"], 1)
        self.assertEqual(learning_calls["count"], 1)
        self.assertEqual(len(provider.requests), 2)
        self.assertEqual(sum(1 for item in result["evaluations"] if item.get("evaluated")), 2)
        self.assertEqual(result["emitted"], [])

    def test_failed_proactive_evaluation_is_retried_instead_of_marked_complete(self):
        service = self._service([])
        service.update_user_settings(
            "zulan",
            proactive_mode_enabled=True,
            agent_settings=self._single_proactive_agent_settings(service, "liwiro-architect", level=6),
        )
        moment = datetime(2026, 3, 29, 0, 0, tzinfo=timezone.utc)
        with patch.object(service, "_evaluate_proactive_agent", side_effect=RuntimeError("provider unavailable")) as evaluate:
            result = service.run_due_proactive_evaluations("zulan", force=False, now=moment)
        self.assertTrue(any(item.get("error") == "provider unavailable" for item in result["evaluations"]))
        state = service.store.load_schedule_state("zulan", "liwiro-architect")
        self.assertEqual(state.last_evaluated_at, "")
        self.assertEqual(evaluate.call_count, 1)

        with patch.object(service, "_evaluate_proactive_agent", return_value=None) as retry:
            service.run_due_proactive_evaluations("zulan", force=False, now=moment)
        self.assertEqual(retry.call_count, 1)
        state = service.store.load_schedule_state("zulan", "liwiro-architect")
        self.assertTrue(state.last_evaluated_at)

    def test_proactive_findings_below_high_severity_are_suppressed(self):
        for username, severity in (("medium-user", "medium"), ("missing-user", None), ("invalid-user", "urgent")):
            with self.subTest(severity=severity):
                response = {
                    "shouldNotify": True,
                    "issueKey": f"{username}-finding",
                    "title": "Routine finding",
                    "summary": "This does not have material impact.",
                    "message": "Review this routine finding when convenient.",
                    "confidence": "High",
                }
                if severity is not None:
                    response["severity"] = severity
                service = self._service([response])
                service.update_user_settings(
                    username,
                    proactive_mode_enabled=True,
                    agent_settings=self._single_proactive_agent_settings(service, "liwiro-architect", level=6),
                )

                result = service.run_due_proactive_evaluations(
                    username,
                    force=True,
                    now=datetime(2026, 3, 29, 0, 0, tzinfo=timezone.utc),
                )

                self.assertEqual(result["emitted"], [])
                self.assertEqual(service.list_proactive_notifications(username, run_scheduler=False)["items"], [])

    def test_proactive_finding_creates_thread_and_notification_with_metadata(self):
        service = self._service(
            [
                {
                    "shouldNotify": True,
                    "issueKey": "api-contract-drift",
                    "title": "API contract drift",
                    "summary": "The generated service shape no longer matches the current draft.",
                    "message": "I found API contract drift between the current service draft and the generated surface.",
                    "confidence": "High",
                    "severity": "high",
                }
            ]
        )
        service.update_user_settings(
            "zulan",
            proactive_mode_enabled=True,
            agent_settings=self._single_proactive_agent_settings(service, "liwiro-architect", level=6),
        )
        result = service.run_due_proactive_evaluations("zulan", force=True, now=datetime(2026, 3, 29, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(len(result["emitted"]), 1)
        notifications = service.list_proactive_notifications("zulan", run_scheduler=False)
        self.assertEqual(notifications["unreadCount"], 1)
        self.assertEqual(notifications["items"][0]["metadata"]["severity"], "high")
        thread_id = notifications["items"][0]["threadId"]
        thread = service.get_thread(thread_id, "zulan")
        self.assertEqual(thread["threadOrigin"], "proactive")
        self.assertEqual(thread["proactiveAgentId"], "liwiro-architect")
        self.assertEqual(thread["issueKey"], "api-contract-drift")
        self.assertEqual(thread["notificationState"], "new")
        self.assertEqual(thread["messages"][0]["notificationState"], "new")

    def test_duplicate_proactive_finding_reuses_thread_after_cooling_period(self):
        service = self._service(
            [
                {
                    "shouldNotify": True,
                    "issueKey": "docs-gap",
                    "title": "Documentation gap",
                    "summary": "Operator guidance is missing for a live surface.",
                    "message": "I found a documentation gap around the live operator workflow.",
                    "confidence": "High",
                    "severity": "high",
                },
                {
                    "shouldNotify": True,
                    "issueKey": "docs-gap",
                    "title": "Documentation gap",
                    "summary": "Operator guidance is still missing for the same workflow.",
                    "message": "Following up: the documentation gap still exists and has not been addressed yet.",
                    "confidence": "High",
                    "severity": "high",
                },
                {
                    "shouldNotify": True,
                    "issueKey": "docs-gap",
                    "title": "Documentation gap",
                    "summary": "Operator guidance is still missing for the same workflow.",
                    "message": "Following up: the documentation gap still exists and has not been addressed yet.",
                    "confidence": "High",
                    "severity": "high",
                },
            ]
        )
        service.update_user_settings(
            "zulan",
            proactive_mode_enabled=True,
            agent_settings=self._single_proactive_agent_settings(service, "liwiro-documentation-advisor", level=6),
        )
        first = service.run_due_proactive_evaluations("zulan", force=True, now=datetime(2026, 3, 29, 0, 0, tzinfo=timezone.utc))
        first_thread_id = first["emitted"][0]["threadId"]
        second = service.run_due_proactive_evaluations("zulan", force=True, now=datetime(2026, 3, 29, 1, 0, tzinfo=timezone.utc))
        self.assertEqual(second["emitted"], [])
        third = service.run_due_proactive_evaluations("zulan", force=True, now=datetime(2026, 3, 29, 5, 0, tzinfo=timezone.utc))
        self.assertEqual(len(third["emitted"]), 1)
        self.assertEqual(third["emitted"][0]["threadId"], first_thread_id)
        self.assertEqual(third["emitted"][0]["status"], "reminded")
        thread = service.get_thread(first_thread_id, "zulan")
        self.assertEqual(thread["notificationState"], "reminded")
        self.assertEqual(len(thread["messages"]), 2)

    def test_ignored_proactive_issue_is_not_raised_again(self):
        service = self._service(
            [
                {
                    "shouldNotify": True,
                    "issueKey": "reliability-hotspot",
                    "title": "Reliability hotspot",
                    "summary": "A retry gap is likely to cause instability.",
                    "message": "I found a retry and resilience hotspot that deserves attention.",
                    "confidence": "High",
                    "severity": "high",
                },
                {
                    "shouldNotify": True,
                    "issueKey": "reliability-hotspot",
                    "title": "Reliability hotspot",
                    "summary": "The retry gap still exists.",
                    "message": "Following up: the retry and resilience hotspot still exists.",
                    "confidence": "High",
                    "severity": "high",
                },
            ]
        )
        service.update_user_settings(
            "zulan",
            proactive_mode_enabled=True,
            agent_settings=self._single_proactive_agent_settings(service, "liwiro-reliability-advisor", level=6),
        )
        first = service.run_due_proactive_evaluations("zulan", force=True, now=datetime(2026, 3, 29, 0, 0, tzinfo=timezone.utc))
        issue_key = first["emitted"][0]["issueKey"]
        thread_id = first["emitted"][0]["threadId"]
        ignore_result = service.ignore_proactive_issue(
            "zulan",
            issue_key=issue_key,
            agent_id="liwiro-reliability-advisor",
            thread_id=thread_id,
        )
        self.assertEqual(ignore_result["issue"]["status"], "ignored")
        second = service.run_due_proactive_evaluations("zulan", force=True, now=datetime(2026, 3, 29, 5, 0, tzinfo=timezone.utc))
        self.assertEqual(second["emitted"], [])


if __name__ == "__main__":
    unittest.main()
