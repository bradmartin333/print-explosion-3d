"""AI layer: neutral types, provider adapters, usage log."""

from __future__ import annotations

from print_explosion_3d.ai.base import (
    Image,
    Message,
    Provider,
    ProviderError,
    Reply,
    Usage,
)
from print_explosion_3d.config import Settings


def make_provider(settings: Settings) -> Provider:
    """Build the adapter named by `PE_PROVIDER`. A missing key is reported on first use."""
    if settings.provider == "anthropic":
        from print_explosion_3d.ai.anthropic_provider import AnthropicProvider

        return AnthropicProvider(settings.anthropic_api_key, settings.model, settings.effort)
    raise ProviderError(f"Unknown AI provider '{settings.provider}'.", "other")


__all__ = ["Image", "Message", "Provider", "ProviderError", "Reply", "Usage", "make_provider"]
