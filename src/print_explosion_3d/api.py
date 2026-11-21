"""The JS bridge. Public methods are callable from the page as `window.pywebview.api.<name>()`.

Keep this thin: validate/convert arguments and delegate to the real modules. pywebview exposes
every public attribute, so anything that must stay Python-only gets a leading underscore.
"""

from __future__ import annotations

from dataclasses import asdict
from importlib.metadata import version
from typing import Any

from print_explosion_3d.config import Settings
from print_explosion_3d.workspace import Project, Workspace, find_projects


class Api:
    def __init__(self, settings: Settings, workspace: Workspace | None = None) -> None:
        self._settings = settings
        self._workspace = workspace or Workspace(settings.workspace_dir)
        self._current: Project | None = None

    def ping(self) -> dict[str, Any]:
        return {"ok": True, "version": version("print-explosion-3d")}

    def get_theme(self) -> dict[str, Any]:
        return asdict(self._settings.theme)

    # --- projects ---------------------------------------------------------------------------

    def list_projects(self) -> list[dict[str, Any]]:
        return [asdict(p) for p in self._workspace.list_projects()]

    def find_project(self, query: str) -> list[dict[str, Any]]:
        """Local fuzzy match for things like "open my bird feeder". No AI call."""
        return [asdict(p) for p in find_projects(str(query), self._workspace.list_projects())]

    def new_project(self, name: str = "New project") -> dict[str, Any]:
        self._current = self._workspace.create(str(name))
        return self._describe(self._current)

    def open_project(self, folder: str | None = None) -> dict[str, Any] | None:
        """Open `folder`, or the last project she had open if none is given."""
        project = self._workspace.get(str(folder)) if folder else self._workspace.open_last()
        if project is None:
            return None
        self._current = project
        self._workspace.set_last_opened(project.folder)
        return self._describe(project)

    def delete_project(self, folder: str) -> bool:
        """Move a project to the Trash (she can still get it back from there)."""
        if self._current and self._current.folder == folder:
            self._current = None
        return self._workspace.delete(str(folder))

    def save_design(self, scad: str) -> dict[str, Any]:
        """Autosave the open project's design. Returns the status line for the UI."""
        if self._current is None:
            return {"saved": False, "status": ""}
        self._current.save_scad(str(scad))
        return {"saved": True, "status": "All changes saved"}

    def _describe(self, project: Project) -> dict[str, Any]:
        return {**asdict(project.info()), "scad": project.read_scad(), "chat": project.read_chat()}
