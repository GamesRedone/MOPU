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

⠀ ⠀
I wasn't able to find a tool that just simply updates your Custom MO2 Profile from one version of a modlist to another. So I made one!



⠀
💾First, MOPU sources the official load order history for your modlist.
⠀
Add support for your own modlist, or any modlist!
⠀
The files modlist.txt and plugins.txt, for every version of the modlist you would like MOPU to support, must be uploaded to a public GitHub repo. With a minimum of 2 load order versions needed to create a version history.
⠀
This is key to how MOPU works.

👍 MOPU has a built in tool to help you package up your Load Order for upload.
As long as the repo is public, MOPU will be able to download the files it needs.
Instructions are listed in the "How to Setup a GitHub Repo" section below.
⠀
⠀
⠀ ⠀


🔍 Then, MOPU makes a list of all the changes the modlist author has made.
⠀
Mods the modlist author added
Mods they removed
Mods they have enabled/disabled
Mods they have renamed
⠀
⠀ ⠀
🪶 With this list of changes, MOPU updates your profile.
⠀
Multi-Version Chaining : By looking at the Official Load Order across multiple version of the same modlist, MOPU can distinguish the author's changes from the user's changes and merge them safely.

Select the modlist version your MO2 profile is currently based on and the target version you want to update/downgrade to.

MOPU analyzes the modlist's version history to identify changes made by the modlist author—including added, removed, enabled, disabled, and renamed mods—applying those changes to your profile while preserving your own customizations.
⠀
Auto Updates Review : If a mod author disables/enables a mod in an update/downgrade, and you still have it in the original state, the mod will be marked to be Automatically Updated. Most of the time you want this change.

Although, you may want to check here to see if any mods were disabled that are required by mods YOU added.

MOPU will show you all mods that have been marked for auto update, with the option to "Keep As Is" and reject the Auto Update. ⠀
Added Mods :  Mods that are added by a modlist author are inserted into your load order at the correct position and enabled/disabled state. Any mod you added yourself (Mods that never existed in any base version of the modlist), are left exactly how YOU configured them. ⠀
Renamed Mods :  Mods renamed by the Modlist Author are preserved. If YOU rename any mods, they will be treated as a new mod.
⠀

⠀
⠀

This mod only edits these three files in your MO2 Profile :
modlist.txt
plugins.txt
loadorder.txt

👍 MOPU never touches your original profile's folder.
It writes the updated profile to a output folder of your choice, that way you can review it before truly overwriting anything.⠀
⠀
How to Use ⠀
Download, extract, and run MO2ProfileUpdater.exeNo installation required.
⠀
Enter the link for the a GitHub Repo hosting the load order history for your modlist
(e.g.) https://github.com/GamesRedone/ZISS/
Click Fetch Repo.
⠀
Pick the base MO2 profile that your Custom Profile was built from.
(All official profiles that have been uploaded to the GitHub repo will be available as options)
So for ZISS, users can choose from :
(e.g.) "ZISS - Community Shaders" or "ZISS - ENB"
With the ability to select the exact modlist version of their Custom MO2 Profile (e.g. ZISS v1.2.0),
and the version they want to update to (e.g. ZISS v1.2.1).
⠀
Point to the folder of your Custom MO2 Profile, as well as the folder for your output and click Analyze My Profile.
⠀
 
The Log Icon will bring up a window allowing you to preview ALL the changes MOPU has prepared to make to your profile.
⠀
After reviewing, click Confirm Profile Update. If the Output folder is NOT within your MO2 Profiles folder already, copy the folder to your profiles folder.
(e.g.) C:/ZISS/profiles/
⠀ ⠀ ⠀
How to Setup a GitHub Repo⠀
Click This Icon 👉   , to package up your Load Order for upload to GitHub.

Enter the path to your Modlist's folder and MOPU will output the prepared files.

Upload the "loadorder" folder to GitHub and setup is complete!

Repeat for every version of the modlist that you would like MOPU to support.

⠀
YourRepo/
├── LoadOrder/
│   ├── <ProfileName>/
│   │   ├── v1.0.0-modlist.txt
│   │   ├── v1.0.0-plugins.txt
│   │   ├── v1.1.0-modlist.txt
│   │   ├── v1.1.0-plugins.txt
│   │   └── ...
│   └── <AnotherProfileName>/
│       └── ...
└── Changelog/
    └── diffs.md
⠀
Folder Structure
The "LoadOrder" and "Changelog" folder names are case-insensitive
<ProfileName> can be anything (e.g. CS, ENB, Default). Each profile becomes a selectable option in the tool.
A least two "modlist.txt" and "plugins.txt" files required for each profile.
The file name for "modlists.txt" and "plugins.txt" must follow these naming conventions:

"v1.0.0-modlists.txt"      "v1.0.0-plugins.txt"

The file version must be written using Semantic Versioning (e.g., v1.0.0).
⠀
👍 "diffs.md" is NOT required.
diff.md ensures that all changes due to renames are not lost. Most of the time renamed mods are added to the Updated MO2 Profile even without being specifically marked in diffs.md. The only time they will not end up being added to the Updated MO2 Profile is if the mod was renamed AND moved in the load order.
To prevent this from happening you can create a diffs.md file.
⠀ ⠀
diffs.md | Format
## v1.0.0 → v1.1.0

### Renamed
- Old Mod Name → New Mod Name
- Another Old Name → Another New Name
I typically like to include other information as well in my diffs.md file, although this is all MOPU needs.
Since there is no way to reliably generate a list of Renamed Mods, we must manually enter them.


Copyright (c) 2026 Games Redone. All rights reserved.
