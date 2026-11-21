"""Anthropic adapter. The only module allowed to import the Anthropic SDK."""

from __future__ import annotations

import base64
from collections.abc import Sequence
from typing import Any

import anthropic

from print_explosion_3d.ai.base import Message, ProviderError, Reply, TextSink, Usage

FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_OUTPUT_TOKENS = 32_000  # a whole .scad file plus thinking; streaming makes this safe

# What she sees. Never an API error body.
MSG_NO_KEY = "I need an Anthropic key to think. Add ANTHROPIC_API_KEY to the .env file and restart."
MSG_BAD_KEY = "The Anthropic key doesn't seem to work. Check ANTHROPIC_API_KEY in the .env file."
MSG_CREDITS = "The AI account is out of credit. Add some on the Anthropic website, then try again."
MSG_OFFLINE = "I can't reach the internet right now. Check the connection and try again."
MSG_BUSY = "The AI is busy at the moment. Give it a minute and try again."
MSG_OTHER = "Something went wrong while I was thinking. Please try again."


def _note_to_user_text(text: str) -> str:
    return f"[Note from the app, not from the user]\n{text}"


def to_api_messages(messages: Sequence[Message]) -> list[dict[str, Any]]:
    """Map neutral messages to API messages.

    A `note` becomes a mid-conversation `{"role": "system"}` message, which keeps the cached
    prefix intact. The API only accepts those right after a user message, so a note that follows
    anything else (an assistant turn, or the start) goes in as a clearly labelled user message.
    The choice depends only on position, so replaying the same history is byte-identical.
    """
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "assistant":
            content: Any = list(m.raw) if m.raw else m.text
            out.append({"role": "assistant", "content": content})
        elif m.role == "note":
            if out and out[-1]["role"] == "user":
                out.append({"role": "system", "content": m.text})
            else:
                out.append({"role": "user", "content": _note_to_user_text(m.text)})
        else:
            blocks: list[dict[str, Any]] = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": img.media_type,
                        "data": base64.standard_b64encode(img.data).decode("ascii"),
                    },
                }
                for img in m.images
            ]
            if blocks:
                blocks.append({"type": "text", "text": m.text})
                out.append({"role": "user", "content": blocks})
            else:
                out.append({"role": "user", "content": m.text})
    return out


def friendly_error(exc: Exception) -> ProviderError:
    """Turn an SDK exception into something she can read."""
    if isinstance(exc, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
        return ProviderError(MSG_BAD_KEY, "bad_key")
    if isinstance(exc, anthropic.RateLimitError):
        return ProviderError(MSG_BUSY, "busy")
    if isinstance(exc, anthropic.APIConnectionError):  # includes timeouts
        return ProviderError(MSG_OFFLINE, "offline")
    if isinstance(exc, anthropic.APIStatusError):
        if "credit balance" in str(exc).lower():
            return ProviderError(MSG_CREDITS, "credits")
        if exc.status_code >= 500:  # includes 529 overloaded
            return ProviderError(MSG_BUSY, "busy")
    return ProviderError(MSG_OTHER, "other")


class AnthropicProvider:
    def __init__(
        self,
        api_key: str | None,
        model: str,
        effort: str,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._effort = effort
        self._client = client

    def _get_client(self) -> anthropic.Anthropic:
        if self._client is None:
            if not self._api_key:
                raise ProviderError(MSG_NO_KEY, "no_key")
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def complete(
        self,
        system: str,
        messages: Sequence[Message],
        on_text: TextSink | None = None,
    ) -> Reply:
        client = self._get_client()
        try:
            with client.beta.messages.stream(
                model=self._model,
                max_tokens=MAX_OUTPUT_TOKENS,
                # Byte-stable: no per-user or per-time data. Those go in messages.
                system=system,
                messages=to_api_messages(messages),  # ty: ignore[invalid-argument-type]
                thinking={"type": "adaptive"},
                output_config={"effort": self._effort},  # ty: ignore[invalid-argument-type]
                cache_control={"type": "ephemeral"},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            ) as stream:
                for delta in stream.text_stream:
                    if on_text:
                        on_text(delta)
                final = stream.get_final_message()
        except anthropic.AnthropicError as exc:
            raise friendly_error(exc) from exc

        # Check the stop reason before reading content.
        if final.stop_reason == "refusal":
            return Reply(text="", usage=_usage(final, self._model), refused=True)
        raw = tuple(block.model_dump(mode="json", exclude_none=True) for block in final.content)
        text = "".join(b.text for b in final.content if b.type == "text")
        return Reply(
            text=text,
            raw=raw,
            usage=_usage(final, self._model),
            truncated=final.stop_reason == "max_tokens",
        )


def _usage(final: Any, requested_model: str) -> Usage:
    u = final.usage
    return Usage(
        model=getattr(final, "model", None) or requested_model,
        input_tokens=u.input_tokens or 0,
        output_tokens=u.output_tokens or 0,
        cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
        cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
    )
