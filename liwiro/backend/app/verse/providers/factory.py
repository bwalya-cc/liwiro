from __future__ import annotations

from .base import AIConfigurationError, AIProvider
from .anthropic import AnthropicClaudeProvider
from .google import GoogleGeminiProvider
from .openai import OpenAIResponsesProvider


def build_ai_provider(config: dict, provider_name: str = "", model: str = "") -> AIProvider:
    provider = str(provider_name or config.get("AI_PROVIDER") or "openai").strip().lower()
    if provider == "google":
        return GoogleGeminiProvider(
            usage_level=config.get("AI_USAGE_LEVEL") or "medium",
            api_key=str(config.get("GOOGLE_API_KEY") or "").strip(),
            model=str(model or config.get("GOOGLE_MODEL") or "gemini-3.8-flash").strip(),
        )
    if provider == "openai":
        return OpenAIResponsesProvider(
            usage_level=config.get("AI_USAGE_LEVEL") or "medium",
            api_key=str(config.get("OPENAI_API_KEY") or "").strip(),
            model=str(model or config.get("OPENAI_MODEL") or "gpt-6-luna").strip(),
        )
    if provider == "anthropic":
        return AnthropicClaudeProvider(
            usage_level=config.get("AI_USAGE_LEVEL") or "medium",
            api_key=str(config.get("ANTHROPIC_API_KEY") or "").strip(),
            model=str(model or config.get("ANTHROPIC_MODEL") or "claude-sonnet-5-5").strip(),
        )
    raise AIConfigurationError(f"Unsupported AI provider: {provider}")
