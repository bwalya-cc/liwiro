"""Verify saved usage controls reach provider wire payloads without live API calls."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.verse.providers.base import AIRequest, AIChatMessage, AIProviderError
from app.verse.providers.factory import build_ai_provider
from app.verse.providers.settings import DEFAULT_MODELS, OUTPUT_TOKEN_FLOORS


class UsageLevelsTest(unittest.TestCase):
    def test_provider_payloads_at_every_level(self):
        request = AIRequest(system_instruction="Help", messages=[AIChatMessage("user", "Hello")])
        for name, model in DEFAULT_MODELS.items():
            for level, floor in OUTPUT_TOKEN_FLOORS.items():
                with self.subTest(provider=name, level=level):
                    config = {f"{name.upper()}_API_KEY": "test", "AI_PROVIDER": name, "AI_USAGE_LEVEL": level}
                    provider = build_ai_provider(config)
                    self.assertEqual(provider.model, model)
                    response = Mock()
                    response.json.return_value = {
                        "output_text": "OK", "status": "completed",
                        "content": [{"type": "text", "text": "OK"}],
                        "candidates": [{"content": {"parts": [{"text": "private summary", "thought": True}, {"text": "OK"}]}, "finishReason": "STOP"}],
                    }
                    with patch(f"app.verse.providers.{name}.provider_post", return_value=response) as post:
                        result = provider.generate(request)
                    self.assertEqual(result.text, "OK")
                    payload = post.call_args.kwargs["json"]
                    if name == "openai":
                        self.assertEqual(payload["reasoning"]["effort"], level)
                        self.assertEqual(payload["max_output_tokens"], floor)
                        self.assertNotIn("temperature", payload)
                    elif name == "google":
                        generation = payload["generationConfig"]
                        self.assertEqual(generation["thinkingConfig"]["thinkingLevel"], level.upper())
                        self.assertEqual(generation["maxOutputTokens"], floor)
                        self.assertNotIn("temperature", generation)
                    else:
                        self.assertEqual(payload["output_config"]["effort"], level)
                        self.assertEqual(payload["max_tokens"], floor)
                        self.assertNotIn("temperature", payload)

    def test_default_medium_custom_model_and_invalid_level(self):
        provider = build_ai_provider({"OPENAI_API_KEY": "test", "OPENAI_MODEL": "gpt-4.1"})
        self.assertEqual(provider.usage_level, "medium")
        payload = provider._payload(AIRequest(system_instruction="", messages=[]))
        self.assertEqual(payload["model"], "gpt-4.1")
        self.assertNotIn("reasoning", payload)
        self.assertIn("temperature", payload)
        with self.assertRaises(ValueError):
            build_ai_provider({"OPENAI_API_KEY": "test", "AI_USAGE_LEVEL": "unlimited"})

    def test_task_output_budget_is_not_reduced(self):
        provider = build_ai_provider({"OPENAI_API_KEY": "test"})
        payload = provider._payload(AIRequest(system_instruction="", messages=[], max_output_tokens=20000))
        self.assertEqual(payload["max_output_tokens"], 20000)
