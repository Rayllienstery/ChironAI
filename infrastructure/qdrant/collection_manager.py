from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Protocol

from modules.external_docs_rag.external_docs_rag.application.use_cases import (  # type: ignore
    ingest_github_repo_markdown,
)
from modules.external_docs_rag.external_docs_rag.domain.entities import (
    ResolvedVersion,
    VersionConstraint,
)
from modules.external_docs_rag.external_docs_rag.domain.ports import (  # type: ignore
    ChunkSink,
    EmbeddingPort,
    FetchClient,
)
from modules.external_docs_rag.external_docs_rag.infrastructure.version_resolver import (  # type: ignore
    resolve_version_for_framework,
)

from infrastructure.database.settings_repository import get_settings_repository


@dataclass(frozen=True)
class LatestTtlConfig:
    days_default: int = 90


class _Clock(Protocol):
    def now(self) -> datetime:
        ...


class _UtcClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class CollectionManager:
    """
    Manage Qdrant collections for framework docs with version-aware semantics.

    Responsibilities:
    - Construct collection names for exact versions and latest aliases.
    - Decide when a latest collection is stale based on TTL.
    - Trigger re-indexing via existing ingest_github_repo_markdown pipeline.
    """

    def __init__(self, clock: Optional[_Clock] = None) -> None:
        self._clock = clock or _UtcClock()
        self._settings = get_settings_repository()

    def _latest_ttl_days(self) -> int:
        raw = self._settings.get_app_setting("framework_latest_ttl_days")
        if not raw:
            return 90
        try:
            value = int(raw)
            return value if value > 0 else 90
        except ValueError:
            return 90

    @staticmethod
    def collection_name_for_version(framework: str, version: ResolvedVersion) -> str:
        return f"{framework}_{version.major}.{version.minor}.{version.patch}"

    @staticmethod
    def collection_name_for_latest(framework: str, version: ResolvedVersion) -> str:
        return f"{framework}_{version.major}.{version.minor}.{version.patch}_latest"

    def _is_latest_fresh(self, collection_name: str) -> bool:
        meta = self._settings.get_collection_meta(collection_name)
        if not meta:
            return False
        last = meta.get("last_refreshed_at")
        if not last:
            return False
        try:
            dt = datetime.fromisoformat(last)
        except Exception:
            return False
        ttl_days = self._latest_ttl_days()
        return self._clock.now() - dt < timedelta(days=ttl_days)

    def get_or_create_version_collection(
        self,
        framework: str,
        full_name: str,
        resolved: ResolvedVersion,
        fetch_client: FetchClient,
        chunk_sink: ChunkSink,
        embed_provider: EmbeddingPort,
    ) -> str:
        """
        Ensure a concrete version collection exists, indexing docs when missing.
        Returns the collection name.
        """
        collection_name = self.collection_name_for_version(framework, resolved)
        meta = self._settings.get_collection_meta(collection_name)
        if meta:
            return collection_name
        owner_repo = full_name.split("/")
        if len(owner_repo) != 2:
            return collection_name
        owner, repo = owner_repo
        result = ingest_github_repo_markdown(
            owner=owner,
            repo=repo,
            ref=resolved.tag,
            collection_name=collection_name,
            framework_id=framework,
            fetch_client=fetch_client,
            chunk_sink=chunk_sink,
            embed_provider=embed_provider,
            on_indexed=self._settings.set_collection_meta,
        )
        if result.chunks_indexed <= 0:
            return collection_name
        return collection_name

    def get_or_refresh_latest_collection(
        self,
        framework: str,
        full_name: str,
        constraint: VersionConstraint,
        fetch_client: FetchClient,
        chunk_sink: ChunkSink,
        embed_provider: EmbeddingPort,
    ) -> Optional[str]:
        """
        Ensure latest collection exists and is within TTL.
        When stale or missing, resolve latest version and re-index docs.
        """
        resolved = resolve_version_for_framework(full_name, constraint, repo_url=f"https://github.com/{full_name}")
        if not resolved:
            return None
        latest_collection = self.collection_name_for_latest(framework, resolved)
        if self._is_latest_fresh(latest_collection):
            return latest_collection
        owner_repo = full_name.split("/")
        if len(owner_repo) != 2:
            return latest_collection
        owner, repo = owner_repo
        result = ingest_github_repo_markdown(
            owner=owner,
            repo=repo,
            ref=resolved.tag,
            collection_name=latest_collection,
            framework_id=framework,
            fetch_client=fetch_client,
            chunk_sink=chunk_sink,
            embed_provider=embed_provider,
            on_indexed=self._settings.set_collection_meta,
        )
        if result.chunks_indexed <= 0:
            return latest_collection
        return latest_collection

