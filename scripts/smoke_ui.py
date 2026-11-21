"""UI smoke test: open the real window, wait for the page to boot, save a viewer snapshot, quit.

Works without Screen Recording permission because the PNG comes from the WebGL canvas itself.

    uv run python scripts/smoke_ui.py [out.png]

Prints the page state as JSON; exits non-zero if the bridge didn't connect or nothing was drawn.
"""

from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path

import webview

from print_explosion_3d.app import create_main_window
from print_explosion_3d.config import load_settings

BOOT_TIMEOUT_S = 20


def probe(window: webview.Window, out: Path, result: dict) -> None:
    try:
        window.events.loaded.wait(BOOT_TIMEOUT_S)
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
            out.write_bytes(base64.b64decode(data_url.split(",", 1)[1]))
            result["snapshot"] = str(out)
    finally:
        window.destroy()


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "smoke.png").resolve()
    window = create_main_window(load_settings())
    result: dict = {}
    webview.start(probe, (window, out, result), http_server=True)
    print(json.dumps(result, indent=2))
    state = result.get("state") or {}
    ok = str(state.get("status", "")).startswith("Connected") and state.get("triangles", 0) > 0
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
