import '../styles/components/CoreUIPipelinePreview.css';

/**
 * @typedef {Object} PipelineStep
 * @property {string} id
 * @property {string} label
 * @property {string} [description]
 * @property {string} [icon]
 * @property {boolean} [active]
 */

/**
 * Standardized vertical pipeline preview component.
 * 
 * @param {{
 *   steps: PipelineStep[],
 *   className?: string
 * }} props
 */
function CoreUIPipelinePreview({ steps, className = '' }) {
  if (!Array.isArray(steps) || steps.length === 0) {
    return null;
  }

  return (
    <div 
      className={`coreui-pipeline-preview ${className}`} 
      role="list" 
      aria-label="Pipeline stages"
    >
      {steps.map((step, i) => {
        const active = Boolean(step.active);
        const isLast = i === steps.length - 1;
        const icon = step.icon || 'settings';

        return (
          <div
            key={step.id || i}
            className={`coreui-pipeline-preview__item${active ? ' coreui-pipeline-preview__item--active' : ''}`}
            role="listitem"
          >
            <div className="coreui-pipeline-preview__rail">
              <span className="coreui-pipeline-preview__icon-wrap" aria-hidden="true">
                <span className={`material-symbols-outlined coreui-pipeline-preview__icon${active ? ' coreui-pipeline-preview__icon--on' : ''}`}>
                  {icon}
                </span>
              </span>
              {!isLast && <span className="coreui-pipeline-preview__line" />}
            </div>
            <div className="coreui-pipeline-preview__content">
              <span className="coreui-pipeline-preview__label">{step.label}</span>
              {step.description && (
                <span className="coreui-pipeline-preview__desc">{step.description}</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default CoreUIPipelinePreview;
