"""Move a folder to the macOS Trash so a delete can be undone from Finder."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def move_to_trash(path: Path) -> None:
    """Trash `path` via NSFileManager. Raises OSError if it can't be trashed.

    Off macOS (dev containers, CI) it falls back to a plain delete.
    """
    if sys.platform != "darwin":
        shutil.rmtree(path)
        return
    from Foundation import NSURL, NSFileManager

    url = NSURL.fileURLWithPath_(str(path))
    ok, _result, error = NSFileManager.defaultManager().trashItemAtURL_resultingItemURL_error_(
        url, None, None
    )
    if not ok:
        raise OSError(f"Could not move {path.name} to the Trash: {error}")
