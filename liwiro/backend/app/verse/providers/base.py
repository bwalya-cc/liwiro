from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import re

import requests


class AIProviderError(RuntimeError):
    pass


class AIConfigurationError(AIProviderError):
    pass


class AIAuthenticationError(AIProviderError):
    pass


class AIRateLimitError(AIProviderError):
    pass


def provider_post(provider: str, url: str, *, api_key: str, **kwargs):
    """Keep transport failures actionable and credentials out of error messages."""
    try:
        response = requests.post(url, timeout=(10, 90), **kwargs)
    except requests.Timeout:
        raise AIProviderError(f"{provider} timed out. Retry the connection test.") from None
    except requests.RequestException:
        raise AIProviderError(f"Cannot reach {provider}. Check this server's DNS, network and proxy settings.") from None
    if response.status_code < 400:
        return response
    try:
        body = response.json()
        error = body.get("error", {}) if isinstance(body, dict) else {}
    except ValueError:
        error = {}
    detail = str(error.get("message") or "") if isinstance(error, dict) else ""
    detail = detail.replace(api_key, "[redacted]") if api_key else detail
    detail = re.sub(r"(?:sk-|AIza)[A-Za-z0-9_\-.*]+", "[redacted]", detail)[:400]
    suffix = f" {detail}" if detail else ""
    if response.status_code == 401:
        raise AIAuthenticationError(f"{provider} rejected the API key (401). Replace it in AI Setup.")
    if response.status_code == 403:
        raise AIProviderError(f"{provider} denied access (403). Check model permissions and regional or network restrictions.{suffix}")
    if response.status_code == 429:
        raise AIRateLimitError(f"{provider} quota or rate limit reached.{suffix}")
    raise AIProviderError(f"{provider} request failed ({response.status_code}).{suffix}")


@dataclass
class AICapabilities:
    provider: str
    supports_text: bool = True
    supports_structured_output: bool = True
    supports_system_instruction: bool = True


@dataclass
class AIChatMessage:
    role: str
    content: str
    name: str = ""


@dataclass
class AIContextBlock:
    label: str
    content: str
    source: str = ""
    reason: str = ""


@dataclass
class AIRequest:
    system_instruction: str
    messages: list[AIChatMessage]
    context_blocks: list[AIContextBlock] = field(default_factory=list)
    structured_output_schema: dict[str, Any] | None = None
    model: str = ""
    temperature: float = 0.2
    max_output_tokens: int = 1200


@dataclass
class AIResponse:
    text: str
    model: str
    provider: str
    raw: dict[str, Any] | None = None
    structured_output: Any = None
    finish_reason: str = ""
    usage: dict[str, Any] = field(default_factory=dict)


class AIProvider:
    def capabilities(self) -> AICapabilities:
        raise NotImplementedError

    def generate(self, request: AIRequest) -> AIResponse:
        raise NotImplementedError

    def healthcheck(self, request: AIRequest | None = None) -> AIResponse:
        probe = request or AIRequest(
            system_instruction="You are a provider health probe. Reply with a short JSON object.",
            messages=[AIChatMessage(role="user", content='{"probe":"ok"}')],
            structured_output_schema={
                "type": "object",
                "properties": {"probe": {"type": "string"}},
                "required": ["probe"],
            },
            temperature=0.0,
            max_output_tokens=1024,
        )
        result = self.generate(probe)
        if not result.text.strip():
            raise AIProviderError("The provider returned no text. Check the model and output token budget.")
        return result
