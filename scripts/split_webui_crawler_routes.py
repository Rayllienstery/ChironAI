"""Split api/http/webui_crawler_routes.py into domain route modules (Phase 3)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTTP = ROOT / "api" / "http"
SRC = HTTP / "webui_crawler_routes.py"
lines = SRC.read_text(encoding="utf-8").splitlines(keepends=True)


def sl(a: int, b: int) -> str:
    return "".join(lines[a - 1 : b])


def dedent_block(text: str, spaces: int = 4) -> str:
    prefix = " " * spaces
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        if line.startswith(prefix):
            out.append(line[spaces:])
        else:
            out.append(line)
    return "".join(out)


def indent_body(text: str, spaces: int = 4) -> str:
    prefix = " " * spaces
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        if line.strip():
            out.append(prefix + line)
        else:
            out.append(line)
    return "".join(out)


def strip_indexing_wrappers(text: str) -> str:
    """Drop thin wrappers that only delegate to webui_crawler_helpers."""
    markers = [
        "def get_crawler_sources_dir_fn",
        "def load_source_meta_fn",
        "def get_source_stats_fn",
        "def discover_sources_fn",
    ]
    start = 0
    for marker in markers:
        idx = text.find(marker)
        if idx == -1:
            continue
        if start == 0 or idx < start:
            start = idx
    if start:
        end = text.find("\n\n", start)
        if end != -1:
            text = text[:start] + text[end + 2 :]
    return text


MODULE_HEADER = '''"""Crawler route registration for the WebUI blueprint."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, Callable

from error_manager.http import error_response as _error_response
from flask import Blueprint, current_app, jsonify, request
from md_ingestion_service.domain.services.indexing_prepare import prepare_markdown_for_indexing
from rag_service.application.params import get_rag_answer_params
from rag_service.domain.services.chunking import chunk_quality_ok, split_markdown_into_chunks
from rag_service.domain.services.metadata_inference import (
    _apple_doc_scope_from_doc_kind,
    build_embed_prefix,
    estimate_token_count,
    extract_versions,
    infer_chunk_display_meta,
    infer_metadata,
)

from application.rag.hybrid_sparse import is_hybrid_sparse_enabled
from config import get_indexing_int, get_qdrant_url
from infrastructure.database import get_settings_repository
from infrastructure.logging.webui_error_logger import get_webui_error_logger
from infrastructure.rag.qdrant_point_builder import (
    build_named_vectors,
    dense_vectors_config,
    hybrid_vectors_config,
)
from webui_backend.paths import webui_data_dir

if TYPE_CHECKING:
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import PointStruct

from api.http.rag_sources_meta import update_page_chunk_hashes
from api.http.webui_crawler_helpers import (
    compute_source_stats,
    discover_crawler_sources,
    get_crawler_sources_dir,
    is_safe_identifier,
    load_source_meta,
)
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
from api.http.webui_crawler_indexing_helpers import (
    write_create_collection_final_log as _write_create_collection_final_log,
)
from api.http.webui_crawler_source_routes import register_crawler_source_routes
from api.http.webui_provider_helpers import default_llm_provider_id as _default_llm_provider_id
from api.http.webui_provider_helpers import invoke_runtime_chat as _invoke_runtime_chat
from api.http.webui_provider_helpers import invoke_runtime_embed as _invoke_runtime_embed
from api.http.webui_rag_routes import get_qdrant_collection_names as _get_qdrant_collection_names

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_WEBUI_BACKEND = os.path.join(_ROOT, "CoreModules", "WebUIBackend")
if os.path.isdir(_WEBUI_BACKEND) and _WEBUI_BACKEND not in sys.path:
    sys.path.insert(0, _WEBUI_BACKEND)

_WEBUI_LOG = logging.getLogger("webui")
_ERROR_LOG = get_webui_error_logger()

try:
    from modules.md_indexer import delete_pipeline as md_indexer_delete_pipeline
    from modules.md_indexer import (
        get_active_pipeline_name,
        list_pipeline_names,
        load_pipeline,
        run_pipeline,
        save_pipeline,
    )
except ImportError:
    md_indexer_delete_pipeline = None  # type: ignore[assignment]
    get_active_pipeline_name = None  # type: ignore[assignment]
    list_pipeline_names = None  # type: ignore[assignment]
    load_pipeline = None  # type: ignore[assignment]
    run_pipeline = None  # type: ignore[assignment]
    save_pipeline = None  # type: ignore[assignment]

'''

_INDEXING_RUNTIME_EMBED_HEADER = '''"""Crawler indexing runtime: embeddings and Qdrant collection setup."""

from __future__ import annotations

import hashlib
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

from config import get_indexing_int
from infrastructure.database import get_settings_repository
from infrastructure.rag.qdrant_point_builder import dense_vectors_config, hybrid_vectors_config

from api.http.webui_crawler_indexing_helpers import (
    clip_text_for_embedding as _clip_text_for_embedding,
    config_default_embed_model as _config_default_embed_model,
    import_qdrant as _import_qdrant,
    is_embed_context_length_error as _is_embed_context_length_error,
    log_indexing_embed_path_once as _log_indexing_embed_path_once,
    max_embed_chars as _max_embed_chars,
    runtime_embed_available as _runtime_embed_available,
)
from api.http.webui_provider_helpers import default_llm_provider_id as _default_llm_provider_id
from api.http.webui_provider_helpers import invoke_runtime_embed as _invoke_runtime_embed

if TYPE_CHECKING:
    from qdrant_client import QdrantClient

_WEBUI_LOG = logging.getLogger("webui")

'''

INDEXING_RUNTIME_CORE_HEADER = '''"""Crawler indexing runtime: page processing and collection build."""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import TYPE_CHECKING, Any, Callable

from application.rag.hybrid_sparse import is_hybrid_sparse_enabled
from config import get_indexing_int, get_qdrant_url
from infrastructure.rag.qdrant_point_builder import build_named_vectors
from md_ingestion_service.domain.services.indexing_prepare import prepare_markdown_for_indexing
from rag_service.domain.services.chunking import chunk_quality_ok, split_markdown_into_chunks
from rag_service.domain.services.metadata_inference import (
    _apple_doc_scope_from_doc_kind,
    build_embed_prefix,
    estimate_token_count,
    extract_versions,
    infer_chunk_display_meta,
    infer_metadata,
)

from api.http.rag_sources_meta import update_page_chunk_hashes
from api.http.webui_crawler_helpers import get_crawler_sources_dir, load_source_meta
from api.http.webui_crawler_indexing_helpers import import_qdrant as _import_qdrant
from api.http.webui_crawler_indexing_runtime_embed import (
    ensure_collection_with_name,
    get_embeddings_simple,
    qdrant_collection_has_sparse_vectors,
)
from api.http.webui_crawler_source_config import load_sources_config

if TYPE_CHECKING:
    from qdrant_client.http.models import PointStruct

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_WEBUI_LOG = logging.getLogger("webui")

_collection_jobs: dict[str, dict[str, Any]] = {}
_collection_jobs_lock = threading.Lock()

'''

# Indexing: lines 132-1154 inside register_crawler_routes
indexing_body = dedent_block(sl(132, 1154))
start = indexing_body.find("def _get_crawler_sources_dir")
end = indexing_body.find("def _sha256")
if start != -1 and end != -1:
    indexing_body = indexing_body[:start] + indexing_body[end:]
# Split indexing at _create_collection_from_sources
idx_split = indexing_body.index("def _create_collection_from_sources(")
indexing_embed = indexing_body[:idx_split].rstrip() + "\n"
indexing_core = indexing_body[idx_split:].rstrip() + "\n"

# Rename nested defs to module-level (drop leading underscore convention kept)
for old, new in [
    ("def _sha256", "def sha256_text"),
    ("def _authority_tier", "def authority_tier"),
    ("def _is_hub_url", "def is_hub_url"),
    ("def _material_class", "def material_class"),
    ("def _point_id_from_hash", "def point_id_from_hash"),
    ("def _get_embeddings_simple", "def get_embeddings_simple"),
    ("def _qdrant_collection_has_sparse_vectors", "def qdrant_collection_has_sparse_vectors"),
    ("def _ensure_collection_with_name", "def ensure_collection_with_name"),
    ("def _touch_collection_job_timing", "def touch_collection_job_timing"),
    ("def _snapshot_indexing_stats", "def snapshot_indexing_stats"),
    ("def _record_prepare_stats", "def record_prepare_stats"),
    ("def _remember_prepare_removal", "def remember_prepare_removal"),
    ("def _remember_embedding_history", "def remember_embedding_history"),
    ("def _record_page_skip", "def record_page_skip"),
    ("def _create_collection_from_sources", "def create_collection_from_sources"),
    ("def _run_create_collection_job", "def run_create_collection_job"),
]:
    indexing_embed = indexing_embed.replace(old, new)
    indexing_core = indexing_core.replace(old, new)

indexing_embed = strip_indexing_wrappers(indexing_embed)
indexing_embed = indexing_embed.replace(
    "# In-memory job progress for create-collection (job_id -> { status, progress, ... })\n"
    "_collection_jobs: dict[str, dict[str, Any]] = {}\n"
    "_collection_jobs_lock = threading.Lock()\n\n",
    "",
)

indexing_embed = indexing_embed.replace("_get_crawler_sources_dir()", "get_crawler_sources_dir()")
indexing_embed = indexing_embed.replace("_load_source_meta(", "load_source_meta(")
indexing_embed = indexing_embed.replace("_load_sources_config()", "load_sources_config()")
indexing_core = indexing_core.replace("_get_crawler_sources_dir()", "get_crawler_sources_dir()")
indexing_core = indexing_core.replace("_load_source_meta(", "load_source_meta(")
indexing_core = indexing_core.replace("load_sources_config()", "load_sources_config(_ROOT)")
indexing_core = indexing_core.replace("_get_embeddings_simple(", "get_embeddings_simple(")
indexing_core = indexing_core.replace("_sha256(", "sha256_text(")
indexing_core = indexing_core.replace("_authority_tier(", "authority_tier(")
indexing_core = indexing_core.replace("_is_hub_url(", "is_hub_url(")
indexing_core = indexing_core.replace("_material_class(", "material_class(")
indexing_core = indexing_core.replace("_point_id_from_hash(", "point_id_from_hash(")
indexing_core = indexing_core.replace("_ensure_collection_with_name(", "ensure_collection_with_name(")
indexing_core = indexing_core.replace("_qdrant_collection_has_sparse_vectors(", "qdrant_collection_has_sparse_vectors(")
indexing_core = indexing_core.replace("_snapshot_indexing_stats(", "snapshot_indexing_stats(")
indexing_core = indexing_core.replace("_record_prepare_stats(", "record_prepare_stats(")
indexing_core = indexing_core.replace("_remember_prepare_removal(", "remember_prepare_removal(")
indexing_core = indexing_core.replace("_remember_embedding_history(", "remember_embedding_history(")
indexing_core = indexing_core.replace("_record_page_skip(", "record_page_skip(")
indexing_core = indexing_core.replace("_create_collection_from_sources(", "create_collection_from_sources(")

tidx = indexing_embed.find("def touch_collection_job_timing")
if tidx != -1:
    indexing_core = indexing_embed[tidx:] + indexing_core
    indexing_embed = indexing_embed[:tidx]

indexing_runtime_embed = (
    _INDEXING_RUNTIME_EMBED_HEADER
    + indexing_embed
    + "\n\n__all__ = [\n"
    + '    "get_embeddings_simple",\n'
    + '    "ensure_collection_with_name",\n'
    + '    "qdrant_collection_has_sparse_vectors",\n'
    + "]\n"
)

indexing_runtime_core = (
    INDEXING_RUNTIME_CORE_HEADER
    + indexing_core
    + "\n\n__all__ = [\n"
    + '    "_collection_jobs",\n'
    + '    "_collection_jobs_lock",\n'
    + '    "create_collection_from_sources",\n'
    + '    "touch_collection_job_timing",\n'
    + "]\n"
)

ROUTE_IMPORTS = '''
from error_manager.http import error_response as _error_response
from flask import current_app, jsonify, request
from typing import Any

from api.http.webui_crawler_indexing_helpers import write_create_collection_final_log as _write_create_collection_final_log
from api.http.webui_crawler_indexing_runtime_core import (
    _collection_jobs,
    _collection_jobs_lock,
    create_collection_from_sources,
    touch_collection_job_timing,
)
from infrastructure.database import get_settings_repository
'''

sources_read = dedent_block(sl(1157, 1291))
sources_stats = dedent_block(sl(2069, 2085))
indexer_routes = dedent_block(sl(1293, 1962))
md_pipeline_routes = dedent_block(sl(1963, 2067))
job_routes = dedent_block(sl(2087, 2669))

config_loaders = dedent_block(sl(2199, 2233))


def wrap_routes(name: str, doc: str, body: str, extra_imports: str = "") -> str:
    body = body.replace("_get_crawler_sources_dir()", "get_crawler_sources_dir()")
    body = body.replace("_load_source_meta(", "load_source_meta(")
    body = body.replace("_get_source_stats(", "compute_source_stats(")
    body = body.replace("_discover_sources()", "discover_crawler_sources()")
    body = body.replace("_load_sources_config()", "load_sources_config()")
    body = body.replace("_save_sources_config(", "save_sources_config(")
    body = body.replace("_create_collection_from_sources(", "create_collection_from_sources(")
    body = body.replace("def _run_create_collection_job", "def run_create_collection_job")
    body = body.replace("_run_create_collection_job(", "run_create_collection_job(")
    body = body.replace("_touch_collection_job_timing(", "touch_collection_job_timing(")
    body = indent_body(body)
    return (
        f'"""{doc}"""\n\nfrom __future__ import annotations\n\n'
        f"import os\nimport subprocess\nimport sys\nimport threading\nimport time\nimport uuid\n"
        f"from typing import Any, Callable\n\n"
        f"{extra_imports}\n"
        f"_ERROR_LOG: Any = None\n\n\n"
        f"def {name}(\n"
        f"    bp,\n"
        f"    *,\n"
        f"    error_log,\n"
        f"    root: str,\n"
        f"    webui_backend: str,\n"
        f"    get_crawler_sources_dir: Callable[[], str],\n"
        f"    load_source_meta: Callable[[str], dict | None],\n"
        f"    load_sources_config: Callable[[], list[dict]],\n"
        f"    save_sources_config: Callable[[list[dict]], bool],\n"
        f") -> None:\n"
        f"    global _ERROR_LOG\n"
        f"    _ERROR_LOG = error_log\n"
        f"    _ROOT = root\n"
        f"    _WEBUI_BACKEND = webui_backend\n\n"
        f"{body}\n\n\n__all__ = [\"{name}\"]\n"
    )


# Pull config loaders out of job routes into shared helper module
config_module = '''"""Load and persist crawler sources.yaml for WebUI routes."""

from __future__ import annotations

import logging
import os

_WEBUI_LOG = logging.getLogger("webui")


def load_sources_config(root: str) -> list[dict]:
    """Load sources from config/sources.yaml."""
    try:
        import yaml

        config_path = os.path.join(root, "config", "sources.yaml")
        if not os.path.isfile(config_path):
            return []

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return data.get("sources", [])
    except Exception as e:
        _WEBUI_LOG.warning(f"Failed to load sources config: {e}")
        return []


def save_sources_config(root: str, sources: list[dict]) -> bool:
    """Save sources to config/sources.yaml. Returns True on success."""
    try:
        import yaml

        config_path = os.path.join(root, "config", "sources.yaml")
        config_dir = os.path.dirname(config_path)
        os.makedirs(config_dir, exist_ok=True)

        data = {"sources": sources}
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return True
    except Exception as e:
        _WEBUI_LOG.error(f"Failed to save sources config: {e}")
        return False


__all__ = ["load_sources_config", "save_sources_config"]
'''

# Remove config loaders from job routes body
job_routes = job_routes.replace(config_loaders, "")

sources_read_module = wrap_routes(
    "register_crawler_sources_read_routes",
    "Crawler source read routes (list, detail, pages, stats).",
    sources_read + "\n" + sources_stats,
    extra_imports=(
        "from error_manager.http import error_response as _error_response\n"
        "from flask import jsonify, request\n"
        "from typing import Callable\n\n"
        "from api.http.webui_crawler_helpers import compute_source_stats, discover_crawler_sources\n"
    ),
)

indexer_module = wrap_routes(
    "register_crawler_indexer_routes",
    "Indexer tester routes for crawl sources.",
    indexer_routes,
    extra_imports=(
        "from error_manager.http import error_response as _error_response\n"
        "from flask import jsonify, request\n"
        "from typing import Callable\n\n"
        "from api.http.webui_provider_helpers import invoke_runtime_chat as _invoke_runtime_chat\n"
        "try:\n"
        "    from modules.md_indexer import get_active_pipeline_name, run_pipeline\n"
        "except ImportError:\n"
        "    get_active_pipeline_name = None  # type: ignore[assignment]\n"
        "    run_pipeline = None  # type: ignore[assignment]\n"
    ),
)

md_pipeline_module = wrap_routes(
    "register_crawler_md_pipeline_routes",
    "Markdown pipeline admin routes for the crawler.",
    md_pipeline_routes,
    extra_imports=(
        "from error_manager.http import error_response as _error_response\n"
        "from flask import jsonify, request\n"
        "from typing import Callable\n\n"
        "try:\n"
        "    from modules.md_indexer import (\n"
        "        delete_pipeline as md_indexer_delete_pipeline,\n"
        "        get_active_pipeline_name,\n"
        "        list_pipeline_names,\n"
        "        load_pipeline,\n"
        "        run_pipeline,\n"
        "        save_pipeline,\n"
        "    )\n"
        "except ImportError:\n"
        "    md_indexer_delete_pipeline = None  # type: ignore[assignment]\n"
        "    get_active_pipeline_name = None  # type: ignore[assignment]\n"
        "    list_pipeline_names = None  # type: ignore[assignment]\n"
        "    load_pipeline = None  # type: ignore[assignment]\n"
        "    run_pipeline = None  # type: ignore[assignment]\n"
        "    save_pipeline = None  # type: ignore[assignment]\n"
    ),
)

job_module = wrap_routes(
    "register_crawler_job_routes",
    "Crawler crawl subprocess and create-collection job routes.",
    job_routes,
    extra_imports=(
        "from error_manager.http import error_response as _error_response\n"
        "from flask import current_app, jsonify, request\n\n"
        "from webui_backend.paths import webui_data_dir\n"
        + ROUTE_IMPORTS
    ),
)

main_routes = '''"""Crawler, source inspection, indexer tester, and collection routes."""

from __future__ import annotations

from typing import Any

from flask import Blueprint

from api.http.webui_crawler_indexing_helpers import (
    clip_text_for_embedding as _clip_text_for_embedding,
    is_embed_context_length_error as _is_embed_context_length_error,
)
from api.http.webui_crawler_helpers import get_crawler_sources_dir, load_source_meta
from api.http.webui_crawler_indexer_routes import register_crawler_indexer_routes
from api.http.webui_crawler_job_routes import register_crawler_job_routes
from api.http.webui_crawler_md_pipeline_routes import register_crawler_md_pipeline_routes
from api.http.webui_crawler_source_config import load_sources_config, save_sources_config
from api.http.webui_crawler_source_routes import register_crawler_source_routes
from api.http.webui_crawler_sources_read_routes import register_crawler_sources_read_routes

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_WEBUI_BACKEND = os.path.join(_ROOT, "CoreModules", "WebUIBackend")


def register_crawler_routes(bp: Blueprint, *, error_log: Any) -> None:
  """Register all crawler-related WebUI routes on ``bp``."""
  deps = {
      "error_log": error_log,
      "root": _ROOT,
      "webui_backend": _WEBUI_BACKEND,
      "get_crawler_sources_dir": get_crawler_sources_dir,
      "load_source_meta": load_source_meta,
      "load_sources_config": lambda: load_sources_config(_ROOT),
      "save_sources_config": lambda sources: save_sources_config(_ROOT, sources),
  }
  for register in (
      register_crawler_sources_read_routes,
      register_crawler_indexer_routes,
      register_crawler_md_pipeline_routes,
      register_crawler_job_routes,
  ):
      register(bp, **deps)
  register_crawler_source_routes(
      bp,
      error_log=error_log,
      get_crawler_sources_dir=get_crawler_sources_dir,
      load_source_meta=load_source_meta,
      load_sources_config=deps["load_sources_config"],
      save_sources_config=deps["save_sources_config"],
  )


__all__ = ["register_crawler_routes", "_clip_text_for_embedding", "_is_embed_context_length_error"]
'''

(HTTP / "webui_crawler_source_config.py").write_text(config_module, encoding="utf-8")
(HTTP / "webui_crawler_indexing_runtime_embed.py").write_text(indexing_runtime_embed, encoding="utf-8")
(HTTP / "webui_crawler_indexing_runtime_core.py").write_text(indexing_runtime_core, encoding="utf-8")
(HTTP / "webui_crawler_sources_read_routes.py").write_text(sources_read_module, encoding="utf-8")
(HTTP / "webui_crawler_indexer_routes.py").write_text(indexer_module, encoding="utf-8")
(HTTP / "webui_crawler_md_pipeline_routes.py").write_text(md_pipeline_module, encoding="utf-8")
(HTTP / "webui_crawler_job_routes.py").write_text(job_module, encoding="utf-8")
SRC.write_text(main_routes, encoding="utf-8")

for name in [
    "webui_crawler_routes.py",
    "webui_crawler_source_config.py",
    "webui_crawler_indexing_runtime_embed.py",
    "webui_crawler_indexing_runtime_core.py",
    "webui_crawler_sources_read_routes.py",
    "webui_crawler_indexer_routes.py",
    "webui_crawler_md_pipeline_routes.py",
    "webui_crawler_job_routes.py",
]:
    n = len((HTTP / name).read_text(encoding="utf-8").splitlines())
    print(f"{name}: {n} lines")
