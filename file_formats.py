"""
Parsing and re-serializing of the three MO2 profile files we care about:

  modlist.txt   -- lines are '#comment' or '+ModName' (enabled) / '-ModName' (disabled)
  plugins.txt   -- lines are '#comment' or '*Plugin.esp' (enabled) / 'Plugin.esp' (disabled)
  loadorder.txt -- lines are '#comment' or 'Plugin.esp' (order only, no state)

All three are CRLF, and we preserve that on write since MO2 expects it.
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Entry:
    name: str                  # the mod/plugin name (key used for matching across versions)
    state: Optional[bool]      # True = enabled, False = disabled, None = no state concept (loadorder.txt)
    is_comment: bool = False   # passthrough line, e.g. "# This file was automatically generated..."
    is_pseudo: bool = False    # modlist.txt only: "*" prefix instead of "+"/"-" -- an MO2-managed
    # pseudo-mod (DLC, Creation Club content) that isn't a real toggleable mod. Always
    # effectively "on"; kept as a real (non-comment) entry so it still participates
    # correctly in Added/Removed/Auto-Update/repositioning logic instead of being
    # invisible to all of it, but the "*" prefix is preserved verbatim on write since
    # it means something different from a regular "+" to MO2 itself.


def _read_lines(path):
    with open(path, "rb") as f:
        data = f.read()
    text = data.decode("utf-8-sig", errors="replace")
    # normalize line endings, we re-add CRLF on write
    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def parse_modlist(path) -> List[Entry]:
    entries = []
    for line in _read_lines(path):
        if line.startswith("#"):
            entries.append(Entry(name=line, state=None, is_comment=True))
        elif line.startswith("+"):
            entries.append(Entry(name=line[1:], state=True))
        elif line.startswith("-"):
            entries.append(Entry(name=line[1:], state=False))
        elif line.startswith("*"):
            entries.append(Entry(name=line[1:], state=True, is_pseudo=True))
        elif line.strip() == "":
            continue
        else:
            # unrecognized line format -- keep it verbatim so we never silently drop data
            entries.append(Entry(name=line, state=None, is_comment=True))
    return entries


def parse_plugins(path) -> List[Entry]:
    entries = []
    for line in _read_lines(path):
        if line.startswith("#"):
            entries.append(Entry(name=line, state=None, is_comment=True))
        elif line.startswith("*"):
            entries.append(Entry(name=line[1:], state=True))
        elif line.strip() == "":
            continue
        else:
            entries.append(Entry(name=line, state=False))
    return entries


def parse_loadorder(path) -> List[Entry]:
    entries = []
    for line in _read_lines(path):
        if line.startswith("#"):
            entries.append(Entry(name=line, state=None, is_comment=True))
        elif line.strip() == "":
            continue
        else:
            entries.append(Entry(name=line, state=None))
    return entries


def write_modlist(path, entries: List[Entry]):
    lines = []
    for e in entries:
        if e.is_comment:
            lines.append(e.name)
        elif e.is_pseudo:
            lines.append("*" + e.name)
        else:
            lines.append(("+" if e.state else "-") + e.name)
    with open(path, "wb") as f:
        f.write(("\r\n".join(lines) + "\r\n").encode("utf-8"))


def write_plugins(path, entries: List[Entry]):
    lines = []
    for e in entries:
        if e.is_comment:
            lines.append(e.name)
        else:
            lines.append(("*" if e.state else "") + e.name)
    with open(path, "wb") as f:
        f.write(("\r\n".join(lines) + "\r\n").encode("utf-8"))


def write_loadorder(path, entries: List[Entry]):
    lines = []
    for e in entries:
        lines.append(e.name)
    with open(path, "wb") as f:
        f.write(("\r\n".join(lines) + "\r\n").encode("utf-8"))
