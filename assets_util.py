import os
import sys


def resource_path(relative_path: str) -> str:
    """Resolve a path to a bundled asset, whether running from source or as a
    PyInstaller --onefile exe (where bundled files are extracted to sys._MEIPASS)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)
