"""Hand a model to Bambu Studio. M5 will refine this (running-instance behaviour, install check)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

MSG_NO_BAMBU = (
    "I couldn't find Bambu Studio on this computer. "
    "You can still save the file and open it yourself."
)


def open_in_bambu(stl: Path) -> dict[str, Any]:
    try:
        done = subprocess.run(
            ["open", "-a", "BambuStudio", str(stl)], capture_output=True, timeout=15, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"opened": False, "error": MSG_NO_BAMBU}
    if done.returncode != 0:
        return {"opened": False, "error": MSG_NO_BAMBU}
    return {"opened": True}
