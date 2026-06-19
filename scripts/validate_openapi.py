"""Validate the generated OpenAPI document."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

REPO_ROOT = Path(__file__).resolve().parent.parent
CORE_ROOT = REPO_ROOT / "Core"
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

OPENAPI_DOCUMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["openapi", "info", "paths"],
    "properties": {
        "openapi": {"type": "string", "pattern": r"^3\.1\.\d+$"},
        "jsonSchemaDialect": {"type": "string"},
        "info": {
            "type": "object",
            "required": ["title", "version"],
            "properties": {
                "title": {"type": "string", "minLength": 1},
                "version": {"type": "string", "minLength": 1},
                "description": {"type": "string"},
            },
            "additionalProperties": True,
        },
        "servers": {"type": "array", "items": {"type": "object"}},
        "paths": {"type": "object", "minProperties": 1},
        "components": {"type": "object"},
    },
    "additionalProperties": True,
}

HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def _format_path(path: tuple[Any, ...]) -> str:
    if not path:
        return "$"
    return "$." + ".".join(str(part) for part in path)


def _iter_schema_refs(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str):
            yield ref
        for child in value.values():
            yield from _iter_schema_refs(child)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_schema_refs(item)


def _iter_component_schemas(spec: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    schemas = ((spec.get("components") or {}).get("schemas") or {})
    if isinstance(schemas, dict):
        for name, schema in schemas.items():
            if isinstance(name, str) and isinstance(schema, dict):
                yield name, schema


def validate_openapi_spec(spec: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    validator = Draft202012Validator(OPENAPI_DOCUMENT_SCHEMA)
    for error in sorted(validator.iter_errors(spec), key=lambda item: list(item.path)):
        errors.append(f"{_format_path(tuple(error.path))}: {error.message}")

    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return errors

    for route, path_item in paths.items():
        if not isinstance(route, str) or not route.startswith("/"):
            errors.append(f"paths key {route!r} must start with /")
            continue
        if not isinstance(path_item, dict):
            errors.append(f"paths.{route}: path item must be an object")
            continue
        for method, operation in path_item.items():
            if str(method).startswith("x-"):
                continue
            if method not in HTTP_METHODS:
                errors.append(f"paths.{route}.{method}: unsupported HTTP method")
                continue
            if not isinstance(operation, dict):
                errors.append(f"paths.{route}.{method}: operation must be an object")
                continue
            if not operation.get("operationId"):
                errors.append(f"paths.{route}.{method}: operationId is required")
            responses = operation.get("responses")
            if not isinstance(responses, dict) or not responses:
                errors.append(f"paths.{route}.{method}: responses object is required")

    component_names = {name for name, _ in _iter_component_schemas(spec)}
    for ref in _iter_schema_refs(spec):
        prefix = "#/components/schemas/"
        if ref.startswith(prefix) and ref[len(prefix) :] not in component_names:
            errors.append(f"unresolved schema reference: {ref}")

    for name, schema in _iter_component_schemas(spec):
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            errors.append(f"components.schemas.{name}: {exc.message}")

    return errors


def build_generated_spec() -> dict[str, Any]:
    from core.bootstrap.import_paths import ensure_webui_composition_paths

    ensure_webui_composition_paths(REPO_ROOT)
    from api.http.rag_routes import create_app
    from core.openapi import build_openapi_spec

    return build_openapi_spec(create_app())


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description="Validate the generated OpenAPI 3.1 document.")


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)

    try:
        spec = build_generated_spec()
        errors = validate_openapi_spec(spec)
    except (ImportError, OSError, ValidationError) as exc:
        print(f"OpenAPI validation failed: {exc}")
        return 1

    if errors:
        print("OpenAPI validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"OpenAPI validation passed: {spec.get('openapi')} with {len(spec.get('paths') or {})} paths.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
