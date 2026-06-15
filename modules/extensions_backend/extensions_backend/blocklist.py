"""Emergency blocklist policy for repository-backed extensions."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

DEFAULT_BLOCKLIST_PATH = "extensions/registry/blocklist.json"
_MAX_BLOCKLIST_RESPONSE_BYTES = 1 * 1024 * 1024  # 1 MB — protect against malicious/runaway URL
_BLOCKLIST_TTL_SEC = 300.0  # 5-minute TTL for remote URLs; local files reload on TTL too

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExtensionBlocklistMatch:
    matched: bool
    reason: str = ""
    source: str = ""
    matched_on: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched": bool(self.matched),
            "reason": self.reason,
            "source": self.source,
            "matched_on": self.matched_on,
        }


class ExtensionBlocklistPolicy:
    """Loads and evaluates local or remote emergency blocklist rules.

    Rules are cached with a TTL (default 5 minutes).  On TTL expiry the rules
    are refreshed synchronously on the next ``match()`` / ``load()`` call.
    Thread-safe: a lock prevents concurrent re-fetches.
    """

    def __init__(
        self,
        blocklist_url: str | None = None,
        *,
        project_root: Path | None = None,
        fallback_url: str | None = None,
        timeout_sec: float = 15.0,
        ttl_sec: float = _BLOCKLIST_TTL_SEC,
    ) -> None:
        self._project_root = project_root or Path.cwd()
        self._blocklist_url = blocklist_url or DEFAULT_BLOCKLIST_PATH
        self._fallback_url = fallback_url or ""
        self._timeout_sec = timeout_sec
        self._ttl_sec = ttl_sec
        self._rules: list[dict[str, Any]] | None = None
        self._loaded_at: float = 0.0
        # True only when every source (primary + fallback) failed on the first
        # ever load attempt.  Callers can query this to fail closed.
        self._initial_load_failed: bool = False
        # _lock: brief atomic reads/writes of _rules/_loaded_at state.
        # _fetch_lock: serialises HTTP fetches so only one thread goes remote
        # at a time.  _lock is NEVER held during a network call — keeping it
        # free lets concurrent readers (e.g. UI threads) access stale-but-valid
        # cached rules without blocking on the in-flight HTTP request.
        self._lock = threading.Lock()
        self._fetch_lock = threading.Lock()

    @property
    def blocklist_url(self) -> str:
        return self._blocklist_url

    @property
    def initial_load_failed(self) -> bool:
        """True when every source failed on the very first load attempt.

        Callers that enforce fail-closed policy should treat this as a signal
        to reject installs/enables until the blocklist can be loaded.
        """
        with self._lock:
            return self._initial_load_failed

    def load(self) -> list[dict[str, Any]]:
        """Return the current list of blocklist rules, reloading if the TTL has expired.

        The network fetch is performed *outside* any lock so that background
        bootstrap threads never block UI threads that are reading stale-but-valid
        cached rules at the same time.
        """
        now = time.monotonic()

        # Fast path: cache is still valid — brief lock, no I/O.
        with self._lock:
            if self._rules is not None and (now - self._loaded_at) < self._ttl_sec:
                return [dict(rule) for rule in self._rules]

        # Slow path: cache is stale or uninitialized.  Serialise fetches with
        # _fetch_lock, but do NOT hold _lock during the HTTP call so that other
        # threads can still read the (possibly stale) rules without waiting.
        with self._fetch_lock:
            # Re-check under _lock after acquiring _fetch_lock — another thread
            # may have already refreshed the cache while we were waiting.
            now = time.monotonic()
            with self._lock:
                if self._rules is not None and (now - self._loaded_at) < self._ttl_sec:
                    return [dict(rule) for rule in self._rules]

            # Network fetch — no locks held here.
            try:
                raw = self._read_payload()
            except Exception as exc:
                with self._lock:
                    if self._rules is not None:
                        _log.warning(
                            "blocklist reload failed — keeping stale rules (%d entries): %s: %s",
                            len(self._rules),
                            type(exc).__name__,
                            exc,
                        )
                        self._loaded_at = time.monotonic()  # back off; retry after TTL
                        return [dict(rule) for rule in self._rules]
                    _log.warning(
                        "blocklist initial load failed — rules unavailable until next retry: %s: %s",
                        type(exc).__name__,
                        exc,
                    )
                    # Keep _rules as None to signal "never successfully loaded" so
                    # callers can choose to fail closed rather than allow everything.
                    self._initial_load_failed = True
                    self._loaded_at = time.monotonic()  # back off; retry after TTL
                    return []

            payload = json.loads(raw) if raw.strip() else {}
            rules = payload.get("blocked") if isinstance(payload, dict) else []
            if not isinstance(rules, list):
                rules = []
            fresh_rules = [dict(rule) for rule in rules if isinstance(rule, dict)]

            with self._lock:
                self._rules = fresh_rules
                self._initial_load_failed = False
                self._loaded_at = time.monotonic()

            return fresh_rules

    def match(
        self,
        *,
        extension_id: str,
        version: str = "",
        ref: str = "",
        repository: str = "",
        repository_id: str = "",
        publisher: str = "",
    ) -> ExtensionBlocklistMatch:
        rules = self.load()
        # Fail closed: if the blocklist was never successfully loaded we must
        # not silently allow everything — signal blocked so callers can decide.
        with self._lock:
            if self._rules is None:
                return ExtensionBlocklistMatch(
                    matched=True,
                    reason="Blocklist unavailable — install blocked until policy can be loaded.",
                    source=self._blocklist_url,
                    matched_on="",
                )
        ext_id = str(extension_id or "").strip()
        selected_version = str(version or "").strip()
        selected_ref = str(ref or "").strip()
        repo = str(repository or "").strip()
        repo_id = str(repository_id or "").strip()
        pub = str(publisher or "").strip()
        for rule in rules:
            match_rule = rule.get("match") if isinstance(rule.get("match"), dict) else rule
            source = str(rule.get("source") or self._blocklist_url)
            reason = str(rule.get("reason") or "Extension is blocked by emergency policy.")
            if self._matches_value(match_rule.get("extension_id"), ext_id):
                if self._matches_optional(match_rule.get("version"), selected_version) and self._matches_optional(
                    match_rule.get("ref"), selected_ref
                ):
                    return ExtensionBlocklistMatch(True, reason, source, "extension_id")
            if repo_id and self._matches_value(match_rule.get("repository_id"), repo_id):
                return ExtensionBlocklistMatch(True, reason, source, "repository_id")
            if repo and self._matches_value(match_rule.get("repository"), repo):
                return ExtensionBlocklistMatch(True, reason, source, "repository")
            if pub and self._matches_value(match_rule.get("publisher"), pub):
                return ExtensionBlocklistMatch(True, reason, source, "publisher")
        return ExtensionBlocklistMatch(False)

    def _read_payload(self) -> str:
        try:
            return self._read_url(self._blocklist_url, missing_ok=not bool(self._fallback_url))
        except Exception:
            if self._fallback_url:
                return self._read_url(self._fallback_url, missing_ok=True)
            raise

    def _read_url(self, url: str, *, missing_ok: bool) -> str:
        if not url:
            return "{}"
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"}:
            resp = requests.get(url, stream=True, timeout=self._timeout_sec)
            resp.raise_for_status()
            chunks: list[bytes] = []
            total = 0
            for chunk in resp.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                total += len(chunk)
                if total > _MAX_BLOCKLIST_RESPONSE_BYTES:
                    raise ValueError(
                        f"blocklist response from {url!r} exceeds maximum allowed size "
                        f"({_MAX_BLOCKLIST_RESPONSE_BYTES // 1024} KB)"
                    )
                chunks.append(chunk)
            return b"".join(chunks).decode("utf-8")
        path = Path(parsed.path if parsed.scheme == "file" else url)
        if not path.is_absolute():
            path = (self._project_root / path).resolve()
        else:
            path = path.resolve()
        # Guard against path traversal: blocklist must remain within project root.
        project_root_resolved = self._project_root.resolve()
        try:
            path.relative_to(project_root_resolved)
        except ValueError:
            raise ValueError(
                f"blocklist path must be within project root, got: {path}"
            )
        if not path.is_file():
            if not missing_ok:
                raise FileNotFoundError(path)
            return "{}"
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _matches_value(expected: Any, actual: str) -> bool:
        if expected is None:
            return False
        if isinstance(expected, list):
            return actual in {str(item).strip() for item in expected}
        return str(expected or "").strip() == actual

    @staticmethod
    def _matches_optional(expected: Any, actual: str) -> bool:
        if expected in {None, ""}:
            return True
        if not actual:
            return False
        if isinstance(expected, list):
            return actual in {str(item).strip() for item in expected}
        return str(expected or "").strip() == actual
