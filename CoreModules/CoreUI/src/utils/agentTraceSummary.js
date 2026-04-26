/**
 * Derive human-readable summary objects from agent/proxy trace records
 * (journal metadata or GET /api/webui/proxy-traces items).
 */

function num(v, fallback = 0) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function safeArr(x) {
  return Array.isArray(x) ? x : [];
}

/**
 * @param {Record<string, unknown> | null | undefined} meta
 * @returns {Record<string, unknown>}
 */
export function summarizeAgentTraceMeta(meta) {
  if (!meta || typeof meta !== 'object') {
    return { empty: true };
  }

  const steps = safeArr(meta.steps);
  const stepCount = num(meta.step_count, steps.length) || steps.length;
  const durationMs = num(meta.elapsed_ms, 0);

  const modelCalls = steps.filter((s) => s && s.kind === 'model_call');
  const perModelCallTokenRows = modelCalls.map((s) => ({
    step: s.step,
    promptEst: num(s.prompt_tokens_est, 0),
    completionEst: num(s.completion_tokens_est, 0),
    ollamaPec: s.prompt_eval_count != null ? num(s.prompt_eval_count, 0) : (s.ollama_prompt_eval_count != null ? num(s.ollama_prompt_eval_count, 0) : null),
    ollamaEc: s.eval_count != null ? num(s.eval_count, 0) : (s.ollama_eval_count != null ? num(s.ollama_eval_count, 0) : null),
    ok: s.ok !== false,
  }));

  const sumPromptFromSteps = perModelCallTokenRows.reduce((a, r) => a + r.promptEst, 0);
  const sumCompletionFromSteps = perModelCallTokenRows.reduce((a, r) => a + r.completionEst, 0);

  const ragSteps = steps.filter((s) => s && s.kind === 'tool_rag');
  const skillSteps = steps.filter((s) => s && s.kind === 'tool_skill');
  const passThroughSteps = steps.filter((s) => s && s.kind === 'tool_pass_through');

  const ragContextCharsTotal = ragSteps.reduce((a, s) => a + num(s.context_chars, 0), 0);
  const skillContextCharsTotal = skillSteps.reduce((a, s) => a + num(s.context_chars, 0), 0);
  const ragChunksTotal = ragSteps.reduce((a, s) => a + num(s.chunks, 0), 0);

  const ragCalls = ragSteps.map((s) => ({
    step: s.step,
    query: typeof s.query === 'string' ? s.query : '',
    chunks: num(s.chunks, 0),
    ok: s.ok !== false,
    error: s.error != null ? String(s.error) : null,
    contextChars: num(s.context_chars, 0),
  }));

  const skillLoads = skillSteps.map((s) => ({
    step: s.step,
    invocation: typeof s.invocation === 'string' ? s.invocation : '',
    skillId: s.skill_id != null ? String(s.skill_id) : '',
    ok: s.ok !== false,
    error: s.error != null ? String(s.error) : null,
    contextChars: num(s.context_chars, 0),
  }));

  const passThrough = passThroughSteps.map((s) => ({
    step: s.step,
    names: safeArr(s.names).map((n) => String(n)),
  }));

  const serverToolCallsOrdered = [];
  for (const s of modelCalls) {
    const tcs = safeArr(s.tool_calls);
    for (const tc of tcs) {
      const name = tc && typeof tc.name === 'string' ? tc.name.trim() : '';
      if (name) serverToolCallsOrdered.push(name);
    }
  }
  const seen = new Set();
  const serverToolCallsUnique = [];
  for (const n of serverToolCallsOrdered) {
    if (!seen.has(n)) {
      seen.add(n);
      serverToolCallsUnique.push(n);
    }
  }

  const req = meta.request && typeof meta.request === 'object' ? meta.request : null;
  const clientNames = req && Array.isArray(req.client_tool_names) ? req.client_tool_names.map(String) : [];
  const requestMessageCount = req && Array.isArray(req.messages) ? req.messages.length : 0;
  const mergeClientTools =
    req && 'merge_client_tools' in req
      ? req.merge_client_tools
      : meta.merge_client_tools != null
        ? meta.merge_client_tools
        : null;

  const skillsObj = meta.skills && typeof meta.skills === 'object' ? meta.skills : null;

  const resolved =
    meta.resolved_model != null && String(meta.resolved_model).trim()
      ? String(meta.resolved_model)
      : '';
  const legacyLogical =
    meta.logical_model_id != null && String(meta.logical_model_id).trim()
      ? String(meta.logical_model_id)
      : '';
  const displayModel = resolved || legacyLogical || '—';

  let totalPromptTokensEst = num(meta.total_prompt_tokens_est, 0);
  let totalCompletionTokensEst = num(meta.total_completion_tokens_est, 0);
  const ollTok =
    meta.ollama && typeof meta.ollama === 'object' && meta.ollama.tokens_estimates
      ? meta.ollama.tokens_estimates
      : null;
  if (totalPromptTokensEst === 0 && totalCompletionTokensEst === 0 && ollTok && typeof ollTok === 'object') {
    totalPromptTokensEst = num(ollTok.prompt_tokens_estimated, 0);
    totalCompletionTokensEst = num(ollTok.completion_tokens_estimated, 0);
  }
  if (totalPromptTokensEst === 0 && totalCompletionTokensEst === 0) {
    const oc = steps.filter((s) => s && (s.name === 'ollama_chat' || s.name === 'provider_chat_stream' || s.name === 'provider_chat_native_tools'));
    const lastOc = oc.length ? oc[oc.length - 1] : null;
    if (lastOc && typeof lastOc === 'object') {
      totalPromptTokensEst = num(lastOc.tokens_in_est, 0);
      totalCompletionTokensEst = num(lastOc.tokens_out_est, 0);
    }
  }
  let durationMsEff = durationMs;
  if (!durationMsEff && steps.length > 0 && !steps.some((s) => s && s.kind === 'model_call')) {
    durationMsEff = steps.reduce((a, s) => a + num(s && s.duration_ms, 0), 0);
  }

  return {
    empty: false,
    traceId: meta.trace_id != null ? String(meta.trace_id) : '',
    stepCount,
    durationMs: durationMsEff,
    resolvedModel: displayModel,
    logicalModelId: legacyLogical || '—',
    clientModel: meta.client_model != null ? String(meta.client_model) : null,
    thinkRequested: meta.think_requested,
    error: meta.error != null ? String(meta.error) : null,
    totalPromptTokensEst,
    totalCompletionTokensEst,
    sumPromptFromSteps,
    sumCompletionFromSteps,
    perModelCallTokenRows,
    ragContextCharsTotal,
    skillContextCharsTotal,
    ragChunksTotal,
    ragCalls,
    skillLoads,
    skillsSnapshot: skillsObj
      ? {
          enabledCount: num(skillsObj.enabled_count, safeArr(skillsObj.enabled_ids).length),
          loadedCount: num(skillsObj.loaded_count, safeArr(skillsObj.loaded_invocations).length),
          loadedInvocations: safeArr(skillsObj.loaded_invocations).map(String),
          enabledIds: safeArr(skillsObj.enabled_ids).map(String),
        }
      : null,
    serverToolCallsOrdered,
    serverToolCallsUnique,
    passThrough,
    clientToolNamesCount: clientNames.length,
    clientToolNamesPreview: clientNames.slice(0, 12),
    requestMessageCount,
    mergeClientTools,
    processRssMb:
      typeof meta.process_rss_mb === 'number' && Number.isFinite(meta.process_rss_mb) ? meta.process_rss_mb : null,
    final: meta.final === true,
  };
}

/**
 * @typedef {{ key: string, label: string, title?: string, variant: 'tool' | 'rag' | 'skill' | 'client' | 'warn' }} AgentUsageCapsule
 */

/**
 * Pills for live UI: model tool choices, executed RAG, skills, IDE pass-through.
 * @param {Record<string, unknown> | null | undefined} trace
 * @returns {{ capsules: AgentUsageCapsule[] }}
 */
function getAgentTraceUsageCapsules(trace) {
  if (!trace || typeof trace !== 'object') {
    return { capsules: [] };
  }
  const steps = safeArr(trace.steps);
  /** @type {AgentUsageCapsule[]} */
  const capsules = [];

  const ragSteps = steps.filter((s) => s && s.kind === 'tool_rag');
  const skillSteps = steps.filter((s) => s && s.kind === 'tool_skill');
  const passSteps = steps.filter((s) => s && s.kind === 'tool_pass_through');
  const unhandledSteps = steps.filter((s) => s && s.kind === 'tool_unhandled');
  const modelCalls = steps.filter((s) => s && s.kind === 'model_call');

  const hasRagExec = ragSteps.length > 0;
  const hasSkillExec = skillSteps.length > 0;

  const toolCounts = new Map();
  for (const s of modelCalls) {
    for (const tc of safeArr(s.tool_calls)) {
      const n = tc && typeof tc.name === 'string' ? tc.name.trim() : '';
      if (!n) continue;
      if (hasRagExec && n === 'rag_query') continue;
      if (hasSkillExec && n === 'load_skill') continue;
      toolCounts.set(n, (toolCounts.get(n) || 0) + 1);
    }
  }

  const toolNamesSorted = [...toolCounts.keys()].sort((a, b) => a.localeCompare(b));
  for (const name of toolNamesSorted) {
    const cnt = toolCounts.get(name) || 1;
    const v = name === 'rag_query' ? 'rag' : name === 'load_skill' ? 'skill' : 'tool';
    capsules.push({
      key: `m-${name}`,
      label: cnt > 1 ? `${name} ×${cnt}` : name,
      title: cnt > 1 ? `Model requested ${name} (${cnt}×)` : `Model requested: ${name}`,
      variant: v,
    });
  }

  if (hasRagExec) {
    const chunks = ragSteps.reduce((a, s) => a + num(s.chunks, 0), 0);
    const failed = ragSteps.some((s) => s.ok === false);
    const qs = ragSteps.map((s) => (typeof s.query === 'string' ? s.query.trim() : '')).filter(Boolean);
    const titleLines = qs.map((q) => (q.length > 220 ? `${q.slice(0, 219)}…` : q));
    capsules.push({
      key: 'rag-exec',
      label: failed && chunks === 0 ? 'RAG · error' : chunks ? `RAG · ${chunks} chunks` : 'RAG · done',
      title:
        titleLines.length > 0
          ? titleLines.join('\n\n')
          : failed
            ? 'RAG step reported an error'
            : 'Context retrieved via rag_query',
      variant: failed ? 'warn' : 'rag',
    });
  }

  const invocationsFromSteps = new Set(
    skillSteps
      .map((s) => {
        const inv = typeof s.invocation === 'string' ? s.invocation.trim().toLowerCase() : '';
        const sid = s.skill_id != null ? String(s.skill_id).trim().toLowerCase() : '';
        return inv || sid;
      })
      .filter(Boolean),
  );

  const skillStepDedup = new Set();
  for (const s of skillSteps) {
    const inv = typeof s.invocation === 'string' ? s.invocation.trim() : '';
    const sid = s.skill_id != null ? String(s.skill_id).trim() : '';
    const dedupe = (inv || sid).toLowerCase() || `step-${s.step}`;
    if (skillStepDedup.has(dedupe)) continue;
    skillStepDedup.add(dedupe);
    const labelBase = inv || sid || 'skill';
    const ok = s.ok !== false;
    const key = `sk-${dedupe.replace(/\s+/g, '-')}`;
    capsules.push({
      key,
      label: ok ? (labelBase.length > 26 ? `${labelBase.slice(0, 25)}…` : labelBase) : 'Skill · error',
      title: ok
        ? `Skill loaded: ${inv || sid || 'unknown'}`
        : `Skill error: ${s.error != null ? String(s.error).slice(0, 320) : 'failed'}`,
      variant: ok ? 'skill' : 'warn',
    });
  }

  const skillsMeta = trace.skills && typeof trace.skills === 'object' ? trace.skills : null;
  const loadedMeta = skillsMeta && Array.isArray(skillsMeta.loaded_invocations) ? skillsMeta.loaded_invocations.map(String) : [];
  for (const raw of loadedMeta) {
    const t = raw.trim();
    if (!t) continue;
    if (invocationsFromSteps.has(t.toLowerCase())) continue;
    const key = `skmeta-${t}`;
    if (capsules.some((c) => c.key === key)) continue;
    capsules.push({
      key,
      label: t.length > 26 ? `${t.slice(0, 25)}…` : t,
      title: `Skill pack loaded: ${t}`,
      variant: 'skill',
    });
  }

  const clientSeen = new Set();
  for (const s of passSteps) {
    for (const n of safeArr(s.names)) {
      const name = String(n).trim();
      if (!name || clientSeen.has(name)) continue;
      clientSeen.add(name);
      capsules.push({
        key: `cli-${name}`,
        label: `IDE · ${name.length > 22 ? `${name.slice(0, 21)}…` : name}`,
        title: `Returned to IDE for execution: ${name}`,
        variant: 'client',
      });
    }
  }

  for (const s of unhandledSteps) {
    const n = s.name != null ? String(s.name).trim() : '';
    const nm = n || 'unknown';
    capsules.push({
      key: `uh-${nm}-${s.step}`,
      label: `Not run · ${nm.length > 14 ? `${nm.slice(0, 13)}…` : nm}`,
      title: typeof s.note === 'string' && s.note.trim() ? s.note.trim().slice(0, 400) : 'Tool not executed in this runtime',
      variant: 'warn',
    });
  }

  return { capsules };
}
