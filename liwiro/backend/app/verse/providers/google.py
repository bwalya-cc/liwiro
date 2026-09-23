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


class GoogleGeminiProvider(AIProvider):
    def __init__(self, api_key: str, model: str):
        self.api_key = str(api_key or "").strip()
        self.model = str(model or "gemini-3-flash-preview").strip() or "gemini-3-flash-preview"
        if not self.api_key:
            raise AIConfigurationError("GOOGLE_API_KEY is required when AI_PROVIDER=google")

    def capabilities(self) -> AICapabilities:
        return AICapabilities(provider="google", supports_structured_output=True, supports_system_instruction=True)

    def _endpoint(self, model: str) -> str:
        selected_model = str(model or self.model).strip() or self.model
        return f"https://generativelanguage.googleapis.com/v1beta/models/{selected_model}:generateContent"

    def _system_instruction(self, request: AIRequest) -> str:
        instruction = str(request.system_instruction or "").strip()
        if request.structured_output_schema:
            instruction = (
                f"{instruction}\n\n"
                "Return only valid JSON. Do not wrap the JSON in markdown fences. "
                f"Target schema: {json.dumps(request.structured_output_schema, ensure_ascii=True)}"
            ).strip()
        return instruction

    def _contents(self, request: AIRequest) -> list[dict[str, Any]]:
        contents: list[dict[str, Any]] = []
        if request.context_blocks:
            context_lines = []
            for block in request.context_blocks:
                reason = f"\nReason: {block.reason}" if block.reason else ""
                source = f"\nSource: {block.source}" if block.source else ""
                context_lines.append(f"[{block.label}]{source}{reason}\n{block.content}")
            contents.append(
                {
                    "role": "user",
                    "parts": [{"text": "Context blocks:\n\n" + "\n\n".join(context_lines)}],
                }
            )
        for message in request.messages:
            role = "model" if str(message.role).strip().lower() in {"assistant", "model"} else "user"
            contents.append({"role": role, "parts": [{"text": str(message.content or "")}]})
        return contents

    def generate(self, request: AIRequest) -> AIResponse:
        payload = {
            "systemInstruction": {"parts": [{"text": self._system_instruction(request)}]},
            "contents": self._contents(request),
            "generationConfig": {
                "temperature": float(request.temperature),
                "maxOutputTokens": int(request.max_output_tokens or 1200),
            },
        }
        response = provider_post(
            "Google Gemini",
            self._endpoint(request.model),
            headers={"x-goog-api-key": self.api_key},
            json=payload,
            api_key=self.api_key,
        )
        body = response.json()
        candidates = body.get("candidates") or []
        parts: list[str] = []
        finish_reason = ""
        if candidates:
            finish_reason = str(candidates[0].get("finishReason") or "")
            for part in (((candidates[0].get("content") or {}).get("parts")) or []):
                text = part.get("text")
                if text:
                    parts.append(str(text))
        if not parts:
            raise AIProviderError("Google Gemini returned no text. Check model output limits or content restrictions.")
        usage = body.get("usageMetadata") or {}
        return AIResponse(
            text="\n".join(parts).strip(),
            model=str(request.model or self.model),
            provider="google",
            raw=body,
            finish_reason=finish_reason,
            usage=usage if isinstance(usage, dict) else {},
        )
