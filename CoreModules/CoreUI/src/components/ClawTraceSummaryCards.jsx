import React from 'react';
import '../styles/components/DashboardTab.css';

function kv(label, value, key) {
  return (
    <div className="dashboard-kv-row" key={key}>
      <span className="dashboard-kv-label">{label}</span>
      <span className="dashboard-kv-value">{value}</span>
    </div>
  );
}

function pill(label, value) {
  return (
    <div className="dashboard-rag-status-pill dashboard-rag-status-pill--wide" key={label}>
      <span className="dashboard-rag-status-label">{label}</span>
      <span className="dashboard-rag-status-value">{value}</span>
    </div>
  );
}

function chipList(items) {
  if (!items || items.length === 0) return <span className="dashboard-card-muted">—</span>;
  return (
    <span className="claw-trace-summary-chips">
      {items.map((t, i) => (
        <code key={`${t}-${i}`} className="claw-trace-summary-chip">
          {t}
        </code>
      ))}
    </span>
  );
}

/**
 * @param {{ summary: Record<string, unknown> }} props
 */
export default function ClawTraceSummaryCards({ summary }) {
  if (!summary || summary.empty) {
    return <p className="dashboard-card-muted">No trace data to summarize.</p>;
  }

  const perRows = summary.perModelCallTokenRows || [];
  const ragCalls = summary.ragCalls || [];
  const skillLoads = summary.skillLoads || [];
  const passThrough = summary.passThrough || [];
  const skillsSnap = summary.skillsSnapshot;
  const mergeLabel =
    summary.mergeClientTools === true ? 'yes' : summary.mergeClientTools === false ? 'no' : '—';

  const tokenMismatch =
    perRows.length > 0 &&
    (summary.sumPromptFromSteps !== summary.totalPromptTokensEst ||
      summary.sumCompletionFromSteps !== summary.totalCompletionTokensEst);

  return (
    <div className="claw-trace-summary-root">
      <p className="claw-trace-summary-lead dashboard-card-muted">
        Token figures are <strong>internal estimates</strong> (serialized message size ÷ 4), not provider billing usage.
      </p>

      <section className="claw-trace-summary-section" aria-labelledby="claw-sum-overview">
        <h4 id="claw-sum-overview" className="dashboard-proxy-block-title">
          Overview
        </h4>
        {summary.traceId ? (
          <p style={{ margin: '0 0 8px 0', wordBreak: 'break-all' }}>
            <strong>trace_id</strong> <code>{summary.traceId}</code>
          </p>
        ) : null}
        <div className="dashboard-rag-status-grid">
          {pill('Steps', summary.stepCount)}
          {pill('Duration', `${summary.durationMs} ms`)}
          {pill('Resolved model', summary.resolvedModel)}
          {pill('Logical agent', summary.logicalModelId)}
        </div>
        {summary.clientModel != null && summary.clientModel !== '' && kv('Client model', summary.clientModel, 'cm')}
        {summary.thinkRequested != null &&
          kv('Ollama think requested', summary.thinkRequested ? 'yes' : 'no', 'think')}
        {kv('Messages in request', summary.requestMessageCount, 'msg')}
        {kv('merge_client_tools', mergeLabel, 'mct')}
        {summary.error != null && (
          <p className="dashboard-card-error" style={{ marginTop: 8 }}>
            {summary.error}
          </p>
        )}
      </section>

      <section className="claw-trace-summary-section" aria-labelledby="claw-sum-tokens">
        <h4 id="claw-sum-tokens" className="dashboard-proxy-block-title">
          Tokens (estimate)
        </h4>
        <div className="dashboard-rag-status-grid">
          {pill('Prompt total', summary.totalPromptTokensEst)}
          {pill('Completion total', summary.totalCompletionTokensEst)}
          {pill('Prompt + completion', summary.totalPromptTokensEst + summary.totalCompletionTokensEst)}
        </div>
        {tokenMismatch && (
          <p className="dashboard-card-muted" style={{ fontSize: 12, marginTop: 8 }}>
            Sum of per-step model estimates (prompt {summary.sumPromptFromSteps}, completion{' '}
            {summary.sumCompletionFromSteps}) differs from trace totals — partial run or legacy trace.
          </p>
        )}
        {perRows.length > 0 && (
          <details className="dashboard-trace-item" style={{ marginTop: 10 }}>
            <summary>Per model_call step</summary>
            <table className="claw-trace-summary-table">
              <thead>
                <tr>
                  <th>Agent step</th>
                  <th>Prompt est.</th>
                  <th>Completion est.</th>
                  <th>Ollama prompt_eval</th>
                  <th>Ollama eval</th>
                </tr>
              </thead>
              <tbody>
                {perRows.map((r, i) => (
                  <tr key={i}>
                    <td>{r.step != null ? r.step : '—'}</td>
                    <td>{r.promptEst}</td>
                    <td>{r.completionEst}</td>
                    <td>{r.ollamaPec != null ? r.ollamaPec : '—'}</td>
                    <td>{r.ollamaEc != null ? r.ollamaEc : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        )}
      </section>

      <section className="claw-trace-summary-section" aria-labelledby="claw-sum-ctx">
        <h4 id="claw-sum-ctx" className="dashboard-proxy-block-title">
          Context volume
        </h4>
        <div className="dashboard-rag-status-grid">
          {pill('RAG context (chars)', summary.ragContextCharsTotal)}
          {pill('Skills context (chars)', summary.skillContextCharsTotal)}
          {pill('RAG chunks (sum)', summary.ragChunksTotal)}
        </div>
      </section>

      {summary.processRssMb != null && (
        <section className="claw-trace-summary-section" aria-labelledby="claw-sum-rss">
          <h4 id="claw-sum-rss" className="dashboard-proxy-block-title">
            Process
          </h4>
          <div className="dashboard-rag-status-grid">{pill('RSS (MB)', summary.processRssMb)}</div>
        </section>
      )}

      <section className="claw-trace-summary-section" aria-labelledby="claw-sum-rag">
        <h4 id="claw-sum-rag" className="dashboard-proxy-block-title">
          RAG
        </h4>
        {ragCalls.length === 0 ? (
          <p className="dashboard-card-muted">No rag_query steps in this trace.</p>
        ) : (
          <ul className="claw-trace-summary-list">
            {ragCalls.map((r, i) => (
              <li key={i}>
                <span className={r.ok ? '' : 'dashboard-card-error'}>
                  {r.ok ? 'OK' : 'Failed'} · chunks {r.chunks} · {r.contextChars} chars
                  {r.step != null ? ` · step ${r.step}` : ''}
                </span>
                {r.query ? (
                  <div className="dashboard-card-muted claw-trace-summary-query">{r.query}</div>
                ) : null}
                {r.error ? <div className="dashboard-card-error">{r.error}</div> : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="claw-trace-summary-section" aria-labelledby="claw-sum-skills">
        <h4 id="claw-sum-skills" className="dashboard-proxy-block-title">
          Skills
        </h4>
        {skillsSnap && (
          <div className="dashboard-card-muted" style={{ marginBottom: 8 }}>
            Enabled: {skillsSnap.enabledCount} · Loaded invocations: {skillsSnap.loadedCount}
            {skillsSnap.loadedInvocations.length > 0 ? (
              <div style={{ marginTop: 6 }}>{chipList(skillsSnap.loadedInvocations)}</div>
            ) : null}
          </div>
        )}
        {!skillsSnap && skillLoads.length === 0 && (
          <p className="dashboard-card-muted">No skills metadata or load_skill steps.</p>
        )}
        {skillLoads.length > 0 && (
          <ul className="claw-trace-summary-list">
            {skillLoads.map((s, i) => (
              <li key={i}>
                <code>{s.invocation || s.skillId || 'load_skill'}</code>
                {s.skillId ? (
                  <>
                    {' '}
                    (<code>{s.skillId}</code>)
                  </>
                ) : null}
                {' · '}
                {s.ok ? 'OK' : 'Failed'} · {s.contextChars} chars
                {s.step != null ? ` · step ${s.step}` : ''}
                {s.error ? <div className="dashboard-card-error">{s.error}</div> : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="claw-trace-summary-section" aria-labelledby="claw-sum-tools">
        <h4 id="claw-sum-tools" className="dashboard-proxy-block-title">
          Server tools (assistant requested)
        </h4>
        <p className="dashboard-card-muted" style={{ fontSize: 12, marginBottom: 8 }}>
          Order of tool_calls across all model turns (includes rag_query / load_skill when the model asked for them).
        </p>
        {chipList(summary.serverToolCallsOrdered)}
        {summary.serverToolCallsUnique && summary.serverToolCallsUnique.length > 0 && (
          <div style={{ marginTop: 10 }}>
            <span className="dashboard-card-muted" style={{ fontSize: 12 }}>
              Unique:{' '}
            </span>
            {chipList(summary.serverToolCallsUnique)}
          </div>
        )}
      </section>

      {passThrough.length > 0 && (
        <section className="claw-trace-summary-section" aria-labelledby="claw-sum-pt">
          <h4 id="claw-sum-pt" className="dashboard-proxy-block-title">
            IDE pass-through
          </h4>
          <p className="dashboard-card-muted" style={{ fontSize: 12, marginBottom: 8 }}>
            Tool batch returned to the client for execution outside ClawCode.
          </p>
          <ul className="claw-trace-summary-list">
            {passThrough.map((p, i) => (
              <li key={i}>
                Step {p.step != null ? p.step : '—'}: {chipList(p.names)}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="claw-trace-summary-section" aria-labelledby="claw-sum-ide">
        <h4 id="claw-sum-ide" className="dashboard-proxy-block-title">
          IDE tool schema
        </h4>
        <p>
          <strong>{summary.clientToolNamesCount}</strong> tools in request schema
          {summary.clientToolNamesPreview && summary.clientToolNamesPreview.length > 0 ? ':' : '.'}
        </p>
        {summary.clientToolNamesPreview && summary.clientToolNamesPreview.length > 0 && (
          <div style={{ marginTop: 6 }}>{chipList(summary.clientToolNamesPreview)}</div>
        )}
        {summary.clientToolNamesCount > (summary.clientToolNamesPreview || []).length && (
          <p className="dashboard-card-muted" style={{ fontSize: 12, marginTop: 6 }}>
            …and {summary.clientToolNamesCount - summary.clientToolNamesPreview.length} more (see request JSON).
          </p>
        )}
      </section>
    </div>
  );
}
