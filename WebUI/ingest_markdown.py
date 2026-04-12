r"""
Ingest local Markdown files (e.g. from Apple-Developer-Documentation-Offline-Archive)
into Qdrant: semantic chunk (domain.services.chunking) -> embed (Ollama) -> upsert.

Payload: text, source, path, section_path, section_path_joined — aligned with the main
RAG indexer fields used for retrieval and optional Qdrant filters.

Chunk sizes come from config indexing (chunk_max_size, chunk_min_size), same as WebUI
"Create collection from sources".

Embedding model and endpoint are shared with the main RAG pipeline:
- Model name: ``config.get_ollama_embed_model()`` (env ``RAG_EMBED_MODEL`` + ``config/models.yaml``).
  If ``config`` cannot be imported, set ``RAG_EMBED_MODEL`` (required in that case).
- Embed URL: ``config.get_ollama_embed_url()`` or env ``OLLAMA_EMBED_URL``.

Usage:
  python ingest_markdown.py C:\path\to\Apple-Developer-Documentation-Offline-Archive\markdown
  python ingest_markdown.py C:\path\to\markdown --collection apple_docs
"""

import os
import re
import sys
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WEBUI_DIR = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if _WEBUI_DIR not in sys.path:
    sys.path.insert(0, _WEBUI_DIR)

from infrastructure.ollama.cli_runner import OllamaInteractorCliError, invoke_embed

from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance, PointStruct

from ingest_markdown_common import chunks_for_local_ingest, qdrant_payload_local

try:
    from config import get_ollama_embed_model, get_ollama_embed_url
except ImportError:
    get_ollama_embed_model = lambda: (os.getenv("RAG_EMBED_MODEL") or "").strip()  # type: ignore[assignment]
    get_ollama_embed_url = lambda: os.getenv(  # type: ignore[assignment]
        "OLLAMA_EMBED_URL", "http://localhost:11434/api/embed"
    )

# Shared embedding configuration with app.py / rag_client.py
QDRANT_URL = "http://localhost:6333"
OLLAMA_EMBED_URL = get_ollama_embed_url()
EMBED_MODEL_NAME = get_ollama_embed_model()
EMBED_BATCH_SIZE = 8
COLLECTION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_collection.txt")


def get_embeddings(texts: list[str], model_name: str = EMBED_MODEL_NAME) -> list:
    """
    Call Ollama /api/embed in batches; returns list of vectors (same order as texts).

    This is the ONLY place that knows about the embedding model/endpoint for local
    markdown ingestion. To switch models/endpoints:
    - Update RAG_EMBED_MODEL / OLLAMA_EMBED_URL env vars; OR
    - Pass a specific `model_name` argument if you really need a one-off override.

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
    out: list = []
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i : i + EMBED_BATCH_SIZE]
        try:
            data = invoke_embed(
                {
                    "url": OLLAMA_EMBED_URL,
                    "json": {"model": model_name, "input": batch},
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
        out.extend(vectors)
    return out


def collection_name_from_path(root: Path) -> str:
    """Derive Qdrant collection name from markdown root path (e.g. .../markdown -> markdown)."""
    name = root.name if root.name else "markdown"
    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", name)[:63]
    return slug or "markdown"


def main():
    if len(sys.argv) < 2:
        print("Usage: python ingest_markdown.py <path_to_markdown_folder> [--collection NAME]")
        print("Example: python ingest_markdown.py C:\\path\\to\\Apple-Developer-Documentation-Offline-Archive\\markdown")
        sys.exit(1)

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

    qclient = QdrantClient(url=QDRANT_URL)
    point_id = 1
    created = False
    total_chunks = 0

    for idx, md_path in enumerate(md_files, 1):
        try:
            content = md_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"  Skip {md_path}: {e}")
            continue

        pairs = chunks_for_local_ingest(content)
        if not pairs:
            continue

        texts = [t for t, _ in pairs]
        embeddings = get_embeddings(texts)
        if len(embeddings) != len(texts):
            print(f"  Embedding count mismatch for {md_path}, skip")
            continue

        if not created:
            dim = len(embeddings[0])
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
        if idx % 50 == 0 or idx == len(md_files):
            print(f"  [{idx}/{len(md_files)}] {rel_path} -> {len(points)} chunks (total {total_chunks})")

    try:
        with open(COLLECTION_FILE, "w", encoding="utf-8") as f:
            f.write(collection)
        print(f"  last_collection.txt -> {collection}")
    except Exception as e:
        print(f"  Warning: could not write last_collection.txt: {e}")

    print(f"Done. {total_chunks} chunks in collection '{collection}'.")


if __name__ == "__main__":
    main()
