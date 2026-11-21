"""Find a project from what the user typed, locally (no AI call): "open my bird feeder"."""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable

from print_explosion_3d.workspace.store import ProjectInfo

# Words around the project name that carry no meaning for matching.
_FILLER = frozenset(
    [
        "a",
        "an",
        "the",
        "my",
        "our",
        "open",
        "resume",
        "continue",
        "load",
        "show",
        "find",
        "go",
        "back",
        "to",
        "switch",
        "work",
        "on",
        "with",
        "please",
        "can",
        "you",
        "could",
        "i",
        "want",
        "would",
        "like",
        "project",
        "design",
        "model",
        "thing",
        "that",
        "this",
        "one",
        "again",
        "called",
        "named",
    ]
)
_WORD = re.compile(r"[a-z0-9]+")
MIN_SCORE = 0.6


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _score(query: list[str], name: list[str]) -> float:
    if not query or not name:
        return 0.0
    q, n = " ".join(query), " ".join(name)
    whole = difflib.SequenceMatcher(None, q, n).ratio()
    # Every query word should be near some word in the name, e.g. "feeder" -> "Bird Feeder".
    per_word = sum(
        max(difflib.SequenceMatcher(None, w, nw).ratio() for nw in name) for w in query
    ) / len(query)
    contains = 1.0 if q in n else 0.0
    return max(whole, per_word * 0.95, contains)


def find_projects(query: str, projects: Iterable[ProjectInfo], limit: int = 5) -> list[ProjectInfo]:
    """Best matches first, most recently updated winning ties. Empty if nothing is close."""
    words = [w for w in _words(query) if w not in _FILLER] or _words(query)
    scored = [(_score(words, _words(p.name)), p) for p in projects]
    scored = [(s, p) for s, p in scored if s >= MIN_SCORE]
    scored.sort(key=lambda sp: (round(sp[0], 2), sp[1].updated), reverse=True)
    return [p for _, p in scored[:limit]]
