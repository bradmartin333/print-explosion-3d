"""The workspace: `<root>/<project>/` folders plus a top-level `state.json` (last opened).

    <project>/
        project.json     name, one-line memory note, timestamps
        model.scad       the current design
        model.stl        the last successful build
        history/         earlier versions of model.scad (newest HISTORY_LIMIT kept)
        chat.json        raw model replay + display text, opaque to this module
        attachments/     photos she shared

Every write is atomic (temp file + rename) so a crash or power cut never leaves half a file.
Nothing here raises for the things that go wrong on a real Mac in normal use; bad or missing
files read as empty so the app keeps working.
"""

from __future__ import annotations

import contextlib
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from print_explosion_3d.workspace.trash import move_to_trash

HISTORY_LIMIT = 20
STATE_FILE = "state.json"
EMPTY_PROJECT_GRACE = 24 * 3600  # an untouched new project is kept for a day

_BAD_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _folder_name(name: str) -> str:
    cleaned = _BAD_NAME_CHARS.sub(" ", name)
    cleaned = " ".join(cleaned.split()).strip(". ")
    return cleaned[:60].strip(". ") or "Untitled"


@dataclass(frozen=True, slots=True)
class ProjectInfo:
    folder: str
    name: str
    note: str
    updated: str  # ISO timestamp; sorts chronologically


class Project:
    def __init__(self, path: Path) -> None:
        self.path = path

    @property
    def folder(self) -> str:
        return self.path.name

    @property
    def scad_path(self) -> Path:
        return self.path / "model.scad"

    @property
    def stl_path(self) -> Path:
        return self.path / "model.stl"

    @property
    def thumb_path(self) -> Path:
        return self.path / "thumbnail.png"

    @property
    def history_dir(self) -> Path:
        return self.path / "history"

    @property
    def chat_path(self) -> Path:
        return self.path / "chat.json"

    @property
    def attachments_dir(self) -> Path:
        return self.path / "attachments"

    # --- metadata ---------------------------------------------------------------------------

    def _meta(self) -> dict[str, Any]:
        return _read_json(self.path / "project.json")

    def update_meta(self, **fields: Any) -> None:
        meta = {"name": self.folder, "note": "", "created": _now(), **self._meta()}
        meta.update({"updated": _now(), **fields})
        _write_atomic(self.path / "project.json", json.dumps(meta, indent=2).encode())

    @property
    def name(self) -> str:
        value = self._meta().get("name")
        return value if isinstance(value, str) and value else self.folder

    @property
    def note(self) -> str:
        value = self._meta().get("note")
        return value if isinstance(value, str) else ""

    def info(self) -> ProjectInfo:
        updated = self._meta().get("updated")
        return ProjectInfo(
            self.folder, self.name, self.note, updated if isinstance(updated, str) else ""
        )

    # --- the design -------------------------------------------------------------------------

    def read_scad(self) -> str:
        try:
            return self.scad_path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def save_scad(self, text: str) -> bool:
        """Save the design, keeping the version it replaces in history/. False if unchanged."""
        previous = self.read_scad()
        if text == previous:
            return False
        if previous:
            self._snapshot(previous)
        _write_atomic(self.scad_path, text.encode("utf-8"))
        self.update_meta()
        return True

    def _snapshot(self, text: str) -> None:
        self.history_dir.mkdir(exist_ok=True)
        # Microsecond stamp: sorts by name and can't collide with a quick second save.
        stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{time.time_ns() // 1000 % 1_000_000:06d}"
        _write_atomic(self.history_dir / f"{stamp}.scad", text.encode("utf-8"))
        versions = self.history()
        for old in versions[: max(0, len(versions) - HISTORY_LIMIT)]:
            old.unlink(missing_ok=True)

    def history(self) -> list[Path]:
        """Saved earlier versions, oldest first."""
        return sorted(self.history_dir.glob("*.scad")) if self.history_dir.is_dir() else []

    def save_stl(self, data: bytes) -> None:
        _write_atomic(self.stl_path, data)

    # --- chat and attachments ---------------------------------------------------------------

    def read_chat(self) -> dict[str, Any]:
        return _read_json(self.chat_path)

    def save_chat(self, chat: dict[str, Any]) -> None:
        _write_atomic(self.chat_path, json.dumps(chat, ensure_ascii=False).encode("utf-8"))
        self.update_meta()

    def add_attachment(self, filename: str, data: bytes) -> Path:
        """Store a photo; returns its path. A clashing name gets a numeric suffix."""
        base = Path(_folder_name(Path(filename).stem) or "photo")
        suffix = Path(filename).suffix.lower()[:8]
        self.attachments_dir.mkdir(exist_ok=True)
        target = self.attachments_dir / f"{base}{suffix}"
        n = 2
        while target.exists():
            target = self.attachments_dir / f"{base} {n}{suffix}"
            n += 1
        _write_atomic(target, data)
        return target

    # --- housekeeping -----------------------------------------------------------------------

    def is_empty(self) -> bool:
        return not self.read_scad().strip() and not self.read_chat()

    def clean_stale(self) -> int:
        """Drop leftovers: temp files, a model.stl older than its design, unused photos.

        Returns how many files were removed.
        """
        removed = 0

        def remove(path: Path) -> None:
            nonlocal removed
            with contextlib.suppress(OSError):
                path.unlink()
                removed += 1

        for tmp in self.path.rglob(".*.tmp"):
            remove(tmp)
        if self.stl_path.exists() and (
            not self.scad_path.exists()
            or self.stl_path.stat().st_mtime < self.scad_path.stat().st_mtime
        ):
            remove(self.stl_path)
        if self.attachments_dir.is_dir():
            chat = self.chat_path.read_text(encoding="utf-8") if self.chat_path.exists() else ""
            for photo in self.attachments_dir.iterdir():
                if photo.is_file() and photo.name not in chat:
                    remove(photo)
        return removed


class Workspace:
    def __init__(self, root: Path, trash: Callable[[Path], None] = move_to_trash) -> None:
        self.root = root
        self._trash = trash
        self.root.mkdir(parents=True, exist_ok=True)

    # --- projects ---------------------------------------------------------------------------

    def _projects(self) -> list[Project]:
        return [
            Project(p) for p in self.root.iterdir() if p.is_dir() and not p.name.startswith(".")
        ]

    def list_projects(self) -> list[ProjectInfo]:
        """Every project, most recently updated first."""
        infos = [p.info() for p in self._projects()]
        return sorted(infos, key=lambda i: (i.updated, i.name.lower()), reverse=True)

    def get(self, folder: str) -> Project | None:
        path = self.root / folder
        # `folder` came from the page; never let it climb out of the workspace.
        if folder in {"", ".", ".."} or path.parent != self.root or not path.is_dir():
            return None
        return Project(path)

    def create(self, name: str = "New project") -> Project:
        base = _folder_name(name)
        path = self.root / base
        n = 2
        while path.exists():
            path = self.root / f"{base} {n}"
            n += 1
        path.mkdir()
        project = Project(path)
        project.update_meta(name=name.strip() or base)
        self.set_last_opened(project.folder)
        return project

    def rename(self, project: Project, name: str) -> None:
        """Change the display name only; the folder keeps its name so paths stay stable."""
        if name.strip():
            project.update_meta(name=name.strip())

    def delete(self, folder: str) -> bool:
        """Move a project to the Trash. False if it doesn't exist or can't be trashed."""
        project = self.get(folder)
        if project is None:
            return False
        try:
            self._trash(project.path)
        except OSError:
            return False
        if self.last_opened() == folder:
            self.set_last_opened(None)
        return True

    # --- last opened ------------------------------------------------------------------------

    def last_opened(self) -> str | None:
        folder = _read_json(self.root / STATE_FILE).get("last_opened")
        return folder if isinstance(folder, str) and self.get(folder) else None

    def set_last_opened(self, folder: str | None) -> None:
        _write_atomic(self.root / STATE_FILE, json.dumps({"last_opened": folder}).encode())

    def open_last(self) -> Project | None:
        folder = self.last_opened()
        return self.get(folder) if folder else None

    # --- startup ----------------------------------------------------------------------------

    def clean_stale(self, now: float | None = None) -> int:
        """Run once at startup. Trashes long-untouched empty projects, tidies the rest.

        Returns how many things were removed.
        """
        now = time.time() if now is None else now
        removed = 0
        for project in self._projects():
            if project.is_empty():
                age = now - project.path.stat().st_mtime
                if age > EMPTY_PROJECT_GRACE and self.delete(project.folder):
                    removed += 1
                continue
            removed += project.clean_stale()
        for tmp in self.root.glob(".*.tmp"):
            with contextlib.suppress(OSError):
                tmp.unlink()
        return removed
