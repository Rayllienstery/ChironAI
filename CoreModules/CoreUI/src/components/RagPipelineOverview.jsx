import { useEffect, useMemo, useState } from 'react';
import CoreUIPillTabs from './CoreUIPillTabs';
import CoreUIPipelinePreview from './CoreUIPipelinePreview';

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
  const [viewMode, setViewMode] = useState('current');

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

  const allPreviewSteps = steps.map(step => {
    let tone = 'neutral';
    if (step.overviewBand === 'core') tone = 'success';
    else if (step.overviewBand === 'option_on') tone = 'info';

    return {
      id: step.id,
      label: step.label,
      description: step.detail,
      icon: step.icon,
      active: step.overviewBand === 'core' || step.overviewBand === 'option_on',
      tone: tone,
      badges: step.overviewBadges,
      onClick: () => setSelectedStepId(step.id)
    };
  });

  const previewSteps = viewMode === 'current' 
    ? allPreviewSteps.filter(s => s.active)
    : allPreviewSteps;

  const tabs = [
    { id: 'current', label: 'Current Config' },
    { id: 'all', label: 'All Steps' }
  ];

  return (
    <>
      <div className="rag-pipeline-overview-container">
        <div className="rag-pipeline-tabs-wrap">
          <CoreUIPillTabs
            tabs={tabs}
            value={viewMode}
            onChange={setViewMode}
            className="rag-pipeline-tabs"
          />
        </div>
        <CoreUIPipelinePreview key={viewMode} steps={previewSteps} animated />
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
