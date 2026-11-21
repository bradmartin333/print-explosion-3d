"""UI smoke test: open the real window, wait for the page to boot, save a viewer snapshot, quit.

Works without Screen Recording permission because the PNG comes from the WebGL canvas itself.

    uv run python scripts/smoke_ui.py [out.png]      # default: build/smoke.png (gitignored)

Prints the page state plus the app name macOS reports, as JSON. Exits non-zero if the bridge
didn't connect, nothing was drawn, or the process is still called "python".
"""

from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path

import AppKit
import webview

from print_explosion_3d.app import TITLE, launch

BOOT_TIMEOUT_S = 20


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
                " ? JSON.stringify(window.__pe.state()) : null"
            )
            if raw:
                state = json.loads(raw)
                break
            time.sleep(0.25)
        result["state"] = state
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
    launch(probe, out, result)
    print(json.dumps(result, indent=2))
    state = result.get("state") or {}
    ok = (
        str(state.get("status", "")).startswith("Connected")
        and state.get("triangles", 0) > 0
        and result.get("app_name") == TITLE
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
