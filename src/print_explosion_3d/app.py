"""Entry point: one native window hosting the web UI in web/."""

from __future__ import annotations

import os

import webview

from print_explosion_3d.api import Api
from print_explosion_3d.config import WEB_DIR, Settings, load_settings

TITLE = "Print Explosion 3D"


def create_main_window(settings: Settings) -> webview.Window:
    window = webview.create_window(
        TITLE,
        url=str(WEB_DIR / "index.html"),
        js_api=Api(settings),
        width=1440,
        height=900,
        min_size=(1100, 700),
        background_color=settings.theme.bg_color,
    )
    assert window is not None
    return window


def main() -> None:
    create_main_window(load_settings())
    # PE_DEBUG=1 enables the Web Inspector (right-click → Inspect Element).
    webview.start(http_server=True, debug=os.environ.get("PE_DEBUG") == "1")


if __name__ == "__main__":
    main()
