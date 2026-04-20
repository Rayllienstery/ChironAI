from llm_proxy.pipeline_steps import (
    get_proxy_pipeline_definition,
    get_proxy_pipeline_step_meta,
)


def test_proxy_pipeline_definition_has_required_metadata() -> None:
    steps = get_proxy_pipeline_definition()
    assert isinstance(steps, list)
    assert len(steps) >= 1
    for step in steps:
        assert isinstance(step, dict)
        assert str(step.get("id") or "").strip()
        assert str(step.get("icon") or "").strip()
        assert str(step.get("title") or "").strip()
        assert str(step.get("description") or "").strip()


def test_proxy_pipeline_step_meta_lookup() -> None:
    merged = get_proxy_pipeline_step_meta("merged_docs")
    assert isinstance(merged, dict)
    assert merged.get("id") == "merged_docs"
    assert str(merged.get("icon") or "").strip()
    assert str(merged.get("title") or "").strip()
    assert str(merged.get("description") or "").strip()

    web = get_proxy_pipeline_step_meta("web_supplement")
    assert isinstance(web, dict)
    assert web.get("id") == "web_supplement"
    assert str(web.get("icon") or "").strip()
    assert str(web.get("title") or "").strip()
    assert str(web.get("description") or "").strip()

    assert get_proxy_pipeline_step_meta("unknown-step") is None
