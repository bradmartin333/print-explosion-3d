"""The designer's turn loop: the user talks, the AI designs, the app builds, failures auto-fix.

A `Designer` owns one conversation about one project. History is append-only: each assistant
turn's raw blocks are replayed unchanged. The one exception is a turn that fails before it
produces anything usable (network error, refusal); that turn is rolled back whole.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from print_explosion_3d.ai.base import Image, Message, Provider, ProviderError, TextSink
from print_explosion_3d.ai.usage import log_usage
from print_explosion_3d.config import Settings
from print_explosion_3d.designer.protocol import parse_reply
from print_explosion_3d.scad.runner import RenderResult, render
from print_explosion_3d.workspace import Project

Build = Callable[[Path, Path], RenderResult]
Status = Callable[[str], None]

# Environment problems: asking the AI to "fix" the design can't help.
_ENVIRONMENT_CODES = {"no_openscad", "old_openscad", "launch_failed", "missing_file"}

MSG_NO_OPENSCAD = (
    "I made a design, but I can't build it because OpenSCAD isn't set up on this computer. "
    "Ask whoever set this up to take a look."
)
MSG_GAVE_UP = "I couldn't get that to work. Try describing it differently, or something simpler."
MSG_REFUSED = "I can't help with that one. Could we try something different?"
MSG_TOO_BIG = "That one got too big for me to finish. Could we try something simpler?"


def load_system_prompt() -> str:
    """The byte-stable system prompt. No timestamps, names or per-user data, ever."""
    return resources.files(__package__).joinpath("system_prompt.md").read_text(encoding="utf-8")


@dataclass(slots=True)
class TurnResult:
    text: str = ""  # what to show the user
    changed: bool = False  # a new design was built and applied ("Design updated")
    title: str | None = None
    note: str | None = None
    choices: tuple[str, ...] = ()
    error: str | None = None  # friendly; set when the turn failed
    error_kind: str | None = None
    auto_fixes: int = 0
    render: RenderResult | None = field(default=None, repr=False)

    @property
    def ok(self) -> bool:
        return self.error is None


class Designer:
    def __init__(
        self,
        provider: Provider,
        project: Project,
        *,
        build: Build,
        max_auto_fixes: int = 2,
        usage_path: Path | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self._provider = provider
        self.project = project
        self._build = build
        self._max_fixes = max(0, max_auto_fixes)
        self._usage_path = usage_path
        self._system = system_prompt if system_prompt is not None else load_system_prompt()

        chat = project.read_chat()
        display = chat.get("display")
        self.display: list[dict[str, Any]] = display if isinstance(display, list) else []
        self.messages: list[Message] = []
        self._known_scad = project.read_scad()
        self._seed()

    @classmethod
    def from_settings(
        cls, settings: Settings, provider: Provider, project: Project, **kwargs: Any
    ) -> Designer:
        def build(scad: Path, stl: Path) -> RenderResult:
            return render(
                scad, stl, openscad_bin=settings.openscad_bin, timeout=settings.render_timeout
            )

        kwargs.setdefault("usage_path", settings.workspace_dir / "usage.jsonl")
        return cls(provider, project, build=build, max_auto_fixes=settings.max_auto_fixes, **kwargs)

    # --- resume -------------------------------------------------------------------------------

    def _seed(self) -> None:
        """A resumed project starts a NEW conversation from its memory note and current file."""
        scad, note = self._known_scad, self.project.note
        if not scad.strip() and not note:
            return
        parts = [f'Resuming the project "{self.project.name}".']
        if note:
            parts.append(f"Memory: {note}")
        if scad.strip():
            parts.append(f"The current file:\n```openscad\n{scad}```")
        self.messages.append(Message("note", "\n".join(parts)))

    # --- a turn -------------------------------------------------------------------------------

    def send(
        self,
        text: str,
        images: Sequence[Image] = (),
        on_text: TextSink | None = None,
        on_status: Status | None = None,
    ) -> TurnResult:
        """Handle one thing the user said. Blocking; run it off the UI thread."""
        status = on_status or (lambda _msg: None)
        mark_messages, mark_display = len(self.messages), len(self.display)
        mark_known = self._known_scad

        saved = [self.project.add_attachment(i.name or "photo.jpg", i.data).name for i in images]
        images = tuple(
            Image(i.media_type, i.data, name) for i, name in zip(images, saved, strict=True)
        )

        # Side-panel edits live in the file; make sure the AI sees the current one.
        current = self.project.read_scad()
        if current != self._known_scad and current.strip():
            self.messages.append(
                Message(
                    "note",
                    "The user changed the settings or the file by hand. The file is now:\n"
                    f"```openscad\n{current}```",
                )
            )
            self._known_scad = current

        self.messages.append(Message("user", text, images))
        self.display.append({"role": "user", "text": text, "images": saved})

        def roll_back(error: str, kind: str) -> TurnResult:
            del self.messages[mark_messages:]
            del self.display[mark_display:]
            self._known_scad = mark_known
            return TurnResult(error=error, error_kind=kind)

        fixes = 0
        while True:
            status("Thinking…" if fixes == 0 else "Fixing a small problem…")
            try:
                reply = self._provider.complete(self._system, self.messages, on_text)
            except ProviderError as exc:
                return roll_back(str(exc), exc.kind)
            self._log(reply.usage, "fix" if fixes else "turn")
            if reply.refused:
                return roll_back(MSG_REFUSED, "refused")

            parsed = parse_reply(reply.text)
            if reply.truncated and parsed.scad is None:
                return roll_back(MSG_TOO_BIG, "truncated")
            self.messages.append(Message("assistant", reply.text, raw=reply.raw or None))

            if parsed.scad is None:  # just talking
                result = TurnResult(
                    text=parsed.prose, choices=parsed.choices, auto_fixes=fixes, note=parsed.note
                )
                return self._finish(result)

            status("Building…")
            built = self._try_build(parsed.scad)
            if built.ok:
                self.project.save_scad(parsed.scad)
                if built.stl_path is not None:
                    self.project.save_stl(built.stl_path.read_bytes())
                self._known_scad = parsed.scad
                if parsed.note:
                    self.project.update_meta(note=parsed.note)
                result = TurnResult(
                    text=parsed.prose,
                    changed=True,
                    title=parsed.title,
                    note=parsed.note,
                    choices=parsed.choices,
                    auto_fixes=fixes,
                    render=built,
                )
                return self._finish(result)

            if any(i.code in _ENVIRONMENT_CODES for i in built.errors):
                self.messages.append(
                    Message(
                        "note",
                        "The design could not be built on this computer and was not "
                        "applied. The project file is unchanged.",
                    )
                )
                return self._finish(
                    TurnResult(error=MSG_NO_OPENSCAD, error_kind="no_openscad", render=built)
                )

            if fixes < self._max_fixes:
                fixes += 1
                self.messages.append(
                    Message(
                        "note",
                        "The design you just sent failed to build, so it was not applied. "
                        f"Problems:\n{built.describe_problems()}\n"
                        "Send the complete corrected file.",
                    )
                )
                continue

            self.messages.append(
                Message(
                    "note",
                    "The last design failed to build and was not applied. The project file is "
                    "unchanged.",
                )
            )
            return self._finish(
                TurnResult(error=MSG_GAVE_UP, error_kind="build", auto_fixes=fixes, render=built)
            )

    # --- helpers ------------------------------------------------------------------------------

    def _try_build(self, scad: str) -> RenderResult:
        """Build in a scratch folder so a broken design never overwrites the good one."""
        with tempfile.TemporaryDirectory(prefix="pe-candidate-") as tmp:
            src, out = Path(tmp) / "model.scad", Path(tmp) / "model.stl"
            src.write_text(scad, encoding="utf-8")
            result = self._build(src, out)
            if result.ok and result.stl_path == out:
                # Keep the bytes beyond the scratch folder's lifetime.
                kept = self.project.path / ".candidate.stl.tmp"
                kept.write_bytes(out.read_bytes())
                return RenderResult(
                    True, kept, result.bbox, result.issues, result.elapsed, result.stderr
                )
            return result

    def _finish(self, result: TurnResult) -> TurnResult:
        entry: dict[str, Any] = {"role": "assistant"}
        if not result.error:  # something worked, so earlier error notices are out of date
            self.display[:] = [e for e in self.display if e.get("role") != "info"]
        if result.error:
            entry = {"role": "info", "text": result.error}
        else:
            entry |= {"text": result.text, "chip": result.changed}
            if result.choices:
                entry["choices"] = list(result.choices)
        self.display.append(entry)
        self.project.save_chat({"display": self.display})
        # Clean up the scratch STL if the project copy was taken from it.
        (self.project.path / ".candidate.stl.tmp").unlink(missing_ok=True)
        return result

    def _log(self, usage: Any, label: str) -> None:
        if self._usage_path is not None:
            log_usage(self._usage_path, usage, label=label, project=self.project.folder)
