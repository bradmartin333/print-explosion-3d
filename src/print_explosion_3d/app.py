"""Entry point: one native window hosting the web UI in web/."""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable
from typing import Any

import webview

from print_explosion_3d.ai import Provider, make_provider
from print_explosion_3d.api import Api
from print_explosion_3d.config import PACKAGE_DIR, WEB_DIR, Settings, load_settings
from print_explosion_3d.macos import brand_process
from print_explosion_3d.workspace import Workspace

TITLE = "Print Explosion 3D"
ICON_PATH = PACKAGE_DIR / "assets" / "icon.png"


def create_main_window(
    settings: Settings, provider_factory: Callable[[Settings], Provider] = make_provider
) -> webview.Window:
    workspace = Workspace(settings.workspace_dir)
    with contextlib.suppress(Exception):  # tidying up must never stop the app opening
        workspace.clean_stale()
    api = Api(settings, workspace, provider_factory=provider_factory)
    window = webview.create_window(
        TITLE,
        url=str(WEB_DIR / "index.html"),
        js_api=api,
        width=1440,
        height=900,
        min_size=(1100, 700),
        background_color=settings.theme.bg_color,
    )
    assert window is not None
    api._attach(window)
    return window


def launch(
    on_start: Callable[..., None] | None = None,
    *extra: Any,
    provider_factory: Callable[[Settings], Provider] = make_provider,
) -> None:
    """Brand the process, open the window, and run the GUI loop until it closes.

    `on_start(window, *extra)` runs on a background thread once the GUI loop starts, and
    `provider_factory` swaps the AI (both used by scripts/smoke_ui.py and scripts/screenshots.py).
    """
    brand_process(TITLE)
    window = create_main_window(load_settings(), provider_factory)
    webview.start(
        on_start,
        (window, *extra) if on_start else None,
        http_server=True,
        # PE_DEBUG=1 enables the Web Inspector (right-click → Inspect Element).
        debug=os.environ.get("PE_DEBUG") == "1",
        icon=str(ICON_PATH),
    )


def main() -> None:
    launch()


if __name__ == "__main__":
    main()
