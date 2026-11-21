"""UI smoke test: open the real window on a sample project, check it, save a snapshot, quit.

Works without Screen Recording permission because the PNG comes from the WebGL canvas itself.
Uses a throwaway workspace, so it never touches real projects and needs neither OpenSCAD nor
an API key.

    uv run python scripts/smoke_ui.py [out.png]      # default: build/smoke.png (gitignored)

Prints the page state plus the app name macOS reports, as JSON. Exits non-zero if the bridge
didn't connect, nothing was drawn, the chat/settings didn't fill in, or the process is still
called "python".
"""

from __future__ import annotations

import base64
import json
import os
import struct
import sys
import tempfile
import time
from pathlib import Path

import AppKit
import webview

from print_explosion_3d.app import TITLE, launch
from print_explosion_3d.workspace import Workspace

BOOT_TIMEOUT_S = 20

SAMPLE_SCAD = """/* [Size] */
// How wide the box is, in mm.
width = 40; // [10:100]
// How tall the box is, in mm.
height = 20; // [5:60]
/* [Options] */
// Put a lid on it.
lid = true;
cube([width, 30, height]);
"""

UI_PROBE = """JSON.stringify({
  messages: document.querySelectorAll('.msg').length,
  chip: !!document.querySelector('.chip'),
  controls: document.querySelectorAll('.param').length,
  project: document.getElementById('project-switch').value,
})"""


def sample_stl(w: float = 40, d: float = 30, h: float = 20) -> bytes:
    """A binary STL box, so the smoke test needs no OpenSCAD."""
    v = [(x, y, z) for z in (0, h) for y in (0, d) for x in (0, w)]
    quads = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    tris = [t for a, b, c, e in quads for t in ((a, b, c), (a, c, e))]
    out = struct.pack("<80sI", b"smoke", len(tris))
    for t in tris:
        out += struct.pack("<3f", 0, 0, 0)
        for i in t:
            out += struct.pack("<3f", *v[i])
        out += b"\x00\x00"
    return out


def seed_workspace(root: Path) -> None:
    """One finished project, so the window opens on a model, chat history and settings."""
    project = Workspace(root, trash=lambda p: None).create("Smoke box")
    project.save_scad(SAMPLE_SCAD)
    project.save_stl(sample_stl())
    project.save_chat(
        {
            "display": [
                {"role": "user", "text": "A small box please"},
                {"role": "assistant", "text": "Here's a little box.", "chip": True},
            ]
        }
    )


def probe(window: webview.Window, out: Path, result: dict) -> None:
    try:
        window.events.loaded.wait(BOOT_TIMEOUT_S)
        app = AppKit.NSRunningApplication.currentApplication()
        result["app_name"] = str(app.localizedName())
        result["has_icon"] = AppKit.NSApp.applicationIconImage() is not None
        deadline = time.monotonic() + BOOT_TIMEOUT_S
        state = None
        while time.monotonic() < deadline:
            raw = window.evaluate_js(
                "window.__pe && window.__pe.state().frames > 30"
                " && window.__pe.state().triangles > 0"
                " ? JSON.stringify(window.__pe.state()) : null"
            )
            if raw:
                state = json.loads(raw)
                break
            time.sleep(0.25)
        result["state"] = state
        result["ui"] = json.loads(window.evaluate_js(UI_PROBE))
        if state:
            data_url = window.evaluate_js("window.__pe.viewer.snapshot()")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(base64.b64decode(data_url.split(",", 1)[1]))
            result["snapshot"] = str(out)
    finally:
        window.destroy()


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "build/smoke.png").resolve()
    result: dict = {}
    with tempfile.TemporaryDirectory(prefix="pe-smoke-") as tmp:
        os.environ["PE_WORKSPACE_DIR"] = tmp  # never touch her real projects
        seed_workspace(Path(tmp))
        launch(probe, out, result)
    print(json.dumps(result, indent=2))
    state = result.get("state") or {}
    ui = result.get("ui") or {}
    ok = (
        str(state.get("status", "")).startswith("Connected")
        and state.get("triangles", 0) > 0
        and result.get("app_name") == TITLE
        and ui.get("chip") is True
        and ui.get("controls", 0) >= 3
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
