"""Build a .scad file into an STL with OpenSCAD and report what happened as structured data.

Rules (see CLAUDE.md): Manifold backend, binary STL, bounding box from `--summary-file`,
`OPENSCADPATH` pointing at the bundled lib. Nothing here raises for a bad design: failures come
back as `RenderResult.issues` so the designer can feed them to the AI and the UI can show friendly
text. `Renderer` runs builds on a background thread so the window never freezes.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from print_explosion_3d.config import SCAD_LIB_DIR
from print_explosion_3d.scad.checks import check_bed
from print_explosion_3d.scad.models import BBox, Issue

MIN_OPENSCAD_YEAR = 2025
DEFAULT_TIMEOUT = 120.0

_FALLBACK_BINARIES = (
    "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD",
    "/opt/homebrew/bin/openscad",  # a Dock-launched app has a minimal PATH, so look here too
    "/usr/local/bin/openscad",
)

_DIAG = re.compile(r"^(ERROR|WARNING): (.*)$")
_LOCATION = re.compile(r"\s*in file (.+?), line (\d+)\s*$")
_VERSION = re.compile(r"(\d{4})\.(\d{1,2})")
# These are only warnings to OpenSCAD, but the design silently builds wrong without the missing
# piece, so we treat them as failures worth an automatic fix.
_SERIOUS_WARNING = re.compile(
    r"Ignoring unknown (module|function|variable)|Can't open (library|include)", re.IGNORECASE
)
_EMPTY = re.compile(r"top level object is empty|not a 3D object", re.IGNORECASE)


def find_openscad(configured: str | None = None) -> Path | None:
    """OPENSCAD_BIN (via settings) → PATH → /Applications (plus Homebrew). None if absent."""
    candidates: list[str | None] = [configured, shutil.which("openscad"), *_FALLBACK_BINARIES]
    for candidate in candidates:
        if candidate:
            path = Path(candidate).expanduser()
            if path.is_file() and os.access(path, os.X_OK):
                return path
    return None


def parse_version(text: str) -> tuple[int, int] | None:
    """Pull (year, month) out of `OpenSCAD version 2026.10.11`. None if unrecognisable."""
    match = _VERSION.search(text)
    return (int(match[1]), int(match[2])) if match else None


@lru_cache(maxsize=8)
def _version_of(binary: str) -> tuple[int, int] | None:
    try:
        proc = subprocess.run(
            [binary, "--version"], capture_output=True, text=True, timeout=15, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_version(proc.stderr + proc.stdout)  # older builds print to stdout


def parse_diagnostics(stderr: str) -> list[Issue]:
    """Turn OpenSCAD's stderr into Issues (line numbers and messages; no TRACE/ECHO noise)."""
    issues: list[Issue] = []
    seen: set[tuple[str, str, int | None]] = set()
    for raw in stderr.splitlines():
        match = _DIAG.match(raw.strip())
        if not match:
            continue
        level, message = match.groups()
        line = file = None
        loc = _LOCATION.search(message)
        if loc:
            file, line = loc[1], int(loc[2])
            message = message[: loc.start()].rstrip(". ")
        message = message.removeprefix("Parser error: ")

        if level == "ERROR":
            code = "syntax" if "syntax error" in message.lower() else "error"
            severity = "error"
            if message.lower().startswith("assertion"):
                code = "assertion"
        else:
            serious = bool(_SERIOUS_WARNING.search(message))
            code = "missing_piece" if serious else "warning"
            severity = "error" if serious else "warning"

        key = (code, message, line)
        if key not in seen:
            seen.add(key)
            issues.append(Issue(code, message, severity, line, file))
    return issues


def _bbox_from_summary(path: Path) -> BBox | None:
    try:
        box = json.loads(path.read_text())["geometry"]["bounding_box"]
        return BBox.of(box["min"], box["max"])
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return None


@dataclass(frozen=True, slots=True)
class RenderResult:
    ok: bool
    stl_path: Path | None = None
    bbox: BBox | None = None
    issues: tuple[Issue, ...] = ()
    elapsed: float = 0.0
    stderr: str = field(default="", repr=False)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    def describe_problems(self) -> str:
        """Technical summary for the AI fix round-trip. Empty string if there are no problems."""
        lines = [f"- {i}" for i in self.issues if i.severity == "error"]
        lines += [f"- (warning) {i}" for i in self.warnings]
        return "\n".join(lines)


def _fail(code: str, message: str, started: float, stderr: str = "") -> RenderResult:
    return RenderResult(
        ok=False,
        issues=(Issue(code, message),),
        elapsed=time.monotonic() - started,
        stderr=stderr,
    )


def render(
    scad_path: Path | str,
    stl_path: Path | str,
    *,
    openscad_bin: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    cancel: threading.Event | None = None,
) -> RenderResult:
    """Build `scad_path` into `stl_path` (blocking). The old STL survives a failed build."""
    started = time.monotonic()
    scad_path, stl_path = Path(scad_path), Path(stl_path)

    binary = find_openscad(openscad_bin)
    if binary is None:
        return _fail("no_openscad", "OpenSCAD is not installed.", started)
    version = _version_of(str(binary))
    if version is not None and version[0] < MIN_OPENSCAD_YEAR:
        return _fail(
            "old_openscad",
            f"OpenSCAD {version[0]}.{version[1]:02d} is too old; {MIN_OPENSCAD_YEAR} or newer "
            "is required.",
            started,
        )
    if not scad_path.is_file():
        return _fail("missing_file", f"Design file not found: {scad_path.name}", started)

    stl_path.parent.mkdir(parents=True, exist_ok=True)
    part = stl_path.with_name(stl_path.name + ".part")
    lib_path = os.pathsep.join(filter(None, [str(SCAD_LIB_DIR), os.environ.get("OPENSCADPATH")]))

    with tempfile.TemporaryDirectory(prefix="pe-scad-") as tmp:
        summary = Path(tmp) / "summary.json"
        cmd = [
            str(binary),
            "--backend",
            "Manifold",
            "--export-format",
            "binstl",
            "--summary",
            "all",  # the bounding box is only written when a summary is requested
            "--summary-file",
            str(summary),
            "-o",
            str(part),
            str(scad_path),
        ]
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=scad_path.parent,
                env={**os.environ, "OPENSCADPATH": lib_path},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
            )
        except OSError as exc:
            return _fail("launch_failed", f"Could not start OpenSCAD: {exc}", started)

        deadline = started + timeout
        while True:
            try:
                _, stderr = proc.communicate(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                reason = None
                if cancel is not None and cancel.is_set():
                    reason = ("cancelled", "The build was replaced by a newer one.")
                elif time.monotonic() > deadline:
                    reason = ("timeout", f"The build took longer than {timeout:.0f} seconds.")
                if reason:
                    proc.kill()
                    _, stderr = proc.communicate()
                    part.unlink(missing_ok=True)
                    return _fail(*reason, started, stderr)

        issues = parse_diagnostics(stderr)
        bbox = _bbox_from_summary(summary)

    if _EMPTY.search(stderr):
        issues.append(Issue("empty", "The design builds nothing: the top-level object is empty."))
    elif proc.returncode != 0 and not any(i.severity == "error" for i in issues):
        tail = " ".join(stderr.strip().splitlines()[-3:]) or f"exit code {proc.returncode}"
        issues.append(Issue("error", f"OpenSCAD failed: {tail}"))

    if bbox is not None and not any(i.code == "empty" for i in issues):
        issues += check_bed(bbox)

    failed = any(i.severity == "error" for i in issues) or not part.is_file()
    if failed:
        part.unlink(missing_ok=True)
        return RenderResult(False, None, bbox, tuple(issues), time.monotonic() - started, stderr)

    part.replace(stl_path)
    return RenderResult(True, stl_path, bbox, tuple(issues), time.monotonic() - started, stderr)


class Renderer:
    """Runs builds on one background thread. A new submit supersedes any build in progress."""

    def __init__(self, *, openscad_bin: str | None = None, timeout: float = DEFAULT_TIMEOUT):
        self._bin = openscad_bin
        self._timeout = timeout
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scad-render")
        self._lock = threading.Lock()
        self._cancel = threading.Event()

    def submit(
        self,
        scad_path: Path | str,
        stl_path: Path | str,
        on_done: Callable[[RenderResult], None] | None = None,
    ) -> Future[RenderResult]:
        """Start a build. `on_done` runs on the worker thread, so hand results to the UI safely."""
        with self._lock:
            self._cancel.set()  # supersede whatever is running or queued
            token = self._cancel = threading.Event()
        future = self._pool.submit(
            render,
            scad_path,
            stl_path,
            openscad_bin=self._bin,
            timeout=self._timeout,
            cancel=token,
        )
        if on_done is not None:
            future.add_done_callback(lambda f: on_done(f.result()))
        return future

    def cancel(self) -> None:
        with self._lock:
            self._cancel.set()

    def shutdown(self) -> None:
        self.cancel()
        self._pool.shutdown(wait=True)
