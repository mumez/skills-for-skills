#!/usr/bin/env python3
"""Download a skill from a URL into a fresh quarantine directory, without running anything.

Usage: python3 -I fetch_remote.py <url>

Supports:
  https://github.com/OWNER/REPO
  https://github.com/OWNER/REPO/tree/REF/path/to/skill
  https://github.com/OWNER/REPO/blob/REF/path/to/SKILL.md
  https://raw.githubusercontent.com/OWNER/REPO/REF/path/SKILL.md
  any other git-cloneable URL, or a direct link to a .zip/.skill/.md file

Prints JSON: {quarantine_dir, target_dir, skill_md_files, notes}.
The clone disables hooks, LFS smudge and submodules so nothing from the repo executes.
"""
import json
import re
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path


def git_clone(url: str, dest: Path, ref: str | None) -> None:
    cmd = [
        "git", "-c", "core.hooksPath=/dev/null", "-c", "filter.lfs.smudge=",
        "-c", "filter.lfs.process=", "-c", "filter.lfs.required=false",
        "clone", "--depth", "1", "--no-recurse-submodules",
    ]
    if ref:
        cmd += ["--branch", ref]
    subprocess.run(cmd + [url, str(dest)], check=True, capture_output=True, text=True,
                   env={"GIT_TERMINAL_PROMPT": "0", "PATH": "/usr/bin:/bin:/usr/local/bin"})


def download(url: str, dest: Path) -> Path:
    name = url.rstrip("/").split("/")[-1].split("?")[0] or "download"
    out = dest / name
    with urllib.request.urlopen(url, timeout=60) as r, open(out, "wb") as f:
        f.write(r.read())
    return out


def safe_unzip(archive: Path, dest: Path, notes: list) -> None:
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            target = (dest / info.filename).resolve()
            if not str(target).startswith(str(dest.resolve())):
                notes.append(f"SUSPICIOUS: zip entry escapes the directory and was skipped: {info.filename}")
                continue
            z.extract(info, dest)


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    url = sys.argv[1].strip()
    q = Path(tempfile.mkdtemp(prefix="explaining-skill-"))
    notes, target = [], q / "src"

    gh = re.match(r"https?://github\.com/([^/]+)/([^/#?]+?)(?:\.git)?(?:/(tree|blob)/([^/]+)(?:/(.*))?)?/?$", url)
    raw = re.match(r"https?://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.*)$", url)
    try:
        if gh or raw:
            if gh:
                owner, repo, kind, ref, sub = gh.groups()
            else:
                owner, repo, ref, sub = raw.groups()
                kind = "blob"
            try:
                git_clone(f"https://github.com/{owner}/{repo}.git", target, ref)
            except subprocess.CalledProcessError:
                # ref may contain slashes (e.g. feature/x); fall back to default branch
                notes.append(f"clone with ref '{ref}' failed; cloned default branch instead")
                git_clone(f"https://github.com/{owner}/{repo}.git", target, None)
            sub_path = target / (sub or "")
            if kind == "blob" and sub_path.is_file():
                sub_path = sub_path.parent
            target = sub_path if sub_path.exists() else target
        elif re.search(r"\.(zip|skill)(\?|$)", url):
            target.mkdir()
            archive = download(url, q)
            safe_unzip(archive, target, notes)
        elif re.search(r"\.md(\?|$)", url):
            target.mkdir()
            download(url, target)
        else:
            git_clone(url, target, None)
    except Exception as e:  # report instead of crashing so the caller can explain
        print(json.dumps({"quarantine_dir": str(q), "error": f"{type(e).__name__}: {e}"}, ensure_ascii=False))
        sys.exit(1)

    skill_mds = sorted(str(p) for p in target.rglob("*")
                       if p.name.lower() == "skill.md" and p.is_file() and ".git" not in p.parts)
    print(json.dumps({"quarantine_dir": str(q), "target_dir": str(target),
                      "skill_md_files": skill_mds, "notes": notes}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
