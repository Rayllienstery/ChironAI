from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

WRAPPER_RULES = {
    "application/container.py": {"default_markdown_store", "wire_rag_use_cases"},
    "application/rag/use_cases.py": set(),
    "application/rag/params.py": {"get_rag_answer_params"},
    "domain/entities/rag.py": set(),
    "domain/services/retrieval.py": {"expand_query_variants"},
    "domain/services/rerank.py": set(),
    "domain/services/rag_trigger.py": set(),
    "domain/services/rag_trace.py": set(),
    "domain/services/prompt_builder.py": set(),
    "domain/services/chunking.py": set(),
    "infrastructure/qdrant/rag_repository_impl.py": set(),
    "infrastructure/ollama/openai_ollama_tool_bridge.py": set(),
}


def _non_docstring_statements(module: ast.Module) -> list[ast.stmt]:
    body = list(module.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    return body


def test_compat_wrapper_files_stay_thin() -> None:
    for rel_path, allowed_functions in WRAPPER_RULES.items():
        source = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
        module = ast.parse(source, filename=rel_path)
        for node in _non_docstring_statements(module):
            if isinstance(node, ast.ImportFrom):
                continue
            if isinstance(node, ast.Assign):
                targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
                assert targets == ["__all__"], f"{rel_path} defines non-__all__ assignment"
                continue
            if isinstance(node, ast.FunctionDef):
                assert node.name in allowed_functions, f"{rel_path} added non-compat function {node.name}"
                continue
            raise AssertionError(f"{rel_path} contains non-wrapper statement: {type(node).__name__}")


def test_qdrant_repository_import_path_remains_compatible() -> None:
    from infrastructure.qdrant.rag_repository_impl import QdrantRagRepository as compat_repo
    from rag_service.infrastructure.qdrant_repository import QdrantRagRepository as canonical_repo

    assert compat_repo is canonical_repo


def test_tool_bridge_import_path_remains_compatible() -> None:
    from infrastructure.ollama.openai_ollama_tool_bridge import openai_messages_to_ollama as canonical_fn
    from rag_service.infrastructure.openai_ollama_tool_bridge import openai_messages_to_ollama as compat_fn

    assert compat_fn is canonical_fn


def test_application_and_domain_reexports_match_canonical_objects() -> None:
    from application.rag.use_cases import build_rag_context as compat_build_rag_context
    from domain.entities.rag import RagContext as compat_rag_context
    from domain.services.prompt_builder import determine_reasoning_level as compat_reasoning_level
    from domain.services.retrieval import rrf_merge_hit_lists as compat_rrf_merge_hit_lists
    from rag_service.application.use_cases import build_rag_context as canonical_build_rag_context
    from rag_service.domain.entities import RagContext as canonical_rag_context
    from rag_service.domain.services.prompt_builder import determine_reasoning_level as canonical_reasoning_level
    from rag_service.domain.services.retrieval import rrf_merge_hit_lists as canonical_rrf_merge_hit_lists

    assert compat_build_rag_context is canonical_build_rag_context
    assert compat_rag_context is canonical_rag_context
    assert compat_reasoning_level is canonical_reasoning_level
    assert compat_rrf_merge_hit_lists is canonical_rrf_merge_hit_lists


def test_application_container_reexports_match_canonical_objects() -> None:
    from application.container import (
        default_chat_client as compat_chat_client,
        default_embed_provider as compat_embed_provider,
        default_rag_repository as compat_rag_repository,
        default_rerank_client as compat_rerank_client,
    )
    from rag_service.infrastructure.container import (
        default_chat_client as canonical_chat_client,
        default_embed_provider as canonical_embed_provider,
        default_rag_repository as canonical_rag_repository,
        default_rerank_client as canonical_rerank_client,
    )

    assert compat_chat_client is canonical_chat_client
    assert compat_embed_provider is canonical_embed_provider
    assert compat_rag_repository is canonical_rag_repository
    assert compat_rerank_client is canonical_rerank_client


def test_webui_routes_uses_shared_prompt_and_identifier_helpers() -> None:
    source = (REPO_ROOT / "api/http/webui_routes.py").read_text(encoding="utf-8")

    assert "from api.http.webui_prompt_routes import register_prompt_routes" in source
    assert "from api.http.webui_crawler_source_routes import register_crawler_source_routes" in source
    assert "from api.http.webui_prompts import is_readme_name" in source
    assert "from api.http.webui_crawler_helpers import is_safe_identifier" in source
    assert 're.match(r"^[a-zA-Z0-9_-]+$"' not in source
    assert '".." in name or "/" in name or "\\\\" in name' not in source
