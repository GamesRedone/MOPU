"""
Generates/updates a diffs-<profile>.md changelog for every profile in a fetched repo,
purely by diffing each profile's own consecutive official versions against each other
(oldest -> newest) -- no custom MO2 profile is involved, unlike orchestrator.run_analysis.

Renames can't be reliably inferred from a plain list diff (see diffs_parser.py's module
docstring), so if the repo already has a diffs-<profile>.md, its existing "### Renamed"
entries are read back in and reapplied for the matching version steps -- this "updates"
an existing changelog (extending it to cover new versions, refreshing Added/Removed/
Enabled/Disabled/Repositioned) without losing renames a human already curated by hand.
A profile with no existing diffs file simply gets renames skipped (they'll show as a
plain Add + Remove instead), exactly like a normal Analyze run with no diffs.md.
"""

import os
import re
from dataclasses import dataclass
from typing import List, Optional

import file_formats as ff
import github_client as gc
from diffs_parser import parse_diffs_md
from merge_engine import merge_step, MergeLog
from version_utils import sort_versions


@dataclass
class GeneratedDiffs:
    profile: str
    output_path: str
    version_count: int


def _tag(name: str, file_label: str) -> str:
    kind = "PLUGIN" if file_label == "plugins.txt" else "MOD"
    return f"[ {kind} ] {name}"


def _existing_renames(repo_data: gc.RepoData, profile: str):
    """Renames already known for this profile, keyed by (old_version, new_version),
    read from its existing diffs-<profile>.md in the fetched repo, if any."""
    diffs_path = repo_data.diffs_paths.get(profile)
    if not diffs_path:
        return {}
    with open(diffs_path, "rb") as f:
        text = f.read().decode("utf-8-sig")
    steps = parse_diffs_md(text)
    return {key: step.renamed for key, step in steps.items()}


def _build_one(profile: str, versions_map: dict, known_renames: dict):
    """Walks every consecutive pair across ALL versions this profile has (oldest ->
    newest), the same way orchestrator.run_analysis walks a chain, except the
    "custom" profile being merged into starts as a plain copy of the oldest version
    instead of a real user's profile -- so every event the official modlist/plugins
    ever went through gets recorded, not just what a specific user's profile still
    needs applied."""
    versions = sort_versions(versions_map.keys())
    log = MergeLog()
    custom_modlist = None
    custom_plugins = None
    tracked_modlist_names = set()
    tracked_plugins_names = set()
    step_bounds = []  # (old_v, new_v, before_counts, after_counts)

    def counts():
        return (len(log.added), len(log.removed), len(log.renamed),
                len(log.repositioned), len(log.enabled), len(log.disabled))

    has_plugins = all(versions_map[v].get("plugins") for v in versions)

    for i in range(len(versions) - 1):
        old_v, new_v = versions[i], versions[i + 1]
        renamed = known_renames.get((old_v, new_v), {})
        before = counts()

        base_old_ml = ff.parse_modlist(versions_map[old_v]["modlist"])
        base_new_ml = ff.parse_modlist(versions_map[new_v]["modlist"])
        if custom_modlist is None:
            import copy
            custom_modlist = copy.deepcopy(base_old_ml)
        custom_modlist = merge_step(base_old_ml, base_new_ml, custom_modlist, renamed,
                                     "modlist.txt", log, tracked_names=tracked_modlist_names)

        if has_plugins:
            base_old_pl = ff.parse_plugins(versions_map[old_v]["plugins"])
            base_new_pl = ff.parse_plugins(versions_map[new_v]["plugins"])
            if custom_plugins is None:
                import copy
                custom_plugins = copy.deepcopy(base_old_pl)
            custom_plugins = merge_step(base_old_pl, base_new_pl, custom_plugins, renamed,
                                         "plugins.txt", log, tracked_names=tracked_plugins_names)

        step_bounds.append((old_v, new_v, before, counts()))

    return log, step_bounds, versions


def _render_md(title: str, log: MergeLog, step_bounds) -> str:
    lines = [
        f"# Changes to the Load Order of {title}",
        "",
        "The renamed mods found within this changelog are used by "
        "[MOPU](https://www.gamesredone.com/mopu/) to update your Custom MO2 Profile.",
    ]
    for old_v, new_v, before, after in reversed(step_bounds):
        added = log.added[before[0]:after[0]]
        removed = log.removed[before[1]:after[1]]
        renamed = log.renamed[before[2]:after[2]]
        repositioned = log.repositioned[before[3]:after[3]]
        enabled = log.enabled[before[4]:after[4]]
        disabled = log.disabled[before[5]:after[5]]

        lines += ["", f"## {old_v} → {new_v}"]

        if added:
            lines += ["", f"### Added ({len(added)})", ""]
            lines += [f"- {_tag(n, fl)}" for n, fl in added]
        if removed:
            lines += ["", f"### Removed ({len(removed)})", ""]
            lines += [f"- {_tag(n, fl)}" for n, fl in removed]
        if enabled:
            lines += ["", f"### Enabled ({len(enabled)})", ""]
            lines += [f"- {_tag(n, fl)}" for n, fl in enabled]
        if disabled:
            lines += ["", f"### Disabled ({len(disabled)})", ""]
            lines += [f"- {_tag(n, fl)}" for n, fl in disabled]
        if renamed:
            lines += ["", f"### Renamed ({len(renamed)})", ""]
            lines += [f"- {_tag(o, fl)} → {n}" for o, n, fl in renamed]
        if repositioned:
            lines += ["", f"### Repositioned ({len(repositioned)})", ""]
            lines += [f"- {_tag(n, fl)}" for n, fl in repositioned]

    lines += ["", "---", "", "*Generated by [MOPU](https://www.gamesredone.com/mopu/)*", ""]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text)


def generate_all_diffs(repo_data: gc.RepoData, title: str, output_dir: str,
                        progress_cb=None, diag=None) -> List[GeneratedDiffs]:
    """Generates/updates a diffs-<profile>.md for every profile in repo_data,
    writing each to output_dir. `title` is used as the changelog's heading (e.g. the
    repo name, matching how the real repo's own diffs.md files are titled -- just
    "ZISS", not the full profile name)."""
    def report(frac, msg):
        if progress_cb:
            progress_cb(frac, msg)

    def d(msg):
        if diag:
            diag.info(msg)

    os.makedirs(output_dir, exist_ok=True)
    profiles = sorted(repo_data.profiles.keys())
    results = []

    for i, profile in enumerate(profiles):
        report(i / max(len(profiles), 1), f"Generating changelog for '{profile}'...")
        versions_map = repo_data.profiles[profile]
        if len(versions_map) < 2:
            d(f"Skipping '{profile}' -- only {len(versions_map)} version(s), nothing to diff.")
            continue

        known_renames = _existing_renames(repo_data, profile)
        if profile in repo_data.diffs_paths:
            d(f"'{profile}': found existing diffs file, carrying forward its Renamed entries.")
        else:
            d(f"'{profile}': no existing diffs file -- renames will be skipped (shown as Add + Remove).")

        log, step_bounds, versions = _build_one(profile, versions_map, known_renames)
        d(f"'{profile}': walked {len(versions)} version(s) ({versions[0]} -> {versions[-1]}).")

        md = _render_md(title, log, step_bounds)
        # Lowercased regardless of the profile's own casing -- diffs-<profile>.md is
        # matched case-insensitively everywhere it's read back in (see
        # github_client._DIFFS_RE), so lowercasing it here just makes it easier to
        # link to, without changing which file MOPU treats as that profile's changelog.
        out_name = f"diffs-{profile.lower()}.md"
        out_path = os.path.join(output_dir, out_name)
        with open(out_path, "w", encoding="utf-8", newline="\r\n") as f:
            f.write(md)
        d(f"Wrote {out_path}")

        results.append(GeneratedDiffs(profile=profile, output_path=out_path,
                                       version_count=len(versions)))

    report(1.0, "Done.")
    return results
