"""Part 2: delete Apple_Collection, recreate from all 7 sources, poll until done."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "Core"))

from config import get_indexing_int, get_webui_port  # noqa: E402
from core.contracts.webui_api import WEBUI_URL_PREFIX  # noqa: E402

SOURCE_IDS = [
    "apple_documentation",
    "wwdc_sessions_2019_plus",
    "hws_swift",
    "objc_io_issues",
    "swiftbysundell_articles",
    "pointfree_collections",
    "swift_book",
]
COLLECTION = "Apple_Collection"
EMBED_MODEL = os.environ.get("RAG_EMBED_MODEL", "mxbai-embed-large").strip()


def _request(method: str, path: str, body: dict | None = None, timeout: float = 120) -> tuple[int, dict]:
    port = get_webui_port()
    url = f"http://127.0.0.1:{port}{WEBUI_URL_PREFIX}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            payload = json.loads(raw) if raw else {"error": str(e)}
        except json.JSONDecodeError:
            payload = {"error": raw or str(e)}
        return e.code, payload


def _wait_server(max_sec: float = 90) -> None:
    deadline = time.time() + max_sec
    while time.time() < deadline:
        try:
            code, _ = _request("GET", "/crawler/sources", timeout=5)
            if code == 200:
                print("WebUI ready.")
                return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("WebUI did not become ready in time")


def main() -> int:
    print(f"Using embed model: {EMBED_MODEL}")
    _wait_server()

    print(f"DELETE /rag/collections/{COLLECTION}")
    code, payload = _request("DELETE", f"/rag/collections/{COLLECTION}", timeout=60)
    print("  ", code, payload)

    body = {
        "collection_name": COLLECTION,
        "source_ids": SOURCE_IDS,
        "chunk_max_size": get_indexing_int("chunk_max_size", 1200),
        "chunk_min_size": get_indexing_int("chunk_min_size", 300),
        "rag_embed_model": EMBED_MODEL,
    }
    print("POST /crawler/create-collection", body)
    code, payload = _request("POST", "/crawler/create-collection", body=body, timeout=60)
    if code not in (200, 202):
        print("create-collection failed:", code, payload)
        return 1
    job_id = payload.get("job_id")
    if not job_id:
        print("No job_id:", payload)
        return 1
    print("Job started:", job_id)

    while True:
        time.sleep(15)
        code, st = _request("GET", f"/crawler/create-collection-status/{job_id}", timeout=30)
        if code != 200:
            print("status error", code, st)
            continue
        status = st.get("status")
        processed = st.get("processed_pages", 0)
        total = st.get("total_pages", 0)
        indexed = st.get("indexed_pages", 0)
        chunks = st.get("total_chunks", 0)
        phase = st.get("current_phase", "")
        print(
            f"  {status} {processed}/{total} pages indexed={indexed} chunks={chunks} phase={phase}",
            flush=True,
        )
        if status in ("success", "failed", "cancelled"):
            print(json.dumps(st, indent=2))
            return 0 if status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
