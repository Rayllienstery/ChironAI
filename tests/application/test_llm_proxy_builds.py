from __future__ import annotations

from application.llm_proxy_builds import (
    DEFAULT_NUM_PREDICT,
    build_ollama_options,
    find_build_by_id,
    normalize_build,
    openai_client_capability_fields,
    openai_model_objects_for_builds,
)


def _base_build() -> dict[str, object]:
    return {
        "id": "Hard-worker",
        "backend": "dumb",
        "provider_id": "ollama",
        "model": "kimi-k2.6:cloud",
        "prompt_name": "system_senior_ios_assistant_v1",
    }


def test_normalize_build_defaults_num_predict_to_65536() -> None:
    normalized, errors = normalize_build(_base_build())

    assert errors == []
    assert normalized is not None
    assert normalized["num_predict"] == DEFAULT_NUM_PREDICT == 65536


def test_normalize_build_accepts_custom_num_predict() -> None:
    build = {**_base_build(), "num_predict": "65536"}

    normalized, errors = normalize_build(build)

    assert errors == []
    assert normalized is not None
    assert normalized["num_predict"] == 65536
    assert build_ollama_options(normalized)["num_predict"] == 65536


def test_normalize_build_defaults_ide_mode_to_false() -> None:
    normalized, errors = normalize_build(_base_build())

    assert errors == []
    assert normalized is not None
    assert normalized["ide_mode"] is False


def test_normalize_build_preserves_ide_mode() -> None:
    normalized, errors = normalize_build({**_base_build(), "ide_mode": True})

    assert errors == []
    assert normalized is not None
    assert normalized["ide_mode"] is True


def test_normalize_build_preserves_optional_vision_model() -> None:
    normalized, errors = normalize_build({**_base_build(), "vision_model": "minimax-m3:cloud"})

    assert errors == []
    assert normalized is not None
    assert normalized["vision_model"] == "minimax-m3:cloud"


def test_normalize_build_defaults_optional_vision_model_to_empty_string() -> None:
    normalized, errors = normalize_build(_base_build())

    assert errors == []
    assert normalized is not None
    assert normalized["vision_model"] == ""


def test_normalize_build_rejects_invalid_num_predict() -> None:
    for raw in ("abc", "0", "262145"):
        normalized, errors = normalize_build({**_base_build(), "num_predict": raw})

        assert normalized is None
        assert any("num_predict" in err for err in errors)


def test_build_ollama_options_defaults_num_predict_for_legacy_build() -> None:
    assert build_ollama_options({"num_ctx": 32768}) == {
        "num_ctx": 32768,
        "num_predict": DEFAULT_NUM_PREDICT,
    }


def test_openai_model_objects_expose_build_context_length() -> None:
    rows = openai_model_objects_for_builds([{**_base_build(), "num_ctx": 202752}])

    assert rows[0]["context_length"] == 202752
    assert rows[0]["num_ctx"] == 202752
    assert rows[0]["metadata"]["context_length"] == 202752
    assert rows[0]["metadata"]["num_ctx"] == 202752


def test_openai_model_objects_expose_opencode_vision_capabilities() -> None:
    rows = openai_model_objects_for_builds([_base_build()])

    assert rows[0]["supports_vision"] is True
    assert rows[0]["attachment"] is True
    assert rows[0]["modalities"] == {"input": ["text", "image"], "output": ["text"]}
    assert rows[0]["tool_call"] is True


def test_openai_client_capability_fields_returns_independent_payload() -> None:
    fields = openai_client_capability_fields()
    fields["modalities"]["input"].append("audio")  # type: ignore[index,union-attr]

    assert openai_client_capability_fields()["modalities"] == {"input": ["text", "image"], "output": ["text"]}


def test_find_build_by_id_trims_requested_model() -> None:
    assert find_build_by_id([_base_build()], " Hard-worker ") is not None
    assert find_build_by_id([_base_build()], "missing") is None
