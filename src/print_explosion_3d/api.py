"""The JS bridge. Public methods are callable from the page as `window.pywebview.api.<name>()`.

Keep this thin: validate/convert arguments and delegate to the real modules. pywebview exposes
every public attribute, so anything that must stay Python-only gets a leading underscore.

Long jobs (an AI turn, a build) run on a worker thread and report back with events: Python calls
`window.peEvent(name, data)` in the page. Events: `status`, `text`, `turn_done`, `built`.
"""

from __future__ import annotations

import base64
import contextlib
import json
import re
import shutil
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from typing import Any

from print_explosion_3d import bambu, updater
from print_explosion_3d.ai import Image, Provider, ProviderError, make_provider
from print_explosion_3d.ai.usage import total_cost
from print_explosion_3d.config import Settings
from print_explosion_3d.designer import Designer, TurnResult, visible_prose
from print_explosion_3d.scad.params import ParamError, apply_values, parse_params, visible_sections
from print_explosion_3d.scad.runner import render
from print_explosion_3d.workspace import Project, Workspace, find_projects

DEFAULT_NAME = "New project"
MAX_IMAGES = 4
MAX_THUMB_BYTES = 400_000
MAX_IMAGE_BYTES = 6_000_000  # after the page has downscaled it, so this is a safety net

_NEW_PROJECT = re.compile(
    r"^\s*(?:please\s+)?(?:let'?s\s+)?(?:start|begin|make|create|do)\s+(?:a\s+|another\s+)?"
    r"(?:brand\s+)?new\s+(?:project|design|one|thing)\s*[.!]?\s*$",
    re.IGNORECASE,
)
_OPEN_PROJECT = re.compile(
    r"^\s*(?:please\s+)?(?:open|resume|continue|reopen|switch\s+to|go\s+back\s+to)\b", re.IGNORECASE
)

MSG_BUSY = "One moment, I'm still working on the last thing."
MSG_BUILD_FAILED = (
    "Those settings didn't work together, so I put things back the way they were. "
    "Try changing them a little less."
)
MSG_NO_OPENSCAD = "I can't build designs on this computer yet. Ask Brad to take a look."
_ENVIRONMENT_CODES = {"no_openscad", "old_openscad", "launch_failed", "missing_file"}

EventSink = Callable[[str, Any], None]


class Api:
    def __init__(
        self,
        settings: Settings,
        workspace: Workspace | None = None,
        *,
        provider_factory: Callable[[Settings], Provider] = make_provider,
        build: Callable[[Path, Path], Any] | None = None,
    ) -> None:
        self._settings = settings
        self._workspace = workspace or Workspace(settings.workspace_dir)
        self._provider_factory = provider_factory
        self._build = build or self._default_build
        self._current: Project | None = None
        self._designer: Designer | None = None
        self._built_scad = ""  # the design text that model.stl was built from
        self._emit: EventSink = lambda _name, _data: None
        self._window: Any = None
        self._busy = threading.Lock()
        self._started = time.strftime("%Y-%m-%dT%H:%M:%S")  # cost readout counts from here

    # --- wiring (Python side only) ------------------------------------------------------------

    def _attach(self, window: Any) -> None:
        """Connect the real window: events go to the page, dialogs open on it."""
        self._window = window

        def emit(name: str, data: Any) -> None:
            with contextlib.suppress(Exception):  # window closing; nobody left to tell
                window.evaluate_js(
                    f"window.peEvent && window.peEvent({json.dumps(name)}, {json.dumps(data)})"
                )

        self._emit = emit

    def _default_build(self, scad: Path, stl: Path) -> Any:
        s = self._settings
        return render(scad, stl, openscad_bin=s.openscad_bin, timeout=s.render_timeout)

    # --- basics -----------------------------------------------------------------------------

    def ping(self) -> dict[str, Any]:
        return {"ok": True, "version": version("print-explosion-3d")}

    def get_theme(self) -> dict[str, Any]:
        return asdict(self._settings.theme)

    def boot(self) -> dict[str, Any]:
        """Everything the page needs at start: theme, the last project (if any), key status."""
        return {
            "version": version("print-explosion-3d"),
            "theme": asdict(self._settings.theme),
            "project": self.open_project(),
            "has_key": bool(self._settings.anthropic_api_key),
            "cost": self.cost_text(),
        }

    def cost_text(self) -> str | None:
        """Status-bar text when PE_SHOW_COST is on; otherwise None."""
        if not self._settings.show_cost:
            return None
        spent = total_cost(self._settings.workspace_dir / "usage.jsonl", self._started)
        return f"AI cost this time: about ${spent:.2f}"

    # --- thumbnails -------------------------------------------------------------------------

    def save_thumbnail(self, data_url: str) -> bool:
        """Keep a small picture of the current model for the project list."""
        project = self._current
        prefix = "data:image/png;base64,"
        if project is None or not str(data_url).startswith(prefix):
            return False
        try:
            data = base64.b64decode(str(data_url)[len(prefix) :])
        except (ValueError, TypeError):
            return False
        if not data or len(data) > MAX_THUMB_BYTES:
            return False
        try:
            project.thumb_path.write_bytes(data)
        except OSError:
            return False
        return True

    def project_thumbs(self) -> dict[str, str]:
        """Folder -> data URL, for projects that have a picture."""
        out: dict[str, str] = {}
        for info in self._workspace.list_projects():
            project = self._workspace.get(info.folder)
            if project is None:
                continue
            try:
                raw = project.thumb_path.read_bytes()
            except OSError:
                continue
            out[info.folder] = "data:image/png;base64," + base64.b64encode(raw).decode()
        return out

    # --- updates ----------------------------------------------------------------------------

    def check_update(self) -> dict[str, Any]:
        """Silent check; the page shows the banner only if `available`."""
        if not self._settings.update_check:
            return {"available": False, "notes": ""}
        info = updater.check()
        return {"available": info.available, "notes": info.notes}

    def apply_update(self) -> dict[str, Any]:
        if self._busy.locked():
            return {"ok": False, "error": MSG_BUSY}
        if not updater.apply():
            return {"ok": False, "error": updater.MSG_UPDATE_FAILED}
        threading.Timer(0.5, updater.relaunch).start()  # let the page show "Restarting…" first
        return {"ok": True}

    # --- projects ---------------------------------------------------------------------------

    def list_projects(self) -> list[dict[str, Any]]:
        return [asdict(p) for p in self._workspace.list_projects()]

    def find_project(self, query: str) -> list[dict[str, Any]]:
        """Local fuzzy match for things like "open my bird feeder". No AI call."""
        return [asdict(p) for p in find_projects(str(query), self._workspace.list_projects())]

    def new_project(self, name: str = DEFAULT_NAME) -> dict[str, Any] | None:
        if self._busy.locked():
            return None
        project = self._workspace.create(str(name))
        self._set_current(project)
        return self._describe(project)

    def open_project(self, folder: str | None = None) -> dict[str, Any] | None:
        """Open `folder`, or the last project she had open if none is given."""
        if self._busy.locked():
            return None
        project = self._workspace.get(str(folder)) if folder else self._workspace.open_last()
        if project is None:
            return None
        self._set_current(project)
        self._workspace.set_last_opened(project.folder)
        return self._describe(project)

    def delete_project(self, folder: str) -> bool:
        """Move a project to the Trash (she can still get it back from there)."""
        if self._busy.locked():
            return False
        if self._current and self._current.folder == folder:
            self._set_current(None)
        return self._workspace.delete(str(folder))

    def save_design(self, scad: str) -> dict[str, Any]:
        """Autosave the open project's design. Returns the status line for the UI."""
        if self._current is None:
            return {"saved": False, "status": ""}
        self._current.save_scad(str(scad))
        return {"saved": True, "status": "All changes saved"}

    def _set_current(self, project: Project | None) -> None:
        self._current = project
        self._designer = None  # a new conversation is created lazily on her next message
        self._built_scad = project.read_scad() if project and project.stl_path.is_file() else ""

    def _describe(self, project: Project) -> dict[str, Any]:
        scad = project.read_scad()
        return {
            **asdict(project.info()),
            "scad": scad,
            "chat": project.read_chat(),
            "params": params_payload(scad),
            "has_stl": project.stl_path.is_file(),
        }

    # --- chat -------------------------------------------------------------------------------

    def send_message(self, text: str, images: list[dict[str, str]] | None = None) -> dict[str, Any]:
        """Start one turn. Returns at once; progress and the result arrive as events.

        `images` is a list of {"name", "data"} where data is a base64 JPEG (already downscaled).
        Obvious commands ("start a new project", "open my bird feeder") are handled locally.
        """
        text = str(text or "").strip()
        photos = _decode_images(images or [])
        if not text and not photos:
            return {"started": False}

        if not photos:
            handled = self._local_command(text)
            if handled is not None:
                return handled

        if not self._busy.acquire(blocking=False):
            return {"started": False, "error": MSG_BUSY}
        try:
            if self._current is None:
                self._set_current(self._workspace.create(DEFAULT_NAME))
            project = self._current
            assert project is not None
            if self._designer is None:
                self._designer = self._make_designer(project)
        except ProviderError as exc:
            self._busy.release()
            return {"started": False, "error": str(exc)}
        except Exception:
            self._busy.release()
            raise
        threading.Thread(
            target=self._run_turn, args=(self._designer, project, text, photos), daemon=True
        ).start()
        return {"started": True, "project": asdict(project.info())}

    def _make_designer(self, project: Project) -> Designer:
        s = self._settings
        return Designer(
            self._provider_factory(s),
            project,
            build=self._build,
            max_auto_fixes=s.max_auto_fixes,
            usage_path=s.workspace_dir / "usage.jsonl",
        )

    def _local_command(self, text: str) -> dict[str, Any] | None:
        if _NEW_PROJECT.match(text):
            project = self.new_project()
            return {"command": "new_project", "project": project} if project else None
        if _OPEN_PROJECT.match(text):
            matches = find_projects(text, self._workspace.list_projects())
            if matches:
                opened = self.open_project(matches[0].folder)
                if opened:
                    return {"command": "open_project", "project": opened}
        return None

    def _run_turn(
        self, designer: Designer, project: Project, text: str, photos: list[Image]
    ) -> None:
        streamed: list[str] = []

        def on_text(delta: str) -> None:
            streamed.append(delta)
            self._emit("text", visible_prose("".join(streamed)))

        try:
            result = designer.send(text, photos, on_text, lambda msg: self._emit("status", msg))
        except Exception:  # never show her a stack trace
            result = TurnResult(
                error="Something went wrong on my end. Please try again.", error_kind="other"
            )
        finally:
            self._busy.release()

        if result.changed:
            self._built_scad = project.read_scad()
        if result.changed and result.title and project.name == DEFAULT_NAME:
            self._workspace.rename(project, result.title)
        self._emit(
            "turn_done",
            {
                "text": result.text,
                "changed": result.changed,
                "choices": list(result.choices),
                "error": result.error,
                "project": asdict(project.info()),
                "params": params_payload(project.read_scad()) if result.changed else None,
                "warnings": [w.code for w in result.render.warnings] if result.render else [],
                "cost": self.cost_text(),
            },
        )

    # --- the model and its settings -----------------------------------------------------------

    def get_stl(self) -> str | None:
        """The built model as base64, for the viewer. None if nothing is built yet."""
        if self._current is None or not self._current.stl_path.is_file():
            return None
        return base64.b64encode(self._current.stl_path.read_bytes()).decode("ascii")

    def set_params(self, values: dict[str, Any]) -> dict[str, Any]:
        """Write her side-panel edits into the design file (no rebuild yet).

        Saving right away means the AI always sees the current values.
        """
        if self._current is None or self._busy.locked():
            return {"saved": False}
        try:
            after = apply_values(self._current.read_scad(), dict(values or {}))
        except ParamError as exc:
            return {"saved": False, "error": str(exc)}
        self._current.save_scad(after)
        return {"saved": True, "status": "All changes saved"}

    def generate(self) -> dict[str, Any]:
        """Rebuild the model from the saved design. A `built` event follows."""
        if self._current is None or not self._current.read_scad().strip():
            return {"started": False}
        if not self._busy.acquire(blocking=False):
            return {"started": False, "error": MSG_BUSY}
        threading.Thread(target=self._run_generate, args=(self._current,), daemon=True).start()
        return {"started": True}

    def _run_generate(self, project: Project) -> None:
        error: str | None = None
        try:
            self._emit("status", "Building…")
            scad = project.read_scad()
            with tempfile.TemporaryDirectory(prefix="pe-gen-") as tmp:
                src, out = Path(tmp) / "model.scad", Path(tmp) / "model.stl"
                src.write_text(scad, encoding="utf-8")
                built = self._build(src, out)
                if built.ok and out.is_file():
                    project.save_stl(out.read_bytes())
                    self._built_scad = scad
                else:
                    environment = any(i.code in _ENVIRONMENT_CODES for i in built.errors)
                    error = MSG_NO_OPENSCAD if environment else MSG_BUILD_FAILED
                    if not environment and self._built_scad:
                        project.save_scad(self._built_scad)  # back to the last design that worked
        except Exception:
            error = MSG_BUILD_FAILED
        finally:
            self._busy.release()
        self._emit(
            "built",
            {
                "error": error,
                "params": params_payload(project.read_scad()),
                "status": "All changes saved",
            },
        )

    # --- getting it printed -------------------------------------------------------------------

    def export_stl(self) -> dict[str, Any]:
        """Ask where to save, then copy the built model there."""
        if self._current is None or not self._current.stl_path.is_file():
            return {"saved": False, "error": "There's nothing to save yet."}
        if self._window is None:
            return {"saved": False}
        import webview

        chosen = self._window.create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename=f"{self._current.name}.stl",
            file_types=("3D print file (*.stl)",),
        )
        if not chosen:
            return {"saved": False}
        target = Path(chosen if isinstance(chosen, str) else chosen[0])
        if target.suffix.lower() != ".stl":
            target = target.with_suffix(".stl")
        try:
            shutil.copyfile(self._current.stl_path, target)
        except OSError:
            return {"saved": False, "error": "I couldn't save it there. Try another folder."}
        return {"saved": True, "name": target.name}

    def open_in_bambu(self) -> dict[str, Any]:
        if self._current is None or not self._current.stl_path.is_file():
            return {"opened": False, "error": "There's nothing to print yet."}
        return bambu.open_in_bambu(self._current.stl_path)


# --- helpers (module level, so tests can use them directly) -----------------------------------


def params_payload(scad: str) -> list[dict[str, Any]]:
    """The side panel's content: sections of editable settings (lists of numbers are skipped)."""
    try:
        sections = visible_sections(parse_params(scad))
    except Exception:  # a half-written file must never break the panel
        return []
    out = []
    for name, params in sections.items():
        items = [
            {
                "name": p.name,
                "label": p.label,
                "kind": p.kind,
                "value": p.value,
                "description": p.description,
                "min": p.min,
                "max": p.max,
                "step": p.step,
                "max_length": p.max_length,
                "options": [{"value": o.value, "label": o.label} for o in p.options],
            }
            for p in params
            if p.kind != "vector"
        ]
        if items:
            out.append({"section": name, "params": items})
    return out


def _decode_images(items: list[dict[str, str]]) -> list[Image]:
    photos: list[Image] = []
    for item in items[:MAX_IMAGES]:
        try:
            data = base64.b64decode(item.get("data", ""))
        except (ValueError, TypeError):
            continue
        if data and len(data) <= MAX_IMAGE_BYTES:
            photos.append(Image("image/jpeg", data, str(item.get("name") or "photo.jpg")))
    return photos
