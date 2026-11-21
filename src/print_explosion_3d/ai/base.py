"""Provider-neutral types for the designer chat.

Nothing outside `anthropic_provider.py` may import the Anthropic SDK. Everything else talks in
these types, so another provider can be dropped in behind the `Provider` protocol.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Role = Literal["user", "assistant", "note"]


@dataclass(frozen=True, slots=True)
class Image:
    media_type: str  # e.g. "image/jpeg"
    data: bytes
    name: str = ""  # attachment filename, for the chat display


@dataclass(frozen=True, slots=True)
class Message:
    """One entry in the conversation.

    - `user`: what she typed, plus any photos.
    - `assistant`: a model turn. `raw` is the provider's own content blocks (thinking included),
      replayed byte-for-byte so prompt caching and preserved thinking keep working. `text` is the
      readable part, for logs and for providers that can't use `raw`.
    - `note`: app-originated info (she edited a value, a build failed). Not her words.
    """

    role: Role
    text: str = ""
    images: tuple[Image, ...] = ()
    raw: tuple[dict[str, Any], ...] | None = None


@dataclass(frozen=True, slots=True)
class Usage:
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass(frozen=True, slots=True)
class Reply:
    text: str
    raw: tuple[dict[str, Any], ...] = ()
    usage: Usage = field(default_factory=Usage)
    refused: bool = False
    truncated: bool = False  # hit the output limit mid-answer


class ProviderError(Exception):
    """A failure with a message that is safe to show her as-is.

    `kind` is a stable tag for code that wants to branch: no_key, bad_key, credits, offline,
    busy, other.
    """

    def __init__(self, message: str, kind: str = "other") -> None:
        super().__init__(message)
        self.kind = kind


TextSink = Callable[[str], None]


class Provider(Protocol):
    def complete(
        self,
        system: str,
        messages: Sequence[Message],
        on_text: TextSink | None = None,
    ) -> Reply:
        """Run one model turn. Streams text deltas to `on_text`; raises `ProviderError`."""
        ...
