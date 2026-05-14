"""
Ingest local Markdown files (e.g. from Apple-Developer-Documentation-Offline-Archive)
into Qdrant using Ollama embedding model.

Uses domain.services.chunking (semantic sections/paragraphs, section_path) and config
indexing limits — same policy as WebUI "Create collection from sources".

Embedding model and endpoint are shared with the main RAG pipeline:
- Model name: ``config.get_ollama_embed_model()`` or env ``RAG_EMBED_MODEL`` if ``config`` is unavailable.
- Embed URL: ``config.get_ollama_embed_url()`` or ``OLLAMA_EMBED_URL``.

Usage (PowerShell):

  python -m webui_backend.ingest_markdown_local `
    "c:\\Users\\Raylee\\AI\\Apple-Developer-Documentation-Offline-Archive-main\\markdown" `
    --collection apple_docs

Requirements:
  - Ollama running with the embedding model referenced by RAG_EMBED_MODEL
  - pip install qdrant-client requests
"""

import os
import re
import sys
from pathlib import Path
from typing import List

from webui_backend.paths import project_root, webui_data_dir

_ROOT = str(project_root())
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from infrastructure.ollama.cli_runner import OllamaInteractorCliError, invoke_embed
from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance, PointStruct

from webui_backend.ingest_markdown_common import (
    chunks_for_local_ingest,
    print_local_ingest_summary,
    qdrant_payload_local,
)

try:
    from config import get_ollama_embed_model, get_ollama_embed_url
except ImportError:
    get_ollama_embed_model = lambda: (os.getenv("RAG_EMBED_MODEL") or "").strip()  # type: ignore[assignment]
    get_ollama_embed_url = lambda: os.getenv(  # type: ignore[assignment]
        "OLLAMA_EMBED_URL", "http://localhost:11434/api/embed"
    )

# Shared embedding configuration with the main RAG pipeline
OLLAMA_EMBED_URL = get_ollama_embed_url()
EMBED_MODEL_NAME = get_ollama_embed_model()
EMBED_BATCH_SIZE = 32
QDRANT_URL = "http://localhost:6333"
COLLECTION_FILE = str(webui_data_dir() / "last_collection.txt")


def get_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Call Ollama /api/embed in batches; returns list of vectors (same order as texts).

    This is the ONLY place that knows about the embedding model/endpoint for local
    markdown ingestion. To switch models/endpoints:
    - Update RAG_EMBED_MODEL / OLLAMA_EMBED_URL env vars.

    Expected Ollama /api/embed response format:
    {
      "embeddings": [
        [float, float, ...],  # one vector per input text
        ...
      ]
    }
    """
    if not texts:
        return []
    result: List[List[float]] = []
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i : i + EMBED_BATCH_SIZE]
        try:
            data = invoke_embed(
                {
                    "url": OLLAMA_EMBED_URL,
                    "json": {"model": EMBED_MODEL_NAME, "input": batch},
                    "timeout": 120,
                },
                default_timeout=120,
            )
        except OllamaInteractorCliError as e:
            raise RuntimeError(str(e)) from e
        vectors = data.get("embeddings", [])
        if len(vectors) != len(batch):
            raise RuntimeError(
                f"Ollama returned {len(vectors)} embeddings for batch size {len(batch)}"
            )
        result.extend(vectors)
    return result


def collection_name_from_path(root: Path) -> str:
    """Derive Qdrant collection name from markdown root path (e.g. .../markdown -> markdown)."""
    name = root.name if root.name else "markdown"
    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", name)[:63]
    return slug or "markdown"


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help"}:
        print("Usage: python -m webui_backend.ingest_markdown_local <path_to_markdown_folder> [--collection NAME]")
        print(
            "Example: python -m webui_backend.ingest_markdown_local "
            "C:\\path\\to\\Apple-Developer-Documentation-Offline-Archive\\markdown --collection apple_docs"
        )
        sys.exit(0 if len(sys.argv) >= 2 else 1)

    root = Path(sys.argv[1]).resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}")
        sys.exit(1)

    collection = None
    args = sys.argv[2:]
    for i, arg in enumerate(args):
        if arg == "--collection" and i + 1 < len(args):
            collection = args[i + 1].strip()
            break
    if not collection:
        collection = collection_name_from_path(root)

    md_files = list(root.rglob("*.md"))
    if not md_files:
        print(f"No .md files under {root}")
        sys.exit(1)

    print(f"Markdown root: {root}")
    print(f"Collection: {collection}")
    print(f"Files: {len(md_files)}")

    print(f"Using Ollama embedding model: {EMBED_MODEL_NAME}")
    # Resolve embedding dimension via one short request.
    try:
        dim_data = invoke_embed(
            {
                "url": OLLAMA_EMBED_URL,
                "json": {"model": EMBED_MODEL_NAME, "input": "."},
                "timeout": 60,
            },
            default_timeout=60,
        )
    except OllamaInteractorCliError as e:
        raise RuntimeError(str(e)) from e
    dim = len(dim_data["embeddings"][0])
    print(f"Embedding dimension: {dim}")

    qclient = QdrantClient(url=QDRANT_URL)
    point_id = 1
    created = False
    total_chunks = 0
    files_total = len(md_files)
    files_indexed_ok = 0
    files_skipped_read_error = 0
    files_skipped_no_chunks = 0
    files_skipped_embed_error = 0
    files_skipped_embed_mismatch = 0

    for idx, md_path in enumerate(md_files, 1):
        try:
            content = md_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            files_skipped_read_error += 1
            print(f"  Skip {md_path}: {e}")
            continue

        pairs = chunks_for_local_ingest(content)
        if not pairs:
            files_skipped_no_chunks += 1
            continue

        texts = [t for t, _ in pairs]
        try:
            embeddings = get_embeddings(texts)
        except Exception as e:
            files_skipped_embed_error += 1
            print(f"  Embed error {md_path}: {e}")
            continue
        if len(embeddings) != len(texts):
            files_skipped_embed_mismatch += 1
            print(f"  Embedding count mismatch for {md_path}, skip")
            continue

        if not created:
            qclient.recreate_collection(
                collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
            created = True
            print(f"  Created collection '{collection}' (dim={dim})")

        rel_path = str(md_path.relative_to(root))
        points = [
            PointStruct(
                id=point_id + j,
                vector=vec,
                payload=qdrant_payload_local(rel_path, pairs[j][0], pairs[j][1]),
            )
            for j, vec in enumerate(embeddings)
        ]
        point_id += len(points)
        total_chunks += len(points)

        qclient.upsert(collection_name=collection, points=points)
        files_indexed_ok += 1
        if idx % 50 == 0 or idx == len(md_files):
            print(f"  [{idx}/{len(md_files)}] {rel_path} -> {len(points)} chunks (total {total_chunks})")

    try:
        with open(COLLECTION_FILE, "w", encoding="utf-8") as f:
            f.write(collection)
        print(f"  last_collection.txt -> {collection}")
    except Exception as e:
        print(f"  Warning: could not write last_collection.txt: {e}")

    print(f"Done. {total_chunks} chunks in collection '{collection}'.")
    print_local_ingest_summary(
        collection=collection,
        total_chunks=total_chunks,
        files_total=files_total,
        files_indexed_ok=files_indexed_ok,
        files_skipped_read_error=files_skipped_read_error,
        files_skipped_no_chunks=files_skipped_no_chunks,
        files_skipped_embed_error=files_skipped_embed_error,
        files_skipped_embed_mismatch=files_skipped_embed_mismatch,
    )


if __name__ == "__main__":
    main()
