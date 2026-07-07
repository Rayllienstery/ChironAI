import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = path.resolve(root, '..', '..');
const catalogRoot = path.join(repoRoot, 'CoreModules', 'Localization', 'localization', 'catalog');
const sourceLocale = 'en';
const locales = ['en', 'uk'];
const allowIdentical = new Set([
  'app.title',
  'nav.docker',
  'nav.rag',
  'nav.rag_fusion_proxy',
  'nav.swagger',
  'settings.db_path.placeholder',
  'crawler.md_pipeline.params.end_regex_placeholder',
  'trace.summary.trace_id',
  'trace.summary.merge_client_tools',
  'trace.summary.rag',
  'trace.summary.status_ok',
  'trace.summary.eval',
  'trace.summary.tools_in_schema_suffix',
  'trace.summary.tools_in_schema_end',
]);

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function collectSourceFiles(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === 'node_modules' || entry.name === 'dist') continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...collectSourceFiles(full));
    } else if (/\.(js|jsx|ts|tsx)$/.test(entry.name) && !/\.(test|spec|stories)\./.test(entry.name)) {
      out.push(full);
    }
  }
  return out;
}

function scanHardcodedStrings() {
  const srcRoot = path.join(root, 'src');
  const files = collectSourceFiles(srcRoot);
  const jsxTextPattern = />\s*([^<>{}\n][^<>{}\n]{3,})\s*</g;
  const warnings = [];

  for (const file of files) {
    const rel = path.relative(root, file);
    if (rel.replace(/\\/g, '/').endsWith('DevDocumentationTab.jsx')) continue;
    const text = fs.readFileSync(file, 'utf8');
    for (const match of text.matchAll(jsxTextPattern)) {
      const literal = String(match[1] || '').replace(/\s+/g, ' ').trim();
      if (!/[A-Za-z][A-Za-z ]{3,}/.test(literal)) continue;
      if (/^(settings|close|menu|delete|edit|save|refresh|search)$/i.test(literal)) continue;
      warnings.push(`${path.relative(root, file)}: "${literal.slice(0, 100)}"`);
    }
  }
  return warnings;
}

const source = readJson(path.join(catalogRoot, sourceLocale, 'common.json'));
const sourceKeys = Object.keys(source).sort();
const failures = [];

for (const locale of locales) {
  const catalog = readJson(path.join(catalogRoot, locale, 'common.json'));
  const keys = Object.keys(catalog).sort();
  const missing = sourceKeys.filter((key) => !(key in catalog));
  const extra = keys.filter((key) => !(key in source));
  const empty = keys.filter((key) => String(catalog[key] ?? '').trim() === '');
  const untranslated =
    locale === sourceLocale
      ? []
      : sourceKeys.filter((key) => {
          if (allowIdentical.has(key)) return false;
          if (key.startsWith('crawler.md_step.') && (key.endsWith('.description') || key.endsWith('.example'))) {
            return false;
          }
          return String(catalog[key]) === String(source[key]);
        });

  if (missing.length > 0) failures.push(`${locale}: missing keys: ${missing.join(', ')}`);
  if (extra.length > 0) failures.push(`${locale}: extra keys: ${extra.join(', ')}`);
  if (empty.length > 0) failures.push(`${locale}: empty values: ${empty.join(', ')}`);
  if (untranslated.length > 0) failures.push(`${locale}: untranslated values: ${untranslated.join(', ')}`);
}

const hardcoded = scanHardcodedStrings();
if (hardcoded.length > 0) {
  console.warn(`i18n-lint advisory: ${hardcoded.length} possible hardcoded UI strings found.`);
  for (const row of hardcoded.slice(0, 25)) console.warn(`  ${row}`);
  if (hardcoded.length > 25) console.warn(`  ... ${hardcoded.length - 25} more`);
}

if (failures.length > 0) {
  console.error(failures.join('\n'));
  process.exit(1);
}

console.log(`i18n-lint passed: ${locales.length} locales, ${sourceKeys.length} keys, 0 untranslated.`);
