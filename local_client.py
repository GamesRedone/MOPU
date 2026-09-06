"""
Supports the "Prepare Your Files For Upload to GitHub" feature: scaffolds a
loadorder/<Profile>/ folder structure -- matching the layout this tool's GitHub-repo
flow expects -- from an existing local MO2 modlist install.
"""

import os
import shutil
import tempfile


class LocalError(Exception):
    pass


def _find_dir_case_insensitive(root: str, name: str):
    try:
        entries = os.listdir(root)
    except OSError:
        return None
    for entry in entries:
        full = os.path.join(root, entry)
        if os.path.isdir(full) and entry.lower() == name.lower():
            return full
    return None


def find_profiles_dir(modlist_folder: str) -> str:
    """Locates the MO2 "profiles" folder, handling both ways a user might point this
    at an install:

    - Portable instance: modlist_folder is the modlist's root folder (e.g. "C:\\ZISS\\"),
      which *contains* a "profiles" subfolder.
    - Regular/Global instance: modlist_folder is *already* the profiles folder itself
      (e.g. "C:\\Users\\<You>\\AppData\\Local\\ModOrganizer\\<Instance>\\profiles"),
      since that's the natural path to give for this kind of install -- there's no
      single "root" folder a step above it that means anything on its own.
    """
    modlist_folder = os.path.normpath(modlist_folder)
    if not os.path.isdir(modlist_folder):
        raise LocalError(f"Modlist folder not found: {modlist_folder}")

    if os.path.basename(modlist_folder).lower() == "profiles":
        return modlist_folder

    profiles_dir = _find_dir_case_insensitive(modlist_folder, "profiles")
    if profiles_dir is None:
        raise LocalError(
            "No 'profiles' folder found. For a portable instance, point this at the "
            "modlist's root folder (e.g. C:\\ZISS\\). For a Regular/Global instance, "
            "point this directly at the profiles folder itself (e.g. "
            "C:\\Users\\<You>\\AppData\\Local\\ModOrganizer\\<Instance>\\profiles)."
        )
    return profiles_dir


def _output_root(modlist_folder: str, profiles_dir: str) -> str:
    """Where the "MO2 Profile Updater" output folder should be created -- next to
    "profiles", not inside it, regardless of which instance type was pointed at."""
    modlist_folder = os.path.normpath(modlist_folder)
    profiles_dir = os.path.normpath(profiles_dir)
    if modlist_folder == profiles_dir:
        # Regular/Global instance -- modlist_folder WAS the profiles folder, so put
        # the output folder one level up, alongside "profiles", not inside it.
        return os.path.dirname(profiles_dir)
    return modlist_folder


def list_available_profiles(modlist_folder: str):
    """Every subfolder of the profiles directory that has both modlist.txt and
    plugins.txt -- both are required, since plugin load order matters just as much
    as mod install order and an incomplete profile isn't safe to publish."""
    profiles_dir = find_profiles_dir(modlist_folder)
    names = []
    for entry in sorted(os.listdir(profiles_dir)):
        full = os.path.join(profiles_dir, entry)
        if not os.path.isdir(full):
            continue
        if os.path.isfile(os.path.join(full, "modlist.txt")) and \
                os.path.isfile(os.path.join(full, "plugins.txt")):
            names.append(entry)
    return names


def _normalize_version(version: str) -> str:
    version = version.strip()
    if version[:1] in ("v", "V"):
        version = version[1:]
    return f"v{version}"


def output_folder_for(modlist_folder: str, modlist_name: str):
    """Returns (mo2_updater_dir, output_folder) without writing anything -- used to
    check in advance whether files would be overwritten."""
    profiles_dir = find_profiles_dir(modlist_folder)
    root = _output_root(modlist_folder, profiles_dir)
    mo2_updater_dir = os.path.normpath(os.path.join(root, "MO2 Profile Updater"))
    output_folder = os.path.normpath(os.path.join(mo2_updater_dir, modlist_name))
    return mo2_updater_dir, output_folder


def existing_output_files(modlist_folder: str, modlist_name: str):
    """Lists files that already exist at the target output location and would be
    overwritten by running create_github_folder_structure again."""
    _, output_folder = output_folder_for(modlist_folder, modlist_name)
    found = []
    if os.path.isdir(output_folder):
        for dirpath, _dirnames, filenames in os.walk(output_folder):
            for fn in filenames:
                found.append(os.path.join(dirpath, fn))
    return found


def _build_structure_tree(modlist_name: str, profile_names, version_tag: str) -> str:
    """Renders the actual generated folder structure as a box-drawing tree, e.g.:

    ZISS/
    |__ loadorder/
        |-- CS/
        |   |-- v1.2.5-modlist.txt
        |   |__ v1.2.5-plugins.txt
        |__ ENB/
            |-- v1.2.5-modlist.txt
            |__ v1.2.5-plugins.txt
    """
    lines = [f"{modlist_name}/", "\u2514\u2500\u2500 loadorder/"]
    for i, profile in enumerate(profile_names):
        is_last = i == len(profile_names) - 1
        branch = "\u2514\u2500\u2500 " if is_last else "\u251c\u2500\u2500 "
        child_indent = "    " if is_last else "\u2502   "
        lines.append(f"    {branch}{profile}/")
        lines.append(f"    {child_indent}\u251c\u2500\u2500 {version_tag}-modlist.txt")
        lines.append(f"    {child_indent}\u2514\u2500\u2500 {version_tag}-plugins.txt")
    return "\n".join(lines)


def create_github_folder_structure(modlist_folder: str, modlist_name: str, modlist_version: str):
    """Scaffolds a loadorder/<Profile>/ folder structure -- matching the layout this
    tool's GitHub-repo flow expects -- from an existing local modlist install.

    The output goes to a deterministic location: "MO2 Profile Updater" next to the
    profiles folder (not inside it, and correctly placed regardless of whether a
    portable or Regular/Global instance path was given), with modlist_name as a
    subfolder of that -- e.g. pointing this at "C:\\ZISS\\" with modlist name "ZISS"
    writes to "C:\\ZISS\\MO2 Profile Updater\\ZISS\\".

    For each profile, the *entire* profile folder is copied over first, then
    everything except modlist.txt/plugins.txt is deleted from the copy (since a
    GitHub repo only needs those two files per version), and the two survivors are
    renamed to the vX.Y.Z- convention using modlist_version (a leading "v"/"V" in
    what's typed is normalized, so "1.2.0" and "v1.2.0" both produce "v1.2.0-...").
    Only profiles with both modlist.txt and plugins.txt are included.

    A "modlist-info.txt" file is also written inside the loadorder folder, showing
    the modlist name and the actual structure that was just generated.

    Returns (mo2_updater_dir, sorted_profile_names) -- mo2_updater_dir is the parent
    "MO2 Profile Updater" folder (not the modlist_name subfolder), since that's what
    gets opened in the file explorer when done.
    """
    profiles_dir = find_profiles_dir(modlist_folder)
    profile_names = list_available_profiles(modlist_folder)
    if not profile_names:
        raise LocalError(
            "No profiles with both modlist.txt and plugins.txt were found in the "
            "profiles folder."
        )

    version_tag = _normalize_version(modlist_version)
    mo2_updater_dir, output_folder = output_folder_for(modlist_folder, modlist_name)

    # Everything risky (delete, copy, prune, rename -- happening many times in a row)
    # is done in a disposable temp folder first, never in the real output location.
    # That location may already exist from a previous run and could be open in File
    # Explorer, watched by antivirus, etc. -- repeatedly deleting/recreating things
    # right under a live viewer like that is a known way to make Explorer unstable.
    # The real output folder is only touched once, right at the end, and only after
    # everything has already succeeded -- so a failure partway through never leaves
    # a broken/partial result there either.
    staging_dir = tempfile.mkdtemp(prefix="mopu_stage_")
    try:
        staged_load_order_dir = os.path.join(staging_dir, "loadorder")
        os.makedirs(staged_load_order_dir, exist_ok=True)

        for profile_name in profile_names:
            source_profile_dir = os.path.join(profiles_dir, profile_name)
            profile_out_dir = os.path.join(staged_load_order_dir, profile_name)
            shutil.copytree(source_profile_dir, profile_out_dir)

            # prune down to just modlist.txt / plugins.txt -- everything else in a
            # profile folder (ini files, archives.txt, lockedorder.txt, etc.) isn't
            # needed for a GitHub repo
            for entry in os.listdir(profile_out_dir):
                if entry.lower() not in ("modlist.txt", "plugins.txt"):
                    full = os.path.join(profile_out_dir, entry)
                    if os.path.isdir(full):
                        shutil.rmtree(full)
                    else:
                        os.remove(full)

            os.rename(os.path.join(profile_out_dir, "modlist.txt"),
                      os.path.join(profile_out_dir, f"{version_tag}-modlist.txt"))
            os.rename(os.path.join(profile_out_dir, "plugins.txt"),
                      os.path.join(profile_out_dir, f"{version_tag}-plugins.txt"))

        tree_text = _build_structure_tree(modlist_name, profile_names, version_tag)
        with open(os.path.join(staged_load_order_dir, "modlist-info.txt"), "w", encoding="utf-8") as f:
            f.write(f"{modlist_name}\n\n{tree_text}\n")

        # Everything above succeeded -- now, and only now, touch the real location.
        os.makedirs(output_folder, exist_ok=True)
        final_load_order_dir = os.path.join(output_folder, "loadorder")
        if os.path.isdir(final_load_order_dir):
            shutil.rmtree(final_load_order_dir)
        shutil.move(staged_load_order_dir, final_load_order_dir)
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)

    return mo2_updater_dir, sorted(profile_names)
