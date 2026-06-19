"""Crawler indexing runtime: embeddings and Qdrant collection setup."""

from __future__ import annotations

import contextlib
import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from api.http.webui_crawler_indexing_helpers import (
    clip_text_for_embedding as _clip_text_for_embedding,
)
from api.http.webui_crawler_indexing_helpers import (
    config_default_embed_model as _config_default_embed_model,
)
from api.http.webui_crawler_indexing_helpers import (
    import_qdrant as _import_qdrant,
)
from api.http.webui_crawler_indexing_helpers import (
    is_embed_context_length_error as _is_embed_context_length_error,
)
from api.http.webui_crawler_indexing_helpers import (
    log_indexing_embed_path_once as _log_indexing_embed_path_once,
)
from api.http.webui_crawler_indexing_helpers import (
    max_embed_chars as _max_embed_chars,
)
from api.http.webui_crawler_indexing_helpers import (
    runtime_embed_available as _runtime_embed_available,
)
from api.http.webui_provider_helpers import default_llm_provider_id as _default_llm_provider_id
from api.http.webui_provider_helpers import invoke_runtime_embed as _invoke_runtime_embed
from config import get_indexing_int
from infrastructure.database import get_settings_repository
from infrastructure.rag.qdrant_point_builder import dense_vectors_config, hybrid_vectors_config

if TYPE_CHECKING:
    from qdrant_client import QdrantClient

_WEBUI_LOG = logging.getLogger("webui")

def sha256_text(text: str) -> str:
    """Compute SHA256 hash of text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def authority_tier(source_id: str) -> int:
    # 3 = official Apple docs, 2 = language guide (swift_book), 1 = community, 0 = WWDC
    if source_id == "apple_documentation":
        return 3
    if source_id == "swift_book":
        return 2
    if source_id.startswith("wwdc_sessions_"):
        return 0
    return 1

def is_hub_url(source_id: str, url: str) -> bool:
    u = (url or "").strip().lower().rstrip("/")
    if not u:
        return False
    if source_id == "hws_swift":
        return u in (
            "https://www.hackingwithswift.com/quick-start/swiftui",
            "https://www.hackingwithswift.com/read",
            "https://www.hackingwithswift.com/example-code",
        )
    if source_id == "pointfree_collections":
        return u.endswith("/collections") or u.endswith("/collections/swiftui/state-management")
    return False

def material_class(source_id: str, url: str) -> str:
    if source_id == "apple_documentation":
        return "official"
    if source_id == "swift_book":
        return "swift_book"
    if source_id.startswith("wwdc_sessions_"):
        return "wwdc"
    if is_hub_url(source_id, url):
        return "hub"
    return "community"


def point_id_from_hash(h: str) -> int:
    """Build a Qdrant-compatible unsigned integer point id from a sha256 hex string."""
    h = (h or "0" * 16)[:16]
    return int(h, 16)


def get_embeddings_simple(
    texts: list[str],
    *,
    embed_provider_id: str | None = None,
    embed_model_override: str | None = None,
    parallel_workers: int | None = None,
) -> list[list[float] | None]:
    """Simple embedding function using the configured blind runtime provider.

    When ``embed_model_override`` is non-empty, it is used for this call only
    (e.g. create-collection job). Otherwise: app_settings, then env, then default.
    """
    if not texts:
        return []

    resolved_provider_id = str(embed_provider_id or "").strip()
    if not resolved_provider_id:
        try:
            settings_repo = get_settings_repository()
            resolved_provider_id = str(settings_repo.get_app_setting("rag_embed_provider_id") or "").strip()
        except Exception:  # safe: settings repository optional for embed provider lookup
            resolved_provider_id = ""
    if not resolved_provider_id:
        resolved_provider_id = _default_llm_provider_id()

    override = (embed_model_override or "").strip()
    if override:
        embed_model = override
    else:
        try:
            settings_repo = get_settings_repository()
            raw = settings_repo.get_app_setting("rag_embed_model")
            rag_embed_model = (raw or "").strip()
        except Exception:  # safe: settings repository optional for embed model lookup
            rag_embed_model = ""

        # Fallback order:
        # 1) app_settings.rag_embed_model (set from WebUI)
        # 2) legacy default embed model from config/env
        embed_model = rag_embed_model or _config_default_embed_model()

    max_embed_chars = _max_embed_chars()
    clipped_texts = [_clip_text_for_embedding(t or "", max_embed_chars) for t in texts]
    batch_size = max(1, get_indexing_int("embed_batch_size", 32))
    worker_count = max(1, min(8, int(parallel_workers or get_indexing_int("embed_parallel_workers", 4))))

    def _embed_batch_runtime(batch: list[str]) -> list[list[float]]:
        if not _runtime_embed_available():
            raise RuntimeError(
                "Embedding provider runtime is unavailable; enable a provider extension "
                "or configure rag_embed_provider_id."
            )
        vectors = _invoke_runtime_embed(
            provider_id=resolved_provider_id,
            model=embed_model,
            texts=batch,
        )
        if len(vectors) != len(batch):
            raise RuntimeError(
                f"Embedding provider returned {len(vectors)} vectors for {len(batch)} texts."
            )
        return vectors

    def _embed_all() -> list[list[float] | None]:
        def _embed_batch(batch: list[str]) -> list[list[float]]:
            return _embed_batch_runtime(batch)

        def _embed_one_with_context_retry(text: str) -> list[float] | None:
            retry_limits = [min(len(text), n) for n in (1200, 900, 600, 360)]
            for limit in retry_limits:
                clipped = _clip_text_for_embedding(text, limit)
                try:
                    vectors = _embed_batch([clipped])
                    return vectors[0] if vectors else None
                except Exception as e:
                    if not _is_embed_context_length_error(e):
                        raise
            _WEBUI_LOG.warning(
                "Dropping one indexing chunk after repeated embedding context-length failures "
                "(chars=%s, clipped_chars=%s, model=%s)",
                len(text or ""),
                len(_clip_text_for_embedding(text, retry_limits[-1] if retry_limits else 0)),
                embed_model,
            )
            return None

        def _embed_adaptive(batch: list[str]) -> list[list[float] | None]:
            try:
                return _embed_batch(batch)
            except Exception as e:
                if not _is_embed_context_length_error(e):
                    raise
                if len(batch) <= 1:
                    return [_embed_one_with_context_retry(batch[0])]
                mid = max(1, len(batch) // 2)
                _WEBUI_LOG.warning(
                    "Embedding batch exceeded provider context; splitting batch "
                    "(batch_size=%s, left=%s, right=%s, model=%s): %s",
                    len(batch),
                    mid,
                    len(batch) - mid,
                    embed_model,
                    e,
                )
                return _embed_adaptive(batch[:mid]) + _embed_adaptive(batch[mid:])

        out: list[list[float] | None] = []
        batches = [
            clipped_texts[i : i + batch_size]
            for i in range(0, len(clipped_texts), batch_size)
        ]
        if worker_count <= 1 or len(batches) <= 1:
            for batch in batches:
                out.extend(_embed_adaptive(batch))
            return out
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="crawler-embed") as pool:
            for batch_vectors in pool.map(_embed_adaptive, batches):
                out.extend(batch_vectors)
        return out

    _log_indexing_embed_path_once(f"extension LLM runtime (workers={worker_count})")

    try:
        return _embed_all()
    except Exception as first_err:
        _WEBUI_LOG.error("Embedding failed for indexing: %s", first_err)
        raise RuntimeError(f"Embedding failed during indexing: {first_err}") from first_err


def qdrant_collection_has_sparse_vectors(qclient: QdrantClient, collection_name: str) -> bool:
    """True if collection was created with sparse_vectors (hybrid indexing)."""
    try:
        info = qclient.get_collection(collection_name)
        params = info.config.params
        sv = getattr(params, "sparse_vectors", None)
        if sv is None:
            return False
        if isinstance(sv, dict):
            return len(sv) > 0
        return bool(sv)
    except Exception:  # safe: Qdrant collection introspection failure treated as non-hybrid
        return False


def ensure_collection_with_name(
    qclient: QdrantClient,
    collection_name: str,
    dim: int,
    *,
    hybrid_sparse: bool = False,
) -> None:
    """Create Qdrant collection with specified name if it doesn't exist."""
    _, Distance, PayloadSchemaType, _, SparseVectorParams, VectorParams = _import_qdrant()
    try:
        qclient.get_collection(collection_name)
        # Collection exists, ensure payload indexes
        try:
            index_fields = [
                "language", "technology", "domain", "product", "doc_type", "doc_scope",
                "symbol", "framework", "section",
            ]
            for field in index_fields:
                with contextlib.suppress(Exception):
                    qclient.create_payload_index(
                        collection_name=collection_name,
                        field_name=field,
                        field_schema=PayloadSchemaType.KEYWORD,
                    )
        except Exception:  # safe: payload index ensure is best-effort on existing collection
            pass
        return
    except Exception:  # safe: collection missing triggers create path below
        pass

    # Create collection (dense-only or dense+sparse hybrid)
    try:
        if hybrid_sparse:
            vectors_config, sparse_vectors_config = hybrid_vectors_config(dim)
            qclient.recreate_collection(
                collection_name,
                vectors_config=vectors_config,
                sparse_vectors_config=sparse_vectors_config,
            )
            _WEBUI_LOG.info(
                f"Created Qdrant collection '{collection_name}' (dim={dim}, hybrid sparse)"
            )
        else:
            qclient.recreate_collection(
                collection_name,
                vectors_config=dense_vectors_config(dim),
            )
            _WEBUI_LOG.info(f"Created Qdrant collection '{collection_name}' (dim={dim}, named dense)")
        # Ensure payload indexes on new collection
        for field in ["language", "technology", "domain", "product", "doc_type", "doc_scope", "symbol", "framework", "section"]:
            with contextlib.suppress(Exception):
                qclient.create_payload_index(
                    collection_name=collection_name,
                    field_name=field,
                    field_schema=PayloadSchemaType.KEYWORD,
                )
    except Exception as e:
        _WEBUI_LOG.error(f"Failed to create collection '{collection_name}': {e}")
        raise





__all__ = [
    "get_embeddings_simple",
    "ensure_collection_with_name",
    "qdrant_collection_has_sparse_vectors",
]
