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

`tracked_names` (optional, threaded across every step of a single Analyze run by the
caller -- one shared set per file, e.g. one for modlist.txt and one for plugins.txt)
lets a mod MOPU itself just added keep following the official file's own position for
it through the *rest of this same run*, if the modlist author moves it again in a later
version step before the chain ends (e.g. tacked onto the end of the list when it was
first introduced, then tidied into its proper spot a version or two later). A mod is
only ever added to this set by Step 4 below -- i.e. only mods MOPU placed on the user's
behalf during this run -- so anything the user already had in their profile before this
run started, including anything they added themselves, is never repositioned by this and
keeps whatever position the user already gave it. See `_reposition_tracked` for how.
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
    added: List[tuple] = field(default_factory=list)    # (name, file_label)
    removed: List[tuple] = field(default_factory=list)  # (name, file_label)
    renamed: List[tuple] = field(default_factory=list)  # (old_name, new_name, file_label)
    enabled: List[tuple] = field(default_factory=list)   # (name, file_label) -- old False -> new True (all)
    disabled: List[tuple] = field(default_factory=list)  # (name, file_label) -- old True -> new False (all)
    auto_updates: List[AutoUpdateItem] = field(default_factory=list)
    repositioned: List[tuple] = field(default_factory=list)  # (name, file_label) -- see _reposition_tracked
    your_mods: List[tuple] = field(default_factory=list)  # (name, file_label) -- never in any official version
    rename_warning: Optional[str] = None  # set when diffs.md was missing -- renames weren't detected


def _named_entries(entries: List[Entry]):
    """Return (index_in_list, entry) for entries that carry a real name (skip comments)."""
    return [(i, e) for i, e in enumerate(entries) if not e.is_comment]


def _find_anchor(new_names, start, end, custom_index_by_name):
    """Where a block of new-version names spanning new_names[start:end] belongs in
    `custom`, found by walking the actual target order rather than trusting wherever
    a SequenceMatcher opcode happened to cut the old sequence -- which can land
    anywhere (even at the very end) once enough of the list has been rearranged
    elsewhere in the same version step. Walks backward from just before the block for
    the nearest name already placed in `custom`, anchoring right after it; if nothing
    before it has landed yet, walks forward instead and anchors right before the
    nearest following name that's already placed. Returns None if neither exists (an
    empty `custom`, or every other name in the file is also new)."""
    for k in range(start - 1, -1, -1):
        name = new_names[k]
        if name in custom_index_by_name:
            return custom_index_by_name[name] + 1
    for k in range(end, len(new_names)):
        name = new_names[k]
        if name in custom_index_by_name:
            return custom_index_by_name[name]
    return None


def _reposition_tracked(custom, new_names, new_name_to_j, tracked_names, common_names, file_label, log):
    """Move every tracked, still-common name to follow the target (new) version's own
    position for it, one at a time in target order, so a mod MOPU placed earlier in
    this same run keeps tracking the official file even if the modlist author moves
    it again in a later step before the chain ends -- e.g. tacked onto the end of the
    list when first added, then tidied into its real spot a version or two later.
    Names never in `tracked_names` (anything the user already had before this run,
    including anything they added themselves) are never touched here.

    Only actually-moved entries are logged to `log.repositioned` -- a tracked name
    that's already sitting where it belongs this step (or has no other placed
    neighbor to anchor to yet) is left alone and stays silent."""
    to_move = sorted(
        (name for name in tracked_names if name in common_names),
        key=lambda name: new_name_to_j[name],
    )
    if not to_move:
        return

    custom_index_by_name = {e.name: i for i, e in enumerate(custom) if not e.is_comment}
    for name in to_move:
        cur_idx = custom_index_by_name.get(name)
        if cur_idx is None:
            continue  # shouldn't happen (it's in common_names, so it's in custom) -- be safe anyway
        entry = custom.pop(cur_idx)
        custom_index_by_name = {e.name: i for i, e in enumerate(custom) if not e.is_comment}

        j = new_name_to_j[name]
        insert_at = _find_anchor(new_names, j, j + 1, custom_index_by_name)
        if insert_at is None:
            # no other common/tracked name has landed anywhere yet to anchor to --
            # leave it exactly where it already was rather than guessing.
            insert_at = cur_idx
        elif insert_at != cur_idx:
            log.repositioned.append((name, file_label))

        custom.insert(insert_at, entry)
        custom_index_by_name = {e.name: i for i, e in enumerate(custom) if not e.is_comment}


def merge_step(
    base_old: List[Entry],
    base_new: List[Entry],
    custom: List[Entry],
    renamed: Dict[str, str],
    file_label: str,
    log: MergeLog,
    tracked_names: Optional[set] = None,
) -> List[Entry]:
    if tracked_names is None:
        tracked_names = set()

    # ---- Step 1: apply renames directly onto custom, matched by old name ----
    for old_name, new_name in renamed.items():
        for e in custom:
            if not e.is_comment and e.name == old_name:
                e.name = new_name
                log.renamed.append((old_name, new_name, file_label))
        if old_name in tracked_names:
            tracked_names.discard(old_name)
            tracked_names.add(new_name)

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
    # SequenceMatcher aligns by position, so a name the modlist author simply moved --
    # reordered elsewhere in the file with no rename and no state change -- can fall
    # outside any matching block and show up inside a "delete"/"replace" opcode even
    # though it's still there in the new version. Filtering by actual name membership
    # in new_names (a true set check, not a positional one) keeps that from being
    # logged as a Removed (and, since it's never removed from `custom`, Step 4 below
    # never re-logs it as Added either -- it was never touched).
    new_names_set = set(new_names)
    removed_names = set()
    for tag, i1, i2, j1, j2 in opcodes:
        if tag in ("delete", "replace"):
            for name in old_names_norm[i1:i2]:
                if name not in new_names_set:
                    removed_names.add(name)
    for name in removed_names:
        before = len(custom)
        custom[:] = [e for e in custom if e.is_comment or e.name != name]
        if len(custom) < before:
            log.removed.append((name, file_label))
        tracked_names.discard(name)

    # ---- Step 3: enabled/disabled defaults changing on mods present in both ----
    common_names = set(old_names_norm) & set(new_names) - removed_names
    for name in common_names:
        old_state = old_state_by_name.get(name)
        new_state = new_state_by_name.get(name)
        if old_state is None or new_state is None or old_state == new_state:
            continue

        if new_state is True:
            log.enabled.append((name, file_label))
        else:
            log.disabled.append((name, file_label))

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

    # ---- Step 3.5: catch up any already-tracked mod to the target's current position ----
    # Must run before Step 4 below, using this step's own `common_names` -- a name
    # that's brand new *in this step* isn't in common_names yet (it's handled by Step 4
    # instead, and only becomes eligible for this in a later step once it exists in
    # both old and new).
    new_name_to_j = {name: j for j, name in enumerate(new_names)}
    _reposition_tracked(custom, new_names, new_name_to_j, tracked_names, common_names, file_label, log)

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

        # Anchor using the NEW (target) order, not where SequenceMatcher happened to
        # cut the OLD sequence -- when a lot of the list is rearranged elsewhere in
        # the same version step, that old-sequence cut point can land anywhere (even
        # at the very end of the old list), which used to silently tail-append
        # unrelated new entries instead of interpositioning them correctly.
        insert_at = _find_anchor(new_names, j1, j2, custom_index_by_name)
        if insert_at is None:
            insert_at = len(custom)

        new_entries = []
        for _, e in new_slice:
            if e.name in custom_index_by_name:
                continue  # already present (e.g. user added it manually already)
            new_entries.append(Entry(name=e.name, state=e.state))
            log.added.append((e.name, file_label))
            # Placed by MOPU, not the user -- keep following the official file's
            # position for it through the rest of this run (see module docstring).
            tracked_names.add(e.name)

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
