import { formatElapsedMs } from '../utils/elapsedTime';
import '../styles/components/ExtensionRuntimeTab.css';

const STATUS_META = {
  done: { icon: 'check_circle', label: 'Loaded' },
  loading: { icon: 'progress_activity', label: 'Loading' },
  pending: { icon: 'radio_button_unchecked', label: 'Waiting' },
  error: { icon: 'error', label: 'Blocked' },
};

function statusMeta(status) {
  return STATUS_META[status] || STATUS_META.pending;
}

export function buildExtensionRuntimeLoadingSteps({
  endpoint,
  message,
  mode = 'request',
} = {}) {
  const runtimeMessage = message || 'Waiting for the extension runtime and provider sandbox.';
  const requestStatus = mode === 'request' ? 'loading' : mode === 'error' ? 'error' : 'done';
  const runtimeStatus = mode === 'runtime' ? 'loading' : mode === 'error' ? 'error' : 'pending';

  return [
    {
      id: 'coreui-shell',
      label: 'CoreUI runtime shell',
      detail: 'ExtensionRuntimeTab chunk is mounted and ready.',
      status: 'done',
    },
    {
      id: 'tab-payload',
      label: 'Tab payload request',
      detail: endpoint || '/api/webui/extensions/:id/tab',
      status: requestStatus,
    },
    {
      id: 'extension-runtime',
      label: 'Extension runtime',
      detail: runtimeMessage,
      status: runtimeStatus,
    },
    {
      id: 'render-surface',
      label: 'Render extension surface',
      detail: 'Schema pages, service cards, iframe content, and diagnostics.',
      status: 'pending',
    },
  ];
}

/**
 * Detailed loading surface for extension runtime tabs.
 *
 * @param {Object} props
 * @param {string} props.title - Extension tab title.
 * @param {string} props.extensionId - Extension identifier used in the API path.
 * @param {Array<{id:string,label:string,detail?:string,status:'done'|'loading'|'pending'|'error'}>} [props.steps]
 * @param {number} [props.elapsedMs] - Time spent waiting for the current load.
 * @param {string} [props.message] - Optional current load message.
 */
export default function ExtensionRuntimeLoadingView({
  title,
  extensionId,
  steps,
  elapsedMs = 0,
  message = '',
}) {
  const safeTitle = title || extensionId || 'Extension';
  const visibleSteps = Array.isArray(steps) && steps.length
    ? steps
    : buildExtensionRuntimeLoadingSteps({ message });
  const current = visibleSteps.find((step) => step.status === 'loading')
    || visibleSteps.find((step) => step.status === 'error')
    || visibleSteps.find((step) => step.status === 'pending');

  return (
    <div className="extensions-runtime-loading-shell tab-view" aria-live="polite">
      <section className="extensions-runtime-loading-card" role="status" aria-label={`${safeTitle} extension loading status`}>
        <div className="extensions-runtime-loading-hero">
          <div className="extensions-runtime-loading-mark" aria-hidden="true">
            <span className="material-symbols-outlined">extension</span>
          </div>
          <div className="extensions-runtime-loading-copy">
            <span className="extensions-runtime-loading-kicker">Extension runtime</span>
            <h2>{safeTitle}</h2>
            <p>{current?.detail || message || 'Preparing extension surface.'}</p>
          </div>
          <div className="extensions-runtime-loading-timer" aria-label={`Elapsed ${formatElapsedMs(elapsedMs)}`}>
            <span className="material-symbols-outlined" aria-hidden="true">timer</span>
            {formatElapsedMs(elapsedMs)}
          </div>
        </div>

        <div className="extensions-runtime-loading-progress" aria-hidden="true">
          <span />
        </div>

        <div className="extensions-runtime-loading-steps">
          {visibleSteps.map((step) => {
            const meta = statusMeta(step.status);
            return (
              <div
                key={step.id}
                className={`extensions-runtime-loading-step extensions-runtime-loading-step--${step.status}`}
              >
                <span className="extensions-runtime-loading-step-icon material-symbols-outlined" aria-hidden="true">
                  {meta.icon}
                </span>
                <div className="extensions-runtime-loading-step-copy">
                  <span className="extensions-runtime-loading-step-label">{step.label}</span>
                  {step.detail ? (
                    <span className="extensions-runtime-loading-step-detail">{step.detail}</span>
                  ) : null}
                </div>
                <span className={`extensions-runtime-loading-step-chip extensions-runtime-loading-step-chip--${step.status}`}>
                  {meta.label}
                </span>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
