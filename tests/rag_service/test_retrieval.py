"""Tests for rag_service.domain.services.retrieval."""


from rag_service.domain.services.retrieval import (
    is_version_question,
    need_more_chunks,
    parse_versions_from_question,
    query_for_retrieval,
)


def test_parse_versions_from_question() -> None:
    ios, swift = parse_versions_from_question("What is new in iOS 18 and Swift 6.0?")
    assert "18" in ios
    assert "6.0" in swift
    ios2, swift2 = parse_versions_from_question("No versions here")
    assert ios2 == []
    assert swift2 == []


def test_is_version_question() -> None:
    assert is_version_question("iOS 18 release") is True
    assert is_version_question("What is Swift 6?") is True
    assert is_version_question("How do I use Observation?") is False


def test_query_for_retrieval_strips_code_blocks() -> None:
    q = query_for_retrieval("Explain this:\n```swift\nlet x = 1\n```")
    assert "let x = 1" not in q or "Explain" in q


def test_need_more_chunks() -> None:
    assert need_more_chunks("compare UIKit and SwiftUI") is True
    assert need_more_chunks("what is View") is False


