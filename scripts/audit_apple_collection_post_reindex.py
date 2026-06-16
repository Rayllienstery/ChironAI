"""Post-reindex quality check: scroll stats + 12 hybrid probes for Apple_Collection.

This script performs a comprehensive audit of the 'Apple_Collection' in Qdrant
after a reindexing operation. It calculates statistics about the collection
(source distribution, fill percentages, duplicates) and runs a set of 12
predefined hybrid search probes to verify retrieval quality.

Usage:
    python scripts/audit_apple_collection_post_reindex.py
"""

from __future__ import annotations

import collections
import hashlib
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "Core"))
sys.path.insert(0, str(ROOT / "CoreModules" / "RagService"))

import httpx  # noqa: E402

from config import get_ollama_embed_model, get_qdrant_url  # noqa: E402
from infrastructure.rag.sparse_text import normalize_text_for_sparse, text_to_sparse_vector  # noqa: E402

COLL = "Apple_Collection"
BASE = get_qdrant_url().rstrip("/")

PROBES = [
    ("P01", "What is the Observation macro and how do you use it with SwiftUI?", "apple_documentation"),
    ("P02", "How do diffable data sources work with UITableView and concurrency?", "apple_documentation"),
    ("P03", "Explain actor isolation and Sendable in Swift concurrency", "apple_documentation"),
    ("P04", "What are win-back offers in StoreKit subscriptions?", "wwdc_sessions_2019_plus"),
    ("P05", "How does NavigationStack work in SwiftUI?", "apple_documentation"),
    ("P06", "SwiftUI @State @Binding and Observable state management", "apple_documentation"),
    ("P07", "UIApplication lifecycle and app states", "apple_documentation"),
    ("P08", "URLSession networking in Foundation", "apple_documentation"),
    ("P09", "Combine publishers and subscribers", "apple_documentation"),
    ("P10", "UIViewController lifecycle viewDidLoad", "apple_documentation"),
    ("P11", "Swift async await concurrency", "apple_documentation"),
    ("P12", "SwiftUI App and Scene lifecycle", "apple_documentation"),
]


def scroll_stats() -> dict:
    sources: collections.Counter[str] = collections.Counter()
    scopes: collections.Counter[str] = collections.Counter()
    symbols_empty = 0
    lens: list[int] = []
    dups: collections.Counter[str] = collections.Counter()
    total = 0
    offset = None
    while True:
        body: dict = {"limit": 1000, "with_payload": True, "with_vector": False}
        if offset is not None:
            body["offset"] = offset
        res = httpx.post(
            f"{BASE}/collections/{COLL}/points/scroll",
            json=body,
            timeout=120,
        ).json()["result"]
        pts = res.get("points") or []
        if not pts:
            break
        for p in pts:
            total += 1
            pl = p.get("payload") or {}
            sources[pl.get("source") or "?"] += 1
            ds = (pl.get("doc_scope") or "").strip()
            scopes[ds or "empty"] += 1
            if not (pl.get("symbol") or "").strip():
                symbols_empty += 1
            lens.append(len(pl.get("text") or ""))
            dups[hashlib.sha256((pl.get("text") or "").encode()).hexdigest()[:16]] += 1
        offset = res.get("next_page_offset")
        if offset is None:
            break
    dup = sum(c - 1 for c in dups.values() if c > 1)
    short = sum(1 for L in lens if L < 300)
    return {
        "total": total,
        "sources": dict(sources),
        "doc_scope": dict(scopes),
        "doc_scope_filled_pct": round(100 * (total - scopes["empty"]) / total, 2) if total else 0,
        "symbol_filled_pct": round(100 * (total - symbols_empty) / total, 2) if total else 0,
        "avg_len": round(statistics.mean(lens), 1) if lens else 0,
        "short_lt_300_pct": round(100 * short / total, 2) if total else 0,
        "dup_pct": round(100 * dup / total, 2) if total else 0,
    }


def hybrid_query(query: str, model: str, limit: int = 5) -> list[dict]:
    v = httpx.post(
        "http://localhost:11434/api/embed",
        json={"model": model, "input": [query]},
        timeout=120,
    ).json()["embeddings"][0]
    i, val = text_to_sparse_vector(normalize_text_for_sparse(query))
    body = {
        "prefetch": [
            {"query": v, "using": "dense", "limit": 8},
            {"query": {"indices": i, "values": val}, "using": "sparse", "limit": 8},
        ],
        "query": {"fusion": "rrf"},
        "limit": limit,
        "with_payload": True,
    }
    pts = httpx.post(
        f"{BASE}/collections/{COLL}/points/query",
        json=body,
        timeout=60,
    ).json()["result"]["points"]
    out = []
    for p in pts:
        pl = p.get("payload") or {}
        out.append(
            {
                "score": p.get("score"),
                "source": pl.get("source"),
                "url": (pl.get("url") or "")[:100],
                "text": (pl.get("text") or "")[:120],
            }
        )
    return out


def verdict(expected: str, hits: list[dict]) -> str:
    sources = [h.get("source") for h in hits]
    if not sources:
        return "FAIL"
    if sources[0] == expected:
        return "PASS"
    if expected in sources:
        return "PARTIAL"
    return "FAIL"


def main() -> int:
    model = get_ollama_embed_model()
    print("embed_model:", model)
    stats = scroll_stats()
    print("\n=== SCROLL STATS ===")
    print(json.dumps(stats, indent=2))

    results = []
    for pid, query, expected in PROBES:
        hits = hybrid_query(query, model)
        v = verdict(expected, hits)
        results.append(
            {
                "id": pid,
                "expected": expected,
                "verdict": v,
                "top1_source": hits[0]["source"] if hits else None,
                "top1_url": hits[0]["url"] if hits else None,
                "top5_sources": [h["source"] for h in hits],
                "hits": hits,
            }
        )

    pass_n = sum(1 for r in results if r["verdict"] == "PASS")
    part_n = sum(1 for r in results if r["verdict"] == "PARTIAL")
    fail_n = sum(1 for r in results if r["verdict"] == "FAIL")

    print("\n=== 12 PROBES ===")
    for r in results:
        print(
            f"{r['id']} {r['verdict']:7} exp={r['expected']:28} "
            f"top1={r['top1_source']} {r['top1_url']}"
        )
    print(f"\nSUMMARY: PASS={pass_n} PARTIAL={part_n} FAIL={fail_n}")

    out_path = ROOT / "logs" / "apple_collection_post_reindex_audit.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"embed_model": model, "stats": stats, "probes": results}, indent=2),
        encoding="utf-8",
    )
    print("written:", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
