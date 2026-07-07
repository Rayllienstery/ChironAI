import '../styles/components/DashboardTab.css';
import { t } from '../services/i18n';

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
    <span className="agent-trace-summary-chips">
      {items.map((item, i) => (
        <code key={`${item}-${i}`} className="agent-trace-summary-chip">
          {item}
        </code>
      ))}
    </span>
  );
}

function statusLabel(ok) {
  return ok ? t('trace.summary.status_ok') : t('trace.summary.status_failed');
}

function yesNoLabel(value) {
  if (value === true) return t('common.yes');
  if (value === false) return t('common.no');
  return '—';
}

/**
 * @param {{ summary: Record<string, unknown> }} props
 */
export default function AgentTraceSummaryCards({ summary }) {
  if (!summary || summary.empty) {
    return <p className="dashboard-card-muted">{t('trace.summary.empty')}</p>;
  }

  const perRows = summary.perModelCallTokenRows || [];
  const ragCalls = summary.ragCalls || [];
  const skillLoads = summary.skillLoads || [];
  const passThrough = summary.passThrough || [];
  const skillsSnap = summary.skillsSnapshot;
  const mergeLabel = yesNoLabel(summary.mergeClientTools);

  const tokenMismatch =
    perRows.length > 0 &&
    (summary.sumPromptFromSteps !== summary.totalPromptTokensEst ||
      summary.sumCompletionFromSteps !== summary.totalCompletionTokensEst);

  return (
    <div className="agent-trace-summary-root">
      <p className="agent-trace-summary-lead dashboard-card-muted">
        {t('trace.summary.token_lead_prefix')}{' '}
        <strong>{t('trace.summary.token_lead_emphasis')}</strong>{' '}
        {t('trace.summary.token_lead_suffix')}
      </p>

      <section className="agent-trace-summary-section" aria-labelledby="agent-sum-overview">
        <h4 id="agent-sum-overview" className="dashboard-proxy-block-title">
          {t('trace.summary.overview')}
        </h4>
        {summary.traceId ? (
          <p className="coreui-text-break-all">
            <strong>{t('trace.summary.trace_id')}</strong> <code>{summary.traceId}</code>
          </p>
        ) : null}
        <div className="dashboard-rag-status-grid">
          {pill(t('trace.summary.steps'), summary.stepCount)}
          {pill(t('trace.summary.duration'), t('trace.summary.duration_ms', { value: summary.durationMs }))}
          {pill(t('trace.summary.model'), summary.resolvedModel)}
        </div>
        {summary.clientModel != null && summary.clientModel !== '' &&
          kv(t('trace.summary.client_model'), summary.clientModel, 'cm')}
        {summary.thinkRequested != null &&
          kv(t('trace.summary.think_requested'), yesNoLabel(summary.thinkRequested), 'think')}
        {kv(t('trace.summary.messages_in_request'), summary.requestMessageCount, 'msg')}
        {kv(t('trace.summary.merge_client_tools'), mergeLabel, 'mct')}
        {summary.error != null && (
          <p className="dashboard-card-error">
            {summary.error}
          </p>
        )}
      </section>

      <section className="agent-trace-summary-section" aria-labelledby="agent-sum-tokens">
        <h4 id="agent-sum-tokens" className="dashboard-proxy-block-title">
          {t('trace.summary.tokens')}
        </h4>
        <div className="dashboard-rag-status-grid">
          {pill(t('trace.summary.prompt_total'), summary.totalPromptTokensEst)}
          {pill(t('trace.summary.completion_total'), summary.totalCompletionTokensEst)}
          {pill(
            t('trace.summary.prompt_plus_completion'),
            summary.totalPromptTokensEst + summary.totalCompletionTokensEst,
          )}
        </div>
        {tokenMismatch && (
          <p className="coreui-text-muted-sm">
            {t('trace.summary.token_mismatch', {
              prompt: summary.sumPromptFromSteps,
              completion: summary.sumCompletionFromSteps,
            })}
          </p>
        )}
        {perRows.length > 0 && (
          <details className="dashboard-trace-item coreui-section-block">
            <summary>{t('trace.summary.per_model_call')}</summary>
            <table className="agent-trace-summary-table">
              <thead>
                <tr>
                  <th>{t('trace.summary.agent_step')}</th>
                  <th>{t('trace.summary.prompt_est')}</th>
                  <th>{t('trace.summary.completion_est')}</th>
                  <th>{t('trace.summary.prompt_eval')}</th>
                  <th>{t('trace.summary.eval')}</th>
                </tr>
              </thead>
              <tbody>
                {perRows.map((r, i) => (
                  <tr key={i}>
                    <td>{r.step != null ? r.step : '—'}</td>
                    <td>{r.promptEst}</td>
                    <td>{r.completionEst}</td>
                    <td>{r.providerPromptEval != null ? r.providerPromptEval : '—'}</td>
                    <td>{r.providerEval != null ? r.providerEval : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        )}
      </section>

      <section className="agent-trace-summary-section" aria-labelledby="agent-sum-ctx">
        <h4 id="agent-sum-ctx" className="dashboard-proxy-block-title">
          {t('trace.summary.context_volume')}
        </h4>
        <div className="dashboard-rag-status-grid">
          {pill(t('trace.summary.rag_context_chars'), summary.ragContextCharsTotal)}
          {pill(t('trace.summary.skills_context_chars'), summary.skillContextCharsTotal)}
          {pill(t('trace.summary.rag_chunks_sum'), summary.ragChunksTotal)}
        </div>
      </section>

      {summary.processRssMb != null && (
        <section className="agent-trace-summary-section" aria-labelledby="agent-sum-rss">
          <h4 id="agent-sum-rss" className="dashboard-proxy-block-title">
            {t('trace.summary.process')}
          </h4>
          <div className="dashboard-rag-status-grid">{pill(t('trace.summary.rss_mb'), summary.processRssMb)}</div>
        </section>
      )}

      <section className="agent-trace-summary-section" aria-labelledby="agent-sum-rag">
        <h4 id="agent-sum-rag" className="dashboard-proxy-block-title">
          {t('trace.summary.rag')}
        </h4>
        {ragCalls.length === 0 ? (
          <p className="dashboard-card-muted">{t('trace.summary.no_rag_steps')}</p>
        ) : (
          <ul className="agent-trace-summary-list">
            {ragCalls.map((r, i) => (
              <li key={i}>
                <span className={r.ok ? '' : 'dashboard-card-error'}>
                  {t('trace.summary.rag_result', {
                    status: statusLabel(r.ok),
                    chunks: r.chunks,
                    chars: r.contextChars,
                  })}
                  {r.step != null ? t('trace.summary.step_suffix', { step: r.step }) : ''}
                </span>
                {r.query ? (
                  <div className="dashboard-card-muted agent-trace-summary-query">{r.query}</div>
                ) : null}
                {r.error ? <div className="dashboard-card-error">{r.error}</div> : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="agent-trace-summary-section" aria-labelledby="agent-sum-skills">
        <h4 id="agent-sum-skills" className="dashboard-proxy-block-title">
          {t('trace.summary.skills')}
        </h4>
        {skillsSnap && (
          <div className="dashboard-card-muted">
            {t('trace.summary.skills_enabled', {
              enabled: skillsSnap.enabledCount,
              loaded: skillsSnap.loadedCount,
            })}
            {skillsSnap.loadedInvocations.length > 0 ? (
              <div className="coreui-section-block">{chipList(skillsSnap.loadedInvocations)}</div>
            ) : null}
          </div>
        )}
        {!skillsSnap && skillLoads.length === 0 && (
          <p className="dashboard-card-muted">{t('trace.summary.no_skills')}</p>
        )}
        {skillLoads.length > 0 && (
          <ul className="agent-trace-summary-list">
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
                {t('trace.summary.skill_result', {
                  status: statusLabel(s.ok),
                  chars: s.contextChars,
                })}
                {s.step != null ? t('trace.summary.step_suffix', { step: s.step }) : ''}
                {s.error ? <div className="dashboard-card-error">{s.error}</div> : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="agent-trace-summary-section" aria-labelledby="agent-sum-tools">
        <h4 id="agent-sum-tools" className="dashboard-proxy-block-title">
          {t('trace.summary.server_tools')}
        </h4>
        <p className="coreui-text-muted-sm">
          {t('trace.summary.server_tools_hint')}
        </p>
        {chipList(summary.serverToolCallsOrdered)}
        {summary.serverToolCallsUnique && summary.serverToolCallsUnique.length > 0 && (
          <div className="coreui-section-block">
            <span className="coreui-text-muted-sm">
              {t('trace.summary.unique')}{' '}
            </span>
            {chipList(summary.serverToolCallsUnique)}
          </div>
        )}
      </section>

      {passThrough.length > 0 && (
        <section className="agent-trace-summary-section" aria-labelledby="agent-sum-pt">
          <h4 id="agent-sum-pt" className="dashboard-proxy-block-title">
            {t('trace.summary.ide_passthrough')}
          </h4>
          <p className="coreui-text-muted-sm">
            {t('trace.summary.ide_passthrough_hint')}
          </p>
          <ul className="agent-trace-summary-list">
            {passThrough.map((p, i) => (
              <li key={i}>
                {t('trace.summary.passthrough_step', { step: p.step != null ? p.step : '—' })} {chipList(p.names)}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="agent-trace-summary-section" aria-labelledby="agent-sum-ide">
        <h4 id="agent-sum-ide" className="dashboard-proxy-block-title">
          {t('trace.summary.ide_tool_schema')}
        </h4>
        <p>
          <strong>{summary.clientToolNamesCount}</strong>{' '}
          {t('trace.summary.tools_in_schema_label')}
          {summary.clientToolNamesPreview && summary.clientToolNamesPreview.length > 0
            ? t('trace.summary.tools_in_schema_suffix')
            : t('trace.summary.tools_in_schema_end')}
        </p>
        {summary.clientToolNamesPreview && summary.clientToolNamesPreview.length > 0 && (
          <div className="coreui-section-block">{chipList(summary.clientToolNamesPreview)}</div>
        )}
        {summary.clientToolNamesCount > (summary.clientToolNamesPreview || []).length && (
          <p className="coreui-text-muted-sm">
            {t('trace.summary.tools_in_schema_more', {
              count: summary.clientToolNamesCount - summary.clientToolNamesPreview.length,
            })}
          </p>
        )}
      </section>
    </div>
  );
}
