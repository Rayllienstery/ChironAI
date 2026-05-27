from __future__ import annotations

import pytest

from extensions_backend import GitHubExtensionRepositoryClient


def test_github_repository_client_maps_latest_release(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Response:
        text = "# Readme"

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "tag_name": "v1.2.3",
                "html_url": "https://github.com/acme/ext/releases/tag/v1.2.3",
                "published_at": "2026-05-27T00:00:00Z",
                "prerelease": False,
                "assets": [{"browser_download_url": "https://github.com/acme/ext/releases/download/v1.2.3/ext.zip"}],
            }

    monkeypatch.setattr("requests.get", lambda url, headers, timeout, params=None: _Response())

    client = GitHubExtensionRepositoryClient(token="server-side-token")
    release = client.latest_release("https://github.com/acme/ext")
    readme = client.readme("acme/ext", ref="v1.2.3")

    assert release["version"] == "v1.2.3"
    assert release["archive_url"].endswith("/ext.zip")
    assert release["provenance_level"] == "github_release_asset"
    assert readme["markdown"] == "# Readme"


def test_github_repository_client_rejects_non_github_repositories() -> None:
    client = GitHubExtensionRepositoryClient()

    with pytest.raises(ValueError, match="only github.com"):
        client.latest_release("https://example.com/acme/ext")

