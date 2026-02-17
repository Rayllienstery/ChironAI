from flask import Flask, request, Response
import os
import re
import threading
import asyncio
import time
import requests
from urllib.parse import urlparse

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
from crawl4ai.deep_crawling.filters import FilterChain, URLPatternFilter
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy

from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance, PointStruct

from langchain_text_splitters import HTMLSemanticPreservingSplitter

app = Flask(__name__)

# Global variables
log_queue = []
stop_flag = False
id_counter = 1

def log(message):
    print(message)
    log_queue.append(message)

def event_stream():
    global stop_flag
    idx = 0
    while not stop_flag or idx < len(log_queue):
        if idx < len(log_queue):
            data = log_queue[idx]
            idx += 1
            yield f"data: {data}\n\n"
        else:
            time.sleep(0.5)

EMBED_BATCH_SIZE = 8  # Ollama quality degrades with large batches (16+)

def get_embeddings(texts, model_name="nomic-embed-text"):
    if not texts:
        return []
    all_embeddings = []
    try:
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[i : i + EMBED_BATCH_SIZE]
            response = requests.post(
                "http://localhost:11434/api/embed",
                json={"model": model_name, "input": batch},
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            embeddings = data.get("embeddings")
            if embeddings is None:
                raise ValueError("No 'embeddings' key in Ollama response")
            all_embeddings.extend(embeddings)
        return all_embeddings
    except Exception as e:
        log(f"❌ Embedding error: {e}")
        return []

async def run_async_crawl(start_url):
    # Only follow http/https links (skip ms-appinstaller:, mailto:, etc.)
    url_filter = URLPatternFilter(patterns=["http*"])
    strategy = BFSDeepCrawlStrategy(
        max_depth=3,
        include_external=False,
        filter_chain=FilterChain([url_filter]),
    )
    config = CrawlerRunConfig(
        deep_crawl_strategy=strategy,
        scraping_strategy=LXMLWebScrapingStrategy(),
        verbose=False
    )
    log(f"🔍 [1/4] Start deep crawl: {start_url}")
    async with AsyncWebCrawler() as crawler:
        results = await crawler.arun(start_url, config=config)
    return results

def collection_name_from_url(url: str) -> str:
    """Build Qdrant collection name from the starting page URL (host + first path segment)."""
    try:
        p = urlparse(url)
        host = (p.netloc or "web").replace(":", "_")
        path_segments = (p.path or "").strip("/").split("/")
        first = path_segments[0] if path_segments else ""
        slug = host.replace(".", "_")
        if first:
            slug += "_" + re.sub(r"[^a-zA-Z0-9_-]", "_", first)
        slug = re.sub(r"[^a-zA-Z0-9_]", "_", slug)[:63]
        return slug or "webcrawl"
    except Exception:
        return "webcrawl"


COLLECTION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_collection.txt")


def do_crawl(start_url):
    global stop_flag, id_counter
    try:
        results = asyncio.run(run_async_crawl(start_url))
        total = len(results)
        log(f"✅ [1/4] Crawl finished. {total} pages found.")

        qclient = QdrantClient(url="http://localhost:6333")
        coll = collection_name_from_url(start_url)
        try:
            with open(COLLECTION_FILE, "w", encoding="utf-8") as f:
                f.write(coll)
        except Exception:
            pass
        log(f"📦 Collection: {coll}")
        created = False

        for i, result in enumerate(results):
            idx = i + 1
            if not result.success:
                log(f"⚠️ [{idx}/{total}] Failed: {result.url}")
                continue

            url = result.url
            log(f"📄 [{idx}/{total}] [2/4] Processing: {url}")

            html = result.cleaned_html or result.html or ""
            if not html:
                log(f"⛔ [{idx}/{total}] Empty content")
                continue

            splitter = HTMLSemanticPreservingSplitter(
                headers_to_split_on=[('h1','h1'), ('h2','h2'), ('h3','h3')],
                max_chunk_size=1000
            )
            docs = splitter.split_text(html)
            texts = [doc.page_content for doc in docs]

            if not texts:
                log(f"⚠️ [{idx}/{total}] No chunks generated")
                continue

            log(f"✂️ [{idx}/{total}] [3/4] Chunks: {len(texts)}")
            embeddings = get_embeddings(texts)
            if not embeddings:
                log(f"❌ [{idx}/{total}] No embeddings, skipping")
                continue

            if not created:
                dim = len(embeddings[0])
                try:
                    qclient.recreate_collection(coll, vectors_config=VectorParams(size=dim, distance=Distance.COSINE))
                    log(f"📦 Created Qdrant collection '{coll}' (dim={dim})")
                except Exception as e:
                    log(f"❗ Qdrant creation error: {e}")
                created = True

            points = [PointStruct(id=id_counter + j, vector=vec, payload={"url": url, "text": texts[j]}) for j, vec in enumerate(embeddings)]
            id_counter += len(points)

            try:
                qclient.upsert(collection_name=coll, points=points)
                log(f"📥 [{idx}/{total}] [4/4] Indexed {len(points)} vectors")
            except Exception as e:
                log(f"❗ Qdrant insert error: {e}")

    except Exception as e:
        log(f"🔥 Crawler exception: {e}")
    finally:
        stop_flag = True
        log("🏁 Done.")

@app.route("/", methods=["GET"])
def index():
    return '''
    <h1>RAG Краулер</h1>
    <form action="/crawl" method="post">
        URL: <input name="url" size="60">
        <button type="submit">Начать</button>
    </form>
    '''

def normalize_url(url):
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url

@app.route("/crawl", methods=["POST"])
def crawl_route():
    global log_queue, stop_flag, id_counter
    url = request.form.get("url")
    url = normalize_url(url)
    if not url:
        return "❌ No URL"
    log_queue = []
    stop_flag = False
    id_counter = 1
    threading.Thread(target=do_crawl, args=(url,), daemon=True).start()
    return '''
    <h2>Лог</h2>
    <div id="log" style="white-space: pre-line; border: 1px solid gray; padding: 10px; height: 400px; overflow: auto;"></div>
    <script>
    var source = new EventSource("/stream");
    source.onmessage = function(event) {
        var logDiv = document.getElementById("log");
        logDiv.innerHTML += event.data + "\n";
        logDiv.scrollTop = logDiv.scrollHeight;
    };
    </script>
    '''

@app.route("/stream")
def stream():
    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)