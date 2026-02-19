"""
CLI for RAG: asks a question, runs RAG (embed -> search -> rerank -> chat) via application layer,
prints the answer. Uses the same prompt, model, and RAG flow as rag_proxy (HTTP).
No embedded prompt or business logic; only calls application.rag.params and use_cases.
"""

import os
import sys

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from application.rag.params import get_rag_answer_params
from application.rag.use_cases import answer_question
from domain.entities.rag import RagQuestionRequest


def main() -> None:
    question = input("🧠 Вопрос: ").strip()
    if not question:
        print("Вопрос не задан.")
        return
    webui_dir = os.path.dirname(os.path.abspath(__file__))
    params, deps = get_rag_answer_params(webui_dir=webui_dir)
    req = RagQuestionRequest(messages=[{"role": "user", "content": question}], model=None)
    response = answer_question(
        req,
        deps.rag_repo,
        deps.embed_provider,
        deps.rerank_client,
        deps.chat_client,
        params.system_prefix,
        params.system_suffix,
        params.context_chunk_chars,
        params.context_total_chars,
        params.confidence_threshold,
        params.model_name,
        reasoning_level=None,
    )
    print("\n🤖 Ответ модели:")
    print(response.content)


if __name__ == "__main__":
    main()
