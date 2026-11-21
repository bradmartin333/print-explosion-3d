"""A scripted provider for tests and offline demos. Never touches the network."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from print_explosion_3d.ai.base import Message, ProviderError, Reply, TextSink, Usage

Script = str | Reply | ProviderError | Callable[[Sequence[Message]], str | Reply]


@dataclass
class FakeProvider:
    """Replays `script` one entry per call. A string becomes a plain reply.

    Records every call in `calls` (system prompt and a copy of the messages) so tests can assert
    on what the designer sent.
    """

    script: Iterable[Script] = ()
    calls: list[tuple[str, list[Message]]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._queue = list(self.script)

    def complete(
        self,
        system: str,
        messages: Sequence[Message],
        on_text: TextSink | None = None,
    ) -> Reply:
        self.calls.append((system, list(messages)))
        if not self._queue:
            raise AssertionError("FakeProvider ran out of scripted replies")
        item = self._queue.pop(0)
        if isinstance(item, ProviderError):
            raise item
        produced = item(messages) if not isinstance(item, str | Reply) else item
        reply = produced if isinstance(produced, Reply) else _plain(produced)
        if on_text and reply.text:
            on_text(reply.text)
        return reply


def _plain(text: str) -> Reply:
    return Reply(
        text=text,
        raw=({"type": "text", "text": text},),
        usage=Usage(model="fake", input_tokens=10, output_tokens=5),
    )
