"""
Loads the bundled EB Garamond font at runtime without installing it system-wide, using
the Windows GDI AddFontResourceEx API with FR_PRIVATE (so it's only usable by this
process, and is automatically released when the app closes). On non-Windows platforms
(e.g. during development) this silently no-ops and Tk falls back to a default font.
"""

import ctypes
import os
import sys

FONT_FAMILY = "EB Garamond"

_loaded = False


def load_bundled_font(ttf_path: str) -> bool:
    global _loaded
    if _loaded:
        return True
    if sys.platform != "win32":
        return False
    if not os.path.isfile(ttf_path):
        return False
    try:
        FR_PRIVATE = 0x10
        added = ctypes.windll.gdi32.AddFontResourceExW(str(ttf_path), FR_PRIVATE, 0)
        if added > 0:
            _loaded = True
            return True
    except Exception:
        pass
    return False
