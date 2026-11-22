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
from dataclasses import asdict, replace
from importlib.metadata import version
from pathlib import Path
from typing import Any

from print_explosion_3d import bambu, updater
from print_explosion_3d.ai import Image, Provider, ProviderError, make_provider
from print_explosion_3d.ai.catalog import choices_for, find_model
from print_explosion_3d.ai.usage import total_cost
from print_explosion_3d.config import Settings
from print_explosion_3d.designer import Designer, TurnResult, visible_prose
from print_explosion_3d.scad.estimate import analyze, size_text, time_text
from print_explosion_3d.scad.labels import label_sheet_scad, parse_names
from print_explosion_3d.scad.params import ParamError, apply_values, parse_params, visible_sections
from print_explosion_3d.scad.runner import render
from print_explosion_3d.workspace import Project, Workspace, find_projects
from print_explosion_3d.workspace.store import SHARE_EXTENSION, safe_file_name

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

_DUPLICATE = re.compile(
    r"^\s*(?:please\s+)?(?:(?:make|create|save|do)\s+(?:me\s+)?(?:a\s+)?)?(?:copy|duplicate)"
    r"(?:\s+(?:of\s+)?(?:this|it|the\s+project|this\s+project))?\s*[.!]?\s*$",
    re.IGNORECASE,
)
_LABELS = re.compile(
    r"^\s*(?:please\s+)?(?:make|create|print|design|i(?:'d)?\s+(?:want|need|like))\s+"
    r"(?:me\s+)?(?:some\s+|a\s+set\s+of\s+|a\s+few\s+)?labels?"
    r"(?:\s*(?:for|:|-|called|that\s+say|saying|with|of)?\s*(?P<names>.*?))?\s*[.!]?\s*$",
    re.IGNORECASE,
)

PREF_FLAGS = ("dark_mode", "still", "show_plate")
MSG_NOTHING_TO_UNDO = "There's nothing to go back to yet"
MSG_LABELS = "Here's your label sheet. Edit the words on the right, then press “Update the model”"

MSG_BUSY = "One moment, still working"
MSG_BUILD_FAILED = "Those settings don't work together, so I put things back. Try a smaller change."
MSG_NO_OPENSCAD = (
    "I can't build designs on this computer yet. Ask whoever set this up to take a look."
)
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
        self._info_cache: tuple[tuple[str, int, int], Any] | None = None
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
            "prefs": self.get_prefs(),
            "models": self.list_models(),
        }

    # --- which AI model to use ------------------------------------------------------------------

    def _effective_settings(self) -> Settings:
        """The settings, with the model the user picked in the app (if any) applied."""
        chosen = find_model(self._workspace.prefs().get("model"))
        if chosen is None:
            return self._settings
        return replace(self._settings, provider=chosen.provider, model=chosen.id)

    def list_models(self) -> dict[str, Any]:
        s = self._effective_settings()
        return {
            "current": f"{s.provider}:{s.model}",
            "choices": [
                {
                    "key": m.key,
                    "label": m.label,
                    "hint": m.hint,
                    "provider": m.provider,
                    "provider_label": m.provider_label,
                }
                for m in choices_for(self._settings.provider, self._settings.model)
            ],
        }

    def set_model(self, key: str) -> dict[str, Any]:
        """Pick the AI model. The next message starts a fresh conversation with it.

        A new conversation (seeded from the project's note and current design, like resuming)
        keeps the saved history valid: one model's thinking can't be replayed to another.
        """
        if self._busy.locked():
            return {"ok": False, "error": MSG_BUSY, **self.list_models()}
        if find_model(key) is None:
            return {"ok": False, **self.list_models()}
        self._workspace.set_prefs({**self._workspace.prefs(), "model": key})
        self._designer = None
        return {"ok": True, **self.list_models()}

    # --- preferences: dark mode and the like ---------------------------------------

    def get_prefs(self) -> dict[str, Any]:
        """Look-and-feel choices. `dark_mode` stays None until set, so the page follows the Mac."""
        saved = self._workspace.prefs()
        prefs: dict[str, Any] = {"dark_mode": None, "still": False, "show_plate": False}
        for key in PREF_FLAGS:
            if isinstance(saved.get(key), bool):
                prefs[key] = saved[key]
        return prefs

    def set_prefs(self, values: dict[str, Any]) -> dict[str, Any]:
        prefs = self.get_prefs()
        for key, value in dict(values or {}).items():
            if key in PREF_FLAGS and isinstance(value, bool):
                prefs[key] = value
        saved = {k: v for k, v in prefs.items() if v is not None}
        self._workspace.set_prefs({**self._workspace.prefs(), **saved})  # keeps the model choice
        return prefs

    def cost_text(self) -> str | None:
        """Status-bar text when PE_SHOW_COST is on; otherwise None."""
        if not self._settings.show_cost:
            return None
        spent = total_cost(self._settings.workspace_dir / "usage.jsonl", self._started)
        return f"AI cost this time: ~${spent:.2f}"

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
        """Open `folder`, or the last project that was open if none is given."""
        if self._busy.locked():
            return None
        project = self._workspace.get(str(folder)) if folder else self._workspace.open_last()
        if project is None:
            return None
        self._set_current(project)
        self._workspace.set_last_opened(project.folder)
        return self._describe(project)

    def delete_project(self, folder: str) -> bool:
        """Move a project to the Trash (it can still be recovered from there)."""
        if self._busy.locked():
            return False
        if self._current and self._current.folder == folder:
            self._set_current(None)
        return self._workspace.delete(str(folder))

    def duplicate_project(self) -> dict[str, Any] | None:
        """Make a separate copy of the open project and switch to it."""
        if self._busy.locked() or self._current is None:
            return None
        copy = self._workspace.duplicate(self._current.folder)
        if copy is None:
            return None
        self._set_current(copy)
        return self._describe(copy)

    def export_project(self) -> dict[str, Any]:
        """Ask where to save, then write the open project as one file to share."""
        if self._current is None or self._window is None:
            return {"saved": False}
        import webview

        chosen = self._window.create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename=f"{safe_file_name(self._current.name)}{SHARE_EXTENSION}",
            file_types=("Print Explosion project (*.pe3d)",),
        )
        if not chosen:
            return {"saved": False}
        target = Path(chosen if isinstance(chosen, str) else chosen[0])
        if target.suffix.lower() != SHARE_EXTENSION:
            target = target.with_suffix(SHARE_EXTENSION)
        if not self._workspace.pack(self._current.folder, target):
            return {"saved": False, "error": "I couldn't save it there. Try another folder."}
        return {"saved": True, "name": target.name}

    def import_project(self) -> dict[str, Any]:
        """Ask for a shared project file and add it as a new project."""
        if self._busy.locked() or self._window is None:
            return {"opened": False}
        import webview

        chosen = self._window.create_file_dialog(
            webview.FileDialog.OPEN, file_types=("Print Explosion project (*.pe3d)",)
        )
        if not chosen:
            return {"opened": False}
        project = self._workspace.unpack(Path(chosen if isinstance(chosen, str) else chosen[0]))
        if project is None:
            return {"opened": False, "error": "That doesn't look like a shared project."}
        self._set_current(project)
        return {"opened": True, "project": self._describe(project)}

    def undo(self) -> dict[str, Any]:
        """Go back one step in the design and rebuild it. A `built` event follows."""
        if self._current is None:
            return {"started": False}
        if self._busy.locked():
            return {"started": False, "error": MSG_BUSY}
        if not self._current.undo():
            return {"started": False, "error": MSG_NOTHING_TO_UNDO}
        return self.generate()

    def make_labels(self, names: list[str] | None = None, said: str = "") -> dict[str, Any] | None:
        """Start a label sheet from the built-in template. No AI call; it builds right away."""
        if self._busy.locked():
            return None
        project = self._workspace.create("Labels")
        self._set_current(project)
        project.save_scad(label_sheet_scad(names))
        words = ", ".join(names) if names else "sample words"
        project.update_meta(note=f"A sheet of name labels with raised words ({words}).")
        display: list[dict[str, Any]] = [{"role": "user", "text": said}] if said else []
        display.append({"role": "assistant", "text": MSG_LABELS})
        project.save_chat({"display": display})
        described = self._describe(project)
        return {**described, "building": bool(self.generate().get("started"))}

    def save_design(self, scad: str) -> dict[str, Any]:
        """Autosave the open project's design. Returns the status line for the UI."""
        if self._current is None:
            return {"saved": False, "status": ""}
        self._current.save_scad(str(scad))
        return {"saved": True, "status": "All changes saved"}

    def _set_current(self, project: Project | None) -> None:
        self._current = project
        self._designer = None  # a new conversation is created lazily on the next message
        self._built_scad = project.read_scad() if project and project.stl_path.is_file() else ""

    def _describe(self, project: Project) -> dict[str, Any]:
        scad = project.read_scad()
        return {
            **asdict(project.info()),
            "scad": scad,
            "chat": project.read_chat(),
            "params": params_payload(scad),
            "has_stl": project.stl_path.is_file(),
            "can_undo": project.can_undo(),
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
        s = self._effective_settings()
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
        if _DUPLICATE.match(text):
            copy = self.duplicate_project()
            return {"command": "duplicate", "project": copy} if copy else None
        match = _LABELS.match(text)
        if match:
            names = parse_names(match["names"] or "")
            if len(names) > 1 or not (match["names"] or "").strip():
                project = self.make_labels(names or None, text)
                return {"command": "labels", "project": project} if project else None
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
        except Exception:  # never show the user a stack trace
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
                "can_undo": project.can_undo(),
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
        """Write the user's side-panel edits into the design file (no rebuild yet).

        Saving right away means the AI always sees the current values.
        """
        if self._current is None or self._busy.locked():
            return {"saved": False}
        try:
            after = apply_values(self._current.read_scad(), dict(values or {}))
        except ParamError as exc:
            return {"saved": False, "error": str(exc)}
        self._current.save_scad(after)
        return {"saved": True, "status": "All changes saved", "can_undo": self._current.can_undo()}

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
                "can_undo": project.can_undo(),
                "status": "All changes saved",
            },
        )

    # --- getting it printed -------------------------------------------------------------------

    def model_info(self) -> dict[str, Any] | None:
        """Size, rough print time and plastic, and any "heads up" notes, in plain English."""
        project = self._current
        if project is None or not project.stl_path.is_file():
            return None
        try:
            stat = project.stl_path.stat()
            key = (str(project.stl_path), stat.st_size, stat.st_mtime_ns)
            if self._info_cache is None or self._info_cache[0] != key:
                self._info_cache = (key, analyze(project.stl_path.read_bytes()))
        except OSError:
            return None
        info = self._info_cache[1]
        if info is None:
            return None
        return {
            "size": size_text(info.size),
            "dimensions": [round(v, 2) for v in info.size],
            "time": time_text(info.minutes),
            "plastic": f"~{max(1, round(info.grams))} g of plastic",
            "notes": list(info.notes),
            "ready": info.ready,
        }

    def _print_file(self, project: Project) -> Path:
        """A copy of the model named after the project, so Bambu Studio shows "Bird feeder"
        instead of "model"."""
        folder = project.path / "for printing"
        folder.mkdir(exist_ok=True)
        for old in folder.glob("*.stl"):
            old.unlink(missing_ok=True)
        target = folder / f"{safe_file_name(project.name)}.stl"
        target.write_bytes(project.stl_path.read_bytes())
        return target

    def export_stl(self) -> dict[str, Any]:
        """Ask where to save, then copy the built model there."""
        if self._current is None or not self._current.stl_path.is_file():
            return {"saved": False, "error": "There's nothing to save yet"}
        if self._window is None:
            return {"saved": False}
        import webview

        try:
            ready = self._print_file(self._current)
        except OSError:
            return {"saved": False, "error": "I couldn't get that ready. Please try again."}
        chosen = self._window.create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename=ready.name,
            file_types=("3D print file (*.stl)",),
        )
        if not chosen:
            return {"saved": False}
        target = Path(chosen if isinstance(chosen, str) else chosen[0])
        if target.suffix.lower() != ".stl":
            target = target.with_suffix(".stl")
        try:
            shutil.copyfile(ready, target)
        except OSError:
            return {"saved": False, "error": "I couldn't save it there. Try another folder."}
        return {"saved": True, "name": target.name}

    def open_in_bambu(self) -> dict[str, Any]:
        if self._current is None or not self._current.stl_path.is_file():
            return {"opened": False, "error": "There's nothing to print yet"}
        try:
            ready = self._print_file(self._current)
        except OSError:
            return {"opened": False, "error": "I couldn't get that ready. Please try again."}
        return bambu.open_in_bambu(ready)


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
