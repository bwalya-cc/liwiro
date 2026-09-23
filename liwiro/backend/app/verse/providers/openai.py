from __future__ import annotations

import json
from typing import Any

import requests

from .base import (
    AIAuthenticationError,
    AICapabilities,
    AIConfigurationError,
    AIProvider,
    AIProviderError,
    AIRequest,
    AIResponse,
    AIRateLimitError,
    provider_post,
)


class OpenAIResponsesProvider(AIProvider):
    def __init__(self, api_key: str, model: str):
        self.api_key = str(api_key or "").strip()
        self.model = str(model or "gpt-5-mini").strip() or "gpt-5-mini"
        if not self.api_key:
            raise AIConfigurationError("OPENAI_API_KEY is required when AI_PROVIDER=openai")

    def capabilities(self) -> AICapabilities:
        return AICapabilities(provider="openai", supports_structured_output=True, supports_system_instruction=True)

    def _system_instruction(self, request: AIRequest) -> str:
        instruction = str(request.system_instruction or "").strip()
        if request.structured_output_schema:
            instruction = (
                f"{instruction}\n\n"
                "Return only valid JSON. Do not wrap the JSON in markdown fences. "
                f"Target schema: {json.dumps(request.structured_output_schema, ensure_ascii=True)}"
            ).strip()
        return instruction

    def _input(self, request: AIRequest) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if request.context_blocks:
            context_lines = []
            for block in request.context_blocks:
                reason = f"\nReason: {block.reason}" if block.reason else ""
                source = f"\nSource: {block.source}" if block.source else ""
                context_lines.append(f"[{block.label}]{source}{reason}\n{block.content}")
            messages.append(
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Context blocks:\n\n" + "\n\n".join(context_lines)}],
                }
            )
        for message in request.messages:
            is_assistant = str(message.role).strip().lower() in {"assistant", "model", "agent"}
            text = str(message.content or "").strip()
            if not text:
                continue
            content_type = "output_text" if is_assistant else "input_text"
            messages.append(
                {
                    "role": "assistant" if is_assistant else "user",
                    "content": [{"type": content_type, "text": text}],
                }
            )
        return messages

    def _payload(self, request: AIRequest) -> dict[str, Any]:
        selected_model = str(request.model or self.model).strip() or self.model
        payload: dict[str, Any] = {
            "model": selected_model,
            "instructions": self._system_instruction(request),
            "input": self._input(request),
            "max_output_tokens": int(request.max_output_tokens or 1200),
            "text": {"format": {"type": "text"}},
        }
        if selected_model.startswith(("gpt-5", "o1", "o3", "o4")):
            payload["reasoning"] = {"effort": "low"}
            payload["max_output_tokens"] = max(4096, payload["max_output_tokens"])
        else:
            payload["temperature"] = float(request.temperature)
        if request.structured_output_schema:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "verse_response",
                    "schema": request.structured_output_schema,
                    "strict": False,
                }
            }
        return payload

    def _extract_text(self, body: dict[str, Any]) -> str:
        output_text = body.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        parts: list[str] = []
        for item in body.get("output") or []:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for content in item.get("content") or []:
                if not isinstance(content, dict):
                    continue
                if content.get("type") == "output_text" and content.get("text"):
                    parts.append(str(content.get("text")))
        return "\n".join(parts).strip()

    def generate(self, request: AIRequest) -> AIResponse:
        payload = self._payload(request)
        response = provider_post(
            "OpenAI",
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            api_key=self.api_key,
        )
        body = response.json()
        if not self._extract_text(body):
            raise AIProviderError("OpenAI returned no text; the response may have exhausted its reasoning token budget.")
        if body.get("status") == "incomplete":
            raise AIProviderError("OpenAI response was truncated. Increase the output token budget or narrow the request.")
        usage = body.get("usage") or {}
        return AIResponse(
            text=self._extract_text(body),
            model=str(body.get("model") or payload["model"]),
            provider="openai",
            raw=body,
            finish_reason=str(body.get("status") or ""),
            usage=usage if isinstance(usage, dict) else {},
        )
