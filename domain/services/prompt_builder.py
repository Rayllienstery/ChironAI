"""
Domain-level prompt building for RAG chat.

Pure logic for:
- Extracting last user message from OpenAI-format messages.
- Determining reasoning level (explicit or automatic for GPT-OSS).
- Filtering chunks by framework (UIKit vs SwiftUI) when user asks for one.
- Building the context block and system content (prefix + context + suffix + reasoning).
No HTTP or infrastructure; callers supply prefix/suffix and config thresholds.
"""

from __future__ import annotations

from typing import Any

from domain.services.retrieval import extract_target_concepts_for_coverage
from domain.value_objects import REASONING_LEVEL_VALUES, ReasoningLevel

# Models that support reasoning levels (GPT-OSS family).
REASONING_LEVEL_MODELS = ("gpt-oss", "gpt-oss-20b", "gpt-oss-120b")

# User task vs retrieved docs: keep English headings stable for model compliance.
_TASK_PRIORITY_BLOCK = """## PRIMARY TASK (highest priority)

Your **only** primary input for this turn is the user's latest message and any material attached in that same turn (files, selections, paths, pasted code). Answer **that** task first: explain, edit, refactor, or reason about **that** content.

Blocks below labeled supplementary knowledge or web supplement come from **retrieval** (indexed documentation). For the topics they cover, treat that material as **accurate (source of truth)** when you rely on it. It is **not** the user's attachment and may be **off-topic** for their task—you are **not required** to use it in your answer; omit it whenever it does not help. Never respond as if a retrieved excerpt were the user's code or the object of their question.

If retrieval conflicts with the user's wording or attachments, **prefer the user**.

"""

_RAG_KNOWLEDGE_BEGIN = "=== BEGIN SUPPLEMENTARY KNOWLEDGE (indexed docs — not the user task or attached file) ==="
_RAG_KNOWLEDGE_END = "=== END SUPPLEMENTARY KNOWLEDGE ==="

_RAG_TRUST_AND_OPTIONAL_USE = (
    "These excerpts are grounded in retrieved documentation: where they apply, treat them as **trustworthy** "
    "for what they describe. They may still be **irrelevant** to the user's question—you are **not obliged** "
    "to cite or use them; answer from the user's message and attachments when that is enough.\n\n"
)

_RAG_RETRIEVAL_REMINDER = (
    "Reminder: center your answer on the user's message and attachments; use the retrieved text only when it helps.\n"
)

_WEB_SUPPLEMENT_BEGIN = "=== BEGIN WEB SUPPLEMENT (optional background) ==="
_WEB_SUPPLEMENT_END = "=== END WEB SUPPLEMENT ==="

COMPLEX_REASONING_KEYWORDS = [
    "refactor", "optimize", "debug", "analyze", "design", "architecture",
    "redesign", "restructure", "improve performance", "fix memory leak",
    "concurrency", "race condition", "thread safety", "actor isolation",
]


def last_user_content(messages: list[dict[str, Any]]) -> str:
    """
    Extract text from the last user message.
    content may be string or array of parts (OpenAI format).
    """
    for m in reversed(messages or []):
        if m.get("role") == "user":
            content = m.get("content")
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                parts = [p.get("text", "") for p in content if p.get("type") == "text"]
                return " ".join(parts).strip()
            return ""
    return ""


def determine_reasoning_level(
    user_message: str,
    context_length: int,
    model_name: str,
    explicit: str | None = None,
) -> ReasoningLevel | None:
    """
    Determine reasoning level for GPT-OSS models.

    Priority: 1) explicit user request, 2) first char "!" -> high,
    3) short queries (< 100 tokens) -> low, 4) complex keywords -> high, 5) default medium.
    Returns None if model does not support reasoning levels.
    """
    if explicit:
        level = explicit.strip().lower()
        if level in REASONING_LEVEL_VALUES:
            return level
        return "medium"
    if not any(kw in (model_name or "").lower() for kw in REASONING_LEVEL_MODELS):
        return None
    msg = (user_message or "").strip()
    msg_lower = msg.lower()
    if "reasoning:high" in msg_lower or "reasoning: high" in msg_lower:
        return "high"
    if "reasoning:low" in msg_lower or "reasoning: low" in msg_lower:
        return "low"
    if "reasoning:medium" in msg_lower or "reasoning: medium" in msg_lower:
        return "medium"
    if msg and msg[0] == "!":
        return "high"
    if context_length < 100:
        return "low"
    if any(kw in msg_lower for kw in COMPLEX_REASONING_KEYWORDS):
        return "high"
    return "medium"


def framework_filter(query: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    When the user clearly asks for one UI framework, keep only chunks from that framework.
    Uses url, path, doc_type, and source to detect UIKit vs SwiftUI docs. Returns all results if no clear preference.
    """
    q = (query or "").lower()
    uikit_asked = "uikit" in q and "swiftui" not in q
    swiftui_asked = "swiftui" in q and "uikit" not in q
    if not uikit_asked and not swiftui_asked:
        return list(results)
    needle = "uikit" if uikit_asked else "swiftui"
    filtered = []
    for h in results:
        payload = h.get("payload") or {}
        url = (payload.get("url") or "").lower()
        path = (payload.get("path") or "").lower()
        doc_type = (payload.get("doc_type") or "").lower()
        source = (payload.get("source") or "").lower()
        if needle in url or needle in path or needle in doc_type or needle in source:
            filtered.append(h)
    return filtered if filtered else list(results)


def _truncate_at_boundary(text: str, max_chars: int) -> str:
    """
    Truncate text to at most max_chars at a sentence or line boundary.
    Avoids cutting in the middle of a sentence or code line.
    """
    if len(text) <= max_chars:
        return text
    chunk = text[: max_chars + 1]
    # If looks like code (fenced block or many lines without sentence endings), cut at last newline.
    if "```" in chunk or chunk.count("\n") > chunk.count(". ") + chunk.count(".\n"):
        last_nl = chunk.rfind("\n")
        if last_nl > max_chars // 2:
            return chunk[:last_nl + 1].rstrip()
    # Prefer sentence boundary: . ! ? followed by space or newline
    sentence_end = max(
        chunk.rfind(". "),
        chunk.rfind(".\n"),
        chunk.rfind("! "),
        chunk.rfind("!\n"),
        chunk.rfind("? "),
        chunk.rfind("?\n"),
    )
    if sentence_end > max_chars // 2:
        return chunk[: sentence_end + 1].strip()
    # Else cut at last newline or space
    last_nl = chunk.rfind("\n")
    last_sp = chunk.rfind(" ")
    cut = max(last_nl, last_sp)
    if cut > max_chars // 2:
        return chunk[: cut + 1].rstrip()
    return chunk[:max_chars].rstrip()


def build_context_block(
    hits: list[dict[str, Any]],
    chunk_chars: int,
    total_chars: int,
    *,
    structured: bool = False,
    question: str = "",
) -> tuple[str, list[dict[str, Any]], float]:
    """
    Build RAG context text and chunks_info from search hits.
    Truncates each chunk at sentence (or line) boundaries to avoid cutting mid-sentence/code.
    When ``structured`` is True (retrieval.yaml ``structured_rag_context_enabled``), prepend
    short Concepts / Evidence sections for readability.
    Returns (context_text, chunks_info, max_score).
    """
    if not hits:
        return "", [], 0.0
    max_score = max(h.get("score", 0.0) for h in hits)
    parts: list[str] = []
    chunks_info: list[dict[str, Any]] = []
    total = 0
    if structured:
        concepts = extract_target_concepts_for_coverage(question)
        if concepts:
            cline = ", ".join(concepts[:24])
            if len(concepts) > 24:
                cline += ", …"
            header_txt = (
                f"### Concepts (heuristic targets from the question)\n{cline}\n\n### Evidence\n"
            )
        else:
            header_txt = "### Evidence\n"
        hlen = len(header_txt)
        if hlen <= total_chars:
            parts.append(header_txt.rstrip())
            total += hlen + 2
    for idx, h in enumerate(hits, start=1):
        if total >= total_chars:
            break
        payload = h.get("payload") or {}
        txt = (payload.get("text") or "").strip()
        if not txt:
            continue
        remaining = total_chars - total
        if remaining <= 0:
            break
        snippet = _truncate_at_boundary(txt, min(chunk_chars, remaining))
        if not snippet:
            continue
        block = f"[{idx}] {snippet}" if structured else snippet
        parts.append(block)
        total += len(block) + 2
        score = h.get("score", 0.0)
        rerank_score = h.get("rerank_score")
        section_path = payload.get("section_path") or []
        section_joined = payload.get("section_path_joined")
        if section_joined is None and section_path:
            section_joined = ":".join(str(s) for s in section_path)
        chunks_info.append({
            "index": idx,
            "score": f"{score:.4f}" if score else "N/A",
            "rerank_score": f"{rerank_score:.4f}" if rerank_score is not None else None,
            "url": payload.get("url") or "N/A",
            "source": payload.get("source") or "N/A",
            "path": payload.get("path") or "N/A",
            "doc_type": payload.get("doc_type") or "N/A",
            "ios_versions": payload.get("ios_versions") or [],
            "swift_versions": payload.get("swift_versions") or [],
            "section_path": section_path,
            "section_path_joined": section_joined or "",
            "text_length": len(snippet),
            "text_preview": snippet[:100] + "..." if len(snippet) > 100 else snippet,
        })
    return "\n\n".join(parts), chunks_info, max_score


def build_system_content(
    prefix: str,
    suffix: str,
    context_block: str,
    max_retrieval_score: float,
    confidence_threshold: float,
    reasoning_level: ReasoningLevel | None,
    model_name: str,
    web_supplement: str | None = None,
    *,
    retrieval_skipped: bool = False,
    coverage_missing_concepts: list[str] | None = None,
) -> str:
    """
    Build final system message: prefix + optional reasoning + primary-task block + delimited
    supplementary RAG/web + suffix. Retrieved snippets are framed as optional knowledge, never as
    the user's task. When ``retrieval_skipped`` is True and context is empty, omit zero-hit RAG boilerplate.
    """
    reasoning_instruction = ""
    if reasoning_level and model_name:
        if any(kw in model_name.lower() for kw in REASONING_LEVEL_MODELS):
            reasoning_instruction = f"\n\nReasoning: {reasoning_level}\n"

    head = (prefix or "") + reasoning_instruction
    head = head.rstrip() + "\n\n" + _TASK_PRIORITY_BLOCK.strip() + "\n"

    supplement_parts: list[str] = []
    ctx_stripped = (context_block or "").strip()

    if ctx_stripped:
        supplement_parts.append(
            f"{_RAG_KNOWLEDGE_BEGIN}\n{_RAG_TRUST_AND_OPTIONAL_USE}{ctx_stripped}\n{_RAG_KNOWLEDGE_END}\n{_RAG_RETRIEVAL_REMINDER}"
        )
        if max_retrieval_score < confidence_threshold:
            supplement_parts.append(
                "Note: Retrieval match quality is low—these snippets may be a weak fit for the question. "
                "You are still not required to use them; prioritize the user's message and attachments.\n"
            )
        miss = [str(x).strip() for x in (coverage_missing_concepts or []) if str(x).strip()]
        if miss:
            shown = ", ".join(miss[:12])
            more = f" (+{len(miss) - 12} more)" if len(miss) > 12 else ""
            supplement_parts.append(
                "Note: The following concepts were inferred from the question but were not clearly found in the "
                f"retrieved snippets: {shown}{more}. Do not invent APIs or behavior for them; say if evidence is missing.\n"
            )
    elif not retrieval_skipped:
        no_hits = (
            "The local documentation base did not return any relevant fragments for this query. "
            "That only reflects retrieval—not the user's question or any files they attached. "
            "Answer from attachments and general knowledge as needed.\n"
        )
        supplement_parts.append(
            f"{_RAG_KNOWLEDGE_BEGIN}\n{no_hits.strip()}\n{_RAG_KNOWLEDGE_END}"
        )

    ws = (web_supplement or "").strip()
    if ws:
        supplement_parts.append(
            f"{_WEB_SUPPLEMENT_BEGIN}\n{ws}\n{_WEB_SUPPLEMENT_END}\n"
            "Reminder: web text above is optional context only; center your answer on the user's message and attachments.\n"
        )

    middle = "\n\n".join(s.rstrip() for s in supplement_parts) if supplement_parts else ""
    tail = (suffix or "").strip()

    chunks: list[str] = [head.rstrip()]
    if middle:
        chunks.append(middle)
    if tail:
        chunks.append(tail)
    return "\n\n".join(chunks)


__all__ = [
    "last_user_content",
    "determine_reasoning_level",
    "framework_filter",
    "build_context_block",
    "build_system_content",
    "REASONING_LEVEL_MODELS",
]
