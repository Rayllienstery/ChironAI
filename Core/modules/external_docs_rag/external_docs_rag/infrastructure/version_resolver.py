from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

try:
    import requests
except ImportError:
    requests = None  # type: ignore

from external_docs_rag.domain.entities import ResolvedVersion, VersionConstraint

GITHUB_API_TAGS = "https://api.github.com/repos/{full_name}/tags"
USER_AGENT = "ExternalDocsRAG/VersionResolver/1.0"


_SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


@dataclass(frozen=True)
class _SemVer:
    major: int
    minor: int
    patch: int
    raw_tag: str


def _parse_semver_tag(tag: str) -> Optional[_SemVer]:
    """
    Parse a Git tag like '5.8.1' or 'v5.8.1' into a semantic version.
    Non-matching tags are ignored.
    """
    m = _SEMVER_RE.match(tag.strip())
    if not m:
        return None
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return _SemVer(major=major, minor=minor, patch=patch, raw_tag=tag)


def _load_all_semver_tags(full_name: str) -> list[_SemVer]:
    """
    Load all tags from GitHub releases/tags API and keep only semantic versions.
    """
    if not requests:
        return []
    try:
        tags: list[_SemVer] = []
        page = 1
        while True:
            resp = requests.get(
                GITHUB_API_TAGS.format(full_name=full_name),
                params={"per_page": 100, "page": page},
                headers={"Accept": "application/vnd.github.v3+json", "User-Agent": USER_AGENT},
                timeout=10,
            )
            if resp.status_code != 200:
                break
            data = resp.json() or []
            if not data:
                break
            for item in data:
                name = (item.get("name") or "").strip()
                ver = _parse_semver_tag(name)
                if ver:
                    tags.append(ver)
            if len(data) < 100:
                break
            page += 1
        return tags
    except Exception:
        return []


def _select_best_matching(
    tags: Iterable[_SemVer],
    constraint: VersionConstraint,
) -> Optional[_SemVer]:
    """
    Apply VersionConstraint to the list of semantic tags and select the best match:
    - major only   -> max patch within that major (any minor/patch)
    - major+minor  -> max patch within that major/minor
    - exact        -> exact major/minor/patch if exists
    - latest       -> global max by (major, minor, patch)
    """
    candidates = list(tags)
    if not candidates:
        return None

    if constraint.is_latest_requested and constraint.major is None:
        # Latest overall
        return max(candidates, key=lambda v: (v.major, v.minor, v.patch))

    # Filter by major/minor when provided
    if constraint.major is not None:
        candidates = [v for v in candidates if v.major == constraint.major]
    if constraint.minor is not None:
        candidates = [v for v in candidates if v.minor == constraint.minor]

    if not candidates:
        return None

    if constraint.patch is not None and not constraint.is_latest_requested:
        for v in candidates:
            if v.patch == constraint.patch:
                return v

    # Fallback: latest in the filtered set
    return max(candidates, key=lambda v: (v.major, v.minor, v.patch))


def resolve_version_for_framework(
    full_name: str,
    constraint: VersionConstraint,
    repo_url: str,
) -> Optional[ResolvedVersion]:
    """
    Resolve a concrete framework version for the given GitHub repo and VersionConstraint.

    full_name: 'owner/repo' on GitHub, e.g. 'Alamofire/Alamofire'.
    repo_url:  canonical HTTPS URL to the repo (for metadata).
    """
    tags = _load_all_semver_tags(full_name)
    best = _select_best_matching(tags, constraint)
    if not best:
        return None
    return ResolvedVersion(
        framework=constraint.framework,
        major=best.major,
        minor=best.minor,
        patch=best.patch,
        tag=best.raw_tag.lstrip("v"),
        repo_url=repo_url,
    )


__all__ = ["resolve_version_for_framework"]

