"""Parse OpenSCAD Customizer parameters out of a .scad file and write edited values back in place.

Designs declare their knobs at the top of the file:

    /* [Size] */
    // How wide the box is
    width = 40; // [10:100]

Only single-line literal assignments above the first `module`/`function` count, matching what
OpenSCAD's own Customizer shows. Write-back rewrites just the value on that line, so comments,
spacing and every other line stay exactly as they were and the AI always sees current values.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal

Kind = Literal["number", "bool", "string", "vector"]
Value = float | int | bool | str | list[float | int]

DEFAULT_SECTION = "General"
HIDDEN_SECTION = "Hidden"

_SECTION = re.compile(r"^\s*/\*\s*\[(?P<name>[^\]]*)\]\s*\*/\s*$")
_COMMENT = re.compile(r"^\s*//\s?(?P<text>.*?)\s*$")
_DECL_START = re.compile(r"^\s*(module|function)\b")
_NUMBER = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_ASSIGN = re.compile(
    r"^(?P<lead>\s*)(?P<name>[A-Za-z_]\w*)(?P<eq>\s*=\s*)"
    rf"(?P<value>\"(?:[^\"\\]|\\.)*\"|true|false|{_NUMBER}|\[[^\[\]]*\])"
    r"(?P<tail>\s*;[ \t]*(?://[ \t]*(?P<comment>.*?))?)\s*$"
)
_NUMBER_RE = re.compile(rf"^{_NUMBER}$")


class ParamError(ValueError):
    """A value can't be written to a parameter (unknown name, wrong type, not an allowed choice)."""


@dataclass(frozen=True, slots=True)
class Option:
    value: float | int | str
    label: str


@dataclass(frozen=True, slots=True)
class Param:
    name: str
    label: str  # "wall_thickness" -> "Wall thickness"
    kind: Kind
    value: Value
    section: str
    description: str  # the plain-English comment on the line above
    hidden: bool = False
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: tuple[Option, ...] = ()  # non-empty means "show a dropdown"
    max_length: int | None = None  # text boxes
    line: int = 0  # 1-based line of the assignment
    value_span: tuple[int, int] = (0, 0)  # column range of the value literal on that line


def humanize(name: str) -> str:
    text = name.replace("_", " ").strip()
    return (text[:1].upper() + text[1:]) if text else name


def _num(text: str) -> float | int:
    value = float(text)
    return int(value) if value.is_integer() and not re.search(r"[.eE]", text) else value


def _parse_literal(text: str) -> tuple[Kind, Value]:
    if text in ("true", "false"):
        return "bool", text == "true"
    if text.startswith('"'):
        return "string", re.sub(
            r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m[1], m[1]), text[1:-1]
        )
    if text.startswith("["):
        items = [i.strip() for i in text[1:-1].split(",") if i.strip()]
        if items and all(_NUMBER_RE.match(i) for i in items):
            return "vector", [_num(i) for i in items]
        raise ValueError("unsupported vector")
    return "number", _num(text)


def _parse_constraint(
    comment: str, kind: Kind, value: Value
) -> tuple[float | None, float | None, float | None, tuple[Option, ...], int | None]:
    """Interpret the trailing `// [...]` comment: range, dropdown, or a text max length."""
    comment = comment.strip()
    if kind == "string" and re.fullmatch(r"\d+", comment):
        return None, None, None, (), int(comment)
    if not (comment.startswith("[") and comment.endswith("]")):
        return None, None, None, (), None
    body = comment[1:-1].strip()
    if not body:
        return None, None, None, (), None

    if kind in ("number", "vector"):
        parts = [p.strip() for p in body.split(":")]
        if 2 <= len(parts) <= 3 and all(_NUMBER_RE.match(p) for p in parts):
            nums = [float(p) for p in parts]
            lo, hi = nums[0], nums[-1]
            step = nums[1] if len(parts) == 3 else None
            if lo > hi:
                lo, hi = hi, lo
            if step is None:
                values = value if isinstance(value, list) else [value]
                ints = all(float(v).is_integer() for v in (lo, hi, *values))
                step = 1.0 if ints else None
            elif step <= 0:
                step = None
            return lo, hi, step, (), None

    if kind in ("number", "string"):
        options: list[Option] = []
        for item in (i.strip() for i in body.split(",")):
            if not item:
                continue
            raw, sep, label = item.partition(":")
            raw, label = raw.strip(), label.strip()
            if kind == "number":
                if not _NUMBER_RE.match(raw):
                    return None, None, None, (), None  # not a dropdown after all
                options.append(Option(_num(raw), label if sep and label else raw))
            else:
                options.append(Option(raw, label if sep and label else raw))
        if len(options) >= 2 or (options and body.count(",") == 0 and ":" not in body):
            return None, None, None, tuple(options), None
    return None, None, None, (), None


def parse_params(source: str) -> list[Param]:
    """All Customizer parameters in `source`, in file order (hidden ones flagged, not dropped)."""
    params: list[Param] = []
    section = DEFAULT_SECTION
    pending: list[str] = []  # comment lines directly above the next assignment

    for number, line in enumerate(source.splitlines(), start=1):
        if _DECL_START.match(line):
            break  # parameters are only recognised above the first module/function
        sec = _SECTION.match(line)
        if sec:
            section = sec["name"].strip() or DEFAULT_SECTION
            pending = []
            continue
        com = _COMMENT.match(line)
        if com:
            pending.append(com["text"])
            continue
        match = _ASSIGN.match(line)
        if match:
            try:
                kind, value = _parse_literal(match["value"])
            except ValueError:
                pending = []
                continue
            lo, hi, step, options, max_len = _parse_constraint(match["comment"] or "", kind, value)
            name = match["name"]
            params.append(
                Param(
                    name=name,
                    label=humanize(name),
                    kind=kind,
                    value=value,
                    section=section,
                    description=" ".join(pending).strip(),
                    hidden=section.lower() == HIDDEN_SECTION.lower(),
                    min=lo,
                    max=hi,
                    step=step,
                    options=options,
                    max_length=max_len,
                    line=number,
                    value_span=(match.start("value"), match.end("value")),
                )
            )
        pending = []
    return params


def visible_sections(params: list[Param]) -> dict[str, list[Param]]:
    """Group the non-hidden parameters by section, keeping file order."""
    grouped: dict[str, list[Param]] = {}
    for p in params:
        if not p.hidden:
            grouped.setdefault(p.section, []).append(p)
    return grouped


def _fmt_number(value: float | int) -> str:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ParamError(f"not a usable number: {value!r}")
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _coerce(param: Param, value: object) -> str:
    """Validate `value` against `param` and return the SCAD literal to write."""
    if param.options:
        for opt in param.options:
            if value == opt.value or str(value) == str(opt.value):
                return (
                    _fmt_number(opt.value)
                    if isinstance(opt.value, int | float)
                    else _quote(str(opt.value))
                )
        raise ParamError(f"{param.label}: {value!r} is not one of the choices")

    if param.kind == "bool":
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return value.lower()
        raise ParamError(f"{param.label}: expected yes or no")

    if param.kind == "number":
        return _fmt_number(_to_number(param, value))

    if param.kind == "vector":
        if not isinstance(value, list | tuple):
            raise ParamError(f"{param.label}: expected a list of numbers")
        size = len(param.value) if isinstance(param.value, list) else len(value)
        if len(value) != size:
            raise ParamError(f"{param.label}: expected {size} numbers")
        return "[" + ", ".join(_fmt_number(_to_number(param, v)) for v in value) + "]"

    text = " ".join(str(value).split())  # strings stay on one line
    if param.max_length is not None:
        text = text[: param.max_length].rstrip()
    return _quote(text)


def _to_number(param: Param, value: object) -> float | int:
    if isinstance(value, bool):
        raise ParamError(f"{param.label}: expected a number")
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            raise ParamError(f"{param.label}: {value!r} is not a number") from None
    if not isinstance(value, int | float) or not math.isfinite(value):
        raise ParamError(f"{param.label}: expected a number")
    return value


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def apply_values(source: str, values: dict[str, object]) -> str:
    """Return `source` with each named parameter's value replaced in place.

    Raises ParamError (and changes nothing) if any name is unknown or any value is invalid.
    """
    by_name = {p.name: p for p in parse_params(source)}
    edits: list[tuple[int, int, int, str]] = []
    for name, value in values.items():
        param = by_name.get(name)
        if param is None:
            raise ParamError(f"There is no setting called {name!r}")
        edits.append((param.line, *param.value_span, _coerce(param, value)))

    lines = source.split("\n")
    for line_no, start, end, literal in edits:
        text = lines[line_no - 1]
        lines[line_no - 1] = text[:start] + literal + text[end:]
    return "\n".join(lines)
