function nonEmptyString(value) {
  if (value == null) return '';
  const s = String(value).trim();
  return s !== '' ? s : '';
}

function traceRequestObject(trace) {
  if (!trace || typeof trace !== 'object') return {};
  if (trace.request && typeof trace.request === 'object') return trace.request;
  if (trace.trace && typeof trace.trace === 'object' && trace.trace.request && typeof trace.trace.request === 'object') {
    return trace.trace.request;
  }
  return {};
}

export function proxyTraceToolLimitWarning(trace) {
  const req = traceRequestObject(trace);
  if (req.tool_loop_limit_reached !== true) return '';
  const stats = req.tool_loop_stats && typeof req.tool_loop_stats === 'object' ? req.tool_loop_stats : {};
  const rounds = Number(stats.rounds || 0);
  const dominantTool = nonEmptyString(stats.dominant_tool);
  const detail = [
    rounds > 0 ? `${rounds} tool rounds` : '',
    dominantTool,
  ].filter(Boolean).join(', ');
  const headline = detail ? `Tool cap reached (${detail}).` : 'Tool cap reached.';
  return `${headline} The answer may be incomplete and the task may not be finished.`;
}
