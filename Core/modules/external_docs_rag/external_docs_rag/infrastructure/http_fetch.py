"""
HTTP fetch client: fetch URL content with timeout and size limit.
Uses only public HTTP(S); no paid APIs.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from external_docs_rag.domain.entities import FetchedDocument

try:
    import requests
except ImportError:
    requests = None  # type: ignore

DEFAULT_TIMEOUT_SEC = 30
DEFAULT_MAX_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB
ALLOWED_CONTENT_TYPES = (
    "text/plain",
    "text/markdown",
    "text/html",
    "application/json",  # some APIs return JSON with text
)


class HttpFetchClient:
    """Fetch document content from a URL via HTTP GET."""

    def __init__(
        self,
        timeout_sec: int = DEFAULT_TIMEOUT_SEC,
        max_size_bytes: int = DEFAULT_MAX_SIZE_BYTES,
    ) -> None:
        self._timeout = timeout_sec
        self._max_size = max_size_bytes

    def fetch(
        self,
        url: str,
        timeout_sec: int | None = None,
        max_size_bytes: int | None = None,
    ) -> FetchedDocument | None:
        """
        Fetch content from URL. Returns FetchedDocument or None on failure.
        Infers source_id and filename from URL path.
        """
        if requests is None:
            return None
        timeout = timeout_sec if timeout_sec is not None else self._timeout
        max_size = max_size_bytes if max_size_bytes is not None else self._max_size
        try:
            resp = requests.get(
                url,
                timeout=timeout,
                stream=True,
                headers={
                    "User-Agent": "ExternalDocsRAG/1.0",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                },
            )
            resp.raise_for_status()
            content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if not any(ct in content_type for ct in ("text", "application/json")):
                content_type = "text/plain"
            content_length = resp.headers.get("Content-Length")
            if content_length and int(content_length) > max_size:
                return None
            data = b""
            for chunk in resp.iter_content(chunk_size=8192):
                data += chunk
                if len(data) > max_size:
                    return None
            text = data.decode("utf-8", errors="replace")
        except Exception:
            return None
        parsed = urlparse(url)
        path = (parsed.path or "").strip("/")
        filename = path.split("/")[-1] if path else "index"
        source_id = path.split("/")[0] if path else "external"
        return FetchedDocument(
            url=url,
            content=text,
            source_id=source_id,
            filename=filename or "index",
            content_type=content_type,
        )


def normalize_raw_markdown(text: str) -> str:
    """Normalize raw markdown: trim, collapse excessive newlines."""
    if not text:
        return ""
    return re.sub(r"\n{3,}", "\n\n", text.strip())


__all__ = ["HttpFetchClient", "normalize_raw_markdown"]
