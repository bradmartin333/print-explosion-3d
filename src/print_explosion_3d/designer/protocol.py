"""Parse the designer's reply: prose, one openscad block, and optional tags. Regex only."""

from __future__ import annotations

import re
from dataclasses import dataclass

_OPENSCAD = re.compile(r"```[ \t]*openscad[ \t]*\r?\n(.*?)```", re.DOTALL | re.IGNORECASE)
_ANY_FENCE = re.compile(r"```.*?```", re.DOTALL)
_OPEN_FENCE = re.compile(r"```.*\Z", re.DOTALL)  # a fence still being streamed
_TITLE = re.compile(r"<title>(.*?)</title>", re.DOTALL | re.IGNORECASE)
_NOTE = re.compile(r"<note>(.*?)</note>", re.DOTALL | re.IGNORECASE)
_CHOICES = re.compile(r"<choices>(.*?)</choices>", re.DOTALL | re.IGNORECASE)
_ANY_TAG = re.compile(r"<(title|note|choices)>.*?</\1>", re.DOTALL | re.IGNORECASE)
_OPEN_TAG = re.compile(r"<(?:title|note|choices)>.*\Z", re.DOTALL | re.IGNORECASE)
_PARTIAL_TAG = re.compile(r"<[a-z/]{0,8}\Z", re.IGNORECASE)  # "<tit" at the very end
_BLANKS = re.compile(r"\n{3,}")

MAX_CHOICES = 6


@dataclass(frozen=True, slots=True)
class ParsedReply:
    prose: str  # what the user reads: no code, no tags
    scad: str | None  # the full file, if the reply holds a design
    title: str | None
    note: str | None
    choices: tuple[str, ...]


def _clean(text: str) -> str:
    return " ".join(text.split())


def parse_reply(text: str) -> ParsedReply:
    """Extract the design and tags. With several code blocks, the last one wins."""
    blocks = _OPENSCAD.findall(text)
    scad = blocks[-1].strip("\n") + "\n" if blocks and blocks[-1].strip() else None

    def tag(pattern: re.Pattern[str]) -> str | None:
        found = pattern.findall(text)
        return _clean(found[-1]) or None if found else None

    raw_choices = tag(_CHOICES)
    choices = (
        tuple(c for c in (_clean(p) for p in raw_choices.split("|")) if c)[:MAX_CHOICES]
        if raw_choices
        else ()
    )
    return ParsedReply(visible_prose(text), scad, tag(_TITLE), tag(_NOTE), choices)


def visible_prose(text: str) -> str:
    """The reply with code and tags removed. Safe on half-streamed text."""
    text = _ANY_FENCE.sub("", text)
    text = _OPEN_FENCE.sub("", text)
    text = _ANY_TAG.sub("", text)
    text = _OPEN_TAG.sub("", text)
    text = _PARTIAL_TAG.sub("", text)
    return _BLANKS.sub("\n\n", text).strip()
