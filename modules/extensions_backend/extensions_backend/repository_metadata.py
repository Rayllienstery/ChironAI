"""GitHub repository metadata client for extension details and versions."""

from __future__ import annotations

from dataclasses import dataclass
import html
import re
from typing import Any
from urllib.parse import quote, urlparse

import requests


_SAFE_GITHUB_SLUG_PART_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,98}[A-Za-z0-9]$|^[A-Za-z0-9]$")


@dataclass(frozen=True)
class GitHubRepositoryRef:
    owner: str
    name: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"


class GitHubExtensionRepositoryClient:
    """Server-side GitHub metadata reader for extension repositories."""

    def __init__(self, *, token: str | None = None, timeout: int = 30) -> None:
        self._timeout = timeout
        self._headers = {"Accept": "application/vnd.github+json"}
        if token:
            self._headers["Authorization"] = f"Bearer {token}"

    def readme(self, repository: str, *, ref: str | None = None) -> dict[str, Any]:
        repo = self._parse_repository(repository)
        params = {"ref": ref} if ref else None
        response = requests.get(
            f"https://api.github.com/repos/{repo.slug}/readme",
            headers={**self._headers, "Accept": "application/vnd.github.raw"},
            params=params,
            timeout=self._timeout,
        )
        response.raise_for_status()
        markdown = response.text
        return {
            "repository": repo.slug,
            "ref": ref or "",
            "markdown": markdown,
            "sanitized_html": sanitize_readme_markdown(markdown),
        }

    def releases(self, repository: str) -> list[dict[str, Any]]:
        repo = self._parse_repository(repository)
        response = requests.get(
            f"https://api.github.com/repos/{repo.slug}/releases",
            headers=self._headers,
            timeout=self._timeout,
        )
        response.raise_for_status()
        raw = response.json()
        if not isinstance(raw, list):
            return []
        return [self._release_to_version(repo, item, latest=False) for item in raw if isinstance(item, dict)]

    def latest_release(self, repository: str) -> dict[str, Any]:
        repo = self._parse_repository(repository)
        response = requests.get(
            f"https://api.github.com/repos/{repo.slug}/releases/latest",
            headers=self._headers,
            timeout=self._timeout,
        )
        response.raise_for_status()
        raw = response.json()
        if not isinstance(raw, dict):
            raise ValueError("GitHub latest release response must be an object")
        return self._release_to_version(repo, raw, latest=True)

    def tags(self, repository: str) -> list[dict[str, Any]]:
        repo = self._parse_repository(repository)
        response = requests.get(
            f"https://api.github.com/repos/{repo.slug}/tags",
            headers=self._headers,
            timeout=self._timeout,
        )
        response.raise_for_status()
        raw = response.json()
        if not isinstance(raw, list):
            return []
        out: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            commit = item.get("commit") if isinstance(item.get("commit"), dict) else {}
            if name:
                out.append(
                    {
                        "version": name,
                        "ref": name,
                        "target_kind": "tag",
                        "commit_sha": str(commit.get("sha") or ""),
                        "archive_url": self.archive_url(repository, ref=name),
                        "provenance_level": "github_tag_archive",
                    }
                )
        return out

    def archive_url(self, repository: str, *, ref: str) -> str:
        repo = self._parse_repository(repository)
        safe_ref = quote(str(ref or "").strip(), safe="")
        if not safe_ref:
            raise ValueError("ref is required")
        return f"https://github.com/{repo.slug}/archive/{safe_ref}.zip"

    def _release_to_version(self, repo: GitHubRepositoryRef, item: dict[str, Any], *, latest: bool) -> dict[str, Any]:
        tag = str(item.get("tag_name") or "").strip()
        assets = item.get("assets") if isinstance(item.get("assets"), list) else []
        asset_url = ""
        digest = ""
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            candidate = str(asset.get("browser_download_url") or "").strip()
            if candidate.endswith(".zip"):
                asset_url = candidate
                digest = str(asset.get("digest") or "").removeprefix("sha256:")
                break
        return {
            "version": tag,
            "ref": tag,
            "target_kind": "release",
            "release_url": str(item.get("html_url") or ""),
            "archive_url": asset_url or f"https://github.com/{repo.slug}/archive/{quote(tag, safe='')}.zip",
            "digest": digest,
            "provenance_level": "github_release_asset" if asset_url else "github_tag_archive",
            "published_at": str(item.get("published_at") or ""),
            "is_latest": latest,
            "is_prerelease": bool(item.get("prerelease", False)),
        }

    def _parse_repository(self, repository: str) -> GitHubRepositoryRef:
        raw = str(repository or "").strip().removesuffix(".git")
        parsed = urlparse(raw)
        if parsed.scheme:
            if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != "github.com":
                raise ValueError("only github.com repositories are supported")
            parts = [part for part in parsed.path.strip("/").split("/") if part]
        else:
            parts = [part for part in raw.strip("/").split("/") if part]
        if len(parts) != 2:
            raise ValueError("GitHub repository must be owner/name or https://github.com/owner/name")
        owner, name = parts[0], parts[1]
        for label, value in (("owner", owner), ("name", name)):
            if not _SAFE_GITHUB_SLUG_PART_RE.match(value):
                raise ValueError(
                    f"GitHub repository {label} {value!r} contains invalid characters; "
                    "only letters, digits, hyphens, underscores, and dots are permitted"
                )
            if value in {".", ".."}:
                raise ValueError(f"GitHub repository {label} must not be '.' or '..'")
        return GitHubRepositoryRef(owner=owner, name=name)


_UNSAFE_MD_LINK_RE = re.compile(r"(!?\[[^\]]*\]\()(?P<url>[^)]+)(\))", re.IGNORECASE)


def sanitize_readme_markdown(markdown: str) -> str:
    """Return escaped, display-safe HTML for README previews.

    Pipeline:
    1. Strip HTML comments (``<!-- ... -->``) with DOTALL so multi-line comments
       are removed before tag stripping.
    2. Strip raw HTML tags with DOTALL so multi-line tags like
       ``<script\\ntype="text/javascript">`` are also removed.
    3. Replace unsafe markdown link/image URLs with a placeholder — safe URLs
       (http/https/#) are kept as-is; everything else is removed.
    4. HTML-escape the entire result once so the final ``<pre>`` block is safe.

    The escaping in step 4 is the single escape point; ``_safe_link`` must NOT
    pre-escape its return value, otherwise characters like ``&`` would be
    double-escaped (``&`` → ``&amp;`` → ``&amp;amp;``).
    """

    def _safe_link(match: re.Match[str]) -> str:
        prefix = match.group(1)
        url = match.group("url").strip().strip("'\"")
        suffix = match.group(3)
        if url.lower().startswith(("http://", "https://", "#")):
            return f"{prefix}{url}{suffix}"
        return f"{prefix}unsafe-link-removed{suffix}"

    raw = markdown or ""
    # Step 1: remove HTML comments (<!--  -->), including multi-line.
    cleaned = re.sub(r"<!--.*?-->", "", raw, flags=re.DOTALL)
    # Step 2: remove HTML tags, including those that span lines.
    cleaned = re.sub(r"<[^>]+>", "", cleaned, flags=re.DOTALL)
    # Step 3: neutralise unsafe markdown links/images.
    cleaned = _UNSAFE_MD_LINK_RE.sub(_safe_link, cleaned)
    return "<pre>" + html.escape(cleaned, quote=False) + "</pre>"
