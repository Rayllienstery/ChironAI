from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import application.rag.hybrid_sparse as hybrid_sparse
import application.rag.retrieval_ui_overrides as retrieval_ui_overrides
import application.rag.webui_retrieval_settings as webui_retrieval_settings
from application.crawl.crawl_use_cases import run_crawl_all_sources
from application.crawl.local_ingest_use_case import ingest_markdown_folder
from application.rag.collection_freshness import check_collection_freshness
from application.rag_tests import lint
from application.rag_tests.authoring import build_rag_test_markdown, normalize_concepts
from application.rag_tests.metrics import (
    CURRENT_RAG_TESTS_EVALUATION_METHOD_VERSION,
    CURRENT_RAG_TESTS_METRICS_VERSION,
    LEGACY_RAG_TESTS_EVALUATION_METHOD_VERSION,
    LEGACY_RAG_TESTS_METRICS_VERSION,
    normalize_rag_test_result,
    normalize_rag_test_run,
)
from application.rag_tests.runner import (
    build_proxy_chat_payload,
    build_rag_test_error_result,
    build_rag_test_result,
    build_test_messages,
    build_test_retrieval_query,
    run_tests_sync,
)
from domain.entities.crawl import CrawlResult, CrawlSource, IndexedPage, crawl_source_from_dict
from domain.services.markdown_meta import parse_and_strip_meta_block
from domain.value_objects import REASONING_LEVEL_VALUES, is_valid_reasoning_level


def test_rag_tests_lint_flags_combined_concepts() -> None:
    tests = [
        {
            "id": "T1",
            "file_path": "rag_tests/t1.md",
            "expected_concepts": ["weak / unowned", "atomic term"],
        }
    ]

    issues = lint.lint_expected_concepts(tests)

    assert lint._looks_multi_concept("one and two") is True
    assert lint._looks_multi_concept("single concept") is False
    assert len(issues) == 1
    assert "split into separate bullets" in issues[0].message
    assert "weak / unowned" in lint.format_issues_text(issues)
    assert lint.format_issues_text([]) == "No multi-concept Expected Concepts entries found."


def test_authoring_helpers_normalize_and_render_optional_fields() -> None:
    concepts = normalize_concepts(
        [" weak / unowned ", "weak", "alpha, beta", "first; second", "", "very long ambiguous / " + ("x" * 50)]
    )
    markdown = build_rag_test_markdown(
        name="Observation",
        question="How does observation work?",
        concepts=concepts[:3],
        platform="iOS",
        framework="SwiftUI",
        difficulty="medium",
        concept_mode="all",
        rag_strict=True,
        min_os="iOS 18",
        notes="Use current docs.",
    )

    assert concepts[:7] == ["weak", "unowned", "weak", "alpha", "beta", "first", "second"]
    assert concepts[-1].startswith("very long ambiguous")
    assert "RAG Strict: true" in markdown
    assert "MinOS: iOS 18" in markdown
    assert "## Notes" in markdown


def test_collection_freshness_handles_missing_stale_and_fresh_dates() -> None:
    now = datetime.now(timezone.utc)

    assert check_collection_freshness(None, 7) == "no_record"
    assert check_collection_freshness({"last_refreshed_at": ""}, 7) == "no_record"
    assert check_collection_freshness({"last_refreshed_at": "not-a-date"}, 7) == "stale"
    assert check_collection_freshness({"last_refreshed_at": (now - timedelta(days=1)).isoformat()}, 7) == "fresh"
    assert (
        check_collection_freshness({"last_refreshed_at": (now - timedelta(days=1)).replace(tzinfo=None).isoformat()}, 7)
        == "fresh"
    )
    assert (
        check_collection_freshness({"last_refreshed_at": (now - timedelta(days=30)).isoformat().replace("+00:00", "Z")}, 7)
        == "stale"
    )


def test_markdown_meta_parser_handles_availability_and_invalid_blocks() -> None:
    markdown = """<!--
url: https://developer.apple.com/documentation/swiftui
framework: SwiftUI
doc-kind: article
doc-scope: framework
platforms: iOS, macOS
availability:
    iOS: 18.0
    Swift: 6.0
summary: ignored
-->
# Title
"""

    meta, rest = parse_and_strip_meta_block(markdown)

    assert meta["url"].endswith("/swiftui")
    assert meta["framework"] == "SwiftUI"
    assert meta["doc_kind"] == "article"
    assert meta["doc_scope"] == "framework"
    assert meta["platforms"] == ["iOS", "macOS"]
    assert meta["availability"] == {"iOS": "18.0", "Swift": "6.0"}
    assert meta["ios_versions"] == ["18.0"]
    assert meta["swift_versions"] == ["6.0"]
    assert rest == "# Title\n"
    assert parse_and_strip_meta_block("")[0] == {}
    assert parse_and_strip_meta_block("<!-- missing end")[0] == {}


def test_webui_retrieval_settings_read_repo_and_fallbacks(monkeypatch) -> None:
    repo = SimpleNamespace(get_app_setting=lambda key: "7" if key == "rag_trigger_threshold" else None)
    assert webui_retrieval_settings.get_effective_rag_trigger_threshold(repo) == 7

    bad_repo = SimpleNamespace(get_app_setting=lambda _key: (_ for _ in ()).throw(RuntimeError("db")))
    monkeypatch.setattr(webui_retrieval_settings, "get_retrieval_int", lambda key, default: 5)
    assert webui_retrieval_settings.get_effective_rag_trigger_threshold(bad_repo) == 5

    keyword_repo = SimpleNamespace(get_enabled_keywords_flat=lambda: ["SwiftUI", "URLSession"])
    assert webui_retrieval_settings.get_rag_required_keywords_from_module(lambda: keyword_repo) == [
        "SwiftUI",
        "URLSession",
    ]
    assert webui_retrieval_settings.get_rag_required_keywords_from_module(None) is None
    assert webui_retrieval_settings.get_rag_required_keywords_from_module(lambda: (_ for _ in ()).throw(RuntimeError())) is None

    monkeypatch.setattr("config.get_default_chat_model", lambda: " chat-model ", raising=False)
    monkeypatch.setattr("config.get_default_embed_model", lambda: " embed-model ", raising=False)
    monkeypatch.setattr("config.get_default_rerank_model", lambda: " rerank-model ", raising=False)
    assert webui_retrieval_settings.config_default_chat_model() == "chat-model"
    assert webui_retrieval_settings.config_default_embed_model() == "embed-model"
    assert webui_retrieval_settings.config_default_rerank_model() == "rerank-model"


def test_retrieval_flag_helpers_use_config_fallbacks(monkeypatch) -> None:
    monkeypatch.setattr(hybrid_sparse, "get_retrieval_bool", lambda key, default: False)
    monkeypatch.setattr(hybrid_sparse, "load_proxy_settings", lambda repo: (_ for _ in ()).throw(RuntimeError("db")))
    assert hybrid_sparse.is_hybrid_sparse_enabled() is False

    monkeypatch.setattr(retrieval_ui_overrides, "get_retrieval_bool", lambda key, default: True)
    monkeypatch.setattr(
        retrieval_ui_overrides,
        "load_proxy_settings",
        lambda repo: (_ for _ in ()).throw(RuntimeError("db")),
    )
    assert retrieval_ui_overrides.retrieval_bool_with_ui_override("coverage_gate_enabled") is True
    assert "coverage_gate_enabled" in retrieval_ui_overrides.RETRIEVAL_UI_BOOL_KEYS


def test_retrieval_flag_helpers_use_proxy_settings(monkeypatch) -> None:
    monkeypatch.setattr(hybrid_sparse, "get_retrieval_bool", lambda key, default: False)
    monkeypatch.setattr(hybrid_sparse, "load_proxy_settings", lambda repo: {"hybrid_sparse_enabled": True})
    assert hybrid_sparse.is_hybrid_sparse_enabled() is True

    monkeypatch.setattr(
        retrieval_ui_overrides,
        "load_proxy_settings",
        lambda repo: {"coverage_gate_enabled": False},
    )
    assert retrieval_ui_overrides.retrieval_bool_with_ui_override("coverage_gate_enabled", yaml_fallback=True) is False


def test_crawl_and_ingest_stubs_return_stable_shapes() -> None:
    calls: list[str] = []
    sources = [
        CrawlSource(id="apple", url="https://developer.apple.com"),
        CrawlSource(id="swift", url="https://swift.org"),
    ]

    status = run_crawl_all_sources(sources, calls.append, object())
    summary = ingest_markdown_folder("docs", "source", object(), object(), object(), object())

    assert calls == ["apple", "swift"]
    assert status == "Crawl requested for 2 sources."
    assert summary == {"files_processed": 0, "chunks_indexed": 0, "errors": []}


def test_domain_crawl_entities_and_value_objects() -> None:
    source = crawl_source_from_dict(
        {
            "id": "docs",
            "url": "https://example.com",
            "max_depth": "3",
            "crawler": "http",
            "doc_only": False,
            "seed_urls": ["https://example.com/start"],
            "owner": "tests",
        }
    )

    assert source.max_depth == 3
    assert source.extra == {"owner": "tests"}
    assert CrawlResult(url="u", html="<p>x</p>", source_id="docs").extra == {}
    assert IndexedPage(filename="page.md", url=None, chunk_hashes=["a"]).chunk_hashes == ["a"]
    assert REASONING_LEVEL_VALUES == ("low", "medium", "high")
    assert is_valid_reasoning_level("medium") is True
    assert is_valid_reasoning_level("other") is False


def test_rag_test_metrics_normalize_legacy_and_current_results() -> None:
    legacy = normalize_rag_test_result({"chunks_count": "2", "grounding_overlap": 1})
    current = normalize_rag_test_result(
        {
            "metrics_version": CURRENT_RAG_TESTS_METRICS_VERSION,
            "retrieval_used": False,
            "strict_mode": True,
            "strict_quote": 123,
            "strict_quote_ok": 1,
            "strict_quote_reason": 7,
        }
    )
    run = normalize_rag_test_run({"results": [current]})
    bad_count = normalize_rag_test_result({"chunks_count": "bad", "rag_used": True})
    list_based = normalize_rag_test_result({"chunks_info": [{"id": 1}], "strict_rag_ok": 0})
    empty_run = normalize_rag_test_run({"results": ["bad"]})

    assert legacy["metrics_version"] == LEGACY_RAG_TESTS_METRICS_VERSION
    assert legacy["evaluation_method_version"] == LEGACY_RAG_TESTS_EVALUATION_METHOD_VERSION
    assert legacy["retrieval_used"] is True
    assert current["evaluation_method_version"] == CURRENT_RAG_TESTS_EVALUATION_METHOD_VERSION
    assert current["strict_quote"] == "123"
    assert bad_count["retrieval_used"] is True
    assert list_based["retrieval_used"] is True
    assert list_based["strict_rag_ok"] is False
    assert empty_run["results"] == []
    assert run["metrics_version"] == CURRENT_RAG_TESTS_METRICS_VERSION


def test_rag_test_runner_builders_and_sync_runner(monkeypatch) -> None:
    test = {
        "id": "T1",
        "name": "Sample",
        "question": "How does SwiftData observation work?",
        "platform": "iOS",
        "framework": "SwiftData",
        "difficulty": "easy",
        "expected_concepts": ["Observation"],
    }
    validation = {"status": "PASS", "rag_used": True, "retrieval_used": True, "confidence_label": "1/1"}

    messages = build_test_messages("Question?", strict_mode=True)
    query = build_test_retrieval_query(test)
    payload = build_proxy_chat_payload(
        question="Question?",
        model="m",
        provider_id="ollama",
        collection_name="docs",
        client_request_id="req",
        prompt_name="p",
        temperature=0,
        top_k=3,
        testing_disable_rerank=True,
        strict_mode=True,
    )
    result = build_rag_test_result(
        test=test,
        model="m",
        content="answer",
        rag_metadata={"chunks_info": [{"id": 1}], "rag_queries": [{"query": "q"}]},
        validation=validation,
        response_time_ms=10,
        order=2,
    )
    error = build_rag_test_error_result(test=test, model="m", provider_id="", error=RuntimeError("boom"), order=1)

    monkeypatch.setattr(
        "application.rag_tests.runner.run_one_test",
        lambda item, model, collection_name=None, strict_mode=False: ("", {}, {"test_id": item["id"]}),
    )
    progress: list[tuple[int, int, str]] = []
    sync_results = run_tests_sync([test], "m", on_progress=lambda current, total, name: progress.append((current, total, name)))

    assert messages[0]["role"] == "system"
    assert "SwiftData" in query and "Observation" in query
    assert payload["testing_disable_rerank"] is True
    assert result["_order"] == 2
    assert result["chunks_info"] == [{"id": 1}]
    assert error["failure_reason"] == "boom"
    assert progress == [(1, 1, "Sample")]
    assert sync_results == [{"test_id": "T1"}]


def test_rag_test_retrieval_query_extra_terms() -> None:
    assert "ActivityKit" in build_test_retrieval_query({"question": "Q", "expected_concepts": ["Live Activity"]})
    assert "@Observable" in build_test_retrieval_query({"question": "Q", "expected_concepts": ["@Observation"]})
    assert "Sendable" in build_test_retrieval_query({"question": "Q", "expected_concepts": ["actor"]})
    assert build_test_retrieval_query({"question": "Only question"}) == "Only question"
