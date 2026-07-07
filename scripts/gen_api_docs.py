"""Generate Markdown API reference from the live OpenAPI document."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
CORE_ROOT = REPO_ROOT / "Core"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "api" / "reference.md"

if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))


def build_generated_spec() -> dict[str, Any]:
    from core.bootstrap.import_paths import ensure_webui_composition_paths

    ensure_webui_composition_paths(REPO_ROOT)
    from api.http.rag_routes import create_app
    from core.openapi import build_openapi_spec

    return build_openapi_spec(create_app(bootstrap_extensions=False))


def _escape_table(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _schema_name(schema: dict[str, Any] | None) -> str:
    if not schema:
        return "object"
    ref = schema.get("$ref")
    if isinstance(ref, str):
        return ref.rsplit("/", 1)[-1]
    if "oneOf" in schema:
        return "oneOf"
    schema_type = schema.get("type")
    if isinstance(schema_type, str):
        if schema_type == "array":
            item = schema.get("items") if isinstance(schema.get("items"), dict) else None
            return f"array<{_schema_name(item)}>"
        return schema_type
    return "object"


def _request_body_label(operation: dict[str, Any]) -> str:
    body = operation.get("requestBody")
    if not isinstance(body, dict):
        return "-"
    content = body.get("content")
    if not isinstance(content, dict):
        return "body"
    labels: list[str] = []
    for media_type, media in sorted(content.items()):
        schema = media.get("schema") if isinstance(media, dict) else None
        labels.append(f"{media_type}: {_schema_name(schema if isinstance(schema, dict) else None)}")
    return ", ".join(labels) if labels else "body"


def _response_rows(operation: dict[str, Any]) -> list[tuple[str, str, str]]:
    responses = operation.get("responses")
    if not isinstance(responses, dict):
        return []
    rows: list[tuple[str, str, str]] = []
    for status, response in sorted(responses.items()):
        if not isinstance(response, dict):
            rows.append((str(status), "", ""))
            continue
        description = str(response.get("description") or "")
        content = response.get("content")
        schema_label = ""
        if isinstance(content, dict):
            schema_bits: list[str] = []
            for media_type, media in sorted(content.items()):
                schema = media.get("schema") if isinstance(media, dict) else None
                schema_bits.append(f"{media_type}: {_schema_name(schema if isinstance(schema, dict) else None)}")
            schema_label = ", ".join(schema_bits)
        rows.append((str(status), description, schema_label))
    return rows


def _parameters_table(operation: dict[str, Any]) -> list[str]:
    parameters = operation.get("parameters")
    if not isinstance(parameters, list) or not parameters:
        return []
    lines = ["| Name | In | Required | Schema |", "|------|----|----------|--------|"]
    for parameter in parameters:
        if not isinstance(parameter, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_table(parameter.get("name", "")),
                    _escape_table(parameter.get("in", "")),
                    _escape_table(parameter.get("required", False)),
                    _escape_table(_schema_name(parameter.get("schema") if isinstance(parameter.get("schema"), dict) else None)),
                ]
            )
            + " |"
        )
    return lines


def _schema_summary(spec: dict[str, Any]) -> list[str]:
    schemas = ((spec.get("components") or {}).get("schemas") or {})
    if not isinstance(schemas, dict) or not schemas:
        return []
    lines = ["## Component Schemas", ""]
    lines.append("| Name | Type | Required Fields |")
    lines.append("|------|------|-----------------|")
    for name, schema in sorted(schemas.items()):
        if not isinstance(schema, dict):
            continue
        required = schema.get("required")
        required_label = ", ".join(map(str, required)) if isinstance(required, list) and required else "-"
        lines.append(
            f"| {_escape_table(name)} | {_escape_table(_schema_name(schema))} | {_escape_table(required_label)} |"
        )
    lines.append("")
    return lines


def render_markdown(spec: dict[str, Any]) -> str:
    info = spec.get("info") if isinstance(spec.get("info"), dict) else {}
    title = str(info.get("title") or "ChironAI API")
    version = str(info.get("version") or "")
    description = str(info.get("description") or "").strip()
    paths = spec.get("paths") if isinstance(spec.get("paths"), dict) else {}

    lines = [
        f"# {title} Reference",
        "",
        "> Generated from the live OpenAPI document. Do not edit by hand; run `python scripts/gen_api_docs.py`.",
        "",
        f"- OpenAPI: `{spec.get('openapi', '')}`",
        f"- Version: `{version}`",
        f"- Paths: `{len(paths)}`",
    ]
    if description:
        lines.extend(["", description])

    grouped: dict[str, list[tuple[str, str, dict[str, Any]]]] = defaultdict(list)
    for path, path_item in sorted(paths.items()):
        if not isinstance(path_item, dict):
            continue
        for method, operation in sorted(path_item.items()):
            if not isinstance(operation, dict) or str(method).startswith("x-"):
                continue
            tags = operation.get("tags")
            tag = str(tags[0]) if isinstance(tags, list) and tags else "Untagged"
            grouped[tag].append((str(method).upper(), str(path), operation))

    lines.extend(["", "## Endpoints", ""])
    for tag in sorted(grouped):
        lines.extend([f"### {tag}", ""])
        for method, path, operation in grouped[tag]:
            summary = str(operation.get("summary") or operation.get("operationId") or "").strip()
            description = str(operation.get("description") or "").strip()
            lines.extend([f"#### `{method} {path}`", ""])
            if summary:
                lines.extend([f"**Summary:** {summary}", ""])
            if description:
                lines.extend([description, ""])
            lines.extend(
                [
                    f"- Operation ID: `{operation.get('operationId', '')}`",
                    f"- Flask endpoint: `{operation.get('x-flask-endpoint', '')}`",
                    f"- Request body: `{_request_body_label(operation)}`",
                    "",
                ]
            )
            parameter_lines = _parameters_table(operation)
            if parameter_lines:
                lines.extend(["Parameters:", "", *parameter_lines, ""])
            response_rows = _response_rows(operation)
            if response_rows:
                lines.extend(["Responses:", "", "| Status | Description | Schema |", "|--------|-------------|--------|"])
                for status, response_description, schema_label in response_rows:
                    lines.append(
                        f"| {_escape_table(status)} | {_escape_table(response_description)} | {_escape_table(schema_label or '-')} |"
                    )
                lines.append("")

    lines.extend(_schema_summary(spec))
    return "\n".join(lines).rstrip() + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate docs/api/reference.md from OpenAPI.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Markdown output path.")
    parser.add_argument("--check", action="store_true", help="Fail if the output file is missing or stale.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    spec = build_generated_spec()
    rendered = render_markdown(spec)
    output = args.output if args.output.is_absolute() else REPO_ROOT / args.output

    if args.check:
        current = output.read_text(encoding="utf-8") if output.exists() else None
        if current != rendered:
            print(f"API reference is stale: {output}")
            print("Run: python scripts/gen_api_docs.py")
            return 1
        print(f"API reference is up to date: {output}")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    print(f"Wrote {output} ({len(spec.get('paths') or {})} paths).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
