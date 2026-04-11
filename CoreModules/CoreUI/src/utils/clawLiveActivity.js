/**
 * Human-readable ClawCode trace / step labels for live notifications.
 * @param {string} s
 * @param {number} max
 */
function truncateText(s, max) {
  if (s.length <= max) return s;
  return `${s.slice(0, Math.max(0, max - 1))}…`;
}

/**
 * @param {unknown} content
 * @returns {string}
 */
function previewMessageContent(content) {
  if (content == null) return '';
  if (typeof content === 'string') return content.trim();
  if (Array.isArray(content)) {
    const parts = [];
    for (const p of content) {
      if (p && typeof p === 'object' && p.type === 'text' && typeof p.text === 'string') {
        parts.push(p.text.trim());
      }
    }
    return parts.join(' ').trim();
  }
  return String(content).trim();
}

/**
 * Last user message preview from trace.request (OpenAI-style messages).
 * @param {Record<string, unknown> | null | undefined} trace
 * @returns {string}
 */
export function getClawTraceTaskLine(trace) {
  if (!trace || typeof trace !== 'object') return '';
  const req = trace.request;
  if (!req || typeof req !== 'object') return '';
  const msgs = Array.isArray(req.messages) ? req.messages : [];
  for (let i = msgs.length - 1; i >= 0; i -= 1) {
    const m = msgs[i];
    if (!m || typeof m !== 'object') continue;
    if (String(m.role || '') !== 'user') continue;
    const text = previewMessageContent(m.content);
    if (text) return truncateText(text, 160);
  }
  return '';
}

/**
 * @param {Record<string, unknown> | null | undefined} step
 * @returns {{ primary: string, secondary?: string, tone: 'model' | 'tools' | 'rag' | 'skill' | 'idle' }}
 */
function describeStepRecord(step) {
  if (!step || typeof step !== 'object') {
    return { primary: 'Working…', tone: 'idle' };
  }
  const kind = step.kind != null ? String(step.kind) : '';

  if (kind === 'proxy_queued') {
    const note = typeof step.note === 'string' && step.note.trim() ? step.note.trim() : '';
    return {
      primary: 'Request accepted',
      secondary: note || undefined,
      tone: 'idle',
    };
  }
  if (kind === 'tool_rag') {
    const q = typeof step.query === 'string' && step.query.trim() ? step.query.trim() : '';
    return {
      primary: 'RAG search (rag_query)',
      secondary: q ? truncateText(q, 100) : undefined,
      tone: 'rag',
    };
  }
  if (kind === 'tool_skill') {
    const inv = typeof step.invocation === 'string' && step.invocation.trim() ? step.invocation.trim() : '';
    const sid = step.skill_id != null && String(step.skill_id).trim() ? String(step.skill_id).trim() : '';
    const bits = [inv && `invocation: ${truncateText(inv, 72)}`, sid && `skill_id: ${truncateText(sid, 40)}`].filter(
      Boolean,
    );
    return {
      primary: 'Load skill (load_skill)',
      secondary: bits.length ? bits.join(' · ') : undefined,
      tone: 'skill',
    };
  }
  if (kind === 'tool_pass_through') {
    const names = Array.isArray(step.names) ? step.names.map((n) => String(n)).filter(Boolean) : [];
    return {
      primary: 'Return tool batch to IDE (client execution)',
      secondary: names.length ? truncateText(names.join(', '), 100) : undefined,
      tone: 'tools',
    };
  }
  if (kind === 'tool_unhandled') {
    const n = step.name != null ? String(step.name) : '';
    const note = typeof step.note === 'string' && step.note.trim() ? truncateText(step.note.trim(), 120) : '';
    return {
      primary: n ? `Tool not run in ClawCode: ${truncateText(n, 48)}` : 'Tool not run in ClawCode',
      secondary: note || undefined,
      tone: 'tools',
    };
  }
  if (kind === 'model_call') {
    const tcs = Array.isArray(step.tool_calls) ? step.tool_calls : [];
    if (tcs.length > 0) {
      const names = tcs
        .map((t) => (t && typeof t === 'object' && t.name != null ? String(t.name).trim() : ''))
        .filter(Boolean);
      const first = tcs[0] && typeof tcs[0] === 'object' ? tcs[0] : null;
      const rawArgs = first && typeof first.arguments === 'string' ? first.arguments.trim() : '';
      const argOneLine = rawArgs ? truncateText(rawArgs.replace(/\s+/g, ' '), 88) : '';
      return {
        primary: names.length ? `Model chose tools: ${truncateText(names.join(', '), 72)}` : 'Model chose tools',
        secondary: argOneLine || undefined,
        tone: 'tools',
      };
    }
    const vis = typeof step.assistant_visible === 'string' ? step.assistant_visible.trim() : '';
    if (vis) {
      return {
        primary: 'Model wrote assistant text',
        secondary: truncateText(vis, 120),
        tone: 'model',
      };
    }
    const th = typeof step.thinking_raw === 'string' ? step.thinking_raw.trim() : '';
    if (th) {
      return {
        primary: 'Model thinking (reasoning)',
        secondary: truncateText(th, 120),
        tone: 'model',
      };
    }
    const fr = step.finish_reason != null ? String(step.finish_reason).trim() : '';
    const dr = step.ollama_done_reason != null ? String(step.ollama_done_reason).trim() : '';
    const meta = [fr && `finish: ${fr}`, dr && `ollama: ${dr}`].filter(Boolean).join(' · ');
    return {
      primary: 'Model call',
      secondary: meta || undefined,
      tone: 'model',
    };
  }

  return { primary: 'Working…', tone: 'idle' };
}

/**
 * Last step in trace as structured description.
 * @param {Record<string, unknown> | null | undefined} trace
 */
export function getClawTraceStepDescription(trace) {
  if (!trace || typeof trace !== 'object') {
    return { primary: 'Starting…', tone: 'idle' };
  }
  const steps = Array.isArray(trace.steps) ? trace.steps : [];
  if (steps.length === 0) {
    return { primary: 'Starting…', tone: 'idle' };
  }
  const last = steps[steps.length - 1];
  return describeStepRecord(last);
}

/**
 * Flat strings for notification snap / compact cards.
 * @param {Record<string, unknown> | null | undefined} trace
 */
export function getClawTraceNotificationFields(trace) {
  const task = getClawTraceTaskLine(trace);
  const { primary, secondary, tone } = getClawTraceStepDescription(trace);
  return {
    run_line: task,
    step_primary: primary,
    step_secondary: secondary,
    tone,
  };
}
