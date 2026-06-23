from __future__ import annotations

import stat
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from llm_interactor.manager_archive import (
    TRUSTED_ARCHIVE_HOSTS,
    download_extension_zip_to_dir,
    github_archive_url,
    github_raw_asset_url,
    install_storage_segment,
    path_contains_symlink,
    validate_archive_url,
    zip_member_is_symlink,
)


def test_github_archive_url_builds_github_zip_link() -> None:
    url = github_archive_url("https://github.com/acme/widget", "v1.2.3")
    assert url == "https://github.com/acme/widget/archive/v1.2.3.zip"


def test_github_archive_url_rejects_non_github_repo() -> None:
    assert github_archive_url("https://example.com/acme/widget", "main") == ""


def test_github_raw_asset_url_builds_raw_link() -> None:
    url = github_raw_asset_url(
        "https://github.com/acme/widget",
        "icons/logo.svg",
        ref="main",
    )
    assert url == "https://github.com/acme/widget/raw/main/icons/logo.svg"


def test_validate_archive_url_rejects_untrusted_host() -> None:
    with pytest.raises(ValueError, match="not in the trusted hosts list"):
        validate_archive_url("https://evil.example.com/archive.zip")


def test_validate_archive_url_accepts_github_cdn() -> None:
    for host in TRUSTED_ARCHIVE_HOSTS:
        validate_archive_url(f"https://{host}/owner/repo/archive/main.zip")


def test_install_storage_segment_preserves_simple_ref() -> None:
    assert install_storage_segment("1.0.0") == "1.0.0"


def test_install_storage_segment_hashes_complex_ref() -> None:
    segment = install_storage_segment("feature/my-branch")
    assert segment != "feature/my-branch"
    assert "/" not in segment


def test_zip_member_is_symlink_detects_symlink_mode() -> None:
    info = zipfile.ZipInfo("link.txt")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    assert zip_member_is_symlink(info) is True


def test_path_contains_symlink_detects_symlink_component(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    candidate = root / "nested" / "file.txt"
    candidate.parent.mkdir(parents=True)

    def _is_symlink(self: Path) -> bool:
        return self == root / "nested"

    monkeypatch.setattr(Path, "is_symlink", _is_symlink, raising=False)
    assert path_contains_symlink(root, candidate) is True
    assert path_contains_symlink(root, root / "other" / "file.txt") is False


def test_download_extension_zip_rejects_path_traversal_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Response:
        def __init__(self, content: bytes) -> None:
            self._content = content

        def raise_for_status(self) -> None:
            return None

        def iter_content(self, chunk_size: int = 65536):
            _ = chunk_size
            yield self._content

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../evil.txt", "bad")
    monkeypatch.setattr("requests.get", lambda url, timeout=60, stream=False: _Response(buf.getvalue()))

    with pytest.raises(ValueError, match="unsafe zip member path"):
        download_extension_zip_to_dir(
            "https://github.com/acme/widget/archive/main.zip",
            tmp_path / "out",
        )

    assert not (tmp_path / "evil.txt").exists()
