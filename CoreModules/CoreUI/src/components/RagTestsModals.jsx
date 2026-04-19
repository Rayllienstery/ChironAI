function TestFormFields({
  form,
  onFormChange,
  conceptsWarning,
}) {
  return (
    <>
      <label>
        Name (optional)
        <input
          type="text"
          value={form.name}
          onChange={(e) => onFormChange((f) => ({ ...f, name: e.target.value }))}
          placeholder="Short title"
          className="rag-tests-input"
        />
      </label>
      <label>
        Question <span className="required">*</span>
        <textarea
          value={form.question}
          onChange={(e) =>
            onFormChange((f) => ({ ...f, question: e.target.value }))
          }
          placeholder="Question to ask the model"
          rows={3}
          className="rag-tests-input"
          required
        />
      </label>
      <label>
        Expected concepts (one per line)
        <textarea
          value={form.concepts}
          onChange={(e) =>
            onFormChange((f) => ({ ...f, concepts: e.target.value }))
          }
          placeholder={"concept1\nconcept2"}
          rows={3}
          className="rag-tests-input"
        />
      </label>
      {conceptsWarning && <p className="rag-tests-hint">{conceptsWarning}</p>}
      <div className="rag-tests-form-row">
        <label>
          Platform
          <select
            value={form.platform}
            onChange={(e) =>
              onFormChange((f) => ({ ...f, platform: e.target.value }))
            }
            className="rag-tests-select"
          >
            <option value="iOS">iOS</option>
            <option value="macOS">macOS</option>
            <option value="watchOS">watchOS</option>
            <option value="visionOS">visionOS</option>
          </select>
        </label>
        <label>
          Framework
          <input
            type="text"
            value={form.framework}
            onChange={(e) =>
              onFormChange((f) => ({ ...f, framework: e.target.value }))
            }
            placeholder="SwiftUI"
            className="rag-tests-input"
          />
        </label>
        <label>
          Difficulty
          <select
            value={form.difficulty}
            onChange={(e) =>
              onFormChange((f) => ({ ...f, difficulty: e.target.value }))
            }
            className="rag-tests-select"
          >
            <option value="beginner">beginner</option>
            <option value="intermediate">intermediate</option>
            <option value="advanced">advanced</option>
          </select>
        </label>
        <label>
          Concept mode
          <select
            value={form.concept_mode}
            onChange={(e) =>
              onFormChange((f) => ({ ...f, concept_mode: e.target.value }))
            }
            className="rag-tests-select"
          >
            <option value="all">all</option>
            <option value="any">any</option>
          </select>
        </label>
      </div>
      <label className="rag-tests-checkbox-label">
        <input
          type="checkbox"
          checked={form.rag_strict}
          onChange={(e) =>
            onFormChange((f) => ({ ...f, rag_strict: e.target.checked }))
          }
        />
        RAG Strict (response must overlap retrieved chunks)
      </label>
      <label>
        Min OS (optional)
        <input
          type="text"
          value={form.min_os}
          onChange={(e) => onFormChange((f) => ({ ...f, min_os: e.target.value }))}
          placeholder="e.g. iOS 18"
          className="rag-tests-input"
        />
      </label>
      <label>
        Notes (optional)
        <textarea
          value={form.notes}
          onChange={(e) => onFormChange((f) => ({ ...f, notes: e.target.value }))}
          rows={2}
          className="rag-tests-input"
        />
      </label>
    </>
  );
}

export function RagTestFormModal({
  open,
  title,
  form,
  onFormChange,
  conceptsWarning,
  onSubmit,
  onClose,
  submitting,
  submitLabel,
}) {
  if (!open) return null;

  return (
    <div
      className="rag-tests-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="rag-test-form-title"
    >
      <div className="rag-tests-modal-content">
        <h3 id="rag-test-form-title">{title}</h3>
        <form onSubmit={onSubmit}>
          <TestFormFields
            form={form}
            onFormChange={onFormChange}
            conceptsWarning={conceptsWarning}
          />
          <div className="rag-tests-modal-actions">
            <button type="button" className="rag-tests-btn" onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              className="rag-tests-btn primary"
              disabled={submitting || !form.question.trim()}
            >
              {submitting ? submitLabel.pending : submitLabel.idle}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export function RagResultDetailModal({ detail, onClose }) {
  if (!detail) return null;

  const tm = detail.test;
  const lm = detail.last;
  const rawChunks = lm && (lm.chunks_info?.length ? lm.chunks_info : lm.retrieved_chunks);
  const chunks = Array.isArray(rawChunks) ? rawChunks : [];
  const ragQ = (lm && lm.rag_queries) || [];
  const ragTimings = lm && lm.rag_timings && typeof lm.rag_timings === 'object' ? lm.rag_timings : null;
  const traceSteps = lm && Array.isArray(lm.trace_steps)
    ? lm.trace_steps.filter((s) => s && typeof s === 'object')
    : [];
  const fmtSec = (v) => {
    const n = Number(v);
    if (!Number.isFinite(n)) return '-';
    return `${n.toFixed(2)} s`;
  };

  return (
    <div
      className="rag-tests-modal rag-tests-result-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="rag-result-modal-title"
      onClick={onClose}
    >
      <div
        className="rag-tests-modal-content rag-tests-result-modal-content"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="rag-tests-result-modal-header">
          <h3 id="rag-result-modal-title">{tm.name || tm.id}</h3>
          <button
            type="button"
            className="rag-tests-result-modal-close"
            onClick={onClose}
            aria-label="Close"
          >
            &times;
          </button>
        </div>
        <p className="rag-tests-result-modal-meta">
          <span className="rag-tests-result-id">{tm.id}</span>
          {lm?.model && <span> | Model: {lm.model}</span>}
          {lm?.status && (
            <span className={`rag-tests-status ${(lm.status || "").toLowerCase()}`}>
              {" "}
              | {lm.status}
            </span>
          )}
        </p>
        {tm.question && (
          <section className="rag-tests-result-section">
            <h4>Question</h4>
            <p className="rag-tests-result-question">{tm.question}</p>
          </section>
        )}
        {lm &&
          (lm.latency_ms != null ||
            lm.response_time_ms != null ||
            lm.prompt_tokens != null) && (
            <section className="rag-tests-result-section">
              <h4>Metrics</h4>
              <p className="rag-tests-detail-metrics">
                Latency: {lm.latency_ms ?? lm.response_time_ms ?? "-"} ms
                {lm.prompt_tokens != null && ` | Prompt tokens: ${lm.prompt_tokens}`}
                {lm.completion_tokens != null &&
                  ` | Completion tokens: ${lm.completion_tokens}`}
                {lm.total_tokens != null && ` | Total tokens: ${lm.total_tokens}`}
                {lm.context_chars != null &&
                  lm.context_chars > 0 &&
                  ` | Context chars: ${lm.context_chars}`}
              </p>
            </section>
          )}
        {ragTimings && (
          <section className="rag-tests-result-section">
            <h4>Pipeline timings</h4>
            <p className="rag-tests-detail-metrics">
              embed: {fmtSec(ragTimings.embed_s)}
              {' | '}search: {fmtSec(ragTimings.search_s)}
              {' | '}rerank: {fmtSec(ragTimings.rerank_s)}
              {' | '}rag_total: {fmtSec(ragTimings.total_rag_s)}
              {' | '}chat_estimated: {fmtSec(ragTimings.chat_s_estimated)}
              {' | '}latency_total: {fmtSec(ragTimings.latency_s_total)}
            </p>
          </section>
        )}
        {traceSteps.length > 0 && (
          <section className="rag-tests-result-section">
            <h4>Pipeline steps</h4>
            <ul className="rag-tests-rag-query-list">
              {traceSteps.map((s, i) => (
                <li key={`${s.name || 'step'}-${i}`}>
                  <span className="rag-tests-rag-query-meta">
                    {String(s.name || `step_${i}`)} | {Number(s.duration_ms || 0)} ms
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}
        {lm?.failure_reason && (
          <section className="rag-tests-result-section">
            <h4>Failure reason</h4>
            <p className="rag-tests-detail-reason">{lm.failure_reason}</p>
          </section>
        )}
        {lm && Array.isArray(lm.found_concepts) && (
          <section className="rag-tests-result-section">
            <h4>Found concepts</h4>
            <p>{lm.found_concepts.length ? lm.found_concepts.join(", ") : "none"}</p>
          </section>
        )}
        {lm && Array.isArray(lm.missing_concepts) && lm.missing_concepts.length > 0 && (
          <section className="rag-tests-result-section">
            <h4>Missing concepts</h4>
            <p>{lm.missing_concepts.join(", ")}</p>
          </section>
        )}
        {lm?.error && (
          <section className="rag-tests-result-section">
            <h4>Error</h4>
            <p className="rag-tests-detail-error">{lm.error}</p>
          </section>
        )}
        <section className="rag-tests-result-section">
          <h4>RAG requests</h4>
          {ragQ.length === 0 ? (
            <p className="rag-tests-result-empty">
              No rag_query calls recorded (or pipeline used implicit retrieval only).
            </p>
          ) : (
            <ul className="rag-tests-rag-query-list">
              {ragQ.map((q, i) => (
                <li key={i}>
                  <span className="rag-tests-rag-query-meta">
                    {q.step != null && <>Step {q.step} | </>}
                    {q.chunks != null && <>chunks {q.chunks} | </>}
                    {q.ok === false && (
                      <span className="rag-tests-detail-error">failed | </span>
                    )}
                  </span>
                  <pre className="rag-tests-pre rag-tests-pre-tight">
                    {q.query || JSON.stringify(q)}
                  </pre>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="rag-tests-result-section">
          <h4>RAG chunks</h4>
          {chunks.length === 0 ? (
            <p className="rag-tests-result-empty">
              No chunks in metadata (empty retrieval or not recorded).
            </p>
          ) : (
            <ul className="rag-tests-chunks rag-tests-chunks-modal">
              {chunks.map((ch, i) => (
                <li key={i}>
                  <span className="rag-tests-chunk-meta">
                    #{ch.index != null ? ch.index : i + 1} score={ch.score ?? "N/A"}{" "}
                    {ch.url ? `url=${ch.url}` : ""} {ch.source ? `source=${ch.source}` : ""}
                  </span>
                  <pre className="rag-tests-pre small">
                    {ch.text_preview || ch.text || ""}
                  </pre>
                </li>
              ))}
            </ul>
          )}
        </section>
        {lm && String(lm.full_response || "").trim() !== "" && (
          <section className="rag-tests-result-section">
            <h4>Model answer</h4>
            <pre className="rag-tests-pre rag-tests-pre-answer">{lm.full_response}</pre>
          </section>
        )}
        {!lm && (
          <p className="rag-tests-result-empty">
            No run result for this test yet. Run the test to see the model answer and
            RAG data.
          </p>
        )}
      </div>
    </div>
  );
}
