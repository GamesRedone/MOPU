# MO2 Profile Updater

Updates a custom Mod Organizer 2 profile against a versioned modlist GitHub repo
(e.g. https://github.com/GamesRedone/ZISS/), using the repo's
`LoadOrder/<profile>/vX.Y.Z-modlist.txt` and `vX.Y.Z-plugins.txt` files plus
`Changelog/diffs.md`.

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
Your original custom profile folder itself is never modified.

Only the files actually needed from the repo are downloaded (not the whole repository),
and everything downloaded is written to a temporary folder that's deleted automatically
when you close the app.

## Network access

This app connects to the internet **only** when you click "Fetch Repo," and only to
these two GitHub-owned domains:

- `api.github.com` -- one call to list every file path in the repo, one call to look
  up the repo's default branch
- `raw.githubusercontent.com` -- to download the specific `modlist.txt`/`plugins.txt`/
  `diffs.md` files identified from that listing, and nothing else in the repo

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

## diffs.md is optional

It works without a `diffs.md` -- **Added**, **Removed**, and default
enabled/disabled changes are always detected directly by diffing the actual `modlist.txt`/
`plugins.txt` files, never from diffs.md. The one thing that depends on it is **renames**:
without diffs.md, a renamed mod can't be told apart from "one mod removed + a different
mod added," so it's simply handled as that instead -- safe, but any customization on the
old entry (its position, or an enabled/disabled override) won't carry over automatically.
When diffs.md is missing, the log calls this out under `=== Renamed ===` with an
explanation of what it means for that update.

## Running it

### Option A -- just run the Python script
Needs Python 3.10+ (with tkinter, which is included in standard Windows/Mac installers).

```
python main.py
```

### Option B -- build a standalone .exe (Windows)
Double-click `build_exe.bat` (or run it from a command prompt). It installs PyInstaller
and builds `dist\MO2ProfileUpdater.exe`, with the app's own icon set for both the exe
file and the window/taskbar icon. After that, the exe is standalone -- no Python needed
to run it on other machines.

## Files
- `main.py` -- entry point
- `gui.py` -- the wizard UI
- `github_client.py` -- selectively fetches only needed files from the repo (Git Trees API)
- `local_client.py` -- scaffolds a GitHub-ready folder structure from a local modlist install ("Prepare Your Files For Upload to GitHub")
- `diffs_parser.py` -- parses diffs.md (used for its Renamed mappings)
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

Either way, the output always goes to a `MO2 Profile Updater\<modlist name>\` folder
created *next to* `profiles` -- never inside it, regardless of which style of path was
given.

Only profiles with *both* `modlist.txt` and `plugins.txt` are included -- plugin load
order matters just as much as mod install order, so an incomplete profile isn't
scaffolded. For each included profile, the whole profile folder is copied over, then
pruned down to just those two files, which are renamed to the `vX.Y.Z-modlist.txt` /
`vX.Y.Z-plugins.txt` convention using the version you entered. No `diffs.md` or
`Changelog` folder is generated -- that's still something you write yourself, since
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
