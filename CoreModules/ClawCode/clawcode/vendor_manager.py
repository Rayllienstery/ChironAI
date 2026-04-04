"""Vendor claw-code: GitHub main SHA, active tree in versions/<sha>, archives in backups/<sha>."""

from __future__ import annotations

import json
import logging
import os
import shutil
import stat
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_LOG = logging.getLogger("clawcode.vendor")

# Written after a successful materialize; avoids treating stripped trees as incomplete.
_VENDOR_SNAPSHOT_MARKER = ".clawcode-vendor-snapshot"


def _rmtree_onerror(func, path, _exc_info):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def _strip_vendor_git(dest: Path) -> None:
    """Remove nested .git so the main repo is not a 'nested git repository' (e.g. Cursor checkpoints)."""
    git_dir = dest / ".git"
    if not git_dir.exists():
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["cmd", "/c", "attrib", "-r", f"{git_dir}\\*.*", "/s", "/d"],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(dest),
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        shutil.rmtree(git_dir, onerror=_rmtree_onerror)
    except OSError:
        shutil.rmtree(git_dir, ignore_errors=True)


def _write_vendor_snapshot_marker(dest: Path) -> None:
    try:
        (dest / _VENDOR_SNAPSHOT_MARKER).write_text("1\n", encoding="utf-8")
    except OSError:
        pass


def _is_sha_dir_name(name: str) -> bool:
    n = name.lower()
    return len(n) == 40 and all(c in "0123456789abcdef" for c in n)


def _iter_sha_children(parent: Path) -> list[Path]:
    if not parent.is_dir():
        return []
    out: list[Path] = []
    for child in parent.iterdir():
        if child.is_dir() and _is_sha_dir_name(child.name):
            out.append(child)
    return out


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


def history_from_active(data: dict[str, Any] | None) -> list[str]:
    """Activation order newest-first; falls back to [sha] when history is missing."""
    if not data:
        return []
    raw = data.get("history")
    if isinstance(raw, list):
        out: list[str] = []
        for x in raw:
            if isinstance(x, str) and _is_sha_dir_name(x):
                out.append(x.lower())
        if out:
            return out
    s = (data.get("sha") or "").strip().lower()
    return [s] if _is_sha_dir_name(s) else []


def can_rollback(root: Path) -> bool:
    return len(history_from_active(read_active(root))) >= 2


def write_active(root: Path, sha: str, history: list[str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    sha = sha.lower()
    norm: list[str] = []
    seen: set[str] = set()
    for h in history:
        if not isinstance(h, str) or not _is_sha_dir_name(h):
            continue
        hl = h.lower()
        if hl in seen:
            continue
        seen.add(hl)
        norm.append(hl)
    if not norm or norm[0] != sha:
        norm = [sha] + [h for h in norm if h != sha]
    rel = f"versions/{sha}"
    (root / "active.json").write_text(
        json.dumps({"sha": sha, "path": rel, "history": norm}, indent=2),
        encoding="utf-8",
    )


def _rmtree_retry(path: Path) -> None:
    try:
        shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass


def _move_into_backup_replace(root: Path, src: Path, sha: str) -> None:
    """Move src (versions/<sha>) to backups/<sha>, replacing existing backup."""
    dst = root / "backups" / sha.lower()
    (root / "backups").mkdir(parents=True, exist_ok=True)
    if dst.exists():
        _rmtree_retry(dst)
    shutil.move(str(src), str(dst))


def migrate_inactive_versions_to_backups(root: Path) -> None:
    """
    Keep only the active SHA under versions/; move other version dirs to backups/.
    No-op if active.json is missing or has no valid sha.
    """
    data = read_active(root)
    hist = history_from_active(data)
    if not hist:
        return
    active_sha = hist[0]
    vdir = root / "versions"
    if not vdir.is_dir():
        return
    for child in _iter_sha_children(vdir):
        n = child.name.lower()
        if n == active_sha:
            continue
        try:
            _move_into_backup_replace(root, child, n)
        except OSError as e:
            _LOG.warning("migrate_inactive_versions_to_backups: move %s failed: %s", n, e)


def list_version_shas(root: Path) -> list[str]:
    """All installed SHAs (active under versions/ and archives under backups/)."""
    found: set[str] = set()
    for base in (root / "versions", root / "backups"):
        for child in _iter_sha_children(base):
            found.add(child.name.lower())
    return sorted(found)


def migrate_strip_nested_git_all_versions(project_root: Path, root_relative: str) -> int:
    """
    Remove nested ``.git`` under versions/<sha> and backups/<sha>.
    Writes ``.clawcode-vendor-snapshot`` when stripping or when a tree has no .git yet.
    Returns the number of directories that had ``.git`` removed.
    """
    root = vendor_root(project_root, root_relative)
    stripped = 0
    for sub in ("versions", "backups"):
        d = root / sub
        if not d.is_dir():
            continue
        for child in _iter_sha_children(d):
            if (child / ".git").is_dir():
                _strip_vendor_git(child)
                _write_vendor_snapshot_marker(child)
                stripped += 1
            elif not (child / _VENDOR_SNAPSHOT_MARKER).is_file() and any(child.iterdir()):
                _write_vendor_snapshot_marker(child)
    return stripped


def ensure_clone(owner: str, repo: str, sha: str, dest: Path) -> tuple[bool, str]:
    """
    Materialize ``dest`` as a git checkout of ``sha`` (full SHA recommended).
    Returns (ok, message).
    """
    marker = dest / _VENDOR_SNAPSHOT_MARKER
    if dest.is_dir():
        if marker.is_file():
            return True, "already exists"
        if (dest / ".git").is_dir():
            _strip_vendor_git(dest)
            _write_vendor_snapshot_marker(dest)
            return True, "already exists (stripped nested .git)"

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
        _strip_vendor_git(dest)
        _write_vendor_snapshot_marker(dest)
        return True, "cloned"
    except (OSError, subprocess.TimeoutExpired) as e:
        _rmtree_retry(dest)
        return False, str(e)


def sync_latest(
    project_root: Path,
    owner: str,
    repo: str,
    root_relative: str,
    token: str | None = None,
) -> dict[str, Any]:
    """Fetch main SHA from GitHub; materialize under versions/<sha>; archive prior active in backups/."""
    sha = fetch_main_sha(owner, repo, token=token)
    if not sha or len(sha) < 40:
        return {"ok": False, "error": "could not resolve full main SHA from GitHub"}
    new_sha = sha.lower()
    root = vendor_root(project_root, root_relative)
    migrate_inactive_versions_to_backups(root)
    prev = read_active(root)
    old_sha = (prev.get("sha") or "").strip().lower() if prev else ""
    old_hist = history_from_active(prev)

    versions_new = root / "versions" / new_sha
    backups_new = root / "backups" / new_sha

    if backups_new.is_dir() and not versions_new.is_dir():
        (root / "versions").mkdir(parents=True, exist_ok=True)
        shutil.move(str(backups_new), str(versions_new))
        msg = "restored from backups"
    else:
        ok, msg = ensure_clone(owner, repo, new_sha, versions_new)
        if not ok:
            return {"ok": False, "error": msg}

    if old_sha and old_sha != new_sha:
        old_path = root / "versions" / old_sha
        if old_path.is_dir():
            try:
                _move_into_backup_replace(root, old_path, old_sha)
            except OSError as e:
                return {"ok": False, "error": f"archive previous version failed: {e}"}

    if not old_sha:
        new_hist = [new_sha]
    elif old_sha == new_sha:
        new_hist = old_hist if old_hist and old_hist[0] == new_sha else [new_sha]
    else:
        tail = [h for h in old_hist if h not in (new_sha, old_sha)]
        new_hist = [new_sha, old_sha] + tail

    write_active(root, new_sha, new_hist)
    return {"ok": True, "sha": new_sha, "message": msg, "path": str(versions_new)}


def rollback_to_previous(project_root: Path, root_relative: str) -> dict[str, Any]:
    """Archive current versions/<sha> to backups/, restore previous SHA from backups if needed."""
    root = vendor_root(project_root, root_relative)
    migrate_inactive_versions_to_backups(root)
    data = read_active(root)
    hist = history_from_active(data)
    if len(hist) < 2:
        return {"ok": False, "error": "no previous version"}
    current, target = hist[0], hist[1]

    v_cur = root / "versions" / current
    if v_cur.is_dir():
        try:
            _move_into_backup_replace(root, v_cur, current)
        except OSError as e:
            return {"ok": False, "error": f"archive current version failed: {e}"}

    v_tgt = root / "versions" / target
    b_tgt = root / "backups" / target
    if not v_tgt.is_dir():
        if b_tgt.is_dir():
            (root / "versions").mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(b_tgt), str(v_tgt))
            except OSError as e:
                return {"ok": False, "error": f"restore previous version failed: {e}"}
        else:
            return {"ok": False, "error": f"target version not found: {target}"}

    write_active(root, target, hist[1:])
    return {"ok": True, "sha": target}
