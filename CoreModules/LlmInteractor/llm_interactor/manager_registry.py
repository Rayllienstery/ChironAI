"""Registry metadata enrichment and GitHub extension details."""

from __future__ import annotations

from typing import Any, Callable


def enrich_registry_entry(
    entry: dict[str, Any],
    *,
    blocklist_match_fn: Callable[[dict[str, Any]], dict[str, Any]],
    github_raw_asset_url_fn: Callable[..., str],
) -> dict[str, Any]:
    out = dict(entry)
    if not str(out.get("icon_url") or "").strip():
        out["icon_url"] = github_raw_asset_url_fn(
            str(out.get("repository") or out.get("repo_url") or ""),
            str(out.get("icon") or ""),
            ref=str(out.get("default_ref") or "HEAD"),
        )
    match = blocklist_match_fn(out)
    if match.get("matched"):
        out["blocklist"] = match
        out["visibility"] = "blocked"
    return out


def load_registry_entries(
    registry_client: Any,
    *,
    blocklist_match_fn: Callable[[dict[str, Any]], dict[str, Any]],
    github_raw_asset_url_fn: Callable[..., str],
) -> list[dict[str, Any]]:
    return [
        enrich_registry_entry(
            entry,
            blocklist_match_fn=blocklist_match_fn,
            github_raw_asset_url_fn=github_raw_asset_url_fn,
        )
        for entry in registry_client.load()
    ]


def registry_diagnostics_payload(
    registry_client: Any,
    *,
    registry_entries_fn: Callable[[], list[dict[str, Any]]],
) -> dict[str, Any]:
    loader = getattr(registry_client, "load_with_diagnostics", None)
    if callable(loader):
        result = loader()
        return {
            "registry_url": result.registry_url,
            "diagnostics": [item.to_dict() for item in result.diagnostics],
            "entries_count": len(result.entries),
        }
    return {
        "registry_url": getattr(registry_client, "registry_url", None),
        "diagnostics": [],
        "entries_count": len(registry_entries_fn()),
    }


def fetch_extension_details(
    extension_id: str,
    *,
    registry_entries_fn: Callable[[], list[dict[str, Any]]],
    repository_client: Any | None,
    ref: str | None = None,
) -> dict[str, Any]:
    ext_id = str(extension_id or "").strip()
    if not ext_id:
        raise ValueError("extension_id is required")
    entry = next(
        (item for item in registry_entries_fn() if str(item.get("id") or "").strip() == ext_id),
        None,
    )
    if entry is None:
        raise ValueError(f"Extension '{ext_id}' not found in registry")
    repository = str(entry.get("repository") or entry.get("repo_url") or "").strip()
    details: dict[str, Any] = {
        "entry": dict(entry),
        "versions": [],
        "latest": {},
        "readme": {"extension_id": ext_id, "repository": repository, "markdown": "", "sanitized_html": ""},
        "publisher": dict(entry.get("publisher") or {}) if isinstance(entry.get("publisher"), dict) else {},
    }
    if not repository or repository_client is None:
        return details
    errors: list[str] = []
    try:
        latest = repository_client.latest_release(repository)
        details["latest"] = latest
    except Exception as e:
        latest = {}
        errors.append(f"latest_release: {type(e).__name__}: {e}")
    try:
        releases = repository_client.releases(repository)
    except Exception as e:
        releases = []
        errors.append(f"releases: {type(e).__name__}: {e}")
    try:
        tags = repository_client.tags(repository)
    except Exception as e:
        tags = []
        errors.append(f"tags: {type(e).__name__}: {e}")
    versions_by_ref: dict[str, dict[str, Any]] = {}
    for row in [latest, *releases, *tags]:
        if not isinstance(row, dict):
            continue
        key = str(row.get("ref") or row.get("version") or "").strip()
        if key and key not in versions_by_ref:
            versions_by_ref[key] = dict(row)
    details["versions"] = list(versions_by_ref.values())
    readme_ref = str(ref or (latest or {}).get("ref") or (latest or {}).get("version") or "").strip() or None
    try:
        readme = repository_client.readme(repository, ref=readme_ref)
        details["readme"] = {"extension_id": ext_id, **readme}
    except Exception as e:
        errors.append(f"readme: {type(e).__name__}: {e}")
        details["readme"] = {
            "extension_id": ext_id,
            "repository": repository,
            "ref": readme_ref or "",
            "markdown": "",
            "sanitized_html": "",
            "error": f"{type(e).__name__}: {e}",
        }
    if errors:
        details["warnings"] = errors
    return details
