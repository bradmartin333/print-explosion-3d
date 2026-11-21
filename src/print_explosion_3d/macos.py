"""macOS niceties for a plain Python process (there's no .app bundle around `uv run`).

Without this the menu bar and Dock say "python3". Call `brand_process()` before pywebview starts.

Everything here is cosmetic, so every failure is swallowed: a broken rename must never stop the
app from opening.
"""

from __future__ import annotations

import ctypes
import logging
import sys

log = logging.getLogger(__name__)

_CORE_SERVICES = "/System/Library/Frameworks/CoreServices.framework/CoreServices"
_LS_DEFAULT_SESSION = -2  # kLSDefaultSessionID
_CF_STRING_ENCODING_UTF8 = 0x08000100


def brand_process(name: str) -> None:
    if sys.platform != "darwin":
        return
    try:
        import AppKit
        import Foundation
    except ImportError:
        return

    # 1. pywebview builds "About/Hide/Quit <name>" menu items from CFBundleName.
    bundle = Foundation.NSBundle.mainBundle()
    info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
    if info is not None:
        info["CFBundleName"] = name
        info["CFBundleDisplayName"] = name
    Foundation.NSProcessInfo.processInfo().setProcessName_(name)

    # 2. The menu bar title and Dock label come from LaunchServices, which registered this
    #    process as "python3". Rename it via the same private LaunchServices call Chromium uses
    #    for its helper processes. Needs the process checked in with the window server first.
    AppKit.NSApplication.sharedApplication()
    try:
        _set_launchservices_display_name(name)
    except Exception as exc:  # private API: anything can happen on a future macOS
        log.debug("LaunchServices rename unavailable: %s", exc)


def _set_launchservices_display_name(name: str) -> None:
    ls = ctypes.CDLL(_CORE_SERVICES)
    get_asn = ls["_LSGetCurrentApplicationASN"]
    get_asn.restype = ctypes.c_void_p
    get_asn.argtypes = []
    set_item = ls["_LSSetApplicationInformationItem"]
    set_item.restype = ctypes.c_int32
    set_item.argtypes = [ctypes.c_int] + [ctypes.c_void_p] * 4
    display_name_key = ctypes.c_void_p.in_dll(ls, "_kLSDisplayNameKey")

    create_string = ls["CFStringCreateWithCString"]
    create_string.restype = ctypes.c_void_p
    create_string.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    release = ls["CFRelease"]
    release.argtypes = [ctypes.c_void_p]

    asn = get_asn()
    if not asn:
        return
    cf_name = create_string(None, name.encode(), _CF_STRING_ENCODING_UTF8)
    try:
        status = set_item(_LS_DEFAULT_SESSION, asn, display_name_key, cf_name, None)
        if status != 0:
            log.debug("LaunchServices rename returned %s", status)
    finally:
        release(cf_name)
