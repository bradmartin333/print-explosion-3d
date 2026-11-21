"""App settings, loaded from the environment and the repo's `.env`, with safe defaults.

Every setting is optional except the API key, and a malformed value falls back to its default
instead of crashing: the end user can't debug a typo in `.env`.

`python -m print_explosion_3d.config` prints a commented `.env` template built from SPEC below,
so SPEC is the single source of truth for setting names, defaults and docs.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parents[1]
WEB_DIR = REPO_ROOT / "web"
SCAD_LIB_DIR = PACKAGE_DIR / "scad" / "lib"
DOTENV_PATH = REPO_ROOT / ".env"

EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True, slots=True)
class Setting:
    env: str
    default: str
    doc: str
    section: str


SPEC: tuple[Setting, ...] = (
    Setting("ANTHROPIC_API_KEY", "", "Required. The only secret the app needs.", "AI"),
    Setting("PE_PROVIDER", "anthropic", "AI provider adapter (see src/.../ai/).", "AI"),
    Setting("PE_MODEL", "claude-sonnet-5-5", "Model used for the designer chat.", "AI"),
    Setting("PE_EFFORT", "medium", f"Thinking effort: {' | '.join(EFFORT_LEVELS)}.", "AI"),
    Setting("PE_MAX_AUTO_FIXES", "2", "Automatic AI retries when a design fails to build.", "AI"),
    Setting("PE_SHOW_COST", "false", "Show a running cost estimate in the status bar.", "AI"),
    Setting("PE_WORKSPACE_DIR", "", "Projects. Empty = ~/Documents/Print Explosion 3D", "Files"),
    Setting("OPENSCAD_BIN", "", "OpenSCAD binary. Empty = PATH, then /Applications.", "Files"),
    Setting("PE_RENDER_TIMEOUT", "120", "Seconds before a build is given up (5 to 600).", "Files"),
    Setting("PE_MODEL_COLOR", "#f2a65a", "Viewer model color (#rrggbb).", "Theme"),
    Setting("PE_BG_COLOR", "#f7f3ee", "Viewer background color (#rrggbb).", "Theme"),
    Setting("PE_SHADOW_OPACITY", "0.18", "Ground shadow darkness, 0 to 1.", "Theme"),
    Setting("PE_SPIN_SPEED", "0.35", "Idle spin speed in radians per second.", "Theme"),
)
_DEFAULTS = {s.env: s.default for s in SPEC}


@dataclass(frozen=True, slots=True)
class Theme:
    model_color: str
    bg_color: str
    shadow_opacity: float
    spin_speed: float


@dataclass(frozen=True, slots=True)
class Settings:
    anthropic_api_key: str | None
    provider: str
    model: str
    effort: str
    max_auto_fixes: int
    show_cost: bool
    workspace_dir: Path
    openscad_bin: str | None
    render_timeout: float
    theme: Theme


def load_settings(env: Mapping[str, str | None] | None = None) -> Settings:
    """Build Settings from `env`, or from `.env` overlaid by the real environment if None."""
    if env is None:
        file_values = dotenv_values(DOTENV_PATH) if DOTENV_PATH.is_file() else {}
        env = {**file_values, **os.environ}

    def raw(key: str) -> str:
        value = env.get(key)
        return value.strip() if value and value.strip() else _DEFAULTS[key]

    def number(key: str, lo: float, hi: float) -> float:
        try:
            value = float(raw(key))
        except ValueError:
            value = float(_DEFAULTS[key])
        return min(max(value, lo), hi)

    def color(key: str) -> str:
        value = raw(key)
        return value if _HEX_COLOR.match(value) else _DEFAULTS[key]

    effort = raw("PE_EFFORT").lower()
    workspace = raw("PE_WORKSPACE_DIR")

    return Settings(
        anthropic_api_key=raw("ANTHROPIC_API_KEY") or None,
        provider=raw("PE_PROVIDER").lower(),
        model=raw("PE_MODEL"),
        effort=effort if effort in EFFORT_LEVELS else _DEFAULTS["PE_EFFORT"],
        max_auto_fixes=int(number("PE_MAX_AUTO_FIXES", 0, 5)),
        show_cost=raw("PE_SHOW_COST").lower() in {"1", "true", "yes", "on"},
        workspace_dir=(
            Path(workspace).expanduser()
            if workspace
            else Path.home() / "Documents" / "Print Explosion 3D"
        ),
        openscad_bin=raw("OPENSCAD_BIN") or None,
        render_timeout=number("PE_RENDER_TIMEOUT", 5, 600),
        theme=Theme(
            model_color=color("PE_MODEL_COLOR"),
            bg_color=color("PE_BG_COLOR"),
            shadow_opacity=number("PE_SHADOW_OPACITY", 0.0, 1.0),
            spin_speed=number("PE_SPIN_SPEED", 0.0, 5.0),
        ),
    )


def env_template() -> str:
    """A commented .env file listing every setting with its default."""
    lines = ["# Print Explosion 3D settings. Only ANTHROPIC_API_KEY is required."]
    section = None
    for s in SPEC:
        if s.section != section:
            section = s.section
            lines += ["", f"# --- {section} ---"]
        lines += [f"# {s.doc}", f"{s.env}={s.default}"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(env_template(), end="")
