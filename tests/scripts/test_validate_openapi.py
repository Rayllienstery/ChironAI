from __future__ import annotations

from copy import deepcopy

import pytest

from scripts import validate_openapi


@pytest.mark.fast
@pytest.mark.scripts
def test_openapi_info_description_includes_app_stage() -> None:
    from core.version import APP_NAME, APP_STAGE

    spec = validate_openapi.build_generated_spec()
    description = spec["info"]["description"]

    assert APP_NAME in description
    assert APP_STAGE in description


@pytest.mark.fast
@pytest.mark.scripts
def test_generated_openapi_spec_is_valid() -> None:
    spec = validate_openapi.build_generated_spec()

    errors = validate_openapi.validate_openapi_spec(spec)

    assert errors == []
    assert spec["openapi"] == "3.1.0"


def test_validate_openapi_spec_rejects_old_openapi_version() -> None:
    spec = validate_openapi.build_generated_spec()
    candidate = deepcopy(spec)
    candidate["openapi"] = "3.0.3"

    errors = validate_openapi.validate_openapi_spec(candidate)

    assert any("3.0.3" in error for error in errors)


def test_validate_openapi_spec_rejects_unresolved_schema_ref() -> None:
    spec = validate_openapi.build_generated_spec()
    candidate = deepcopy(spec)
    candidate["paths"]["/api/webui/version"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ] = {"$ref": "#/components/schemas/MissingSchema"}

    errors = validate_openapi.validate_openapi_spec(candidate)

    assert "unresolved schema reference: #/components/schemas/MissingSchema" in errors
