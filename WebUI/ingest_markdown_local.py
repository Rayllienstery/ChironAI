"""
Ingest local Markdown files (e.g. from Apple-Developer-Documentation-Offline-Archive)
into Qdrant using Ollama embedding model.

This script uses LangChain RecursiveCharacterTextSplitter (chunk_size, chunk_overlap).
It does NOT use the domain chunking (section_path, code/table boundaries, <!-- meta -->
parsing). For Apple documentation, the recommended path is:
- WebUI app: python app.py index (or "Index" from UI), or
- WebUI API: "Create collection from sources" (RagTab),
which use domain.services.chunking with section_path, meta parsing, and unified config.

Embedding model and endpoint are shared with the main RAG pipeline:
- Model name: taken from RAG_EMBED_MODEL (defaults to "mxbai-embed-large").
- Embed URL: taken from OLLAMA_EMBED_URL (defaults to "http://localhost:11434/api/embed").

To switch to another embedding model or Ollama host, change ONLY these env vars –
the rest of the pipeline (including rag_client.py and app.py) will keep working.

Usage (PowerShell):

  cd "c:\\Users\\Raylee\\AI\\WebUI"
  python .\\ingest_markdown_local.py `
    "c:\\Users\\Raylee\\AI\\Apple-Developer-Documentation-Offline-Archive-main\\markdown" `
    --collection apple_docs

Requirements:
  - Ollama running with the embedding model referenced by RAG_EMBED_MODEL
  - pip install qdrant-client langchain-text-splitters requests
"""

import os
import re
import sys
from pathlib import Path
from typing import List

import requests
from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance, PointStruct
from langchain_text_splitters import RecursiveCharacterTextSplitter


# Shared embedding configuration with app.py / rag_client.py
OLLAMA_EMBED_URL = os.getenv("OLLAMA_EMBED_URL", "http://localhost:11434/api/embed")
EMBED_MODEL_NAME = os.getenv("RAG_EMBED_MODEL", "mxbai-embed-large")
EMBED_BATCH_SIZE = 32
# Chunk size ~1200 chars (~300–400 tokens) for precise RAG over Apple docs; 12% overlap.
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150
QDRANT_URL = "http://localhost:6333"
COLLECTION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_collection.txt")


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
        resp = requests.post(
            OLLAMA_EMBED_URL,
            json={"model": EMBED_MODEL_NAME, "input": batch},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
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
    if len(sys.argv) < 2:
        print("Usage: python ingest_markdown_local.py <path_to_markdown_folder> [--collection NAME]")
        print(
            "Example: python ingest_markdown_local.py "
            "C:\\path\\to\\Apple-Developer-Documentation-Offline-Archive\\markdown --collection apple_docs"
        )
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

    # Splitting order: section headers first, then code block boundaries (avoid cutting inside ```),
    # then paragraphs and lines. Keeps Apple Docs code samples intact.
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n## ", "\n### ", "\n#### ", "\n```\n", "\n\n", "\n", " "],
    )

    print(f"Using Ollama embedding model: {EMBED_MODEL_NAME}")
    # Resolve embedding dimension via one short request.
    dim_resp = requests.post(
        OLLAMA_EMBED_URL,
        json={"model": EMBED_MODEL_NAME, "input": "."},
        timeout=60,
    )
    dim_resp.raise_for_status()
    dim = len(dim_resp.json()["embeddings"][0])
    print(f"Embedding dimension: {dim}")

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

        chunks = splitter.split_text(content)
        if not chunks:
            continue

        texts = [c.strip() for c in chunks if c.strip()]
        if not texts:
            continue

        embeddings = get_embeddings(texts)
        if len(embeddings) != len(texts):
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
                payload={"text": texts[j], "source": rel_path},
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

