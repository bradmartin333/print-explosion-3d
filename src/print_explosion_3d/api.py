"""The JS bridge. Public methods are callable from the page as `window.pywebview.api.<name>()`.

Keep this thin: validate/convert arguments and delegate to the real modules. pywebview exposes
every public attribute, so anything that must stay Python-only gets a leading underscore.
"""

from __future__ import annotations

from dataclasses import asdict
from importlib.metadata import version
from typing import Any

from print_explosion_3d.config import Settings


class Api:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def ping(self) -> dict[str, Any]:
        return {"ok": True, "version": version("print-explosion-3d")}

    def get_theme(self) -> dict[str, Any]:
        return asdict(self._settings.theme)
