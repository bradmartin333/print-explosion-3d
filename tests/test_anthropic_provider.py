from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import httpx2 as httpx
import pytest

from print_explosion_3d.ai.anthropic_provider import (
    FALLBACK_BETA,
    MSG_BAD_KEY,
    MSG_CREDITS,
    MSG_NO_KEY,
    MSG_OFFLINE,
    AnthropicProvider,
    to_api_messages,
)
from print_explosion_3d.ai.base import Image, Message, ProviderError


class FakeBlock(SimpleNamespace):
    def model_dump(self, **_kw):
        return {k: v for k, v in vars(self).items() if v is not None}


def final_message(stop="end_turn", text="Hi there"):
    return SimpleNamespace(
        stop_reason=stop,
        model="claude-sonnet-5-5",
        content=[
            FakeBlock(type="thinking", thinking="", signature="sig"),
            FakeBlock(type="text", text=text),
        ],
        usage=SimpleNamespace(
            input_tokens=100,
            output_tokens=20,
            cache_read_input_tokens=80,
            cache_creation_input_tokens=None,
        ),
    )


def client_with(final=None, error=None):
    client = MagicMock()
    stream = MagicMock()
    stream.text_stream = iter(["Hi ", "there"])
    stream.get_final_message.return_value = final
    cm = client.beta.messages.stream.return_value
    cm.__enter__.return_value = stream
    if error:
        client.beta.messages.stream.side_effect = error
    return client


def provider(client):
    return AnthropicProvider("key", "claude-sonnet-5-5", "medium", client=client)


def test_request_shape_and_reply():
    client = client_with(final_message())
    seen = []
    reply = provider(client).complete("SYS", [Message("user", "hello")], seen.append)

    kwargs = client.beta.messages.stream.call_args.kwargs
    assert kwargs["model"] == "claude-sonnet-5-5"
    assert kwargs["system"] == "SYS"
    assert kwargs["thinking"] == {"type": "adaptive"}
    assert kwargs["output_config"] == {"effort": "medium"}
    assert kwargs["cache_control"] == {"type": "ephemeral"}
    assert kwargs["betas"] == [FALLBACK_BETA]
    assert kwargs["fallbacks"] == "default"
    assert "tool_choice" not in kwargs
    assert kwargs["messages"] == [{"role": "user", "content": "hello"}]

    assert seen == ["Hi ", "there"]
    assert reply.text == "Hi there"
    # Raw blocks, thinking included, kept for byte-exact replay.
    assert reply.raw[0] == {"type": "thinking", "thinking": "", "signature": "sig"}
    assert reply.usage.cache_read_tokens == 80
    assert reply.usage.cache_write_tokens == 0
    assert not reply.refused


def test_refusal_is_checked_before_content():
    reply = provider(client_with(final_message(stop="refusal"))).complete("S", [])
    assert reply.refused
    assert reply.text == ""
    assert reply.raw == ()


def test_truncation_flag():
    reply = provider(client_with(final_message(stop="max_tokens"))).complete("S", [])
    assert reply.truncated


def test_no_key_is_friendly_and_makes_no_client():
    p = AnthropicProvider(None, "m", "medium")
    with pytest.raises(ProviderError) as e:
        p.complete("S", [])
    assert str(e.value) == MSG_NO_KEY
    assert e.value.kind == "no_key"


def _status_error(cls, status, body="x"):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status, request=request)
    return cls(body, response=response, body=None)


@pytest.mark.parametrize(
    ("error", "message", "kind"),
    [
        (_status_error(anthropic.AuthenticationError, 401), MSG_BAD_KEY, "bad_key"),
        (
            _status_error(
                anthropic.BadRequestError, 400, "Your credit balance is too low to access"
            ),
            MSG_CREDITS,
            "credits",
        ),
        (
            anthropic.APIConnectionError(
                request=httpx.Request("POST", "https://api.anthropic.com")
            ),
            MSG_OFFLINE,
            "offline",
        ),
        (_status_error(anthropic.RateLimitError, 429), None, "busy"),
        (_status_error(anthropic.InternalServerError, 529), None, "busy"),
        (_status_error(anthropic.BadRequestError, 400, "weird"), None, "other"),
    ],
)
def test_errors_become_friendly_text(error, message, kind):
    with pytest.raises(ProviderError) as e:
        provider(client_with(error=error)).complete("S", [])
    assert e.value.kind == kind
    if message:
        assert str(e.value) == message
    assert "400" not in str(e.value)  # never an API body


def test_message_mapping():
    img = Image("image/png", b"\x89PNG", "a.png")
    raw = ({"type": "thinking", "thinking": "", "signature": "s"}, {"type": "text", "text": "ok"})
    msgs = [
        Message("note", "seed"),  # start of conversation: labelled user message
        Message("user", "make a box", (img,)),
        Message("note", "she edited a value"),  # right after a user turn: system message
        Message("assistant", "ok", raw=raw),
        Message("note", "build failed"),  # after assistant: labelled user message
    ]
    out = to_api_messages(msgs)
    assert out[0]["role"] == "user"
    assert out[0]["content"].startswith("[Note from the app")
    assert out[1]["content"][0]["type"] == "image"
    assert out[1]["content"][1] == {"type": "text", "text": "make a box"}
    assert out[2] == {"role": "system", "content": "she edited a value"}
    assert out[3] == {"role": "assistant", "content": list(raw)}
    assert out[4]["role"] == "user"
    assert "build failed" in out[4]["content"]
    # Deterministic: replaying the same history gives identical output.
    assert to_api_messages(msgs) == out
