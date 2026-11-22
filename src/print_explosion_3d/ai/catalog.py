"""Which AI models the app offers, in words a non-technical person can choose between.

Adding another provider later means: add an adapter behind `Provider`, register it in
`make_provider` (ai/__init__.py), and list its models here. The picker in the app, the saved
choice and the "start a fresh conversation when it changes" rule all follow from this list.
"""

from __future__ import annotations

from dataclasses import dataclass

PROVIDER_LABELS = {"anthropic": "Claude"}


@dataclass(frozen=True, slots=True)
class ModelChoice:
    provider: str  # matches PE_PROVIDER
    id: str  # the provider's own model name
    label: str  # plain English
    hint: str

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.id}"

    @property
    def provider_label(self) -> str:
        return PROVIDER_LABELS.get(self.provider, self.provider.title())


MODELS: tuple[ModelChoice, ...] = (
    ModelChoice("anthropic", "claude-sonnet-5-5", "Everyday", "Good at most things. Recommended."),
    ModelChoice("anthropic", "claude-opus-5-5", "Extra careful", "Slower and costs more."),
    ModelChoice("anthropic", "claude-haiku-5-5", "Quick and thrifty", "Fast and cheap, simpler."),
    ModelChoice("anthropic", "claude-fable-5-2", "Most capable", "For tricky designs. Costs most."),
)


def find_model(key: object) -> ModelChoice | None:
    return next((m for m in MODELS if m.key == key), None)


def choices_for(provider: str, model: str) -> list[ModelChoice]:
    """The picker's list. A model set by hand in .env that isn't listed is added at the top."""
    current = ModelChoice(provider, model, "Custom (from settings)", model)
    return list(MODELS) if find_model(current.key) else [current, *MODELS]
