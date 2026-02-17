import os
import re
import requests
from qdrant_client import QdrantClient
import httpx

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_EMBED_URL = os.getenv("OLLAMA_EMBED_URL", "http://localhost:11434/api/embed")
QDRANT_URL = "http://localhost:6333"

# Имя embed‑модели в Ollama. Должно совпадать с EMBED_MODEL_NAME в app.py.
# Провайдером эмбеддингов всегда остаётся Ollama; по умолчанию используем mxbai-embed-large.
# При смене модели достаточно поменять EMBED_MODEL_NAME (или RAG_EMBED_MODEL в окружении).
EMBED_MODEL_NAME = os.getenv("RAG_EMBED_MODEL", "mxbai-embed-large")

_COLLECTION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_collection.txt")

_IOS_VERSION_Q_RE = re.compile(r"\biOS\s+(\d+(?:\.\d+)*)", re.IGNORECASE)
_SWIFT_VERSION_Q_RE = re.compile(r"\bSwift\s+(\d+(?:\.\d+)*)", re.IGNORECASE)


def get_collection_name() -> str:
    """Use collection name from last crawl (app.py writes it), else default."""
    try:
        if os.path.isfile(_COLLECTION_FILE):
            with open(_COLLECTION_FILE, encoding="utf-8") as f:
                name = f.read().strip()
            if name:
                return name
    except Exception:
        pass
    return "webcrawl"

# Greetings/filler to strip so retrieval focuses on technical terms
RETRIEVAL_STOP_WORDS = (
    "привет", "здравствуй", "здравствуйте", "расскажи", "расскажите",
    "мне о", "мне про", "пожалуйста", "можно", "хочу узнать", "что такое",
    "как работает", "объясни", "объясните", "давай", "давайте",
)

def _parse_versions_from_question(question: str) -> tuple[list[str], list[str]]:
    """
    Extract explicit iOS/Swift versions mentioned in the question.
    Returns (ios_versions, swift_versions).
    """
    ios = {m.group(1) for m in _IOS_VERSION_Q_RE.finditer(question or "")}
    swift = {m.group(1) for m in _SWIFT_VERSION_Q_RE.finditer(question or "")}
    return sorted(ios), sorted(swift)


def query_for_retrieval(question: str) -> str:
    """Build a query for vector search: drop greetings, keep technical terms, remove code blocks."""
    q_raw = question.strip()
    
    # Удаляем блоки кода (```swift ... ```) — они не нужны для поиска, только увеличивают длину
    import re
    q_raw = re.sub(r'```[\w]*\n.*?```', '', q_raw, flags=re.DOTALL)
    # Удаляем оставшиеся маркеры кода
    q_raw = re.sub(r'```', '', q_raw)
    
    q = q_raw.lower()
    for w in RETRIEVAL_STOP_WORDS:
        q = q.replace(w, " ")
    q = " ".join(q.split()).strip().lstrip(".,;:!? ")
    if len(q) < 3:
        return "Swift documentation " + q_raw[:400]
    out = q if len(q) >= 5 else (q_raw + " " + q)
    # Bias retrieval toward the requested UI framework when clearly stated
    if "uikit" in q and "swiftui" not in q:
        out = out + " UIKit UIViewController UIView"
    elif "swiftui" in q and "uikit" not in q:
        out = out + " SwiftUI View"
    # For version questions, bias retrieval toward version/release chunks
    ios_q, swift_q = _parse_versions_from_question(question)
    if ios_q or swift_q or "версия" in q_raw.lower() or "version" in q_raw.lower() or "последняя" in q_raw.lower():
        extra_parts: list[str] = []
        for v in swift_q:
            extra_parts.append(f"Swift {v} version RELEASE")
        for v in ios_q:
            extra_parts.append(f"iOS {v} version RELEASE")
        if not extra_parts:
            extra_parts.append("Swift version release number RELEASE")
        out = out + " " + " ".join(extra_parts)
    
    # Финальное ограничение длины для эмбеддинга (модель имеет лимит ~512 токенов)
    if len(out) > 400:
        out = out[:400]
    return out


def is_version_question(question: str) -> bool:
    """True if the question is about Swift/iOS version / latest release."""
    q = question.lower()
    has_keywords = "версия" in q or "version" in q or "последняя" in q or "latest" in q
    ios_q, swift_q = _parse_versions_from_question(question)
    return has_keywords or bool(ios_q) or bool(swift_q)


def embed(text: str) -> list[float]:
    """
    Embed a single query string via Ollama.

    Единственная точка, которую нужно менять при смене embed‑модели:
    - EMBED_MODEL_NAME / OLLAMA_EMBED_URL (или RAG_EMBED_MODEL / OLLAMA_EMBED_URL в окружении);
    - при необходимости — формат разбора ответа.

    Ожидаемый формат ответа Ollama /api/embed:
    {
      "embeddings": [
        [float, float, ...]
      ]
    }
    """
    # Ограничиваем длину текста для эмбеддинга (модель mxbai-embed-large имеет лимит ~512 токенов)
    # Берем первые 400 символов, чтобы оставить запас (примерно 100-150 токенов)
    MAX_EMBED_TEXT_LENGTH = 400
    if len(text) > MAX_EMBED_TEXT_LENGTH:
        text = text[:MAX_EMBED_TEXT_LENGTH]
    
    try:
        resp = requests.post(
            OLLAMA_EMBED_URL,
            json={"model": EMBED_MODEL_NAME, "input": text},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        embeddings = data.get("embeddings")
        if not embeddings:
            raise ValueError(f"No 'embeddings' key in Ollama response: {data}")
        if isinstance(embeddings, list) and len(embeddings) > 0:
            # Если вернулся массив эмбеддингов, берем первый
            return embeddings[0] if isinstance(embeddings[0], list) else embeddings
        raise ValueError(f"Unexpected embeddings format: {embeddings}")
    except requests.exceptions.HTTPError as e:
        # Логируем детали ошибки для отладки
        error_detail = ""
        try:
            error_detail = f", response: {e.response.text[:200]}"
        except:
            pass
        raise RuntimeError(
            f"Ollama embed API error (model={EMBED_MODEL_NAME}, url={OLLAMA_EMBED_URL}, "
            f"text_length={len(text)}{error_detail}): {e}"
        ) from e

TOP_K = 8  # how many candidates we ask Qdrant for per vector search

# Doc types preferred for QA: conceptual > overview > tutorial > documentation/howto > release_notes/news.
# Used for Qdrant pre-filter (metadata-first) and for scoring/ordering.
DOC_TYPE_PREFERRED_FOR_QA = (
    "conceptual",
    "overview",
    "tutorial",
    "documentation",
    "howto",
)
DOC_TYPE_WEIGHT = {
    "conceptual": 3,
    "overview": 2,
    "tutorial": 1,
    "documentation": 1,
    "howto": 1,
    "release_notes": -2,
    "news": -2,
}

# Keywords that suggest the user needs more chunks (compare, explain fully, list all, lifecycle).
MULTI_CHUNK_KEYWORDS = (
    "compare", "comparison", "сравни", "сравнение", "difference", "разница",
    "explain fully", "fully explain", "подробно объясни", "lifecycle", "жизненный цикл",
    "all ways", "all options", "все способы", "list all", "перечисли все",
    "step by step", "пошагово", "overview of", "обзор",
)

MULTI_CHUNK_TOP_K = 16
MULTI_CHUNK_FINAL_K = 8


def _build_qdrant_filter(question: str) -> dict | None:
    """
    Build Qdrant filter for metadata-first retrieval.
    For non-version questions, restrict to preferred doc_type so semantic search
    runs inside documentation/conceptual/tutorial space (avoids unrelated/news).
    Returns None when no filter should be applied (e.g. version questions).
    """
    if is_version_question(question):
        return None
    # Prefer doc_type in preferred set; use "should" so points match if doc_type is any of these.
    conditions = [
        {"key": "doc_type", "match": {"value": dt}}
        for dt in DOC_TYPE_PREFERRED_FOR_QA
    ]
    if not conditions:
        return None
    return {"should": conditions}


def need_more_chunks(question: str) -> bool:
    """True if the question likely needs multiple chunks (compare, explain fully, list, lifecycle)."""
    q = (question or "").lower()
    return any(kw in q for kw in MULTI_CHUNK_KEYWORDS)


def search(qdrant_client, vector, top_k=TOP_K, filter_dict: dict | None = None):
    coll = get_collection_name()
    body = {
        "vector": vector,
        "limit": top_k,
        "with_payload": True,
    }
    if filter_dict:
        body["filter"] = filter_dict
    response = httpx.post(f"{QDRANT_URL}/collections/{coll}/points/search", json=body)
    response.raise_for_status()
    return response.json()["result"]


RERANK_MAX_CANDIDATES = 12  # сколько кандидатов запрашиваем из Qdrant для rerank (для обычных вопросов)
FINAL_CONTEXT_K = 4  # сколько чанков реально пойдёт в prompt


def rerank(question: str, hits: list[dict]) -> list[dict]:
    """
    Re-rank Qdrant hits for a question using an LLM from Ollama.

    Мы берём top-N кандидатов (RERANK_MAX_CANDIDATES), показываем их модели devstral-ios
    с коротким prompt'ом и просим вернуть JSON-массив номеров кандидатов в порядке
    убывания релевантности, например: [2, 1, 3].

    Если что-то пошло не так (ошибка сети, невалидный JSON и т.п.), возвращаем hits
    в исходном порядке без изменений.
    """
    if not hits:
        return hits

    # Ограничимся первыми N кандидатами, чтобы не раздувать prompt.
    candidates = hits[:RERANK_MAX_CANDIDATES]

    # Готовим компактные тексты: первые ~300 символов из payload["text"].
    def _shorten(text: str, max_len: int = 300) -> str:
        t = (text or "").strip()
        if len(t) <= max_len:
            return t
        return t[: max_len - 1] + "…"

    lines: list[str] = []
    for idx, hit in enumerate(candidates, start=1):
        payload = hit.get("payload") or {}
        txt = _shorten(payload.get("text", ""))
        lines.append(f"{idx}: {txt}")

    numbered_chunks = "\n\n".join(lines)

    rerank_prompt = f"""У тебя есть вопрос и несколько фрагментов документации.
Твоя задача — отсортировать фрагменты по релевантности к вопросу.

Вопрос:
{question}

Фрагменты (каждый с номером):
{numbered_chunks}

Ответь ТОЛЬКО одним JSON-массивом номеров фрагментов в порядке убывания релевантности.
Примеры допустимых ответов:
[2, 1, 3]
[1, 2]
Если какие‑то номера отсутствуют, просто не включай их.
Не добавляй никакого текста до или после JSON."""

    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": "devstral-ios",
                "prompt": rerank_prompt,
                "stream": False,
                "options": {
                    "num_predict": 256,
                },
            },
            timeout=120,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()
    except Exception:
        # Если не удалось запросить LLM — оставляем исходный порядок.
        return hits

    import json

    order: list[int] = []
    try:
        # Пытаемся распарсить ответ как чистый JSON-массив.
        order = json.loads(raw)
        if not isinstance(order, list):
            raise ValueError("rerank response is not a JSON list")
    except Exception:
        # Если модель вернула что‑то не‑JSON, не ломаем пайплайн.
        return hits

    # Преобразуем список номеров (1‑based) в новый порядок кандидатов.
    indexed = {i + 1: hit for i, hit in enumerate(candidates)}
    new_order: list[dict] = []
    added_ids = set()
    for n in order:
        hit = indexed.get(n)
        if hit is not None and id(hit) not in added_ids:
            new_order.append(hit)
            added_ids.add(id(hit))

    # Добавляем все оставшиеся кандидаты, которые не попали в JSON-ответ, в исходном порядке.
    for hit in candidates:
        if id(hit) not in added_ids:
            new_order.append(hit)

    # Остальные (за пределами RERANK_MAX_CANDIDATES) просто дозаполняем как есть.
    if len(hits) > len(candidates):
        new_order.extend(hits[len(candidates) :])

    return new_order


def apply_rerank_and_cut(
    question: str, hits: list[dict], final_k: int | None = None
) -> list[dict]:
    """
    Apply LLM-based rerank and keep only the top final_k hits (default FINAL_CONTEXT_K).

    Also annotates each hit with rerank_score = 1 / rank for combining with
    Qdrant score and doc_type weighting.
    """
    if not hits:
        return []
    k = final_k if final_k is not None else FINAL_CONTEXT_K

    reranked = rerank(question, hits)
    for rank, hit in enumerate(reranked, start=1):
        hit["rerank_score"] = 1.0 / rank

    return reranked[:k]


def _doc_type_priority(hit: dict) -> int:
    """
    Doc-type weighting for QA: conceptual > overview > tutorial > documentation/howto > release_notes/news.
    Used to order candidates before rerank so title-like queries don't land on unrelated pages.
    """
    payload = hit.get("payload") or {}
    doc_type = (payload.get("doc_type") or "documentation").lower()
    return DOC_TYPE_WEIGHT.get(doc_type, 0)


def search_rag(question: str, top_k: int | None = None) -> list:
    """
    Run RAG retrieval for a question. Uses metadata-first filter (doc_type) when not
    a version question; applies doc_type weighting; uses more chunks for compare/explain-full
    queries. For version questions, runs a second version-focused search and merges.
    
    Args:
        question: The question to search for
        top_k: Number of candidates per vector search. If None, uses TOP_K or MULTI_CHUNK_TOP_K for broad queries.
    """
    if top_k is None:
        top_k = MULTI_CHUNK_TOP_K if need_more_chunks(question) else TOP_K
    search_query = query_for_retrieval(question)
    vec = embed(search_query)
    filter_dict = _build_qdrant_filter(question)
    k = max(top_k, RERANK_MAX_CANDIDATES) if not is_version_question(question) else top_k
    results = search(None, vec, top_k=k, filter_dict=filter_dict)
    # If metadata filter returned nothing, retry without filter (e.g. collection may not use doc_type).
    if filter_dict and not results:
        results = search(None, vec, top_k=k, filter_dict=None)

    final_k = MULTI_CHUNK_FINAL_K if need_more_chunks(question) else FINAL_CONTEXT_K

    if not is_version_question(question):
        results.sort(key=_doc_type_priority, reverse=True)
        return apply_rerank_and_cut(question, results, final_k=final_k)

    ios_q, swift_q = _parse_versions_from_question(question)
    extra_results: list = []

    # Extra focused searches for explicit versions mentioned in the question
    for v in swift_q:
        qv = f"Swift {v} version RELEASE"
        vec_v = embed(qv)
        extra_results.extend(search(None, vec_v, top_k=6))
    for v in ios_q:
        qv = f"iOS {v} version RELEASE"
        vec_v = embed(qv)
        extra_results.extend(search(None, vec_v, top_k=6))

    # Fallback generic version query if nothing explicit parsed
    if not extra_results:
        vec_version = embed("Swift version release number RELEASE")
        extra_results.extend(search(None, vec_version, top_k=8))

    # Merge, keeping uniqueness
    seen_ids = {r["id"] for r in results}
    for r in extra_results:
        if r["id"] not in seen_ids:
            results.append(r)
            seen_ids.add(r["id"])

    # Re-rank: boost chunks whose payload ios_versions/swift_versions contains the asked version(s)
    ios_set = set(ios_q)
    swift_set = set(swift_q)

    def _score(hit) -> int:
        payload = hit.get("payload") or {}
        ios_payload = set(payload.get("ios_versions") or [])
        swift_payload = set(payload.get("swift_versions") or [])
        score = 0
        if ios_set and ios_payload & ios_set:
            score += 3
        if swift_set and swift_payload & swift_set:
            score += 3
        # small bonus if any version at all is present when we asked about versions
        if (ios_set or swift_set) and (ios_payload or swift_payload):
            score += 1
        return score

    if ios_set or swift_set:
        results.sort(key=lambda h: _score(h), reverse=True)
        results.sort(key=_doc_type_priority, reverse=True)

    return results[:final_k]


def ask_model(prompt, context):
    full_prompt = f"""Ты — эксперт по Swift. Ниже — актуальная документация, проиндексированная недавно (RAG). Игнорируй дату своих знаний: отвечай ТОЛЬКО по этому тексту.

Правила:
- Отвечай строго на основе фрагментов документации ниже.
- Если в тексте нет точного номера версии (например 6.2.3), используй ближайшую по смыслу (Swift 6, текущая версия и т.д.).
- Не отказывайся отвечать из-за «устаревших знаний» — контекст ниже и есть твой источник.
- Если в контексте действительно нет ответа, напиши: «В приведённых фрагментах этого нет».

Запрещено:
- делать общие выводы
- перечислять «улучшения», «новые функции», «повышенную безопасность»
- использовать маркетинговые формулировки

Разрешено ТОЛЬКО:
- конкретные API
- названия классов, протоколов, атрибутов
- @available / iOS version markers


========= ДОКУМЕНТАЦИЯ =========
{context}
=================================

Вопрос: {prompt}
Ответ (только по документации выше):"""
    r = requests.post(
        OLLAMA_URL,
        json={
            "model": "devstral-ios",
            "prompt": full_prompt,
            "stream": False,
            "options": {
                # 512 токенов достаточно для: краткий ответ + 2–5 пунктов + итог.
                "num_predict": 512,
            },
        },
    )
    r.raise_for_status()
    return r.json()["response"]

def main():
    question = input("🧠 Вопрос: ").strip()
    if not question:
        print("Вопрос не задан.")
        return
    qdrant = QdrantClient(url=QDRANT_URL)
    results = search_rag(question)
    if not results:
        print("В базе нет подходящих фрагментов. Сначала запустите краулер (app.py).")
        return

    context = "\n\n".join([hit["payload"].get("text", "") for hit in results])
    answer = ask_model(question, context)

    print("\n🤖 Ответ модели:")
    print(answer)

if __name__ == "__main__":
    main()