"""Extension archive URL validation and safe zip extraction."""

from __future__ import annotations

import re
import shutil
import stat
import tempfile
import zipfile
from hashlib import sha256
from pathlib import Path
from urllib.parse import quote, urlparse

import requests

MAX_EXTENSION_ZIP_BYTES = 500 * 1024 * 1024  # 500 MB hard ceiling
MAX_EXTENSION_ZIP_UNCOMPRESSED_BYTES = 500 * 1024 * 1024  # 500 MB after extraction
MAX_EXTENSION_ZIP_ENTRY_COUNT = 5000
MAX_EXTENSION_ZIP_COMPRESSION_RATIO = 100.0

# Trusted hostnames for extension archive downloads.
TRUSTED_ARCHIVE_HOSTS: frozenset[str] = frozenset(
    {
        "github.com",
        "objects.githubusercontent.com",  # GitHub release asset CDN
        "codeload.github.com",  # GitHub archive download service
        "raw.githubusercontent.com",
    }
)


def github_archive_url(repository: str, ref: str) -> str:
    repo = str(repository or "").strip()
    selected_ref = str(ref or "").strip()
    if not repo or not selected_ref:
        return ""
    parsed = urlparse(repo)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != "github.com":
        return ""
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        return ""
    owner = quote(parts[0], safe="")
    name = quote(parts[1].removesuffix(".git"), safe="")
    safe_ref = quote(selected_ref, safe="")
    return f"https://github.com/{owner}/{name}/archive/{safe_ref}.zip"


def github_raw_asset_url(repository: str, asset_path: str, *, ref: str = "HEAD") -> str:
    repo = str(repository or "").strip()
    rel = str(asset_path or "").strip().replace("\\", "/")
    selected_ref = str(ref or "").strip() or "HEAD"
    if not repo or not rel:
        return ""
    parsed_asset = urlparse(rel)
    if parsed_asset.scheme or parsed_asset.netloc or rel.startswith("/"):
        return ""
    parts = [part for part in rel.split("/") if part]
    if not parts or any(part in {".", ".."} for part in parts):
        return ""
    parsed_repo = urlparse(repo)
    if parsed_repo.scheme not in {"http", "https"} or parsed_repo.netloc.lower() != "github.com":
        return ""
    repo_parts = [part for part in parsed_repo.path.strip("/").split("/") if part]
    if len(repo_parts) < 2:
        return ""
    owner = quote(repo_parts[0], safe="")
    name = quote(repo_parts[1].removesuffix(".git"), safe="")
    safe_ref = quote(selected_ref, safe="")
    safe_path = "/".join(quote(part, safe="") for part in parts)
    return f"https://github.com/{owner}/{name}/raw/{safe_ref}/{safe_path}"


def validate_archive_url(url: str) -> None:
    """Raise ValueError if *url* is not from a trusted archive host."""
    if not url:
        raise ValueError("archive URL is required")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(
            f"archive URL must use http or https scheme, got: {parsed.scheme!r}"
        )
    host = (parsed.hostname or "").lower().strip()
    if not host:
        raise ValueError("archive URL must have a valid hostname")
    if host not in TRUSTED_ARCHIVE_HOSTS:
        raise ValueError(
            f"archive URL host {host!r} is not in the trusted hosts list; "
            "only github.com and its CDN domains are permitted"
        )


def zip_member_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o170000
    return stat.S_ISLNK(mode)


def path_contains_symlink(root: Path, candidate: Path) -> bool:
    """Return True if any existing component from root to candidate is a symlink."""
    try:
        rel = candidate.relative_to(root)
    except ValueError:
        return True
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def install_storage_segment(selected_ref: str) -> str:
    ref = str(selected_ref or "").strip()
    if not ref:
        return ""
    if "/" not in ref and "\\" not in ref and ref not in {".", ".."}:
        return ref
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", ref).strip(".-")[:48] or "ref"
    return f"{normalized}-{sha256(ref.encode('utf-8')).hexdigest()[:12]}"


def download_extension_zip_to_dir(
    url: str,
    target_dir: Path,
    *,
    expected_digest: str = "",
    max_zip_bytes: int | None = None,
    max_uncompressed_bytes: int | None = None,
    max_entry_count: int | None = None,
    max_compression_ratio: float | None = None,
) -> None:
    zip_limit = max_zip_bytes if max_zip_bytes is not None else MAX_EXTENSION_ZIP_BYTES
    uncompressed_limit = (
        max_uncompressed_bytes if max_uncompressed_bytes is not None else MAX_EXTENSION_ZIP_UNCOMPRESSED_BYTES
    )
    entry_limit = max_entry_count if max_entry_count is not None else MAX_EXTENSION_ZIP_ENTRY_COUNT
    compression_limit = (
        max_compression_ratio if max_compression_ratio is not None else MAX_EXTENSION_ZIP_COMPRESSION_RATIO
    )
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    hasher = sha256()
    total_bytes = 0
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
            tmp_path = Path(tmp.name)
            for chunk in resp.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                total_bytes += len(chunk)
                if total_bytes > zip_limit:
                    raise ValueError(
                        f"extension archive exceeds maximum allowed size "
                        f"({zip_limit // (1024 * 1024)} MB): {url}"
                    )
                hasher.update(chunk)
                tmp.write(chunk)
        if expected_digest:
            actual_digest = hasher.hexdigest()
            clean_expected = expected_digest.removeprefix("sha256:")
            if actual_digest != clean_expected:
                raise ValueError(
                    f"extension archive digest mismatch for {url}: "
                    f"expected sha256:{clean_expected}, got sha256:{actual_digest}"
                )
        with zipfile.ZipFile(tmp_path) as zf:
            infos = [info for info in zf.infolist() if info.filename and not info.filename.endswith("/")]
            if len(infos) > entry_limit:
                raise ValueError(
                    f"extension archive contains too many files "
                    f"({len(infos)} > {entry_limit})"
                )
            uncompressed_total = 0
            names = [info.filename.replace("\\", "/") for info in infos]
            for info, name in zip(infos, names, strict=True):
                if zip_member_is_symlink(info):
                    raise ValueError(f"unsafe zip member is a symlink: {name}")
                uncompressed_total += int(info.file_size or 0)
                if uncompressed_total > uncompressed_limit:
                    raise ValueError(
                        f"extension archive expands beyond maximum allowed size "
                        f"({uncompressed_limit // (1024 * 1024)} MB): {url}"
                    )
                if info.file_size and info.compress_size == 0:
                    raise ValueError(f"unsafe zip member has invalid compressed size: {name}")
                if info.file_size and info.compress_size:
                    ratio = float(info.file_size) / float(info.compress_size)
                    if ratio > compression_limit:
                        raise ValueError(f"unsafe zip member compression ratio: {name}")
                parts = [part for part in name.split("/") if part]
                if (
                    not parts
                    or name.startswith("/")
                    or ":" in parts[0]
                    or any(part == ".." for part in parts)
                ):
                    raise ValueError(f"unsafe zip member path: {name}")
            root_prefix = ""
            if names:
                first = names[0].split("/")[0]
                if first and all(name == first or name.startswith(first + "/") for name in names):
                    root_prefix = first + "/"
            if target_dir.exists():
                shutil.rmtree(target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            for info in infos:
                name = info.filename.replace("\\", "/")
                rel = name[len(root_prefix):] if root_prefix and name.startswith(root_prefix) else name
                if not rel:
                    continue
                dest = (target_dir / rel).resolve()
                root = target_dir.resolve()
                try:
                    dest.relative_to(root)
                except ValueError as e:
                    raise ValueError(f"unsafe zip member path: {name}") from e
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, dest.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
