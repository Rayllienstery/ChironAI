from __future__ import annotations

from application.rag_tests.runner import build_proxy_chat_payload, build_test_retrieval_query


def test_build_proxy_chat_payload_includes_required_fields() -> None:
    payload = build_proxy_chat_payload(
        question="What is SwiftUI?",
        model="llama3",
        collection_name="ios-docs",
        client_request_id="rid-1",
    )
    assert payload["model"] == "llama3"
    assert payload["collection_name"] == "ios-docs"
    assert payload["stream"] is True
    assert payload["include_rag_metadata"] is True
    assert payload["client_request_id"] == "rid-1"
    assert payload["messages"][0]["content"] == "What is SwiftUI?"


def test_build_proxy_chat_payload_optional_rerank_policy_flag() -> None:
    payload = build_proxy_chat_payload(
        question="Q",
        model="m",
        provider_id="ollama",
        collection_name="c",
        client_request_id="rid-2",
        prompt_name="system_senior_ios_assistant_v1",
        temperature=0.2,
        top_k=12,
        testing_disable_rerank=True,
    )
    assert payload["provider_id"] == "ollama"
    assert payload["prompt_name"] == "system_senior_ios_assistant_v1"
    assert payload["temperature"] == 0.2
    assert payload["top_k"] == 12.0
    assert payload["testing_disable_rerank"] is True


def test_build_proxy_chat_payload_strict_mode_injects_quote_instruction() -> None:
    payload = build_proxy_chat_payload(
        question="Q",
        model="m",
        collection_name="c",
        client_request_id="rid-3",
        strict_mode=True,
    )
    assert payload["strict_mode"] is True
    assert payload["messages"][0]["role"] == "system"
    assert "RAG QUOTE" in payload["messages"][0]["content"]
    assert payload["messages"][-1] == {"role": "user", "content": "Q"}


def test_build_test_retrieval_query_enriches_question_with_expected_terms() -> None:
    query = build_test_retrieval_query(
        {
            "question": "How do I use Observation with SwiftUI?",
            "platform": "iOS",
            "framework": "SwiftUI",
            "expected_concepts": ["@Observable", "observation tracking"],
        }
    )
    assert "How do I use Observation with SwiftUI?" in query
    assert "Relevant terms:" in query
    assert "iOS" in query
    assert "SwiftUI" in query
    assert "@Observable" in query
    assert "Observation framework" in query
