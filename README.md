<div align="center">

<img src="https://raw.githubusercontent.com/GamesRedone/MOPU/main/images/mopu.png" alt="Description" width="50%">

</div>

<h1 align="center">MOPU - The MO2 Profile Updater</h1>

<br>

## Introduction

MOPU updates/downgrades your custom MO2 Profile to reflect the changes a modlist author makes to the Official Profile during an update. Such as; mods they added, removed, renamed, repositioned, or enabled/disabled. With every change YOU made to your Custom Profile preserved. Including any mods you may have added, enabled, or disabled.

<br>

<div align="center">
<img src="https://raw.githubusercontent.com/GamesRedone/MOPU/main/images/mopu_readme1.png" alt="Description" width="50%">
<br>
<h2>1. MOPU sources the official load order history.</h2>
</div>

<details><summary>Learn More</summary>

<br>

Click Here to view the modlists that currently support MOPU.

Adding support for your own modlist, or any modlist, is easy!

👍 MOPU has a built in tool to help you package up your Load Order for upload to GitHub. The new home of your modlist's version history.

Once you, or the modlist author, upload a minimum of ***2 load order versions***, anyone can use the repo to update their profile!

> Instructions are listed in the [How to Setup a GitHub Repo](https://github.com/GamesRedone/MOPU/new/main#how-to-setup-a-github-repo) section below.<br><br>
> Checkout the [MOPU-Test](https://github.com/GamesRedone/MOPU-Test) Repo if you would like to see a live example.<br>
> Two test profiles are included so you can tryout MOPU.

</details>

<br>

<div align="center">
<img src="https://raw.githubusercontent.com/GamesRedone/MOPU/main/images/mopu_readme2.png" alt="Description" width="75%">
<br>
<h2>2. MOPU makes a list of all the changes.</h2>
</div>

<details><summary>Learn More</summary>

<br>

- Mods/plugins the modlist author added
- Mods/plugins they have renamed
- Mods/plugins they removed
- Mods/plugins they repositioned
- Mods/plugins they have enabled/disabled
- Mods/plugins YOU added

</details>

<br>

<div align="center">
<img src="https://raw.githubusercontent.com/GamesRedone/MOPU/main/images/mopu_readme3.png" alt="Description" width="50%">
<br>
<H2>3. With this list of changes, MOPU updates your profile.</H2>
</div>


<details><summary>Learn More</summary>

<br>

**MOPU only edits these three files in your MO2 Profile :**
> modlist.txt<br>
> plugins.txt<br>
> loadorder.txt<br>

<br>

**🔐 MOPU never touches your original profile's folder.**
> It writes the updated profile to a output folder of your choice, that way you can review it before truly overwriting anything.

<BR>

- **Multi-Version Chaining** : By looking at the Official Load Order across multiple version of the same modlist, MOPU can distinguish the author's changes from the user's changes and merge them safely.
    > With that said, only two versions of the Official load Order are required. So if you want to update/downgrade from one specific version to another, you only need to upload the Official Load Order for these two versions. Not every version in-between. 
⠀
- **Auto Updates Review** : If a mod author disables/enables a mod in an update/downgrade, and you still have it in the original state, the mod will be marked to be Automatically Updated. Most of the time you want this change.
    > Although, you may want to check here to see if any mods were disabled that are required by mods YOU added.
    > MOPU will show you all mods that have been marked for auto update, with the option to "Keep As Is" and reject the Auto Update.
- **Package Your Current Load Order** :
- **Sync Your Changelog** :

<BR>

</details>

<br>

## How to Use

Be sure to review the important [Dos & Don't](#dos-donts) before using MOPU.

1. Download, extract, and run `MOPU.exe`
2. Enter the link for the GitHub Repo hosting the load order history for your modlist and click `Fetch Repo`.
3. Pick the base MO2 profile that your Custom Profile was built from.
    > *(All Official Profiles that have been uploaded to the GitHub repo will be available as options)*<br><br>
    > So for ZISS, users can choose from :<br>
    > (e.g.) `ZISS - Community Shaders` or `ZISS - ENB`<br><br>
    > With the ability to select the exact modlist version of their Custom MO2 Profile *(e.g.) `ZISS v1.2.0`*,<br>
    > and the version they want to update to *(e.g.) `ZISS v1.2.1`*.
4. Point to the folder of your Custom MO2 Profile, as well as the folder for your output and click `Analyze My Profile`.
5. After reviewing, click `Confirm Profile Update`.
    > If the Output folder is ***NOT*** within your MO2 Profiles folder already, copy the folder to your profiles folder.<br><br>
    > (e.g.) `C:\ZISS\profiles\`<br>
    > (e.g.) `C:\Users\<YourUsername>\AppData\Local\ModOrganizer\<InstanceName>\profiles\`

<br>

## Dos & Don'ts

*A majority of these Dos & Don'ts are simply the best practices for updating a customized modlist.*<br>

Follow this guide when editing the load order for your modlist to ensure your changes are properly preserved.

<br>

### ***Don'ts***

- ***DO NOT*** use MOPU with the incorrect official base profile selected.
    > MOPU was designed to update your profile from one specific version of a modlist to another.<br>
    > If you enter the incorrect base profile *(The Official Profile your custom profile was built from)*, you will experience errors.
- ***DO NOT*** remove any mods the modlist author has included in the modlist. *Unwanted mods should be disabled.*
    > Your modlist installer will just end up reinstalling any mods you remove when you update your modlist.
- ***DO NOT*** rearrange the sorting, rename, reinstall, or directly reconfigure any mod the modlist author has included.
    > If you wish to setup a custom configuration for a mod...<br>
    > ***Disable the mod you want to configure and install the mod a second time.***<br><br> 
    > The 2nd installation of the mod should be named something different then the first. *Modify this newly installed mod.*<br><br>
    > (e.g.) You install a mod that requires a patch from [Lux - Via (patch hub)](https://www.nexusmods.com/skyrimspecialedition/mods/116722) that has not been installed by the modlist author.<br><br>
    > 1.Disable `Lux - Via (patch hub)`<br>
    > 2. Install `Lux - Via (patch hub)` again, name it something like `(CUSTOM)Lux - Via (patch hub)`<br>
    > 3. Select the patch you need from the FMOD installer and place anywhere in your load order.

<br>

### ***Dos***

- ***YOU SHOULD*** backup your MO2 Profile.
    > Modlist installers like Wabbajack will wipe out any custom MO2 profiles within your modlist folder during an update.<br>
    > Backup your profile before ***AND*** after using MOPU.<br><br>
    > The folder for your profile can be found within your modlists `profiles` folder.<br>
    ```
    (e.g.) C:\ZISS\profiles\
    (e.g.) C:\Users\<YourUsername>\AppData\Local\ModOrganizer\<InstanceName>\profiles\<ProfileName>
    ```
    
- ***YOU SHOULD*** backup your Mod Files for the mods you added ***(+)*** your custom MO2 Separators.
    > Modlist installers like Wabbajack will wipe out any customizations within your modlist folder during an update.
    > When using Wabbajack, you can backup any mods/separators that you have added by adding the prefix `[NoDelete]` to the name of the mod/separator.<br>
    ```
    (e.g.) [NoDelete]Immersive Armors` or `[NoDelete](CUSTOM)Lux - Via (patch hub)
    ```
    > If you are not using Wabbajack you can backup any mods you have added by copying the mod folder(s)/separator folder(s) within the MO2 `mods` directory.
    ```
    (e.g.) C:\ZISS\mods\
    ```
    
- ***YOU SHOULD*** update your modlist with your modlist installer before using your updated MO2 profile.
    > MOPU is ***NOT*** a modlist installer.<br><br>
    > This means MOPU's output will ***ONLY*** add new mods the modlists author added to `modlist.txt` and `plugins.txt`.<br><br>
    > MOPU will ***NOT*** install the actual mod files themselves.
- ***YOU SHOULD*** always check the Auto Updates section of the log.
    > Mods that are marked to be automatically disabled are listed at the top. Check here to see if any mods are being disabled that are required by mods you have added.

<br>

## How to Setup a GitHub Repo⠀

1. If you do not have a GitHub repo for the modlist already, you can create one by clicking the `New` button within the `Repositories` tab of your GitHub profile.

    <details><summary>Screenshot</summary>

    </details>

2. Enter the name of the modlist as the `Repository name`, ensure the repo is set to `Public`.

    <details><summary>Screenshot</summary>

    </details>

1. Click this Icon 👉 <img src="https://raw.githubusercontent.com/GamesRedone/MOPU/main/images/upload-cloud-blue.png" alt="Description"> within MOPU to package up your Load Order for upload to GitHub.

2. Enter the path to your Modlist's folder and MOPU will output the prepared files.

    <details><summary>Screenshot</summary>

    </details>

3. Upload the `loadorder` folder to GitHub and setup is complete!

    <details><summary>Screenshots</summary>

    </details>

4. Repeat for every version of the modlist that you would like MOPU to support.
    > Only upload the `v1.0.0-modlist.txt` & `v1.0.0-plugins.txt` files after the first upload, ***NOT*** the `loadorder` folder a second time.<br><br>
    > If you upload the `loadorder` folder when there is already a `loadorder` folder hosted on the GitHub repo, GitHub will end up placing the folder within your existing `loadorder` folder. This would break the Folder Structure.

    <details><summary>Screenshot</summary>

    </details>

<br>

### *Folder Structure*
```
YourRepo/
├── LoadOrder/
│   ├── [ProfileName]/
│   │   ├── v1.0.0-modlist.txt
│   │   ├── v1.0.0-plugins.txt
│   │   ├── v1.1.0-modlist.txt
│   │   ├── v1.1.0-plugins.txt
│   │   └── ...
│   └── [AnotherProfileName]/
│       └── ...
└── Changelog/
    └── diffs-[ProfileName].md
    └── diffs-[AnotherProfileName].md
```

MOPU takes care of the Folder Structure for you when you package your current load order. *Click this Icon 👉 <img src="https://raw.githubusercontent.com/GamesRedone/MOPU/main/images/upload-cloud-blue.png" alt="Description">*

- The `Changelog` folder and `diffs-[ProfileName].md` files are optional. [Click Here](#diffsmd) to learn more about the `diffs.md` file.
    > These are not generated when you package your current load order.
- The `LoadOrder` and `Changelog` folder names are case-insensitive.
    > `[ProfileName]` can be anything (e.g.) `CS`, `ENB`, `Default`. Each profile becomes a selectable option in the tool.
- A least two `modlist.txt` and `plugins.txt` files required for each profile.
    > So if you want to update/downgrade from one specific version to another, you only need to upload the official Load Order for these two versions. Not every version in-between.  
- The file name for `modlist.txt` and `plugins.txt` must follow these naming conventions :
  
  **`v1.0.0-modlist.txt`<br>`v1.0.0-plugins.txt`**
  > *The file version must be written using Semantic Versioning (e.g.) `v1.0.0`*
- The file name for `diffs.md` must follow this naming convention :
  
  **`diffs-[ProfileName].md`**
  > `[ProfileName]` must match the name of a profile's folder.
  > `diffs.md` file names are case-insensitive.

<br>⠀

## diffs.md
`diff.md` ensures that all changes due to renames are documented. Although, even without a `diffs.md` file renamed mods will ***NOT*** be lost. They will still be "Added" to the updated MO2 profile.<br><br>

Without a `diffs-[ProfileName].md` file you will receive the following message in your log:
```
No diffs-<profile>.md found -- rename detection was skipped.

This means renamed mods will appear as a Added Mod.
Not as a rename.
```

👍 You only *really* need to Generate a Changelog if you would like to distinguish this change.
> (e.g.) You want it to be clear a mod was renamed not added.

<br>

### How to Generate a Changelog

⚠️ Since there is no way to reliably generate a list of Renamed Mods, we must manually enter them.
> The arrow can be written `→` or `->`

```
## v1.0.0 → v1.1.0

### Renamed
- Old Mod Name → New Mod Name
- Another Old Name → Another New Name
```

This is all MOPU needs. Although, I typically like to include other information as well in my diffs.md file.<br>

<br>

***To generate the other information for your changelog...***
> *Mods that were added, removed, repositioned, or enabled/disabled.*

Click this icon 👉 <img src="https://raw.githubusercontent.com/GamesRedone/MOPU/main/images/refresh-loop-blue.png" alt="Description"> within MOPU to Sync Your Changelog.

This will generate updated versions of your Diffs Changelog(s), reflecting all changes across every uploaded `modlist.txt` and `plugins.txt` file.
> If there is an existing `diffs.md` file within the `Changelog` folder of the GitHub repo, any previously renamed mod will be pulled from here.<br><br>
> You will only ever need to manually enter renamed mods once.

<details><summary>Example of a Changelog Generated by MOPU</summary>

```
# Changes to the Load Order of MOPU-Test

The renamed mods found within this changelog are used by [MOPU](https://www.gamesredone.com/mopu/) to update your Custom MO2 Profile.

## v1.2.2 → v1.2.3

### Added (1)

- [ MOD ] Attack MCO unarmed PA fix

### Removed (1)

- [ PLUGIN ] DisarmlessDraugr.esp

### Disabled (2)

- [ MOD ] ZISS - Icons
- [ MOD ] Disarmless Draugrs

### Repositioned (2)

- [ MOD ] CS - Wheeler Valhalla Icons
- [ PLUGIN ] DragonbornsBestiaryMCM.esp

## v1.2.1 → v1.2.2

### Added (4)

- [ MOD ] CS - Wheeler Valhalla Icons
- [ MOD ] Dragonborns Bestiary MCM
- [ MOD ] ENB - Wheeler Valhalla Icons
- [ PLUGIN ] DragonbornsBestiaryMCM.esp

### Removed (1)

- [ MOD ] Wheeler Valhalla Icons

### Enabled (1)

- [ MOD ] ZISS - Icons

## v1.2.0 → v1.2.1

### Added (4)

- [ MOD ] Wrye Bash Output
- [ MOD ] Variadic Collision Dynamics - Resources
- [ MOD ] Harrald_TraintoSandbox.esp
- [ PLUGIN ] Harrald_TraintoSandbox.esp

### Renamed (1)

- [ MOD ] BethINI → BethINI Pie

---

*Generated by [MOPU](https://www.gamesredone.com/mopu/)*
```

</details>

<br><br>

## Error Log

A diagnostic log for troubleshooting is generated automatically. Please include a copy of this log when reporting any issues/bugs.

All issues/bugs must be reported through the [Issues Page](https://github.com/GamesRedone/MOPU/issues) on GitHub. 

You can find this log in the output folder of your updated MO2 Profile.

`<Output Folder>\MOPU\mopu-error-log-<YYYY-MM-DD>_<HH-MM-SS>.txt`

<br>

### *Error Reference*

| Stage | Error | Trigger |
|---|---|---|
| Fetch Repo | "Please enter a GitHub repo URL first." | URL field empty |
| Fetch Repo | "Please enter a GitHub repository URL in this format: github.com/GamesRedone/ZISS" | URL doesn't match the expected pattern |
| Fetch Repo | "Doesn't look like a GitHub repo URL: {url}" | URL parse failed |
| Fetch Repo | "Couldn't read the repository tree for {owner}/{repo}. Check the URL." | GitHub API call failed (bad repo, private repo, rate limit, network) |
| Fetch Repo | "No 'LoadOrder' folder found in this repo." | Repo doesn't follow the expected layout |
| Fetch Repo | "No versioned modlist.txt files found under LoadOrder/<profile>/." | No vX.Y.Z-modlist.txt files present |
| Fetch Repo | "No profile subfolders found inside LoadOrder." | LoadOrder folder is empty |
| Fetch Repo | "Failed to download {path}: {e}" | A specific file failed to download after the tree listing succeeded |
| Analyze | "No modlist.txt found in {folder} -- is this a valid MO2 profile folder?" | Selected custom profile folder is missing modlist.txt |
| Analyze | "Current or target version not found in available versions." | Version chain couldn't be built (shouldn't normally happen via the UI, since versions come from a dropdown) |
| Review→Finalize | "Please select both a profile folder and an output folder." | Either path field left empty |
| Review→Finalize | "This doesn't look like a valid MO2 profile folder -- it's missing modlist.txt and/or plugins.txt." | Selected folder missing one of the required files |
| Finalize | "Error writing output: {e}" | Any I/O failure writing modlist.txt/plugins.txt/loadorder.txt/saves/other files (permissions, disk full, path too long) |
| Done | "Error saving log" | Saving the log preview text failed |
| Prepare Files | "Please enter the file path/name/version first." | Any of the three fields left empty in that helper |
| Prepare Files | "Please enter the modlist version using Semantic Versioning" | Version doesn't match vX.Y.Z |
| Prepare Files | "Modlist folder not found: {path}" | Path doesn't exist |
| Prepare Files | "No 'profiles' folder found. For a portable instance..." | Neither a profiles folder nor a valid root folder found |
| Prepare Files | "No profiles with both modlist.txt and plugins.txt were found..." | No complete profiles to scaffold |
| Prepare Files | generic "Error: {e}" | Any other exception during folder generation |
