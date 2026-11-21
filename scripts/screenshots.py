"""README screenshots from the real window: hero, chat, adjust and projects PNGs.

    uv run python scripts/screenshots.py [out_dir]      # default: docs/screenshots

Seeds a throwaway workspace with the demo designs in scripts/demo/ (built by the real OpenSCAD),
then runs the real app with a scripted designer in place of the AI, so it spends no credits and
never touches real projects. The chat goes through the real UI: a photo is dropped in, messages
are sent, quick replies are clicked. Captures come from WebKit's own snapshot (see smoke_ui.py),
so no Screen Recording permission is needed. Needs OpenSCAD 2025+.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import AppKit
import Quartz
import webview
from smoke_ui import BOOT_TIMEOUT_S, window_png

from print_explosion_3d.ai.fake_provider import FakeProvider
from print_explosion_3d.app import launch
from print_explosion_3d.config import REPO_ROOT, load_settings
from print_explosion_3d.scad.runner import render
from print_explosion_3d.workspace import Workspace

DEMO = Path(__file__).parent / "demo"
WIDE_PX = 1600  # full-width shots are scaled to this; panel crops stay at screen resolution
TURN_TIMEOUT_S = 120

SEEDED = [  # (name, design file, what she asked, what the designer said, memory note)
    (
        "Herb Marker",
        "herb_marker.scad",
        "A little sign for the basil pot",
        "Here's a garden marker with BASIL in raised letters. The point pushes into the soil.",
        "Garden stake with raised plant name.",
    ),
    (
        "Phone Stand",
        "phone_stand.scad",
        "Something to hold my phone up on the counter while I cook",
        "Here's a stand that leans your phone back a little, with a gap for the charger cable.",
        "Counter phone stand, 12 mm phone with case.",
    ),
    (
        "Succulent Pot",
        "succulent_pot.scad",
        "A small pot for a succulent, something pretty",
        "Here's a six-sided pot with a gentle twist and a drain hole in the bottom.",
        "Twisted hexagonal succulent pot with drain hole.",
    ),
]

ASK = "Could you make something like this for my spice jars?"
REPLY_1 = """Here's a rack with steps, so you can read every label. It holds three jars on \
each of two steps. Would you like a third step?

```openscad
{scad}
```
<title>Spice Rack</title>
<note>Stepped spice rack for 45 mm jars, three per step, to fit the cupboard by the stove.</note>
<choices>Yes, add a third step|Two is enough</choices>"""
REPLY_2 = """Done! Three steps now, so nine jars, with a little edge so nothing slides off. \
Slanted sides or square?

```openscad
{scad}
```
<note>Stepped spice rack for 45 mm jars, three steps of three, front lips, slanted sides.</note>
<choices>Slanted|Square</choices>"""


# ---- seeding -------------------------------------------------------------------------------


def build(scad: Path, stl: Path) -> None:
    s = load_settings()
    result = render(scad, stl, openscad_bin=s.openscad_bin, timeout=s.render_timeout)
    if not result.ok:
        raise SystemExit(f"OpenSCAD failed on {scad.name}: {result.issues}")


def seed(root: Path) -> None:
    ws = Workspace(root, trash=lambda p: None)
    for name, design, asked, answered, note in SEEDED:
        project = ws.create(name)
        project.save_scad((DEMO / design).read_text())
        build(project.scad_path, project.stl_path)
        project.update_meta(note=note)
        chat = [
            {"role": "user", "text": asked},
            {"role": "assistant", "text": answered, "chip": True},
        ]
        project.save_chat({"display": chat})
        time.sleep(1.1)  # distinct "updated" times keep the project list in this order


def photo_jpeg(tmp: Path) -> bytes:
    """The stand-in photo she shares: spice jars on a shelf, drawn by OpenSCAD."""
    png, jpg = tmp / "jars.png", tmp / "jars.jpg"
    subprocess.run(
        ["openscad", "-o", png, "--imgsize=900,900", "--camera=0,10,70,62,0,0,560",
         "--projection=p", "--colorscheme=Nature", DEMO / "spice_jars_photo.scad"],
        check=True, capture_output=True,
    )  # fmt: skip
    subprocess.run(
        ["sips", "-s", "format", "jpeg", "-Z", "600", png, "--out", jpg],
        check=True, capture_output=True,
    )  # fmt: skip
    return jpg.read_bytes()


# ---- driving the page ----------------------------------------------------------------------


def js(window: webview.Window, expr: str):
    return window.evaluate_js(expr)


def wait_for(window: webview.Window, expr: str, timeout: float = BOOT_TIMEOUT_S) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if js(window, f"!!({expr})"):
            return
        time.sleep(0.25)
    raise TimeoutError(f"Timed out waiting for: {expr}")


def model_ready(window: webview.Window, name: str) -> None:
    wait_for(
        window,
        f"document.getElementById('project-name').textContent === {json.dumps(name)}"
        " && window.__pe.viewer.hasModel",
    )
    time.sleep(0.5)  # a few frames


def settle_view(window: webview.Window, turn: float) -> None:
    js(window, f"window.__pe.viewer.setSpinning(false); window.__pe.viewer.setTurn({turn})")
    time.sleep(0.3)


def make_thumbnails(window: webview.Window, root: Path) -> None:
    """Open each seeded project in the UI and save its picture, as a real build would."""
    for name, *_ in SEEDED:
        js(
            window,
            "[...document.querySelectorAll('#project-menu li')]"
            f".find((li) => li.querySelector('.nm').textContent === {json.dumps(name)}).click()",
        )
        model_ready(window, name)
        settle_view(window, -30)
        js(window, "window.__pe.thumbnail()")
        folder = next(p.folder for p in Workspace(root).list_projects() if p.name == name)
        thumb = root / folder / "thumbnail.png"
        deadline = time.monotonic() + BOOT_TIMEOUT_S
        while not thumb.is_file() and time.monotonic() < deadline:
            time.sleep(0.2)


def drop_photo(window: webview.Window, jpeg: bytes) -> None:
    data = base64.b64encode(jpeg).decode()
    js(
        window,
        f"""(() => {{
          const bytes = Uint8Array.from(atob("{data}"), (c) => c.charCodeAt(0));
          const dt = new DataTransfer();
          dt.items.add(new File([bytes], "spice-jars.jpg", {{ type: "image/jpeg" }}));
          document.getElementById("chat-panel").dispatchEvent(
            new DragEvent("drop", {{ dataTransfer: dt, bubbles: true, cancelable: true }}));
        }})()""",
    )
    wait_for(window, "!document.getElementById('attachments').hidden")


def turn_finished(window: webview.Window, chips: int) -> None:
    wait_for(
        window,
        f"document.querySelectorAll('.chip').length >= {chips}"
        " && document.getElementById('busy').hidden",
        TURN_TIMEOUT_S,
    )
    time.sleep(0.8)  # model load + thumbnail


# ---- capturing -----------------------------------------------------------------------------


def rect(window: webview.Window, selectors: list[str], pad: float = 0) -> tuple[float, ...]:
    """Union of the elements' boxes, in CSS pixels, padded and clamped to the page."""
    return tuple(
        json.loads(
            js(
                window,
                f"""JSON.stringify((() => {{
                  const rs = {json.dumps(selectors)}
                    .map((s) => document.querySelector(s).getBoundingClientRect());
                  const l = Math.max(0, Math.min(...rs.map((r) => r.left)) - {pad});
                  const t = Math.max(0, Math.min(...rs.map((r) => r.top)) - {pad});
                  const r = Math.min(innerWidth, Math.max(...rs.map((r) => r.right)) + {pad});
                  const b = Math.min(innerHeight, Math.max(...rs.map((r) => r.bottom)) + {pad});
                  return [l, t, r - l, b - t];
                }})())""",
            )
        )
    )


def crop(png: bytes, box: tuple[float, ...], scale: float) -> bytes:
    rep = AppKit.NSBitmapImageRep.imageRepWithData_(png)
    x, y, w, h = (round(v * scale) for v in box)
    part = Quartz.CGImageCreateWithImageInRect(rep.CGImage(), Quartz.CGRectMake(x, y, w, h))
    out = AppKit.NSBitmapImageRep.alloc().initWithCGImage_(part)
    return bytes(out.representationUsingType_properties_(AppKit.NSBitmapImageFileTypePNG, {}))


def save(path: Path, png: bytes, max_width: int | None = None) -> None:
    path.write_bytes(png)
    if max_width:
        subprocess.run(
            ["sips", "--resampleWidth", str(max_width), str(path)], check=True, capture_output=True
        )
    print(f"wrote {path}")


def shoot(window: webview.Window, out_dir: Path, root: Path, jpeg: bytes, result: dict) -> None:
    try:
        window.events.loaded.wait(BOOT_TIMEOUT_S)
        wait_for(window, "window.__pe && window.__pe.state().frames > 30")
        make_thumbnails(window, root)

        # The hero conversation, through the real composer.
        js(window, "document.getElementById('new-project').click()")
        wait_for(window, "document.getElementById('project-name').textContent === 'New project'")
        drop_photo(window, jpeg)
        js(window, f"document.getElementById('prompt').value = {json.dumps(ASK)}")
        js(window, "document.getElementById('composer').requestSubmit()")
        turn_finished(window, 1)
        js(window, "document.querySelector('.choices button').click()")
        turn_finished(window, 2)
        model_ready(window, "Spice Rack")
        settle_view(window, -32)
        js(window, "document.activeElement.blur()")

        scale = float(js(window, "window.devicePixelRatio"))
        out_dir.mkdir(parents=True, exist_ok=True)
        full = window_png(window)
        if full is None:
            raise RuntimeError("WebKit snapshot failed")
        save(out_dir / "hero.png", full, WIDE_PX)
        save(out_dir / "chat.png", crop(full, rect(window, ["#chat-panel"], 8), scale))
        box = rect(window, [".panel.viewer", ".panel.params"], 8)
        save(out_dir / "adjust.png", crop(full, box, scale), WIDE_PX)

        js(window, "document.getElementById('project-switch').click()")
        wait_for(window, "!document.getElementById('project-menu').hidden")
        time.sleep(0.3)
        menu = window_png(window)
        if menu is None:
            raise RuntimeError("WebKit snapshot failed")
        box = rect(window, [".chat-head", "#project-menu"], 12)
        save(out_dir / "projects.png", crop(menu, box, scale))
        result["ok"] = True
    except Exception as exc:  # report, then still close the window
        result["error"] = repr(exc)
    finally:
        window.destroy()


def main() -> int:
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else REPO_ROOT / "docs" / "screenshots")
    result: dict = {}
    with tempfile.TemporaryDirectory(prefix="pe-shots-") as tmp:
        root = Path(tmp) / "projects"
        os.environ.update(
            PE_WORKSPACE_DIR=str(root),  # never touch her real projects
            PE_SHOW_COST="false",
            ANTHROPIC_API_KEY="unused-the-designer-is-scripted",  # hides the "needs a key" note
        )
        seed(root)
        jpeg = photo_jpeg(Path(tmp))
        rack = (DEMO / "spice_rack.scad").read_text()
        two_steps = rack.replace("steps = 3; //", "steps = 2; //", 1)
        designer = FakeProvider([REPLY_1.format(scad=two_steps), REPLY_2.format(scad=rack)])
        launch(shoot, out_dir.resolve(), root, jpeg, result, provider_factory=lambda s: designer)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
