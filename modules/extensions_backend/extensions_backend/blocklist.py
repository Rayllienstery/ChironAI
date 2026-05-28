"""Emergency blocklist policy for repository-backed extensions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


DEFAULT_BLOCKLIST_PATH = "extensions/registry/blocklist.json"


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
    """Loads and evaluates local or remote emergency blocklist rules."""

    def __init__(
        self,
        blocklist_url: str | None = None,
        *,
        project_root: Path | None = None,
        timeout_sec: float = 15.0,
    ) -> None:
        self._project_root = project_root or Path.cwd()
        self._blocklist_url = blocklist_url or DEFAULT_BLOCKLIST_PATH
        self._timeout_sec = timeout_sec
        self._rules: list[dict[str, Any]] | None = None

    @property
    def blocklist_url(self) -> str:
        return self._blocklist_url

    def load(self) -> list[dict[str, Any]]:
        if self._rules is not None:
            return [dict(rule) for rule in self._rules]
        raw = self._read_payload()
        payload = json.loads(raw) if raw.strip() else {}
        rules = payload.get("blocked") if isinstance(payload, dict) else []
        if not isinstance(rules, list):
            rules = []
        self._rules = [dict(rule) for rule in rules if isinstance(rule, dict)]
        return [dict(rule) for rule in self._rules]

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
        ext_id = str(extension_id or "").strip()
        selected_version = str(version or "").strip()
        selected_ref = str(ref or "").strip()
        repo = str(repository or "").strip()
        repo_id = str(repository_id or "").strip()
        pub = str(publisher or "").strip()
        for rule in self.load():
            source = str(rule.get("source") or self._blocklist_url)
            reason = str(rule.get("reason") or "Extension is blocked by emergency policy.")
            if self._matches_value(rule.get("extension_id"), ext_id):
                if self._matches_optional(rule.get("version"), selected_version) and self._matches_optional(
                    rule.get("ref"), selected_ref
                ):
                    return ExtensionBlocklistMatch(True, reason, source, "extension_id")
            if repo_id and self._matches_value(rule.get("repository_id"), repo_id):
                return ExtensionBlocklistMatch(True, reason, source, "repository_id")
            if repo and self._matches_value(rule.get("repository"), repo):
                return ExtensionBlocklistMatch(True, reason, source, "repository")
            if pub and self._matches_value(rule.get("publisher"), pub):
                return ExtensionBlocklistMatch(True, reason, source, "publisher")
        return ExtensionBlocklistMatch(False)

    def _read_payload(self) -> str:
        parsed = urlparse(self._blocklist_url)
        if parsed.scheme in {"http", "https"}:
            resp = requests.get(self._blocklist_url, timeout=self._timeout_sec)
            resp.raise_for_status()
            return resp.text
        path = Path(parsed.path if parsed.scheme == "file" else self._blocklist_url)
        if not path.is_absolute():
            path = self._project_root / path
        if not path.is_file():
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
