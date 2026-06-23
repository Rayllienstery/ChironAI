import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const coreUiRoot = path.resolve(scriptDir, '..');
const repoRoot = path.resolve(coreUiRoot, '..', '..');
const outputPath = path.join(coreUiRoot, 'src', 'services', 'api.types.ts');

const pythonCode = `
import json
from pathlib import Path
import sys

repo = Path.cwd()
for rel in ("Core", "Core/modules/webui_backend"):
    path = str(repo / rel)
    if path not in sys.path:
        sys.path.insert(0, path)

from api.http.rag_routes import create_app
from core.openapi import build_openapi_spec

app = create_app()
print(json.dumps(build_openapi_spec(app), sort_keys=True))
`;

const generated = spawnSync('python', ['-c', pythonCode], {
  cwd: repoRoot,
  env: {
    ...process.env,
    PYTHONPATH: [
      path.join(repoRoot, 'Core'),
      path.join(repoRoot, 'Core', 'modules', 'webui_backend'),
      process.env.PYTHONPATH || '',
    ].filter(Boolean).join(path.delimiter),
  },
  encoding: 'utf8',
  maxBuffer: 1024 * 1024 * 20,
});

if (generated.error) {
  if (generated.error.code === 'ENOENT' && existsSync(outputPath)) {
    console.warn(
      `Python is unavailable; keeping existing ${path.relative(repoRoot, outputPath)} for this build.`,
    );
    process.exit(0);
  }
  process.stderr.write(generated.error.message || String(generated.error));
  process.exit(1);
}

if (generated.status !== 0) {
  process.stderr.write(generated.stderr || generated.stdout || 'OpenAPI type generation failed.');
  process.exit(generated.status || 1);
}

const spec = JSON.parse(generated.stdout);

function q(value) {
  return JSON.stringify(value);
}

function refName(ref) {
  return String(ref || '').split('/').pop() || 'unknown';
}

function schemaToTs(schema, fallback = 'unknown') {
  if (!schema || typeof schema !== 'object') return fallback;
  if (schema.$ref) return `components["schemas"][${q(refName(schema.$ref))}]`;
  if (Array.isArray(schema.enum)) return schema.enum.map((value) => q(value)).join(' | ') || 'never';
  if (Array.isArray(schema.oneOf)) return schema.oneOf.map((item) => schemaToTs(item)).join(' | ') || fallback;
  if (Array.isArray(schema.anyOf)) return schema.anyOf.map((item) => schemaToTs(item)).join(' | ') || fallback;
  if (Array.isArray(schema.allOf)) return schema.allOf.map((item) => schemaToTs(item)).join(' & ') || fallback;

  const type = Array.isArray(schema.type) ? schema.type.filter((item) => item !== 'null')[0] : schema.type;
  const nullable = Array.isArray(schema.type) ? schema.type.includes('null') : schema.nullable === true;
  let out;

  switch (type) {
    case 'string':
      out = 'string';
      break;
    case 'integer':
    case 'number':
      out = 'number';
      break;
    case 'boolean':
      out = 'boolean';
      break;
    case 'array':
      out = `${schemaToTs(schema.items, 'unknown')}[]`;
      break;
    case 'object':
    default:
      out = objectSchemaToTs(schema);
      break;
  }

  return nullable ? `${out} | null` : out;
}

function objectSchemaToTs(schema) {
  const properties = schema.properties && typeof schema.properties === 'object' ? schema.properties : null;
  const required = new Set(Array.isArray(schema.required) ? schema.required : []);
  if (!properties) {
    if (schema.additionalProperties && typeof schema.additionalProperties === 'object') {
      return `Record<string, ${schemaToTs(schema.additionalProperties)}>`;
    }
    return schema.additionalProperties === false ? 'Record<string, never>' : 'Record<string, unknown>';
  }

  const lines = ['{'];
  for (const [name, value] of Object.entries(properties)) {
    const optional = required.has(name) ? '' : '?';
    lines.push(`    ${q(name)}${optional}: ${schemaToTs(value)};`);
  }
  if (schema.additionalProperties && typeof schema.additionalProperties === 'object') {
    lines.push(`    [key: string]: ${schemaToTs(schema.additionalProperties)};`);
  } else if (schema.additionalProperties === true) {
    lines.push('    [key: string]: unknown;');
  }
  lines.push('  }');
  return lines.join('\n');
}

function contentSchema(content) {
  if (!content || typeof content !== 'object') return 'never';
  const json = content['application/json'] || content['application/problem+json'];
  return schemaToTs(json?.schema, 'unknown');
}

function parametersToTs(parameters) {
  const grouped = {};
  for (const param of Array.isArray(parameters) ? parameters : []) {
    if (!param || typeof param !== 'object') continue;
    const location = param.in || 'query';
    grouped[location] ||= [];
    grouped[location].push(param);
  }
  const locations = Object.entries(grouped);
  if (locations.length === 0) return 'never';
  const lines = ['{'];
  for (const [location, params] of locations) {
    lines.push(`      ${q(location)}: {`);
    for (const param of params) {
      const optional = param.required ? '' : '?';
      lines.push(`        ${q(param.name)}${optional}: ${schemaToTs(param.schema)};`);
    }
    lines.push('      };');
  }
  lines.push('    }');
  return lines.join('\n');
}

function requestBodyToTs(requestBody) {
  if (!requestBody || typeof requestBody !== 'object') return 'never';
  return contentSchema(requestBody.content);
}

function responsesToTs(responses) {
  if (!responses || typeof responses !== 'object') return 'never';
  const lines = ['{'];
  for (const [status, response] of Object.entries(responses)) {
    lines.push(`      ${q(status)}: ${contentSchema(response?.content)};`);
  }
  lines.push('    }');
  return lines.join('\n');
}

function operationToTs(operation) {
  return [
    '{',
    `    parameters: ${parametersToTs(operation.parameters)};`,
    `    requestBody: ${requestBodyToTs(operation.requestBody)};`,
    `    responses: ${responsesToTs(operation.responses)};`,
    '  }',
  ].join('\n');
}

const schemas = spec.components?.schemas || {};
const lines = [
  '/* eslint-disable */',
  '// This file is generated by CoreModules/CoreUI/scripts/gen_api_types.mjs.',
  '// Source of truth: backend OpenAPI from core.openapi.build_openapi_spec(create_app()).',
  '',
  'interface components {',
  '  schemas: {',
];

for (const [name, schema] of Object.entries(schemas)) {
  lines.push(`    ${q(name)}: ${schemaToTs(schema)};`);
}

lines.push('  };', '}', '', 'export interface paths {');

for (const [route, methods] of Object.entries(spec.paths || {})) {
  lines.push(`  ${q(route)}: {`);
  for (const [method, operation] of Object.entries(methods || {})) {
    lines.push(`  ${method}: ${operationToTs(operation)};`);
  }
  lines.push('  };');
}

lines.push('}', '');

mkdirSync(path.dirname(outputPath), { recursive: true });
let output = `${lines.join('\n')}\n`;
try {
  const prettier = await import('prettier');
  output = await prettier.format(output, { parser: 'typescript' });
} catch {
  // Keep generation dependency-light; formatting is best-effort when Prettier is available.
}
writeFileSync(outputPath, output, 'utf8');
console.log(`Generated ${path.relative(repoRoot, outputPath)} from ${Object.keys(spec.paths || {}).length} OpenAPI paths.`);
