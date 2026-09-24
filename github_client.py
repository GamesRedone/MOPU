"""
Fetches only the files we actually need from a GitHub repo (LoadOrder/**/*.txt that
match the version-file naming pattern, plus each profile's own Changelog/diffs-<profile>.md)
instead of downloading the whole repository as a zip. This makes exactly one GitHub API
call (a recursive tree listing) and then pulls individual file contents from
raw.githubusercontent.com, which isn't subject to the API's low unauthenticated rate limit.
"""

import os
import re
import json
import urllib.request
import urllib.parse


class RepoError(Exception):
    pass


_UA = {"User-Agent": "mo2-profile-updater"}

# Anchored (whole-string match, not search) and restricted to the characters GitHub
# actually allows in an owner/repo name -- doesn't rely on gui.py's own REPO_URL_RE
# having already screened the input first, so this module is safe to call on its
# own (a future caller, a CLI, direct reuse) without inheriting a GUI-only guard.
_REPO_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)

# Generous but bounded -- a modlist repo's tree listing or any single text file it
# serves has no legitimate reason to approach this size. Caps memory use if a
# compromised or malicious repo tries to serve an oversized response.
_MAX_RESPONSE_BYTES = 20 * 1024 * 1024  # 20 MB


def _parse_repo_url(url: str):
    url = url.strip()
    m = _REPO_URL_RE.match(url)
    if not m:
        raise RepoError(f"Doesn't look like a GitHub repo URL: {url}")
    owner, repo = m.group(1), m.group(2)
    if owner in (".", "..") or repo in (".", ".."):
        raise RepoError(f"Doesn't look like a GitHub repo URL: {url}")
    return owner, repo


def _read_capped(resp, max_bytes=_MAX_RESPONSE_BYTES):
    data = resp.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise RepoError("Response from GitHub was larger than expected -- refusing to load it.")
    return data


def _get_json(url):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(_read_capped(resp).decode("utf-8"))


def _get_default_branch(owner, repo):
    try:
        info = _get_json(f"https://api.github.com/repos/{owner}/{repo}")
        return info.get("default_branch")
    except Exception:
        return None


def _get_tree(owner, repo, branch):
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    return _get_json(url)


_MODLIST_RE = re.compile(r"^(v[0-9][^/\s\-]*)-modlist\.txt$", re.IGNORECASE)
_PLUGINS_RE = re.compile(r"^(v[0-9][^/\s\-]*)-plugins\.txt$", re.IGNORECASE)
_DIFFS_RE = re.compile(r"^diffs-(.+)\.md$", re.IGNORECASE)


class RepoData:
    """Local cache of everything fetched for one repo."""

    def __init__(self, workdir):
        self.workdir = workdir
        self.diffs_paths = {}  # profile name -> local_path (only set if that profile has one)
        # profile -> version -> {"modlist": local_path, "plugins": local_path or None}
        self.profiles = {}


def fetch_repo_data(repo_url: str, workdir: str, progress_cb=None) -> RepoData:
    """progress_cb(fraction: float, message: str) is called periodically, fraction in [0,1]."""

    def report(frac, msg):
        if progress_cb:
            progress_cb(frac, msg)

    owner, repo = _parse_repo_url(repo_url)
    report(0.0, "Looking up repository...")

    branch = _get_default_branch(owner, repo)
    branches_to_try = ([branch] if branch else []) + [b for b in ("main", "master") if b != branch]

    tree = None
    used_branch = None
    for b in branches_to_try:
        try:
            tree = _get_tree(owner, repo, b)
            used_branch = b
            break
        except Exception:
            continue
    if tree is None:
        raise RepoError(f"Couldn't read the repository tree for {owner}/{repo}. Check the URL.")

    report(0.15, "Locating LoadOrder and Changelog files...")

    all_paths = [item["path"] for item in tree.get("tree", []) if item.get("type") == "blob"]

    def top_folder(path, name):
        parts = path.split("/")
        return len(parts) > 0 and parts[0].lower() == name.lower()

    loadorder_paths = [p for p in all_paths if top_folder(p, "LoadOrder")]
    changelog_paths = [p for p in all_paths if top_folder(p, "Changelog")]

    if not loadorder_paths:
        raise RepoError("No 'LoadOrder' folder found in this repo.")

    profile_versions = {}  # profile -> version -> {"modlist": repo_path, "plugins": repo_path or None}
    for p in loadorder_paths:
        parts = p.split("/")
        if len(parts) != 3:
            continue
        _, profile, filename = parts
        m_mod = _MODLIST_RE.match(filename)
        m_plug = _PLUGINS_RE.match(filename)
        if m_mod:
            v = m_mod.group(1)
            profile_versions.setdefault(profile, {}).setdefault(v, {})["modlist"] = p
        elif m_plug:
            v = m_plug.group(1)
            profile_versions.setdefault(profile, {}).setdefault(v, {})["plugins"] = p

    if not profile_versions:
        raise RepoError("No versioned modlist.txt files found under LoadOrder/<profile>/.")

    # diffs-<profile>.md is optional, and scoped to its own profile -- matched by
    # profile name (case-insensitive) against the profile folders actually found
    # under LoadOrder, so "diffs-CS.md" is only ever consulted for the "CS" profile,
    # never accidentally applied to "ENB" or any other profile in the same repo. If
    # a given profile has no matching file, rename detection just gets skipped for
    # that profile later and the merge log notes it -- everything else still works.
    profile_names_lower = {name.lower(): name for name in profile_versions.keys()}
    diffs_repo_path_by_profile = {}  # profile name -> repo path
    for p in changelog_paths:
        m = _DIFFS_RE.match(os.path.basename(p))
        if not m:
            continue
        matched_profile = profile_names_lower.get(m.group(1).lower())
        if matched_profile:
            diffs_repo_path_by_profile[matched_profile] = p

    to_download = list(diffs_repo_path_by_profile.values())
    for profile, versions in profile_versions.items():
        for v, files in versions.items():
            if "modlist" in files:
                to_download.append(files["modlist"])
            if "plugins" in files:
                to_download.append(files["plugins"])

    data = RepoData(workdir)
    local_dir = os.path.join(workdir, "fetched")
    os.makedirs(local_dir, exist_ok=True)

    profile_for_diffs_repo_path = {v: k for k, v in diffs_repo_path_by_profile.items()}

    total = len(to_download)
    for i, repo_path in enumerate(to_download):
        frac = 0.2 + 0.75 * (i / max(total, 1))
        report(frac, f"Downloading {os.path.basename(repo_path)}...")
        raw_url = ("https://raw.githubusercontent.com/" + owner + "/" + repo + "/" + used_branch + "/"
                   + "/".join(urllib.parse.quote(seg) for seg in repo_path.split("/")))
        req = urllib.request.Request(raw_url, headers=_UA)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = _read_capped(resp)
        except Exception as e:
            raise RepoError(f"Failed to download {repo_path}: {e}")

        local_path = os.path.join(local_dir, repo_path.replace("/", "__"))
        with open(local_path, "wb") as f:
            f.write(content)

        if repo_path in profile_for_diffs_repo_path:
            data.diffs_paths[profile_for_diffs_repo_path[repo_path]] = local_path

    for profile, versions in profile_versions.items():
        data.profiles[profile] = {}
        for v, files in versions.items():
            modlist_repo_path = files.get("modlist")
            plugins_repo_path = files.get("plugins")
            if not modlist_repo_path:
                continue
            data.profiles[profile][v] = {
                "modlist": os.path.join(local_dir, modlist_repo_path.replace("/", "__")),
                "plugins": (os.path.join(local_dir, plugins_repo_path.replace("/", "__"))
                            if plugins_repo_path else None),
            }

    report(1.0, "Done.")
    return data


def list_profiles(data: RepoData):
    return sorted(data.profiles.keys())


def list_versions(data: RepoData, profile: str):
    return list(data.profiles.get(profile, {}).keys())


def repo_name_from_url(url: str) -> str:
    """Returns just the repo name (e.g. 'ZISS' from '.../GamesRedone/ZISS/')."""
    try:
        _, repo = _parse_repo_url(url)
        return repo
    except Exception:
        return ""
