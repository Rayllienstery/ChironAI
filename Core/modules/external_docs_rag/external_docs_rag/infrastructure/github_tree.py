"""
List markdown files in a GitHub repo up to a given depth (path segments).

Uses GitHub Git Tree API: resolve ref to tree SHA, then get recursive tree,
filter by .md and path depth.
"""

from __future__ import annotations

try:
    import requests
except ImportError:
    requests = None  # type: ignore

GITHUB_API_COMMIT = "https://api.github.com/repos/{owner}/{repo}/commits/{ref}"
GITHUB_API_TREE = "https://api.github.com/repos/{owner}/{repo}/git/trees/{tree_sha}"
USER_AGENT = "ExternalDocsRAG/1.0"

RAW_URL_TEMPLATE = "https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"


def list_markdown_paths(
    owner: str,
    repo: str,
    ref: str,
    max_depth: int = 3,
) -> list[str]:
    """
    List paths of all .md files in the repo at ref, with path depth <= max_depth.

    Path depth = number of path segments (e.g. "a/b/c.md" has depth 3).
    So max_depth=3 allows "README.md", "a/b.md", "a/b/c.md".

    Returns list of paths (e.g. ["README.md", "Documentation/Usage.md"]).
    """
    if not requests:
        return []
    # Resolve ref to tree SHA
    try:
        commit_url = GITHUB_API_COMMIT.format(owner=owner, repo=repo, ref=ref)
        resp = requests.get(
            commit_url,
            headers={"Accept": "application/vnd.github.v3+json", "User-Agent": USER_AGENT},
            timeout=15,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        tree_sha = (data.get("commit") or {}).get("tree", {}).get("sha")
        if not tree_sha:
            return []
    except Exception:
        return []

    # Get recursive tree
    try:
        tree_url = GITHUB_API_TREE.format(owner=owner, repo=repo, tree_sha=tree_sha)
        resp = requests.get(
            tree_url,
            params={"recursive": "1"},
            headers={"Accept": "application/vnd.github.v3+json", "User-Agent": USER_AGENT},
            timeout=30,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        tree = data.get("tree") or []
    except Exception:
        return []

    out: list[str] = []
    for item in tree:
        if item.get("type") != "blob":
            continue
        path = (item.get("path") or "").strip()
        if not path.endswith(".md"):
            continue
        # depth = number of segments
        segments = [s for s in path.split("/") if s]
        if len(segments) > max_depth:
            continue
        out.append(path)
    return sorted(out)


def list_markdown_raw_urls(
    owner: str,
    repo: str,
    ref: str,
    max_depth: int = 3,
) -> list[str]:
    """
    List full raw URLs for all .md files in the repo at ref (depth <= max_depth).
    """
    paths = list_markdown_paths(owner, repo, ref, max_depth=max_depth)
    return [RAW_URL_TEMPLATE.format(owner=owner, repo=repo, ref=ref, path=p) for p in paths]


__all__ = ["list_markdown_paths", "list_markdown_raw_urls"]
