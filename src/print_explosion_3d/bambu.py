"""Hand a model to Bambu Studio, or show where it is when Bambu Studio isn't installed."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

MSG_NO_BAMBU = "Bambu Studio isn't installed, so here's the file instead."
MSG_NO_BAMBU_NO_FINDER = (
    "Bambu Studio isn't installed. You can still save the file and open it yourself."
)

_APP_NAMES = ("BambuStudio.app", "Bambu Studio.app")
_APP_FOLDERS = (Path("/Applications"), Path.home() / "Applications")


def find_bambu() -> Path | None:
    """Where Bambu Studio is installed, or None."""
    for folder in _APP_FOLDERS:
        for name in _APP_NAMES:
            if (folder / name).is_dir():
                return folder / name
    return None


def _run(cmd: list[str]) -> bool:
    try:
        done = subprocess.run(cmd, capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0


def open_in_bambu(stl: Path) -> dict[str, Any]:
    app = find_bambu()
    if app is not None and _run(["open", "-a", str(app), str(stl)]):
        return {"opened": True}
    # Not installed (or it wouldn't open): show the file in Finder so nothing is lost.
    revealed = _run(["open", "-R", str(stl)])
    return {
        "opened": False,
        "revealed": revealed,
        "error": MSG_NO_BAMBU if revealed else MSG_NO_BAMBU_NO_FINDER,
    }
