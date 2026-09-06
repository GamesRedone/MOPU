"""
Parses a diffs.md file (the "FNS Changelog Tracker" format) into a dict keyed by
(old_version, new_version) -> DiffStep, where each DiffStep holds the renamed-name
mapping for that version step. Renames are the one thing that can't be reliably
inferred by diffing two file listings, so diffs.md is authoritative for those.
Added/Removed/Enabled/Disabled are still cross-checked directly against the real
base modlist files by merge_engine, since diffs.md's own lists can include extra
annotations (e.g. "ModName -- d2026.8.31.0") that aren't part of the actual name.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass
class DiffStep:
    old_version: str
    new_version: str
    renamed: Dict[str, str] = field(default_factory=dict)  # old_name -> new_name


_SECTION_RE = re.compile(
    r"##\s*v?([0-9][^\s]*)\s*(?:→|->)\s*v?([0-9][^\s]*)", re.IGNORECASE
)
_RENAME_LINE_RE = re.compile(r"^-\s*(.+?)\s*(?:→|->)\s*(.+?)\s*$")


def _strip_trailing_annotation(name: str) -> str:
    """Strip trailing ' — dYYYY.M.D.N' style annotations some entries carry."""
    return re.split(r"\s+—\s+", name)[0].strip()


def parse_diffs_md(text: str) -> Dict[Tuple[str, str], DiffStep]:
    text = text.replace("\r\n", "\n")
    # Split into per-version-step chunks anchored on "## vX -> vY" headers
    matches = list(_SECTION_RE.finditer(text))
    steps: Dict[Tuple[str, str], DiffStep] = {}
    for idx, m in enumerate(matches):
        old_v, new_v = "v" + m.group(1), "v" + m.group(2)
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        chunk = text[start:end]

        step = DiffStep(old_version=old_v, new_version=new_v)

        renamed_match = re.search(
            r"###\s*Renamed\s*\n(.*?)(?=\n###|\Z)", chunk, re.DOTALL | re.IGNORECASE
        )
        if renamed_match:
            for line in renamed_match.group(1).splitlines():
                line = line.strip()
                if not line:
                    continue
                rm = _RENAME_LINE_RE.match(line)
                if rm:
                    old_name = _strip_trailing_annotation(rm.group(1))
                    new_name = _strip_trailing_annotation(rm.group(2))
                    step.renamed[old_name] = new_name

        steps[(old_v, new_v)] = step
    return steps
