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


class AnthropicClaudeProvider(AIProvider):
    def __init__(self, api_key: str, model: str):
        self.api_key = str(api_key or "").strip()
        selected_model = str(model or "claude-sonnet-4-6").strip() or "claude-sonnet-4-6"
        self.model = {
            "claude-sonnet-4-20250514": "claude-sonnet-4-6",
            "claude-3-7-sonnet-20250219": "claude-sonnet-4-6",
        }.get(selected_model, selected_model)
        if not self.api_key:
            raise AIConfigurationError("ANTHROPIC_API_KEY is required when AI_PROVIDER=anthropic")

    def capabilities(self) -> AICapabilities:
        return AICapabilities(provider="anthropic", supports_structured_output=True, supports_system_instruction=True)

    def _system_instruction(self, request: AIRequest) -> str:
        instruction = str(request.system_instruction or "").strip()
        if request.structured_output_schema:
            instruction = (
                f"{instruction}\n\n"
                "Return only valid JSON. Do not wrap the JSON in markdown fences. "
                f"Target schema: {json.dumps(request.structured_output_schema, ensure_ascii=True)}"
            ).strip()
        return instruction

    def _messages(self, request: AIRequest) -> list[dict[str, Any]]:
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
                    "content": [{"type": "text", "text": "Context blocks:\n\n" + "\n\n".join(context_lines)}],
                }
            )
        for message in request.messages:
            role = "assistant" if str(message.role).strip().lower() in {"assistant", "model"} else "user"
            messages.append(
                {
                    "role": role,
                    "content": [{"type": "text", "text": str(message.content or "")}],
                }
            )
        return messages

    def generate(self, request: AIRequest) -> AIResponse:
        payload = {
            "model": str(request.model or self.model).strip() or self.model,
            "system": self._system_instruction(request),
            "messages": self._messages(request),
            "temperature": float(request.temperature),
            "max_tokens": int(request.max_output_tokens or 1200),
        }
        response = provider_post(
            "Anthropic Claude",
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
            api_key=self.api_key,
        )
        body = response.json()
        content_parts = []
        for item in body.get("content") or []:
            if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                content_parts.append(str(item.get("text")))
        if not content_parts:
            raise AIProviderError("Anthropic Claude returned no text. Check model output limits or content restrictions.")
        usage = body.get("usage") or {}
        return AIResponse(
            text="\n".join(content_parts).strip(),
            model=str(body.get("model") or payload["model"]),
            provider="anthropic",
            raw=body,
            finish_reason=str(body.get("stop_reason") or ""),
            usage=usage if isinstance(usage, dict) else {},
        )
