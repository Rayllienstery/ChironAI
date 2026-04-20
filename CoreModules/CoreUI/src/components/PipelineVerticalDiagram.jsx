import { useMemo } from 'react';
import { computePipelineActive } from './PipelineCiDiagram';
import '../styles/components/PipelineVerticalDiagram.css';

function getVerticalSteps(data) {
  const defs = data?.pipeline_definition?.proxy?.steps;
  if (!Array.isArray(defs)) return [];
  return defs
    .filter((s) => s && typeof s === 'object' && s.id)
    .map((s) => ({
      id: String(s.id),
      icon: String(s.icon || 'settings'),
      label: String(s.title || s.label || s.id),
      description: String(s.description || ''),
    }));
}

function PipelineVerticalDiagram({ data }) {
  const activeMap = useMemo(() => (data ? computePipelineActive(data) : null), [data]);
  const steps = useMemo(() => getVerticalSteps(data), [data]);

  if (!activeMap || steps.length < 1) return null;

  return (
    <div className="pipeline-vert" role="list" aria-label="LLM proxy pipeline stages">
      {steps.map((step, i) => {
        const active = Boolean(activeMap[step.id]);
        const isLast = i === steps.length - 1;
        return (
          <div
            key={step.id}
            className={`pipeline-vert__item${active ? ' pipeline-vert__item--active' : ''}`}
            role="listitem"
          >
            <div className="pipeline-vert__rail">
              <span className="pipeline-vert__icon-wrap" aria-hidden="true">
                <span className={`material-symbols-outlined pipeline-vert__icon${active ? ' pipeline-vert__icon--on' : ''}`}>
                  {step.icon}
                </span>
              </span>
              {!isLast && <span className="pipeline-vert__line" />}
            </div>
            <div className="pipeline-vert__content">
              <span className="pipeline-vert__label">{step.label}</span>
              <span className="pipeline-vert__desc">{step.description}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default PipelineVerticalDiagram;
