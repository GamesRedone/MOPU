"""
Orchestrates the merge across every version step, for both modlist.txt and plugins.txt,
and derives loadorder.txt afterward. Split into two phases so re-running "Analyze" with
different current/target versions never re-hits the network -- fetch_repo_data() is
called once (Step 1), and run_analysis() only does local computation from then on.
"""

import os
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
                  progress_cb=None):
    def report(frac, msg):
        if progress_cb:
            progress_cb(frac, msg)

    versions_map = repo_data.profiles.get(profile, {})
    all_versions = list(versions_map.keys())
    chain = version_chain(all_versions, current_version, target_version)

    log = MergeLog()

    if repo_data.diffs_path:
        with open(repo_data.diffs_path, "rb") as f:
            diffs_text = f.read().decode("utf-8-sig")
        diff_steps = parse_diffs_md(diffs_text)
    else:
        diff_steps = {}
        if len(chain) > 1:
            log.rename_warning = (
                "No diffs.md found -- rename detection was skipped.\n\n"
                "This means renamed mods will appear as a Added Mod.\n"
                "Not as a rename."
            )

    custom_modlist_path = os.path.join(custom_profile_dir, "modlist.txt")
    if not os.path.isfile(custom_modlist_path):
        raise FileNotFoundError(
            f"No modlist.txt found in {custom_profile_dir} -- is this a valid MO2 profile folder?"
        )
    custom_modlist = ff.parse_modlist(custom_modlist_path)

    custom_plugins_path = os.path.join(custom_profile_dir, "plugins.txt")
    has_plugins = all(versions_map[v].get("plugins") for v in chain) and os.path.isfile(custom_plugins_path)
    custom_plugins = ff.parse_plugins(custom_plugins_path) if os.path.isfile(custom_plugins_path) else []

    total_steps = max(len(chain) - 1, 1)

    for i in range(len(chain) - 1):
        old_v, new_v = chain[i], chain[i + 1]
        report(i / total_steps, f"Merging {old_v} -> {new_v}...")

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
        custom_modlist = merge_step(base_old_ml, base_new_ml, custom_modlist, renamed, "modlist.txt", log)

        if has_plugins:
            base_old_pl = ff.parse_plugins(versions_map[old_v]["plugins"])
            base_new_pl = ff.parse_plugins(versions_map[new_v]["plugins"])
            custom_plugins = merge_step(base_old_pl, base_new_pl, custom_plugins, renamed, "plugins.txt", log)

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

    report(1.0, "Done.")
    return AnalysisResult(
        chain=chain,
        log=log,
        modlist_entries=custom_modlist,
        plugins_entries=custom_plugins,
        loadorder_entries=loadorder_entries,
        has_plugins=has_plugins,
    )


def write_output(custom_profile_dir, output_dir, result: AnalysisResult):
    os.makedirs(output_dir, exist_ok=True)
    # copy every other file from the custom profile untouched (ini files, etc.) --
    # overwriting anything already present in the output folder.
    skip = {"modlist.txt", "plugins.txt", "loadorder.txt"}
    for entry in os.listdir(custom_profile_dir):
        if entry in skip:
            continue
        src = os.path.join(custom_profile_dir, entry)
        dst = os.path.join(output_dir, entry)
        if os.path.isfile(src):
            with open(src, "rb") as f_in, open(dst, "wb") as f_out:
                f_out.write(f_in.read())

    ff.write_modlist(os.path.join(output_dir, "modlist.txt"), result.modlist_entries)
    if result.has_plugins:
        ff.write_plugins(os.path.join(output_dir, "plugins.txt"), result.plugins_entries)
        ff.write_loadorder(os.path.join(output_dir, "loadorder.txt"), result.loadorder_entries)
