from __future__ import annotations

import pytest

from extensions_backend import GitHubExtensionRepositoryClient
from extensions_backend.repository_metadata import sanitize_readme_markdown


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
                "assets": [
                    {
                        "browser_download_url": "https://github.com/acme/ext/releases/download/v1.2.3/ext.zip",
                        "digest": "sha256:abc123",
                    }
                ],
            }

    monkeypatch.setattr("requests.get", lambda url, headers, timeout, params=None: _Response())

    client = GitHubExtensionRepositoryClient(token="server-side-token")
    release = client.latest_release("https://github.com/acme/ext")
    readme = client.readme("acme/ext", ref="v1.2.3")

    assert release["version"] == "v1.2.3"
    assert release["archive_url"].endswith("/ext.zip")
    assert release["digest"] == "abc123"
    assert release["provenance_level"] == "github_release_asset"
    assert readme["markdown"] == "# Readme"
    assert readme["sanitized_html"] == "<pre># Readme</pre>"


def test_github_repository_client_rejects_non_github_repositories() -> None:
    client = GitHubExtensionRepositoryClient()

    with pytest.raises(ValueError, match="only github.com"):
        client.latest_release("https://example.com/acme/ext")


def test_readme_sanitizer_strips_html_and_unsafe_urls() -> None:
    html = sanitize_readme_markdown("<script>alert(1)</script>[x](javascript:alert(1))![p](file:///tmp/a.png)")

    assert "<script" not in html
    assert "javascript:" not in html
    assert "file://" not in html
    assert "unsafe-link-removed" in html


def test_readme_sanitizer_does_not_double_escape_ampersands() -> None:
    result = sanitize_readme_markdown("A & B [link](https://example.com?a=1&b=2) <tag>")

    assert "&amp;amp;" not in result, "double-escaping detected: & → &amp; → &amp;amp;"
    assert "&amp;" in result, "& should be escaped exactly once to &amp;"
    assert "https://example.com?a=1&amp;b=2" in result, "URL ampersand should be escaped once"
    assert "<tag>" not in result, "raw HTML tag must be stripped"


def test_readme_sanitizer_preserves_safe_https_links() -> None:
    result = sanitize_readme_markdown("[Docs](https://docs.example.com/page#section)")

    assert "unsafe-link-removed" not in result
    assert "https://docs.example.com/page#section" in result


def test_readme_sanitizer_removes_unsafe_protocol_links() -> None:
    result = sanitize_readme_markdown("[bad](data:text/html,<h1>xss</h1>) [ok](https://ok.example.com)")

    assert "data:text/html" not in result
    assert "unsafe-link-removed" in result
    assert "https://ok.example.com" in result
