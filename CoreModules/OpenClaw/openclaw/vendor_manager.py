"""Vendor claw-code: GitHub main SHA, clone into versions/<sha>, active pointer."""

from __future__ import annotations

import json
import logging
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_LOG = logging.getLogger("openclaw.vendor")


def fetch_main_sha(owner: str, repo: str, token: str | None = None) -> str | None:
    """Return 40-char commit SHA for default branch tip (GitHub REST)."""
    url = f"https://api.github.com/repos/{owner}/{repo}/commits/main"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        sha = data.get("sha")
        if isinstance(sha, str) and len(sha) >= 40:
            return sha[:40]
        if isinstance(sha, str) and len(sha) == 7:
            return sha  # short — caller may reject
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
        _LOG.warning("fetch_main_sha failed: %s", e)
    return None


def vendor_root(project_root: Path, root_relative: str) -> Path:
    return (project_root / root_relative).resolve()


def read_active(root: Path) -> dict[str, Any] | None:
    p = root / "active.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_active(root: Path, sha: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    rel = f"versions/{sha}"
    (root / "active.json").write_text(
        json.dumps({"sha": sha, "path": rel}, indent=2),
        encoding="utf-8",
    )


def list_version_shas(root: Path) -> list[str]:
    d = root / "versions"
    if not d.is_dir():
        return []
    out = []
    for child in d.iterdir():
        n = child.name.lower()
        if child.is_dir() and len(n) == 40 and all(c in "0123456789abcdef" for c in n):
            out.append(n)
    return sorted(out)


def ensure_clone(owner: str, repo: str, sha: str, dest: Path) -> tuple[bool, str]:
    """
    Materialize ``dest`` as a git checkout of ``sha`` (full SHA recommended).
    Returns (ok, message).
    """
    if dest.is_dir() and (dest / ".git").is_dir():
        return True, "already exists"

    remote = f"https://github.com/{owner}/{repo}.git"
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            _rmtree_retry(dest)
        dest.mkdir(parents=True)
        for cmd in (
            ["git", "init"],
            ["git", "remote", "add", "origin", remote],
            ["git", "fetch", "--depth", "1", "origin", sha],
            ["git", "checkout", "-f", "FETCH_HEAD"],
        ):
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=str(dest))
            if r.returncode != 0:
                err = (r.stderr or r.stdout or "git failed")[:2000]
                _rmtree_retry(dest)
                return False, f"{' '.join(cmd)}: {err}"
        return True, "cloned"
    except (OSError, subprocess.TimeoutExpired) as e:
        _rmtree_retry(dest)
        return False, str(e)


def _rmtree_retry(path: Path) -> None:
    import shutil

    try:
        shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass


def sync_latest(
    project_root: Path,
    owner: str,
    repo: str,
    root_relative: str,
    token: str | None = None,
) -> dict[str, Any]:
    """Fetch main SHA from GitHub; clone into versions/<sha>; set active."""
    sha = fetch_main_sha(owner, repo, token=token)
    if not sha or len(sha) < 40:
        return {"ok": False, "error": "could not resolve full main SHA from GitHub"}
    root = vendor_root(project_root, root_relative)
    dest = root / "versions" / sha.lower()
    ok, msg = ensure_clone(owner, repo, sha.lower(), dest)
    if not ok:
        return {"ok": False, "error": msg}
    write_active(root, sha.lower())
    return {"ok": True, "sha": sha.lower(), "message": msg, "path": str(dest)}


def rollback(project_root: Path, sha: str, root_relative: str) -> dict[str, Any]:
    root = vendor_root(project_root, root_relative)
    dest = root / "versions" / sha.lower()
    if not dest.is_dir():
        return {"ok": False, "error": f"version not found: {sha}"}
    write_active(root, sha.lower())
    return {"ok": True, "sha": sha.lower()}
