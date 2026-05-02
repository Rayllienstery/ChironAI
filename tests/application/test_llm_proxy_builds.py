from __future__ import annotations

from application.llm_proxy_builds import (
    DEFAULT_NUM_PREDICT,
    build_ollama_options,
    normalize_build,
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
