import { useEffect, useMemo, useState } from 'react';

/**
 * @typedef {'core' | 'option_on' | 'option_off'} OverviewBand
 */

function getRagDefinitionSteps(pipelineSettings) {
  const defs = pipelineSettings?.pipeline_definition?.rag?.steps;
  if (!Array.isArray(defs)) return [];
  return defs
    .filter((s) => s && typeof s === 'object' && s.id)
    .map((s) => ({
      id: String(s.id),
      icon: String(s.icon || 'widgets'),
      label: String(s.title || s.label || s.id),
      detail: String(s.description || s.detail || ''),
      longDescription: String(s.long_description || s.description || s.detail || ''),
      whyItMatters: String(s.why_it_matters || ''),
      example: String(s.example || ''),
    }));
}

/**
 * @param {Record<string, unknown>} s
 * @returns {Array<{ id: string, icon: string, label: string, detail: string, overviewBand: OverviewBand, overviewBadges?: string[] }>}
 */
function buildOverviewStepsWithHighlights(s) {
  const steps = getRagDefinitionSteps(s);
  const hybrid = Boolean(s?.hybrid_sparse_enabled);
  const rerank = Boolean(s?.rerank_for_rag);
  const concept = Boolean(s?.concept_expansion_enabled);
  const gate = Boolean(s?.coverage_gate_enabled);
  const retry = Boolean(s?.coverage_retry_supplemental_search_enabled);
  const structured = Boolean(s?.structured_rag_context_enabled);

  return steps.map((step) => {
    /** @type {OverviewBand} */
    let overviewBand = 'core';
    /** @type {string[]} */
    const overviewBadges = [];

    switch (step.id) {
      case 'embed_search_pass1':
        if (hybrid) overviewBadges.push('Hybrid sparse on');
        break;
      case 'concept_expansion_pass2':
        overviewBand = concept ? 'option_on' : 'option_off';
        break;
      case 'rerank':
        overviewBand = rerank ? 'option_on' : 'option_off';
        break;
      case 'coverage_gate':
        overviewBand = gate ? 'option_on' : 'option_off';
        break;
      case 'coverage_supplemental':
        overviewBand = retry ? 'option_on' : 'option_off';
        break;
      case 'context_assembly':
        if (structured) overviewBadges.push('Structured layout on');
        break;
      default:
        break;
    }

    const out = { ...step, overviewBand };
    if (overviewBadges.length) out.overviewBadges = overviewBadges;
    return out;
  });
}

/**
 * @param {{ pipelineSettings?: Record<string, unknown> }} props
 */
export default function RagPipelineOverview({ pipelineSettings = {} }) {
  const steps = useMemo(() => buildOverviewStepsWithHighlights(pipelineSettings), [pipelineSettings]);
  const [selectedStepId, setSelectedStepId] = useState(null);
  const selectedStep = useMemo(
    () => steps.find((s) => s.id === selectedStepId) || null,
    [steps, selectedStepId],
  );

  useEffect(() => {
    if (!selectedStep) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') setSelectedStepId(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selectedStep]);

  if (!Array.isArray(steps) || steps.length < 1) {
    return <p className="rag-pipeline-mirror-empty">Pipeline definition unavailable from backend.</p>;
  }
  return (
    <>
      <div className="rag-pipeline-cards" role="list" aria-label="RAG pipeline map">
        {steps.map((step, i) => {
          const isLast = i === steps.length - 1;
          const band = String(step.overviewBand || 'core');
          return (
            <div key={step.id} className="rag-pipeline-cards__item" role="listitem">
              <button
                type="button"
                className={`rag-pipeline-step-card rag-pipeline-step-card--${band}`}
                aria-label={`${step.label} (${band}). Open details.`}
                onClick={() => setSelectedStepId(step.id)}
              >
                <div className="rag-pipeline-step-card__header">
                  <span className="rag-pipeline-step-card__icon-wrap" aria-hidden="true">
                    <span className="material-symbols-outlined rag-pipeline-step-card__icon">
                      {step.icon || 'widgets'}
                    </span>
                  </span>
                  <h4 className="rag-pipeline-step-card__title">{step.label}</h4>
                </div>

                {Array.isArray(step.overviewBadges) && step.overviewBadges.length > 0 ? (
                  <div className="rag-pipeline-step-card__badges" aria-label="Step options">
                    {step.overviewBadges.map((b) => (
                      <span key={b} className="rag-pipeline-step-card__badge">
                        {String(b).toUpperCase()}
                      </span>
                    ))}
                  </div>
                ) : null}

                {step.detail ? <p className="rag-pipeline-step-card__desc">{step.detail}</p> : null}
              </button>

              {!isLast ? (
                <div className={`rag-pipeline-step-arrow rag-pipeline-step-arrow--${band}`} aria-hidden="true">
                  <span className="material-symbols-outlined">arrow_downward</span>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>

      {selectedStep ? (
        <div
          className="rag-pipeline-modal-overlay"
          role="presentation"
          onClick={() => setSelectedStepId(null)}
        >
          <div
            className="rag-pipeline-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="rag-pipeline-step-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="rag-pipeline-modal__header">
              <div className="rag-pipeline-modal__title-wrap">
                <h3 id="rag-pipeline-step-modal-title">{selectedStep.label}</h3>
                <p className="rag-pipeline-modal__meta">Step id: {selectedStep.id}</p>
              </div>
              <button type="button" className="rag-pipeline-modal__close" onClick={() => setSelectedStepId(null)}>
                Close
              </button>
            </div>

            <div className="rag-pipeline-modal__body">
              <section>
                <h4>What this step does</h4>
                <p>{selectedStep.longDescription || selectedStep.detail || 'No details available.'}</p>
              </section>

              <section>
                <h4>Why it matters</h4>
                <p>{selectedStep.whyItMatters || 'Improves retrieval quality and final answer reliability.'}</p>
              </section>

              <section>
                <h4>Example</h4>
                <p>{selectedStep.example || 'The step transforms retrieval or ranking to improve final context.'}</p>
              </section>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
