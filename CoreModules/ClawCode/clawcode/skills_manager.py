from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SkillSource:
    type: str  # "git" | "local"
    url: str | None = None
    ref: str | None = None
    subdir: str | None = None
    local_path: str | None = None
    repo_rel_skill_dir: str | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": self.type}
        if self.url is not None:
            out["url"] = self.url
        if self.ref is not None:
            out["ref"] = self.ref
        if self.subdir is not None:
            out["subdir"] = self.subdir
        if self.local_path is not None:
            out["local_path"] = self.local_path
        if self.repo_rel_skill_dir is not None:
            out["repo_rel_skill_dir"] = self.repo_rel_skill_dir
        return out

    @staticmethod
    def from_json(obj: object) -> "SkillSource":
        if not isinstance(obj, dict):
            return SkillSource(type="local", local_path=None)
        return SkillSource(
            type=str(obj.get("type") or "local"),
            url=str(obj.get("url")) if obj.get("url") is not None else None,
            ref=str(obj.get("ref")) if obj.get("ref") is not None else None,
            subdir=str(obj.get("subdir")) if obj.get("subdir") is not None else None,
            local_path=str(obj.get("local_path")) if obj.get("local_path") is not None else None,
            repo_rel_skill_dir=str(obj.get("repo_rel_skill_dir"))
            if obj.get("repo_rel_skill_dir") is not None
            else None,
        )


@dataclass
class SkillRecord:
    id: str
    invocation_name: str
    display_name: str | None
    description: str | None
    source: SkillSource
    installed_path: str
    installed_at: float
    updated_at: float
    source_commit_sha: str | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "invocation_name": self.invocation_name,
            "display_name": self.display_name,
            "description": self.description,
            "source": self.source.to_json(),
            "installed_path": self.installed_path,
            "installed_at": self.installed_at,
            "updated_at": self.updated_at,
        }
        if self.source_commit_sha is not None:
            out["source_commit_sha"] = self.source_commit_sha
        return out

    @staticmethod
    def from_json(obj: object) -> "SkillRecord | None":
        if not isinstance(obj, dict):
            return None
        try:
            raw_sha = obj.get("source_commit_sha")
            sha = str(raw_sha).strip() if raw_sha is not None and str(raw_sha).strip() else None
            return SkillRecord(
                id=str(obj.get("id") or ""),
                invocation_name=str(obj.get("invocation_name") or ""),
                display_name=str(obj.get("display_name")) if obj.get("display_name") is not None else None,
                description=str(obj.get("description")) if obj.get("description") is not None else None,
                source=SkillSource.from_json(obj.get("source")),
                installed_path=str(obj.get("installed_path") or ""),
                installed_at=float(obj.get("installed_at") or 0),
                updated_at=float(obj.get("updated_at") or 0),
                source_commit_sha=sha,
            )
        except Exception:
            return None


_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def _repo_root() -> Path:
    # .../CoreModules/ClawCode/clawcode/skills_manager.py -> repo root is parents[3]
    return Path(__file__).resolve().parents[3]


def default_skills_storage_root() -> Path:
    return _repo_root() / "CoreModules" / "ClawCode" / ".data" / "skills"


def _hash_id(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _sanitize_invocation_name(name: str) -> str:
    raw = (name or "").strip().lower()
    raw = raw.lstrip("/$").strip()
    if not raw:
        return ""
    out = []
    last_sep = False
    for ch in raw:
        if ch.isalnum() or ch in ("-", "_", "."):
            out.append(ch)
            last_sep = False
        elif (ch.isspace() or ch in ("/", "\\")) and not last_sep and out:
            out.append("-")
            last_sep = True
    s = "".join(out).strip("-_.")
    return s


def parse_skill_frontmatter(markdown: str) -> tuple[str | None, str | None]:
    """
    Parse YAML frontmatter from SKILL.md.
    Required by Anthropic skills: name, description.
    We intentionally implement a tiny subset: `key: value` scalars only.
    """
    text = markdown.lstrip("\ufeff")
    if not text.startswith("---"):
        return None, None
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, None
    fm: dict[str, str] = {}
    for i in range(1, min(len(lines), 2000)):
        line = lines[i]
        if line.strip() == "---":
            break
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            fm[k] = v
    name = fm.get("name")
    desc = fm.get("description")
    return (name.strip() if isinstance(name, str) and name.strip() else None,
            desc.strip() if isinstance(desc, str) and desc.strip() else None)


def read_skill_metadata(skill_dir: Path) -> tuple[str | None, str | None, str]:
    skill_md = skill_dir / "SKILL.md"
    contents = skill_md.read_text(encoding="utf-8")
    name, desc = parse_skill_frontmatter(contents)
    invocation = _sanitize_invocation_name(name or skill_dir.name)
    if not invocation or not _NAME_RE.match(invocation):
        invocation = _sanitize_invocation_name(skill_dir.name) or f"skill-{_hash_id(str(skill_dir))}"
    return name, desc, invocation


def _run_git(args: list[str], *, cwd: Path, timeout_s: int = 600) -> None:
    r = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    if r.returncode != 0:
        msg = (r.stderr or r.stdout or "git failed").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {msg}")


def _git_head_sha(repo_dir: Path, *, timeout_s: int = 60) -> str:
    r = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    if r.returncode != 0:
        msg = (r.stderr or r.stdout or "git rev-parse failed").strip()
        raise RuntimeError(f"git rev-parse HEAD failed: {msg}")
    sha = (r.stdout or "").strip()
    if len(sha) < 7:
        raise RuntimeError("git rev-parse HEAD returned empty")
    return sha


def _ensure_repo_checkout(url: str, ref: str | None, *, repos_root: Path) -> tuple[Path, str | None]:
    repos_root.mkdir(parents=True, exist_ok=True)
    repo_id = _hash_id(url)
    repo_dir = repos_root / repo_id
    if not repo_dir.is_dir():
        repo_dir.mkdir(parents=True, exist_ok=True)
        _run_git(["init"], cwd=repo_dir)
        _run_git(["remote", "add", "origin", url], cwd=repo_dir)
    _run_git(["fetch", "--tags", "--prune", "origin"], cwd=repo_dir)
    if ref:
        _run_git(["checkout", "-f", ref], cwd=repo_dir)
        resolved = ref
    else:
        _run_git(["checkout", "-f", "origin/HEAD"], cwd=repo_dir)
        resolved = None
    return repo_dir, resolved


def _discover_skill_dirs(root: Path) -> list[Path]:
    out: list[Path] = []
    if not root.is_dir():
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip nested git artifacts
        if ".git" in dirnames:
            dirnames.remove(".git")
        if "node_modules" in dirnames:
            dirnames.remove("node_modules")
        if "SKILL.md" in filenames:
            out.append(Path(dirpath))
    out.sort(key=lambda p: str(p).lower())
    return out


def install_skills_from_git(
    *,
    url: str,
    ref: str | None = None,
    subdir: str | None = None,
    storage_root: Path | None = None,
) -> list[SkillRecord]:
    storage_root = storage_root or default_skills_storage_root()
    repos_root = storage_root / "repos"
    installed_root = storage_root / "installed"
    repos_root.mkdir(parents=True, exist_ok=True)
    installed_root.mkdir(parents=True, exist_ok=True)

    repo_dir, resolved_ref = _ensure_repo_checkout(url, ref, repos_root=repos_root)
    scan_root = repo_dir
    if subdir:
        scan_root = repo_dir / subdir
    else:
        if (repo_dir / "skills").is_dir():
            scan_root = repo_dir / "skills"
    skill_dirs = _discover_skill_dirs(scan_root)
    if not skill_dirs:
        raise RuntimeError(f"no SKILL.md found under {scan_root}")

    head_sha = _git_head_sha(repo_dir)
    now = time.time()
    records: list[SkillRecord] = []
    for skill_dir in skill_dirs:
        name, desc, invocation = read_skill_metadata(skill_dir)
        repo_rel_dir = str(skill_dir.relative_to(repo_dir)).replace("\\", "/")
        skill_id_seed = f"git:{url}@{resolved_ref or ref or 'HEAD'}:{repo_rel_dir}"
        skill_id = _hash_id(skill_id_seed)
        install_slug = f"{invocation}-{skill_id}"
        install_path = installed_root / install_slug
        if install_path.exists():
            # treat as already installed; still refresh contents from source
            shutil.rmtree(install_path, ignore_errors=True)
        install_path.mkdir(parents=True, exist_ok=True)
        _copy_dir(skill_dir, install_path)
        records.append(
            SkillRecord(
                id=skill_id,
                invocation_name=invocation,
                display_name=name,
                description=desc,
                source=SkillSource(
                    type="git",
                    url=url,
                    ref=resolved_ref or ref,
                    subdir=subdir,
                    repo_rel_skill_dir=repo_rel_dir,
                ),
                installed_path=str(install_path),
                installed_at=now,
                updated_at=now,
                source_commit_sha=head_sha,
            )
        )
    return records


def update_skill_from_source(record: SkillRecord, *, storage_root: Path | None = None) -> SkillRecord:
    storage_root = storage_root or default_skills_storage_root()
    src = record.source
    if src.type != "git" or not src.url or not src.repo_rel_skill_dir:
        raise RuntimeError("only git-installed skills can be updated in v1")
    repos_root = storage_root / "repos"
    repo_dir, resolved_ref = _ensure_repo_checkout(src.url, src.ref, repos_root=repos_root)
    head_sha = _git_head_sha(repo_dir)
    skill_dir = repo_dir / src.repo_rel_skill_dir
    if not (skill_dir / "SKILL.md").is_file():
        raise RuntimeError(f"missing SKILL.md in repo at {src.repo_rel_skill_dir}")
    install_path = Path(record.installed_path)
    if install_path.exists():
        shutil.rmtree(install_path, ignore_errors=True)
    install_path.mkdir(parents=True, exist_ok=True)
    _copy_dir(skill_dir, install_path)
    name, desc, invocation = read_skill_metadata(skill_dir)
    updated_at = time.time()
    return SkillRecord(
        id=record.id,
        invocation_name=invocation,
        display_name=name,
        description=desc,
        source=SkillSource(
            type="git",
            url=src.url,
            ref=resolved_ref or src.ref,
            subdir=src.subdir,
            repo_rel_skill_dir=src.repo_rel_skill_dir,
        ),
        installed_path=str(install_path),
        installed_at=record.installed_at or updated_at,
        updated_at=updated_at,
        source_commit_sha=head_sha,
    )


def resolve_remote_head_sha(
    url: str,
    ref: str | None = None,
    *,
    storage_root: Path | None = None,
) -> str:
    storage_root = storage_root or default_skills_storage_root()
    repos_root = storage_root / "repos"
    repo_dir, _resolved = _ensure_repo_checkout(url, ref, repos_root=repos_root)
    return _git_head_sha(repo_dir)


def _norm_ref_subdir(ref: str | None, subdir: str | None) -> tuple[str | None, str | None]:
    r = ref.strip() if isinstance(ref, str) and ref.strip() else None
    s = subdir.strip() if isinstance(subdir, str) and subdir.strip() else None
    return r, s


def source_matches_install_key(
    src: SkillSource,
    *,
    url: str,
    ref: str | None,
    subdir: str | None,
) -> bool:
    if src.type != "git" or not src.url:
        return False
    if src.url.strip() != (url or "").strip():
        return False
    sr, ss = _norm_ref_subdir(src.ref, src.subdir)
    rr, rs = _norm_ref_subdir(ref, subdir)
    return sr == rr and ss == rs


def update_skills_by_source(
    *,
    url: str,
    ref: str | None = None,
    subdir: str | None = None,
    registry: dict[str, SkillRecord],
    storage_root: Path | None = None,
) -> list[SkillRecord]:
    """Refresh every git skill whose source matches url/ref/subdir (one fetch + checkout)."""
    storage_root = storage_root or default_skills_storage_root()
    matching = [
        rec
        for rec in registry.values()
        if source_matches_install_key(rec.source, url=url, ref=ref, subdir=subdir)
    ]
    if not matching:
        return []
    repos_root = storage_root / "repos"
    repo_dir, resolved_ref = _ensure_repo_checkout(url, ref, repos_root=repos_root)
    head_sha = _git_head_sha(repo_dir)
    now = time.time()
    updated: list[SkillRecord] = []
    for record in matching:
        src = record.source
        if not src.repo_rel_skill_dir:
            raise RuntimeError(f"skill {record.id} has no repo_rel_skill_dir")
        skill_dir = repo_dir / src.repo_rel_skill_dir
        if not (skill_dir / "SKILL.md").is_file():
            raise RuntimeError(f"missing SKILL.md in repo at {src.repo_rel_skill_dir}")
        install_path = Path(record.installed_path)
        if install_path.exists():
            shutil.rmtree(install_path, ignore_errors=True)
        install_path.mkdir(parents=True, exist_ok=True)
        _copy_dir(skill_dir, install_path)
        name, desc, invocation = read_skill_metadata(skill_dir)
        updated_rec = SkillRecord(
            id=record.id,
            invocation_name=invocation,
            display_name=name,
            description=desc,
            source=SkillSource(
                type="git",
                url=src.url,
                ref=resolved_ref or ref,
                subdir=src.subdir,
                repo_rel_skill_dir=src.repo_rel_skill_dir,
            ),
            installed_path=str(install_path),
            installed_at=record.installed_at or now,
            updated_at=now,
            source_commit_sha=head_sha,
        )
        updated.append(updated_rec)
    return updated


def delete_skills_by_source(
    *,
    url: str,
    ref: str | None = None,
    subdir: str | None = None,
    registry: dict[str, SkillRecord],
) -> list[str]:
    """Remove registry entries and installed dirs for matching git source key."""
    deleted_ids: list[str] = []
    for sid in list(registry.keys()):
        rec = registry.get(sid)
        if rec is None or not source_matches_install_key(rec.source, url=url, ref=ref, subdir=subdir):
            continue
        registry.pop(sid, None)
        deleted_ids.append(sid)
        try:
            p = Path(str(rec.installed_path))
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
        except Exception:
            pass
    return deleted_ids


def _copy_dir(src: Path, dst: Path) -> None:
    for entry in src.iterdir():
        if entry.name == ".git":
            continue
        target = dst / entry.name
        if entry.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            _copy_dir(entry, target)
        else:
            shutil.copy2(entry, target)

