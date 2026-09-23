from __future__ import annotations

from .base import AIConfigurationError, AIProvider
from .anthropic import AnthropicClaudeProvider
from .google import GoogleGeminiProvider
from .openai import OpenAIResponsesProvider


def build_ai_provider(config: dict, provider_name: str = "", model: str = "") -> AIProvider:
    provider = str(provider_name or config.get("AI_PROVIDER") or "openai").strip().lower()
    if provider == "google":
        return GoogleGeminiProvider(
            api_key=str(config.get("GOOGLE_API_KEY") or "").strip(),
            model=str(model or config.get("GOOGLE_MODEL") or "gemini-3-flash-preview").strip(),
        )
    if provider == "openai":
        return OpenAIResponsesProvider(
            api_key=str(config.get("OPENAI_API_KEY") or "").strip(),
            model=str(model or config.get("OPENAI_MODEL") or "gpt-5-mini").strip(),
        )
    if provider == "anthropic":
        return AnthropicClaudeProvider(
            api_key=str(config.get("ANTHROPIC_API_KEY") or "").strip(),
            model=str(model or config.get("ANTHROPIC_MODEL") or "claude-sonnet-4-6").strip(),
        )
    raise AIConfigurationError(f"Unsupported AI provider: {provider}")
