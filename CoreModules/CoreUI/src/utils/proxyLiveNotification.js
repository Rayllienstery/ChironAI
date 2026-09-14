function numOrNull(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function nonEmptyString(value) {
  if (value == null) return '';
  const s = String(value).trim();
  return s !== '' ? s : '';
}

function traceRequest(trace) {
  return trace && typeof trace === 'object' && trace.request && typeof trace.request === 'object'
    ? trace.request
    : {};
}

function traceProvider(trace) {
  if (!trace || typeof trace !== 'object') return {};
  const provider = trace.provider || trace.ollama;
  return provider && typeof provider === 'object' ? provider : {};
}

export function traceIsSseStream(trace) {
  const req = traceRequest(trace);
  if (Boolean(req.stream) || Boolean(req.ollama_chat_stream)) return true;
  return Boolean(traceProvider(trace).chat_stream);
}

function providerTokensEstimates(trace) {
  const estimates = traceProvider(trace).tokens_estimates;
  return estimates && typeof estimates === 'object' ? estimates : {};
}

export function liveStreamCompletionTokens(trace) {
  if (!traceIsSseStream(trace)) return null;
  const n = numOrNull(providerTokensEstimates(trace).completion_tokens_estimated);
  return n != null && n >= 0 ? Math.floor(n) : 0;
}

function liveUsedContextTokens(trace) {
  const estimates = providerTokensEstimates(trace);
  const total = numOrNull(estimates.total_tokens_estimated);
  if (total != null && total >= 0) return Math.floor(total);
  const prompt = numOrNull(estimates.prompt_tokens_estimated);
  const completion = numOrNull(estimates.completion_tokens_estimated);
  if (prompt != null && prompt >= 0 && completion != null && completion >= 0) {
    return Math.floor(prompt + completion);
  }
  if (prompt != null && prompt >= 0) return Math.floor(prompt);
  if (completion != null && completion >= 0) return Math.floor(completion);
  return null;
}

function liveContextWindowTokens(trace) {
  const request = traceRequest(trace);
  const fromReq = numOrNull(request.effective_num_ctx);
  if (fromReq != null && fromReq > 0) return Math.floor(fromReq);
  const budget = request.input_budget && typeof request.input_budget === 'object'
    ? request.input_budget
    : {};
  const fromBudget = numOrNull(budget.num_ctx);
  if (fromBudget != null && fromBudget > 0) return Math.floor(fromBudget);
  return null;
}

export function liveContextWindowUsage(trace) {
  const used = liveUsedContextTokens(trace);
  const window = liveContextWindowTokens(trace);
  if (used == null || used <= 0 || window == null || window <= 0) return null;
  return { used, window, percent: (used / window) * 100 };
}

export function formatContextWindowPercent(percent) {
  const n = Number(percent);
  if (!Number.isFinite(n) || n < 0) return null;
  if (n > 0 && n < 0.5) return '<1%';
  return `${Math.round(n)}%`;
}

export function liveUrlFetchCount(trace) {
  const request = traceRequest(trace);
  const internet = trace && typeof trace === 'object' && trace.internet && typeof trace.internet === 'object'
    ? trace.internet
    : {};
  const n = numOrNull(request.url_fetch_count) ?? numOrNull(internet.url_fetch_count);
  return n != null && n > 0 ? Math.floor(n) : null;
}

export function liveGenTokensPerSecond(trace) {
  if (!trace || typeof trace !== 'object') return null;
  const completionTokens = liveStreamCompletionTokens(trace);
  if (completionTokens == null || completionTokens <= 0) return null;

  const response = trace.response && typeof trace.response === 'object' ? trace.response : {};
  const latencyMs = numOrNull(response.latency_ms);
  if (latencyMs != null && latencyMs > 0) {
    return { value: (completionTokens / latencyMs) * 1000, source: 'latency_ms' };
  }

  const createdAt = trace.created_at;
  if (typeof createdAt === 'string' && createdAt) {
    const start = new Date(createdAt).getTime();
    if (Number.isFinite(start) && start > 0) {
      const elapsed = Date.now() - start;
      if (elapsed > 500) {
        return { value: (completionTokens / elapsed) * 1000, source: 'created_at' };
      }
    }
  }

  return null;
}

export function liveStreamPreview(trace) {
  const provider = traceProvider(trace);
  const raw = nonEmptyString(provider.live_visible_tail);
  if (!raw) return null;
  return {
    text: raw.slice(-200),
    truncated: Boolean(provider.live_visible_tail_truncated) || raw.length > 200,
  };
}
