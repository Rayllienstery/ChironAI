"""
Unit tests for application.rag_tests.validator.
"""

from __future__ import annotations


from application.rag_tests.validator import concept_satisfied, validate_concepts, validate_result


class TestValidateConcepts:
    """Tests for validate_concepts."""

    def test_any_mode_one_match_passes(self) -> None:
        passed, hits, total, missing = validate_concepts(
            "The answer uses SwiftUI for views.",
            ["SwiftUI", "UIKit"],
            "any",
        )
        assert passed is True
        assert hits == 1
        assert total == 2
        assert missing == ["UIKit"]

    def test_any_mode_no_match_fails(self) -> None:
        passed, hits, total, missing = validate_concepts(
            "Nothing here.",
            ["SwiftUI", "UIKit"],
            "any",
        )
        assert passed is False
        assert hits == 0
        assert total == 2
        assert missing == ["SwiftUI", "UIKit"]

    def test_all_mode_all_must_match(self) -> None:
        passed, hits, total, missing = validate_concepts(
            "SwiftUI and UIKit are frameworks.",
            ["SwiftUI", "UIKit"],
            "all",
        )
        assert passed is True
        assert hits == 2
        assert total == 2
        assert missing == []

    def test_all_mode_one_missing_fails(self) -> None:
        passed, hits, total, missing = validate_concepts(
            "Only SwiftUI here.",
            ["SwiftUI", "UIKit"],
            "all",
        )
        assert passed is False
        assert hits == 1
        assert total == 2
        assert "UIKit" in missing

    def test_case_insensitive(self) -> None:
        passed, hits, total, _ = validate_concepts(
            "swiftui is great",
            ["SwiftUI"],
            "all",
        )
        assert passed is True
        assert hits == 1
        assert total == 1

    def test_empty_concepts_list_passes(self) -> None:
        passed, hits, total, missing = validate_concepts("Any response", [], "all")
        assert passed is True
        assert hits == 0
        assert total == 0
        assert missing == []

    def test_data_race_heuristic_matches_race_condition(self) -> None:
        assert concept_satisfied("There is a race condition on the main thread.", "data race") is True

    def test_weak_reference_heuristic_matches_weak_var(self) -> None:
        assert concept_satisfied("Use weak var coordinator to avoid cycles.", "weak reference") is True


class TestValidateResult:
    """Tests for validate_result."""

    def test_pass_when_concepts_and_rag_ok(self) -> None:
        test = {
            "expected_concepts": ["Swift"],
            "concept_mode": "all",
            "rag_requirement": True,
            "rag_strict": False,
        }
        out = validate_result(
            test,
            "Swift is a programming language.",
            {"chunks_count": 2, "chunks_info": [{"text_preview": "Swift docs"}]},
        )
        assert out["status"] == "PASS"
        assert out["rag_used"] is True
        assert out["confidence_label"] == "1/1 concepts found"
        assert out.get("full_response") is None
        assert out.get("retrieved_chunks") is None

    def test_fail_when_concepts_missing(self) -> None:
        test = {
            "expected_concepts": ["Swift", "UIKit"],
            "concept_mode": "all",
            "rag_requirement": True,
            "rag_strict": False,
        }
        out = validate_result(
            test,
            "Only Swift mentioned.",
            {"chunks_count": 1, "chunks_info": []},
        )
        assert out["status"] == "FAIL"
        assert "UIKit" in out["missing_concepts"]
        assert out["full_response"] == "Only Swift mentioned."
        assert out["confidence_label"] == "1/2 concepts found"

    def test_fail_when_chunks_count_zero_and_rag_required(self) -> None:
        test = {
            "expected_concepts": [],
            "concept_mode": "all",
            "rag_requirement": True,
            "rag_strict": False,
        }
        out = validate_result(test, "Some answer.", {"chunks_count": 0, "chunks_info": []})
        assert out["status"] == "FAIL"
        assert out["rag_used"] is False

    def test_pass_when_rag_requirement_false_and_no_chunks(self) -> None:
        test = {
            "expected_concepts": [],
            "concept_mode": "all",
            "rag_requirement": False,
            "rag_strict": False,
        }
        out = validate_result(test, "Answer without RAG.", None)
        assert out["status"] == "PASS"
        assert out["rag_used"] is False

    def test_rag_strict_true_no_overlap_fails(self) -> None:
        test = {
            "expected_concepts": [],
            "concept_mode": "all",
            "rag_requirement": True,
            "rag_strict": True,
        }
        # Chunks have text that does not appear in response
        chunks = [{"text_preview": "Some completely different documentation snippet that is long enough."}]
        out = validate_result(
            test,
            "The model wrote something unrelated.",
            {"chunks_count": 1, "chunks_info": chunks},
        )
        assert out["status"] == "FAIL"
        assert out["rag_used"] is False

    def test_rag_strict_true_with_overlap_passes(self) -> None:
        test = {
            "expected_concepts": [],
            "concept_mode": "all",
            "rag_requirement": True,
            "rag_strict": True,
        }
        chunk_text = "SwiftUI is a declarative framework for building user interfaces."
        chunks = [{"text_preview": chunk_text}]
        out = validate_result(
            test,
            "According to the docs, SwiftUI is a declarative framework for building user interfaces.",
            {"chunks_count": 1, "chunks_info": chunks},
        )
        assert out["status"] == "PASS"
        assert out["rag_used"] is True

    def test_confidence_label_format(self) -> None:
        test = {"expected_concepts": ["A", "B", "C"], "concept_mode": "all", "rag_requirement": False}
        out = validate_result(test, "Only A and B here.", None)
        assert out["confidence_label"] == "2/3 concepts found"

    def test_fail_returns_retrieved_chunks_when_present(self) -> None:
        test = {
            "expected_concepts": ["SwiftUI"],
            "concept_mode": "all",
            "rag_requirement": True,
            "rag_strict": False,
        }
        chunks = [{"index": 1, "score": "0.9", "url": "https://example.com", "text_preview": "doc"}]
        out = validate_result(
            test,
            "This answer does not mention the required concept.",
            {"chunks_count": 1, "chunks_info": chunks},
        )
        assert out["status"] == "FAIL"
        assert out["retrieved_chunks"] == chunks

    def test_fail_when_empty_response(self) -> None:
        test = {"expected_concepts": [], "concept_mode": "all", "rag_requirement": False}
        out = validate_result(test, "   ", {"chunks_count": 1, "chunks_info": []})
        assert out["status"] == "FAIL"

    def test_fail_when_response_too_short(self) -> None:
        test = {"expected_concepts": [], "concept_mode": "all", "rag_requirement": False}
        out = validate_result(test, "Hi", {"chunks_count": 1, "chunks_info": []})
        assert out["status"] == "FAIL"

    def test_fail_due_to_rag_not_triggered_has_failure_reason(self) -> None:
        test = {
            "expected_concepts": ["Swift", "ARC"],
            "concept_mode": "all",
            "rag_requirement": True,
            "rag_strict": False,
        }
        out = validate_result(
            test,
            "Swift and ARC are both covered in this answer.",
            {"chunks_count": 0, "chunks_info": []},
        )
        assert out["status"] == "FAIL"
        assert "failure_reason" in out
        assert "RAG not triggered" in out["failure_reason"]
        assert out["found_concepts"] == ["Swift", "ARC"]
        assert out["missing_concepts"] == []

    def test_fail_due_to_missing_concepts_has_failure_reason_and_found_concepts(self) -> None:
        test = {
            "expected_concepts": ["Swift", "UIKit"],
            "concept_mode": "all",
            "rag_requirement": True,
            "rag_strict": False,
        }
        out = validate_result(
            test,
            "Only Swift mentioned.",
            {"chunks_count": 1, "chunks_info": []},
        )
        assert out["status"] == "FAIL"
        assert "failure_reason" in out
        assert "Missing concepts" in out["failure_reason"]
        assert "UIKit" in out["failure_reason"]
        assert out["found_concepts"] == ["Swift"]
        assert out["missing_concepts"] == ["UIKit"]

    def test_found_concepts_present_on_pass(self) -> None:
        test = {
            "expected_concepts": ["A", "B"],
            "concept_mode": "all",
            "rag_requirement": False,
        }
        out = validate_result(test, "A and B are present.", None)
        assert out["status"] == "PASS"
        assert out["found_concepts"] == ["A", "B"]
        assert "failure_reason" not in out

    def test_fail_empty_response_has_failure_reason(self) -> None:
        test = {"expected_concepts": [], "concept_mode": "all", "rag_requirement": False}
        out = validate_result(test, "   ", {"chunks_count": 1, "chunks_info": []})
        assert out["status"] == "FAIL"
        assert "failure_reason" in out
        assert "Response empty" in out["failure_reason"]

    def test_fail_response_too_short_has_failure_reason(self) -> None:
        test = {"expected_concepts": [], "concept_mode": "all", "rag_requirement": False}
        out = validate_result(test, "Hi", {"chunks_count": 1, "chunks_info": []})
        assert out["status"] == "FAIL"
        assert "failure_reason" in out
        assert "Response too short" in out["failure_reason"]

    def test_fail_rag_strict_no_overlap_has_failure_reason(self) -> None:
        test = {
            "expected_concepts": [],
            "concept_mode": "all",
            "rag_requirement": True,
            "rag_strict": True,
        }
        chunks = [{"text_preview": "Some completely different documentation snippet that is long enough."}]
        out = validate_result(
            test,
            "The model wrote something unrelated.",
            {"chunks_count": 1, "chunks_info": chunks},
        )
        assert out["status"] == "FAIL"
        assert "failure_reason" in out
        assert "RAG chunks did not overlap" in out["failure_reason"]
