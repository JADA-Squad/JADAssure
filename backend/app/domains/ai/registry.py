"""Which provider an org uses (BE-028, GR-08).

The org setting `ai_provider` defaults to "stub" (offline). "anthropic" applies only when an admin
has opted in (audited, BE-032) AND ANTHROPIC_API_KEY is configured. With no key, the org falls back
to the stub rather than sending data anywhere.
"""

from typing import Any

from app.core.config import get_settings
from app.domains.ai.anthropic_provider import AnthropicProvider
from app.domains.ai.provider import AIProvider
from app.domains.ai.stub import StubProvider

PROVIDERS = ("stub", "anthropic")


def external_available() -> bool:
    return bool(get_settings().anthropic_api_key)


def provider_for(org_settings: dict[str, Any] | None) -> AIProvider:
    choice = (org_settings or {}).get("ai_provider", "stub")
    if choice == "anthropic" and external_available():
        return AnthropicProvider()
    return StubProvider()
