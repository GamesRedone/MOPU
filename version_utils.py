"""Utilities for parsing and sorting version strings like 'v1.2.0', 'v1.0.12', 'v1.0.123'."""

import re


def parse_version(v: str):
    """Turn 'v1.2.0' or '1.2.0' into a tuple of ints (1, 2, 0) for correct numeric sorting.

    Falls back gracefully for non-numeric components so odd version strings don't crash --
    they'll just sort lexically relative to each other.
    """
    v = v.strip()
    if v.lower().startswith("v"):
        v = v[1:]
    parts = re.split(r"[.\-_]", v)
    out = []
    for p in parts:
        if p.isdigit():
            out.append((0, int(p)))
        else:
            out.append((1, p))
    return tuple(out)


def sort_versions(versions):
    """Return versions sorted oldest -> newest."""
    return sorted(set(versions), key=parse_version)


def version_chain(all_versions, current, target):
    """Given every known version string, and a current/target pair, return the ordered
    list of versions [current, ..., target] walking every intermediate version in between
    (regardless of direction -- if target < current this still returns a valid descending
    chain, though normal usage is upgrading).
    """
    ordered = sort_versions(all_versions)
    if current not in ordered or target not in ordered:
        raise ValueError("Current or target version not found in available versions.")
    i_cur = ordered.index(current)
    i_tgt = ordered.index(target)
    if i_cur <= i_tgt:
        return ordered[i_cur:i_tgt + 1]
    else:
        return list(reversed(ordered[i_tgt:i_cur + 1]))
