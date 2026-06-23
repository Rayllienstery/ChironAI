import '../styles/components/CoreUIPipelinePreview.css';
import CoreUIBadge from './CoreUIBadge';

/**
 * @typedef {Object} PipelineStep
 * @property {string} id
 * @property {string} label
 * @property {string} [description]
 * @property {string} [icon]
 * @property {boolean} [active]
 * @property {'primary' | 'success' | 'info' | 'neutral'} [tone]
 * @property {string[]} [badges]
 * @property {() => void} [onClick]
 */

/**
 * Standardized vertical pipeline preview component.
 * 
 * @param {{
 *   steps: PipelineStep[],
 *   className?: string,
 *   animated?: boolean
 * }} props
 */
function CoreUIPipelinePreview({ steps, className = '', animated = false }) {
  if (!Array.isArray(steps) || steps.length === 0) {
    return null;
  }

  const rootClassName = [
    'coreui-pipeline-preview',
    animated && 'coreui-pipeline-preview--animated',
    className
  ].filter(Boolean).join(' ');

  return (
    <div 
      className={rootClassName} 
      role="list" 
      aria-label="Pipeline stages"
    >
      {steps.map((step, i) => {
        const active = Boolean(step.active);
        const tone = step.tone || (active ? 'primary' : 'neutral');
        const isLast = i === steps.length - 1;
        const icon = step.icon || 'settings';
        const isClickable = typeof step.onClick === 'function';

        const ItemTag = isClickable ? 'button' : 'div';
        const itemProps = isClickable ? {
          type: 'button',
          onClick: step.onClick,
          className: `coreui-pipeline-preview__item coreui-pipeline-preview__item--clickable${active ? ' coreui-pipeline-preview__item--active' : ''} coreui-pipeline-preview__item--tone-${tone}`,
          'aria-label': `${step.label}. Click for details.`,
          style: animated ? { animationDelay: `${i * 40}ms` } : undefined
        } : {
          className: `coreui-pipeline-preview__item${active ? ' coreui-pipeline-preview__item--active' : ''} coreui-pipeline-preview__item--tone-${tone}`,
          style: animated ? { animationDelay: `${i * 40}ms` } : undefined
        };

        return (
          <div key={step.id || i} className="coreui-pipeline-preview__wrapper">
            <ItemTag {...itemProps} role="listitem">
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
                {Array.isArray(step.badges) && step.badges.length > 0 && (
                  <div className="coreui-pipeline-preview__badges">
                    {step.badges.map(badge => (
                      <CoreUIBadge key={badge} tone="info" className="coreui-pipeline-preview__badge">
                        {badge}
                      </CoreUIBadge>
                    ))}
                  </div>
                )}
              </div>
            </ItemTag>
          </div>
        );
      })}
    </div>
  );
}

export default CoreUIPipelinePreview;
