"""
Merge multiple Qdrant collections into one. Use when you have several Swift doc
collections (e.g. docs_swift_org_swift_book + www_swift_org_documentation) and
want a single collection for RAG.

Usage:
  python merge_collections.py

Edits SOURCE_COLLECTIONS and TARGET_COLLECTION below if needed, then run.
Updates last_collection.txt so rag_client and rag_proxy use the new collection.
"""

import os
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.models import Distance

QDRANT_URL = "http://localhost:6333"
SOURCE_COLLECTIONS = [
    "docs_swift_org_swift_book",
    "www_swift_org_documentation",
]
TARGET_COLLECTION = "swift_docs"
COLLECTION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_collection.txt")
BATCH_SIZE = 200


def scroll_all(client: QdrantClient, collection_name: str):
    """Yield all points (id, vector, payload) from a collection."""
    offset = None
    while True:
        result, next_offset = client.scroll(
            collection_name=collection_name,
            limit=BATCH_SIZE,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        for point in result:
            yield point
        if next_offset is None:
            break
        offset = next_offset


def main():
    client = QdrantClient(url=QDRANT_URL)

    # Get vector size from first existing collection (both use 768, cosine)
    info = client.get_collection(SOURCE_COLLECTIONS[0])
    dim = info.config.params.vectors.size
    print(f"Vector config: size={dim}, distance=cosine")

    # Create target collection (recreate so it's empty)
    client.recreate_collection(
        TARGET_COLLECTION,
        vectors_config=qmodels.VectorParams(size=dim, distance=Distance.COSINE),
    )
    print(f"Created collection: {TARGET_COLLECTION}")

    next_id = 1
    total = 0

    for coll_name in SOURCE_COLLECTIONS:
        try:
            coll_info = client.get_collection(coll_name)
            count = coll_info.points_count
            print(f"Reading {coll_name} (~{count} points)...")
        except Exception as e:
            print(f"Skip {coll_name}: {e}")
            continue

        batch = []
        for point in scroll_all(client, coll_name):
            vec = point.vector
            if isinstance(vec, dict):
                vec = next(iter(vec.values()), vec)
            if not isinstance(vec, list):
                continue
            batch.append(
                qmodels.PointStruct(
                    id=next_id,
                    vector=vec,
                    payload=point.payload or {},
                )
            )
            next_id += 1
            if len(batch) >= BATCH_SIZE:
                client.upsert(collection_name=TARGET_COLLECTION, points=batch)
                total += len(batch)
                print(f"  upserted {total} so far...")
                batch = []

        if batch:
            client.upsert(collection_name=TARGET_COLLECTION, points=batch)
            total += len(batch)
        print(f"  done {coll_name}.")

    print(f"Merge complete: {total} points in {TARGET_COLLECTION}")

    try:
        with open(COLLECTION_FILE, "w", encoding="utf-8") as f:
            f.write(TARGET_COLLECTION)
        print(f"Updated {COLLECTION_FILE} -> {TARGET_COLLECTION}")
    except Exception as e:
        print(f"Could not write last_collection.txt: {e}")

    print("You can delete the old collections in Qdrant UI if you want.")


if __name__ == "__main__":
    main()
