# MOPU

Updates a custom Mod Organizer 2 profile against a versioned modlist GitHub repo
(e.g. https://github.com/GamesRedone/ZISS/), using the repo's
`LoadOrder/<profile>/vX.Y.Z-modlist.txt` and `vX.Y.Z-plugins.txt` files plus each
profile's own `Changelog/diffs-<profile>.md` (e.g. `diffs-cs.md` for the `CS` profile).

## What it does

Given a modlist repo URL, the base profile (e.g. `CS` or `ENB`), your current version,
the version you want to upgrade to, and the folder containing your custom MO2 profile,
it walks every intermediate version between the two and:

- **Renamed** mods/plugins are renamed in place, keeping your enabled/disabled state and position.
- **Removed** mods/plugins are deleted.
- **Added** mods/plugins are inserted at the correct position with the state they ship with.
- If a mod's own default enabled/disabled state changes upstream, it's shown on the
  Review screen as an **Auto Update** -- checked to apply the new default by default
  (so ignoring it behaves the same as before), with a one-click way to keep it as-is
  instead (e.g. if something else depends on it staying the way it currently is).
- Any mods/plugins *you* added yourself (never present in any base version) are left
  completely untouched.

`loadorder.txt` is derived automatically: master/DLC/Creation-Club entries (never
touched by modlist updates) are kept exactly as they were, followed by the merged
`plugins.txt` order. No LOOT run and no manual load-order input is ever required.

The result is written to the output folder you choose. **Any files already in that
folder are overwritten** -- the app warns about this on the folder-selection screen.
Your original custom profile folder itself is never modified -- enforced by a check
that rejects an output folder that's the same as, inside, or containing the custom
profile folder, before anything is written.

Only the files actually needed from the repo are downloaded (not the whole repository),
and everything downloaded is written to a temporary folder that's deleted automatically
when you close the app.

## Network access

This app connects to the internet **only** when you click "Fetch Repo," and only to
these two GitHub-owned domains:

- `api.github.com` -- one call to list every file path in the repo, one call to look
  up the repo's default branch
- `raw.githubusercontent.com` -- to download the specific `modlist.txt`/`plugins.txt`/
  `diffs-<profile>.md` files identified from that listing, and nothing else in the repo

There is no other network activity anywhere in the app: no telemetry, no analytics, no
auto-update check for the app itself, and no communication with anything other than the
GitHub repo URL you explicitly typed in. This access is required for the app's basic
function, not an optional add-on -- comparing two versions of a modlist is impossible
without being able to read both of them, and the whole point of pointing this at a
GitHub repo is that the version history lives there rather than on your own disk.

The only other places a URL appears anywhere in this app are a handful of clickable
text links (Documentation, Discord, the GamesRedone site, a link to semver.org) --
clicking one of these opens your own default web browser to that page via the OS,
the same as clicking a link in any other application. The app itself never contacts
any of those addresses.

## diffs-<profile>.md is optional, and scoped to its own profile

Each profile has its own rename file, named `diffs-<profile>.md` (lowercase, matching
the profile folder's name, e.g. `diffs-cs.md` for the `CS` profile under
`LoadOrder/CS/`) -- matched case-insensitively, and looked up only for that specific
profile. This means two profiles in the same repo can each rename a mod that started
with the same name to two *different* new names, and each profile's own update still
picks up its own correct rename -- there's no single shared file where one profile's
history could clobber another's.

The app works fine without a `diffs-<profile>.md` for a given profile -- **Added**,
**Removed**, and default enabled/disabled changes are always detected directly by
diffing the actual `modlist.txt`/`plugins.txt` files, never from this file. The one
thing that depends on it is **renames**: without it, a renamed mod can't be told apart
from "one mod removed + a different mod added," so it's simply handled as that instead
-- safe, but any customization on the old entry (its position, or an enabled/disabled
override) won't carry over automatically. When it's missing for a profile, the log
calls this out under `=== Renamed ===` with an explanation of what it means for that
update.

Older repos using the previous shared `Changelog/diffs.md` convention (one file for
the whole repo, not per profile) will need to rename/split that file into one
`diffs-<profile>.md` per profile -- the old shared filename is no longer recognized.

## Running it

### Option A -- just run the Python script
Needs Python 3.10+ (with tkinter, which is included in standard Windows/Mac installers).

```
python main.py
```

### Option B -- build a standalone .exe (Windows)
Double-click `build_exe.bat` (or run it from a command prompt). It installs PyInstaller
and builds `dist\MOPU.exe`, with the app's own icon set for both the exe
file and the window/taskbar icon. After that, the exe is standalone -- no Python needed
to run it on other machines.

## modlist.txt's "*" prefix

`file_formats.py` now recognizes `*` as a valid `modlist.txt` prefix, alongside `+`
(enabled) and `-` (disabled) -- it marks a pseudo-mod MO2 manages itself (DLC and
Creation Club content) rather than a real toggleable mod. This was previously
unrecognized and silently treated as an inert comment line, making every DLC/CC entry
invisible to Added/Removed/Auto-Update detection. Confirmed this had been
undercounting real ZISS profile data by 74 entries (768 vs the actual 842) without
ever surfacing, since a mistreated comment just passes through untouched either way
in MOPU's own version-upgrade logic -- ground-truth regression re-confirmed passing
after the fix.

## Files
- `main.py` -- entry point
- `gui.py` -- the wizard UI
- `github_client.py` -- selectively fetches only needed files from the repo (Git Trees API)
- `local_client.py` -- scaffolds a GitHub-ready folder structure from a local modlist install ("Prepare Your Files For Upload to GitHub")
- `diffs_parser.py` -- parses each profile's `diffs-<profile>.md` (used for its Renamed mappings)
- `file_formats.py` -- reads/writes modlist.txt / plugins.txt / loadorder.txt exactly
- `merge_engine.py` -- the core per-version merge logic
- `orchestrator.py` -- chains merge_engine across every version in the upgrade path,
  and derives loadorder.txt
- `version_utils.py` -- version string parsing/sorting (handles v1.0.12 vs v1.0.123 etc.)
- `assets_util.py` -- resolves bundled asset paths in both dev and frozen-exe modes
- `widgets.py` -- custom rounded-pill buttons and rounded dropdown menus, drawn with plain
  Tkinter Canvas (no extra dependency)
- `font_loader.py` -- loads the bundled EB Garamond font privately at runtime (Windows,
  via GDI `AddFontResourceEx`), so it's never installed system-wide and is released
  automatically when the app closes
- `assets/` -- app icon, logo, font, and UI icons

## Log preview

On the Review screen, the small document icon next to "Review" opens a preview of the
full change log exactly as it will appear on the final "Done" screen if you confirm now.
While that preview is open, toggling any Auto Update's "Apply New Default" / "Keep As Is"
choice updates the preview immediately -- no need to close and reopen it.

## Icon licensing

The document/log icon used on the Review screen and the upload-cloud icon used on the
first screen are both Feather Icons glyphs (`file-text` and `upload-cloud`,
`assets/icons/`), MIT licensed, Copyright (c) 2013-2023 Cole Bemis
(`assets/icons/FEATHER_LICENSE.txt`). Both are used unmodified aside from recoloring.

The sync-loop icon next to it (`assets/icons/refresh-loop-blue.png`), which opens
"Update your diffs.md file(s)", is original artwork -- not sourced from Feather Icons
or any other third party -- so it isn't listed in `THIRD-PARTY-LICENSES.txt` and
carries the same copyright as the rest of the app's own UI.

## Update your diffs.md file(s)

The sync-loop icon in the top-right corner of the first screen opens a helper that
regenerates a `diffs-<profile>.md` for every profile a repo has, computed directly
from that profile's own `modlist.txt`/`plugins.txt` version history (every version
diffed against the very next one) -- no custom MO2 profile involved. Point it at a
repo (same `owner/repo` URL as Step 1) and an output folder, and it writes one file
per profile.

Renamed mods can't be reliably detected from the file listings alone (see
`diffs_parser.py`), so if the repo already has a `diffs-<profile>.md` for a profile,
its existing `### Renamed` entries are read back in and carried forward for the
matching version steps -- this "updates" an existing changelog to cover new versions
without losing renames someone already curated by hand. A profile with no existing
diffs file just skips renames for that run, the same as a normal Analyze with no
diffs.md (they'll show as a plain Add + Remove instead).

## Prepare Your Files For Upload to GitHub

The upload-cloud icon in the top-right corner of the first screen opens "Package Your
Current Load Order" -- a helper for modlist authors, separate from the main update
flow. Point it at your modlist's `profiles` folder, give it a modlist name and a
version number (Semantic Versioning, e.g. `v1.0.0`), and it scaffolds a
`loadorder/<Profile>/` folder ready to commit to a GitHub repo in the layout this
tool expects.

Both ways of pointing it at an install are supported and handled correctly:
- **Portable instance**: point it at the modlist's root folder (e.g. `C:\ZISS\`),
  which contains a `profiles` subfolder.
- **Regular/Global instance**: point it directly at the profiles folder itself (e.g.
  `C:\Users\<You>\AppData\Local\ModOrganizer\<Instance>\profiles`), since there's no
  single meaningful "root" folder above it for this kind of install.

Either way, the output always goes to a `MOPU\<modlist name>\` folder
created *next to* `profiles` -- never inside it, regardless of which style of path was
given.

Only profiles with *both* `modlist.txt` and `plugins.txt` are included -- plugin load
order matters just as much as mod install order, so an incomplete profile isn't
scaffolded. For each included profile, the whole profile folder is copied over, then
pruned down to just those two files, which are renamed to the `vX.Y.Z-modlist.txt` /
`vX.Y.Z-plugins.txt` convention using the version you entered. No `diffs-<profile>.md`
or `Changelog` folder is generated -- that's still something you write yourself, since
only you know what actually changed and what got renamed in a given release.

A `modlist-info.txt` file is written directly inside the generated `loadorder` folder,
showing the modlist name and the actual folder structure that was just created (real
profile names, real version tag) as a quick reference for whoever's setting up the repo.

## Font licensing (EB Garamond)

EB Garamond is licensed under the SIL Open Font License, Version 1.1 (`assets/fonts/OFL.txt`).
The OFL explicitly permits embedding/bundling the font inside software -- including
closed-source, all-rights-reserved software -- as long as the font itself isn't sold on
its own and this license file travels with it, which is exactly how it's packaged here.
This app's own source code is **not** released under the OFL and remains all rights
reserved; only the bundled font file is OFL-licensed.

## Log display polish

The log (Log preview popup and the Done page) now tags each line `[ MOD ]` or
`[ PLUGIN ]` instead of a trailing `(modlist.txt)`/`(plugins.txt)`, matches the same
format in the Auto Updates table's Mod/Plugin Name column (left-aligned, matching
that column's header), and both surfaces now scroll. Plugins are hidden by default;
a shared "Show Plugins" checkbox reveals them everywhere the log appears. The
checkbox itself needed two separate fixes to render cleanly: `takefocus=False` alone
didn't stop the dotted focus ring, since a direct mouse click still gives a widget
focus regardless of that setting (it only affects Tab-key navigation) -- the actual
fix was `self._style.map("TCheckbutton", focuscolor=[("", COLOR_BG)])`, making the
ring the same color as the background instead of trying to prevent focus entirely.

## Later polish pass

The checkbox had a second, separate bug beyond the focus ring -- a light background
highlight on mouse *hover* (ttk's "active" state), which `focuscolor` doesn't touch.
Fixed with `self._style.map("TCheckbutton", background=[("active", COLOR_BG)])`.

The Auto Updates help modal now has a real scrollbar instead of a fixed size, ported
proactively from the same fix on MOPC (whose longer replacement text was getting cut
off there) -- not reported broken here, but the same latent risk existed since it's
the identical fixed-height pattern, so it's worth being ahead of rather than waiting
to hit it later. Footer gained a copyright/EULA line under the site link, and the
documentation link now points at gamesredone.com/mopu/ instead of a leftover Nexus
mod-page URL from an earlier round.

## Two more layout bugs, found fixing the same thing in MOPC

The Done page's footer and "Start Over" button were being pushed off the bottom of
the fixed-size window. The text box had lost its explicit `height=` when the
scrollbar was added, and `tk.Text()` without one defaults to Tkinter's built-in
24-line height -- combined with everything else on the page, that exceeded the
window's fixed 760px, squeezing the bottom-packed content out of view. Fixed by
giving the text box back a bounded height (14 lines) while keeping the scrollbar
for anything beyond that.

The Auto Updates help modal's scrollbar (added proactively last round) turned out
to be unnecessary once sized correctly -- confirmed all text fits at a plain fixed
height, so it was just clutter. Reverted to the simpler non-scrolling Text widget.
