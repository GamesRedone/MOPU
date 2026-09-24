"""
Orchestrates the merge across every version step, for both modlist.txt and plugins.txt,
and derives loadorder.txt afterward. Split into two phases so re-running "Analyze" with
different current/target versions never re-hits the network -- fetch_repo_data() is
called once (Step 1), and run_analysis() only does local computation from then on.
"""

import os
import shutil
from dataclasses import dataclass
from typing import List

import file_formats as ff
import github_client as gc
from diffs_parser import parse_diffs_md
from merge_engine import merge_step, MergeLog
from version_utils import version_chain, parse_version


@dataclass
class AnalysisResult:
    chain: List[str]
    log: MergeLog
    modlist_entries: list
    plugins_entries: list
    loadorder_entries: list
    has_plugins: bool


def run_analysis(repo_data: gc.RepoData, profile, current_version, target_version, custom_profile_dir,
                  progress_cb=None, diag=None):
    def report(frac, msg):
        if progress_cb:
            progress_cb(frac, msg)

    def d(msg):
        if diag:
            diag.info(msg)

    d(f"Analyze started -- profile '{profile}', {current_version} -> {target_version}")
    d(f"Custom profile folder: {custom_profile_dir}")

    versions_map = repo_data.profiles.get(profile, {})
    all_versions = list(versions_map.keys())
    chain = version_chain(all_versions, current_version, target_version)
    d(f"Version chain ({len(chain)} version(s)): {' -> '.join(chain)}")

    log = MergeLog()

    diffs_path = repo_data.diffs_paths.get(profile)
    if diffs_path:
        d(f"Diffs file found: {diffs_path}")
        with open(diffs_path, "rb") as f:
            diffs_text = f.read().decode("utf-8-sig")
        diff_steps = parse_diffs_md(diffs_text)
        d(f"Diffs file covers {len(diff_steps)} version-step(s) with rename data")
    else:
        diff_steps = {}
        d(f"No diffs-{profile.lower()}.md found for this profile -- rename detection will be "
          f"skipped for every step in this run (renames will show as a plain Add + Remove)")
        if len(chain) > 1:
            log.rename_warning = (
                f"No diffs-{profile.lower()}.md found -- rename detection was skipped.\n\n"
                "This means renamed mods will appear as a Added Mod.\n"
                "Not as a rename."
            )

    custom_modlist_path = os.path.join(custom_profile_dir, "modlist.txt")
    if not os.path.isfile(custom_modlist_path):
        d(f"ERROR: no modlist.txt found at {custom_modlist_path}")
        raise FileNotFoundError(
            f"No modlist.txt found in {custom_profile_dir} -- is this a valid MO2 profile folder?"
        )
    custom_modlist = ff.parse_modlist(custom_modlist_path)
    d(f"Parsed custom modlist.txt: {sum(1 for e in custom_modlist if not e.is_comment)} entries")

    custom_plugins_path = os.path.join(custom_profile_dir, "plugins.txt")
    has_plugins = all(versions_map[v].get("plugins") for v in chain) and os.path.isfile(custom_plugins_path)
    custom_plugins = ff.parse_plugins(custom_plugins_path) if os.path.isfile(custom_plugins_path) else []
    if has_plugins:
        d(f"Parsed custom plugins.txt: {sum(1 for e in custom_plugins if not e.is_comment)} entries")
    else:
        reason = ("custom profile has no plugins.txt" if not os.path.isfile(custom_plugins_path)
                   else "one or more versions in the chain has no official plugins.txt")
        d(f"Skipping plugins.txt entirely for this run ({reason})")

    total_steps = max(len(chain) - 1, 1)

    # One shared set per file, threaded across every step of this run -- lets a mod
    # MOPU itself just added keep following the official file's position for it
    # through the rest of the chain if the modlist author moves it again in a later
    # step (see merge_engine.merge_step's docstring). Scoped to this single
    # run_analysis() call only, so anything the user already had before this run --
    # including their own manual reordering of a mod MOPU added on a *previous*
    # update -- is never touched by it.
    tracked_modlist_names = set()
    tracked_plugins_names = set()

    def _counts(log):
        return (len(log.added), len(log.removed), len(log.renamed),
                len(log.repositioned), len(log.enabled), len(log.disabled), len(log.auto_updates))

    def _log_step(file_label, before, after):
        # Each of these slices out exactly the entries this single merge_step() call
        # just appended (added[before:after], etc.) -- since merge_step only ever
        # appends to the shared log for the one file_label it was called with, the
        # slice is guaranteed to belong to this file, even though log.added itself
        # holds both modlist.txt and plugins.txt entries mixed together across the
        # whole run. Named per-mod rather than just a count, so the troubleshooting
        # log actually says *which* mods/plugins were touched, not just how many.
        parts = []

        added = [name for name, _ in log.added[before[0]:after[0]]]
        if added:
            parts.append(f"Added ({len(added)}): {', '.join(added)}")

        removed = [name for name, _ in log.removed[before[1]:after[1]]]
        if removed:
            parts.append(f"Removed ({len(removed)}): {', '.join(removed)}")

        renamed = [f"{old} -> {new}" for old, new, _ in log.renamed[before[2]:after[2]]]
        if renamed:
            parts.append(f"Renamed ({len(renamed)}): {', '.join(renamed)}")

        repositioned = [name for name, _ in log.repositioned[before[3]:after[3]]]
        if repositioned:
            parts.append(f"Repositioned ({len(repositioned)}): {', '.join(repositioned)}")

        enabled = [name for name, _ in log.enabled[before[4]:after[4]]]
        if enabled:
            parts.append(f"Enabled ({len(enabled)}): {', '.join(enabled)}")

        disabled = [name for name, _ in log.disabled[before[5]:after[5]]]
        if disabled:
            parts.append(f"Disabled ({len(disabled)}): {', '.join(disabled)}")

        auto_updates = [f"{a.name} ({a.old_state} -> {a.new_state})"
                         for a in log.auto_updates[before[6]:after[6]]]
        if auto_updates:
            parts.append(f"Auto Updates ({len(auto_updates)}): {', '.join(auto_updates)}")

        if not parts:
            d(f"  {file_label}: no changes")
            return
        d(f"  {file_label}:")
        for p in parts:
            d(f"    {p}")

    for i in range(len(chain) - 1):
        old_v, new_v = chain[i], chain[i + 1]
        report(i / total_steps, f"Merging {old_v} -> {new_v}...")
        d(f"Step {old_v} -> {new_v}:")

        # diffs.md is always authored forward (chronologically older -> newer). When the
        # chain is walking backward (a downgrade), look the step up under its actual
        # forward key and invert the rename mapping so it still applies correctly in
        # reverse (name-in-old_v -> name-in-new_v, whichever direction that is).
        if parse_version(old_v) <= parse_version(new_v):
            step = diff_steps.get((old_v, new_v))
            renamed = step.renamed if step else {}
        else:
            step = diff_steps.get((new_v, old_v))
            renamed = {v: k for k, v in step.renamed.items()} if step else {}

        base_old_ml = ff.parse_modlist(versions_map[old_v]["modlist"])
        base_new_ml = ff.parse_modlist(versions_map[new_v]["modlist"])
        before = _counts(log)
        custom_modlist = merge_step(base_old_ml, base_new_ml, custom_modlist, renamed, "modlist.txt", log,
                                     tracked_names=tracked_modlist_names)
        _log_step("modlist.txt", before, _counts(log))

        if has_plugins:
            base_old_pl = ff.parse_plugins(versions_map[old_v]["plugins"])
            base_new_pl = ff.parse_plugins(versions_map[new_v]["plugins"])
            before = _counts(log)
            custom_plugins = merge_step(base_old_pl, base_new_pl, custom_plugins, renamed, "plugins.txt", log,
                                         tracked_names=tracked_plugins_names)
            _log_step("plugins.txt", before, _counts(log))

    loadorder_entries = []
    if has_plugins:
        custom_loadorder_path = os.path.join(custom_profile_dir, "loadorder.txt")
        if os.path.isfile(custom_loadorder_path):
            old_plugins_names = {e.name for e in ff.parse_plugins(custom_plugins_path) if not e.is_comment}
            orig_loadorder = ff.parse_loadorder(custom_loadorder_path)
            # master/CC-content lines: present in loadorder.txt but never in plugins.txt at all.
            # These are never touched by ZISS updates, so we keep them exactly as they were,
            # in their existing relative order, ahead of the regular plugin list.
            master_lines = [e for e in orig_loadorder if e.is_comment or e.name not in old_plugins_names]
            plugin_lines = [ff.Entry(name=e.name, state=None)
                             for e in custom_plugins if not e.is_comment]
            loadorder_entries = master_lines + plugin_lines
            d(f"Derived loadorder.txt: {len(master_lines)} master/CC line(s) kept as-is, "
              f"{len(plugin_lines)} plugin line(s) following the new plugins.txt order")
        else:
            d(f"No loadorder.txt found at {custom_loadorder_path} -- none will be written")

    # ---- "Your Mods" -- anything in the final profile that was never part of any
    # official version of this profile, at any version the repo has (not just the
    # versions actually walked this run, so a coincidental name match to some
    # long-past or not-yet-reached version doesn't get misflagged). By definition,
    # this is everything the user added themselves rather than the modlist author --
    # the exact set worth backing up before an installer update, since only the
    # user's own installer knows about it, and MOPU itself never touches mod files.
    ever_official_modlist_names = set()
    ever_official_plugins_names = set()
    for v in all_versions:
        files = versions_map[v]
        if files.get("modlist"):
            ever_official_modlist_names.update(
                e.name for e in ff.parse_modlist(files["modlist"]) if not e.is_comment
            )
        if files.get("plugins"):
            ever_official_plugins_names.update(
                e.name for e in ff.parse_plugins(files["plugins"]) if not e.is_comment
            )

    log.your_mods = [
        (e.name, "modlist.txt") for e in custom_modlist
        if not e.is_comment and e.name not in ever_official_modlist_names
    ]
    if has_plugins:
        log.your_mods.extend(
            (e.name, "plugins.txt") for e in custom_plugins
            if not e.is_comment and e.name not in ever_official_plugins_names
        )
    d(f"\"Your Mods\" (never in any official version): {len(log.your_mods)}")

    d("Analyze finished successfully.")
    report(1.0, "Done.")
    return AnalysisResult(
        chain=chain,
        log=log,
        modlist_entries=custom_modlist,
        plugins_entries=custom_plugins,
        loadorder_entries=loadorder_entries,
        has_plugins=has_plugins,
    )


def predict_output_files(custom_profile_dir):
    """Every path (relative to output_dir) that write_output() below will actually
    write, computed in advance from custom_profile_dir alone -- mirrors its logic
    exactly, so a caller can check in advance which of these already exist in the
    output folder rather than warning about the folder's entire contents (most of
    which may have nothing to do with this run)."""
    skip = {"modlist.txt", "plugins.txt", "loadorder.txt"}
    paths = {"modlist.txt"}
    if os.path.isfile(os.path.join(custom_profile_dir, "plugins.txt")):
        paths.add("plugins.txt")
        paths.add("loadorder.txt")

    for entry in os.listdir(custom_profile_dir):
        if entry in skip:
            continue
        if os.path.isfile(os.path.join(custom_profile_dir, entry)):
            paths.add(entry)

    saves_src = os.path.join(custom_profile_dir, "saves")
    if os.path.isdir(saves_src):
        for dirpath, _dirnames, filenames in os.walk(saves_src):
            rel_dir = os.path.relpath(dirpath, custom_profile_dir)
            for fn in filenames:
                paths.add(os.path.normpath(os.path.join(rel_dir, fn)))

    return paths


def write_output(custom_profile_dir, output_dir, result: AnalysisResult, diag=None):
    def d(msg):
        if diag:
            diag.info(msg)

    d(f"Writing output to: {output_dir}")
    os.makedirs(output_dir, exist_ok=True)
    # copy every other file from the custom profile untouched (ini files, etc.) --
    # overwriting anything already present in the output folder. Only covers files
    # directly in the profile folder -- subfolders are handled separately below.
    skip = {"modlist.txt", "plugins.txt", "loadorder.txt"}
    copied_files = []
    for entry in os.listdir(custom_profile_dir):
        if entry in skip:
            continue
        src = os.path.join(custom_profile_dir, entry)
        dst = os.path.join(output_dir, entry)
        if os.path.isfile(src):
            with open(src, "rb") as f_in, open(dst, "wb") as f_out:
                f_out.write(f_in.read())
            copied_files.append(entry)
    d(f"Copied {len(copied_files)} other file(s) from the profile folder as-is: "
      + (", ".join(copied_files) if copied_files else "(none)"))

    # "saves" is the one subfolder MO2 can keep directly inside a profile (when
    # "use profile-specific saves" is on) -- copied over in full, recursively,
    # since it's the one thing in here a user would actually be upset to lose.
    saves_src = os.path.join(custom_profile_dir, "saves")
    if os.path.isdir(saves_src):
        saves_dst = os.path.join(output_dir, "saves")
        shutil.copytree(saves_src, saves_dst, dirs_exist_ok=True)
        save_count = sum(len(files) for _, _, files in os.walk(saves_dst))
        d(f"Copied saves folder: {save_count} file(s) (recursively, including subfolders)")
    else:
        d("No saves folder found in the profile -- nothing to copy for it")

    ff.write_modlist(os.path.join(output_dir, "modlist.txt"), result.modlist_entries)
    d(f"Wrote modlist.txt: {sum(1 for e in result.modlist_entries if not e.is_comment)} entries")
    if result.has_plugins:
        ff.write_plugins(os.path.join(output_dir, "plugins.txt"), result.plugins_entries)
        ff.write_loadorder(os.path.join(output_dir, "loadorder.txt"), result.loadorder_entries)
        d(f"Wrote plugins.txt: {sum(1 for e in result.plugins_entries if not e.is_comment)} entries")
        d(f"Wrote loadorder.txt: {sum(1 for e in result.loadorder_entries if not e.is_comment)} entries")
    else:
        d("Skipped plugins.txt/loadorder.txt (has_plugins was False for this run)")
    d("Output write finished successfully.")
