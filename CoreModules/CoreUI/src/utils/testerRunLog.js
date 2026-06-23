/**
 * Model Tester "Run log" cards (same layout tokens as RAG Chunks) + debug trace ids.
 */

function formatDurationMs(ms) {
  if (ms == null) return null;
  const n = Number(ms);
  if (Number.isNaN(n)) return null;
  if (n < 1000) return `${n} ms`;
  return `${(n / 1000).toFixed(2)} s`;
}

/**
 * Collect non-empty debug / correlation ids from a tester chat API result.
 * @param {Record<string, unknown>|null|undefined} result
 * @returns {string[]}
 */
function collectDebugTraceIds(result) {
  if (!result || typeof result !== 'object') return [];
  const seen = new Set();
  const out = [];
  const push = (v) => {
    if (v == null) return;
    const s = String(v).trim();
    if (!s || seen.has(s)) return;
    seen.add(s);
    out.push(s);
  };
  push(result.trace_id);
  push(result.tester_request_id);
  const id = result.id;
  if (typeof id === 'string' && id.startsWith('chatcmpl-')) push(id);
  return out;
}

/**
 * @param {Record<string, unknown>|null|undefined} result
 * @returns {{ label: string, value: string }[]}
 */
function debugTraceIdRows(result) {
  if (!result || typeof result !== 'object') return [];
  const rows = [];
  const seen = new Set();
  const add = (label, value) => {
    if (value == null) return;
    const s = String(value).trim();
    if (!s || seen.has(s)) return;
    seen.add(s);
    rows.push({ label, value: s });
  };
  add('tester_request_id', result.tester_request_id);
  add('trace_id', result.trace_id);
  const id = result.id;
  if (typeof id === 'string' && id.trim()) add('completion id', id);
  return rows;
}

/**
 * Build flat list of run-log cards for Model Tester UI.
 * @param {object} options
 * @param {Record<string, unknown>|null} options.result — successful testerChat JSON
 * @param {string|null} options.errorMessage — set on fetch failure
 */
export function buildTesterRunLogCards({ result, errorMessage }) {
  const cards = [];

  if (errorMessage) {
    cards.push({
      key: 'error',
      indexLabel: '#!',
      badges: [{ key: 'err', text: 'error', variant: 'score' }],
      body: errorMessage,
      skillClickable: false,
    });
    return { cards, skillsBlock: null, debugIds: [] };
  }

  if (!result || typeof result !== 'object') {
    return { cards, skillsBlock: null, debugIds: [] };
  }

  const debugIds = collectDebugTraceIds(result);
  let idx = 0;
  const nextIndex = () => {
    idx += 1;
    return `#${idx}`;
  };

  const rm = result.rag_metadata;
  const ragTrace = rm && Array.isArray(rm.rag_trace) ? rm.rag_trace : null;

  if (ragTrace && ragTrace.length > 0) {
    ragTrace.forEach((step, i) => {
      const id = step && step.id != null ? String(step.id) : `rag-${i}`;
      const label = (step && step.label) || id;
      const status = step && step.status != null ? String(step.status) : '';
      const dur = formatDurationMs(step && step.duration_ms);
      const badges = [];
      if (dur) badges.push({ key: 'dur', text: dur, variant: 'score' });
      if (status) badges.push({ key: 'st', text: status, variant: 'rerank' });
      const detail = step && step.detail != null ? String(step.detail) : '';
      cards.push({
        key: `rag-${id}-${i}`,
        indexLabel: nextIndex(),
        title: label,
        badges,
        body: detail || null,
        skillClickable: false,
      });
    });
  }

  const usage = result.usage && typeof result.usage === 'object' ? result.usage : {};
  const pt = usage.prompt_tokens;
  const ct = usage.completion_tokens;
  const tt = usage.total_tokens;
  const lat = typeof result.latency_ms === 'number' ? result.latency_ms : null;
  const llmMs = typeof result.llm_phase_ms === 'number' ? result.llm_phase_ms : null;

  const llmBadges = [];
  const llmDur = formatDurationMs(llmMs != null ? llmMs : lat);
  if (llmMs != null) {
    llmBadges.push({ key: 'llm', text: `LLM ${formatDurationMs(llmMs)}`, variant: 'score' });
    if (lat != null && llmMs !== lat) llmBadges.push({ key: 'tot', text: `total ${formatDurationMs(lat)}`, variant: 'rerank' });
  } else if (lat != null) {
    llmBadges.push({ key: 'lat', text: formatDurationMs(lat), variant: 'score' });
  }
  if (pt != null && ct != null) {
    llmBadges.push({ key: 'tok', text: `${pt} in / ${ct} out`, variant: llmBadges.length ? 'rerank' : 'score' });
  } else if (tt != null) {
    llmBadges.push({ key: 'tt', text: `tokens ~${tt}`, variant: llmBadges.length ? 'rerank' : 'score' });
  }

  const llmDetailParts = [];
  if (llmMs == null && lat != null) llmDetailParts.push('LLM duration: total request latency (no separate LLM phase).');

  cards.push({
    key: 'llm-completion',
    indexLabel: nextIndex(),
    title: 'Model response (LLM)',
    badges: llmBadges,
    body: llmDetailParts.length ? llmDetailParts.join('\n') : null,
    skillClickable: false,
  });

  const sk = result.skills && typeof result.skills === 'object' ? result.skills : null;
  const inv = sk && Array.isArray(sk.loaded_invocations) ? sk.loaded_invocations.filter(Boolean).map(String) : [];
  const loadedFromCount = sk && sk.loaded_count != null ? Number(sk.loaded_count) : NaN;
  const loadedNum = !Number.isNaN(loadedFromCount) ? loadedFromCount : inv.length;
  const enabledRun = sk && typeof sk.enabled_count === 'number' ? sk.enabled_count : null;
  let skillsBlock = null;

  if (sk && (loadedNum > 0 || inv.length > 0 || enabledRun != null)) {
    skillsBlock = { loaded: loadedNum, enabled: enabledRun, invocations: inv };
    cards.push({
      key: 'skills-summary',
      indexLabel: nextIndex(),
      title: 'Skills',
      badges: [
        { key: 'ld', text: `Loaded: ${loadedNum}`, variant: 'score' },
        ...(enabledRun != null
          ? [{ key: 'en', text: `Enabled in run: ${enabledRun}`, variant: 'rerank' }]
          : []),
      ],
      body: null,
      skillClickable: false,
    });
    inv.forEach((name, j) => {
      cards.push({
        key: `skill-${name}-${j}`,
        indexLabel: nextIndex(),
        title: name,
        badges: [],
        body: 'Loaded invocation (see proxy / agent traces for SKILL.md context).',
        skillClickable: false,
      });
    });
  }

  return { cards, skillsBlock, debugIds, debugRows: debugTraceIdRows(result) };
}
