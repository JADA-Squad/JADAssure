"""Which provider an org uses (BE-028, GR-08, decision 0010).

The org setting `ai_provider` defaults to "stub" (offline). An external provider ("anthropic" or
"openai") applies only when an admin has opted in (audited, BE-032) AND that provider's API key is
configured on the server. Otherwise the org falls back to the stub rather than sending data anywhere.
"""

from typing import Any

from app.core.config import get_settings
from app.domains.ai.anthropic_provider import AnthropicProvider
from app.domains.ai.openai_provider import OpenAIProvider
from app.domains.ai.provider import AIProvider
from app.domains.ai.stub import StubProvider

PROVIDERS = ("stub", "anthropic", "openai")
EXTERNAL = {"anthropic": ("Claude (Anthropic)", "ANTHROPIC_API_KEY"), "openai": ("OpenAI", "OPENAI_API_KEY")}


def configured(provider: str) -> bool:
    """Does the server hold a key for this provider? The offline stub always works."""
    s = get_settings()
    return {"stub": True, "anthropic": bool(s.anthropic_api_key), "openai": bool(s.openai_api_key)}.get(provider, False)


def configured_external() -> list[str]:
    return [p for p in EXTERNAL if configured(p)]


def external_available() -> bool:
    return bool(configured_external())


def provider_for(org_settings: dict[str, Any] | None) -> AIProvider:
    choice = (org_settings or {}).get("ai_provider", "stub")
    if choice == "anthropic" and configured(choice):
        return AnthropicProvider()
    if choice == "openai" and configured(choice):
        return OpenAIProvider()
    return StubProvider()
