"""
Core merge logic. For one version step (old -> new), given:
  - base_old:  the vanilla entries at the old version
  - base_new:  the vanilla entries at the new version
  - custom:    the user's current custom-profile entries (mutated in place and returned,
               so it can be threaded through multiple version steps)
  - renamed:   dict of old_name -> new_name for this step (from diffs.md)

...applies Renamed / Removed / Added / Enabled-Disabled changes onto `custom`, matching
purely by name so any mod the user added themselves (never present in any base version)
is left completely untouched.

Enabled/Disabled changes are never applied immediately during the merge itself -- they're
returned as AutoUpdateItem objects for the caller (the GUI) to review, defaulting to
"apply the new base default" so ignoring the Review screen produces the same result as
if they'd been applied automatically.
"""

import difflib
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from file_formats import Entry


@dataclass
class AutoUpdateItem:
    """A mod whose default enabled/disabled state changed upstream, where the user's
    profile matched the OLD default (i.e. never manually overridden). Reviewable on
    the Review screen rather than always auto-applied, since silently disabling a mod
    something else depends on is exactly the kind of thing a user should get a say in.

    (There's no separate "conflict" case: since state is a plain boolean and the old
    and new defaults are guaranteed to differ whenever this fires, the user's current
    state can only ever match one or the other -- there's no third value it could be
    to actually disagree with both. So the only two reachable outcomes are "matches
    the old default" (this class) or "already matches the new default" (nothing to
    do, silently skipped).)"""
    name: str
    file: str
    old_state: bool
    new_state: bool
    resolution: str = "apply_new_default"  # or "keep_as_is" -- GUI sets this


@dataclass
class MergeLog:
    added: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    renamed: List[str] = field(default_factory=list)
    enabled: List[str] = field(default_factory=list)   # old False -> new True (all)
    disabled: List[str] = field(default_factory=list)  # old True -> new False (all)
    auto_updates: List[AutoUpdateItem] = field(default_factory=list)
    rename_warning: Optional[str] = None  # set when diffs.md was missing -- renames weren't detected


def _named_entries(entries: List[Entry]):
    """Return (index_in_list, entry) for entries that carry a real name (skip comments)."""
    return [(i, e) for i, e in enumerate(entries) if not e.is_comment]


def merge_step(
    base_old: List[Entry],
    base_new: List[Entry],
    custom: List[Entry],
    renamed: Dict[str, str],
    file_label: str,
    log: MergeLog,
) -> List[Entry]:
    # ---- Step 1: apply renames directly onto custom, matched by old name ----
    for old_name, new_name in renamed.items():
        for e in custom:
            if not e.is_comment and e.name == old_name:
                e.name = new_name
                log.renamed.append(f"{old_name} -> {new_name} ({file_label})")

    # ---- Build normalized old-base name sequence (renames applied) for alignment ----
    old_named = _named_entries(base_old)
    new_named = _named_entries(base_new)

    old_names_norm = [renamed.get(e.name, e.name) for _, e in old_named]
    new_names = [e.name for _, e in new_named]

    old_state_by_name = {}
    for (_, e), norm_name in zip(old_named, old_names_norm):
        old_state_by_name[norm_name] = e.state

    new_state_by_name = {e.name: e.state for _, e in new_named}

    sm = difflib.SequenceMatcher(None, old_names_norm, new_names, autojunk=False)
    opcodes = sm.get_opcodes()

    # ---- Step 2: removals (present in old, absent in new) ----
    removed_names = set()
    for tag, i1, i2, j1, j2 in opcodes:
        if tag in ("delete", "replace"):
            for name in old_names_norm[i1:i2]:
                removed_names.add(name)
    for name in removed_names:
        before = len(custom)
        custom[:] = [e for e in custom if e.is_comment or e.name != name]
        if len(custom) < before:
            log.removed.append(f"{name} ({file_label})")

    # ---- Step 3: enabled/disabled defaults changing on mods present in both ----
    common_names = set(old_names_norm) & set(new_names) - removed_names
    for name in common_names:
        old_state = old_state_by_name.get(name)
        new_state = new_state_by_name.get(name)
        if old_state is None or new_state is None or old_state == new_state:
            continue

        if new_state is True:
            log.enabled.append(f"{name} ({file_label})")
        else:
            log.disabled.append(f"{name} ({file_label})")

        match = next((e for e in custom if not e.is_comment and e.name == name), None)
        if match is None:
            continue
        if match.state == old_state:
            # user never overrode it -- not applied immediately, recorded as a
            # reviewable AutoUpdateItem instead, defaulting to "apply", so ignoring
            # it on the Review screen produces the same result as if it had just
            # been applied automatically -- but a user who needs to keep it as-is
            # (e.g. something else depends on it) can opt out with one checkbox.
            log.auto_updates.append(
                AutoUpdateItem(name=name, file=file_label, old_state=old_state, new_state=new_state)
            )
        # else: match.state already equals new_state (the only other value a boolean
        # can hold), meaning the profile is already exactly what upstream now wants --
        # nothing to do, nothing to log.

    # ---- Step 4: additions (present in new, absent in old) -- insert at matching position ----
    custom_index_by_name = {
        e.name: i for i, e in enumerate(custom) if not e.is_comment
    }

    for tag, i1, i2, j1, j2 in opcodes:
        if tag not in ("insert", "replace"):
            continue
        new_slice = new_named[j1:j2]
        if not new_slice:
            continue

        # anchor: the custom-list position right after the base name that precedes
        # this insertion point (i1-1 in the old/renamed sequence), if it still exists
        # in custom; otherwise fall back to end of list.
        insert_at = len(custom)
        if i1 > 0:
            anchor_name = old_names_norm[i1 - 1]
            if anchor_name in custom_index_by_name:
                insert_at = custom_index_by_name[anchor_name] + 1

        new_entries = []
        for _, e in new_slice:
            if e.name in custom_index_by_name:
                continue  # already present (e.g. user added it manually already)
            new_entries.append(Entry(name=e.name, state=e.state))
            log.added.append(f"{e.name} ({file_label})")

        if new_entries:
            custom[insert_at:insert_at] = new_entries
            # shift indices for anything after the insertion point
            custom_index_by_name = {
                e.name: i for i, e in enumerate(custom) if not e.is_comment
            }

    return custom


def apply_auto_update_resolutions(custom: List[Entry], auto_updates: List["AutoUpdateItem"]):
    for a in auto_updates:
        if a.resolution != "apply_new_default":
            continue
        for e in custom:
            if not e.is_comment and e.name == a.name:
                e.state = a.new_state
                break
