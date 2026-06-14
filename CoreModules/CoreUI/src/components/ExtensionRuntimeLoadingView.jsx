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
  loadState,
  message,
  mode = 'request',
} = {}) {
  const runtimeMessage = message || 'Waiting for the extension runtime and provider sandbox.';
  const status = String(loadState?.status || '').toLowerCase();
  const phases = loadState?.phases || {};
  const isError = mode === 'error' || status === 'failed' || status === 'timeout';
  const isReady = status === 'ready';
  const isStale = status === 'stale';
  const isRefreshing = status === 'refreshing';
  const runtimeStatus = mode === 'runtime' ? 'loading' : isError ? 'error' : 'done';
  const descriptorStatus = isError && phases.descriptor !== 'ready'
    ? phases.descriptor === 'timeout' ? 'error' : 'error'
    : phases.descriptor === 'ready' || phases.descriptor === 'skipped' || isReady || isStale
      ? 'done'
      : isRefreshing && phases.descriptor === 'refreshing'
        ? 'loading'
        : isRefreshing || status === 'missing'
          ? 'pending'
          : 'pending';
  const payloadStatus = isError
    ? 'error'
    : phases.payload === 'ready' || isReady || isStale
      ? 'done'
      : isRefreshing && phases.payload === 'refreshing'
        ? 'loading'
        : mode === 'payload' || isRefreshing || status === 'missing'
          ? 'loading'
          : 'pending';

  return [
    {
      id: 'manifest',
      label: 'Manifest tab registered',
      detail: 'CoreUI has mounted the extension shell from manifest metadata.',
      status: 'done',
    },
    {
      id: 'runtime',
      label: 'Extension runtime',
      detail: runtimeMessage,
      status: runtimeStatus,
    },
    {
      id: 'descriptor',
      label: 'Provider descriptor',
      detail: loadState?.job_id ? `Background job ${loadState.job_id}` : 'Waiting for descriptor cache.',
      status: descriptorStatus,
    },
    {
      id: 'payload',
      label: 'Tab payload',
      detail: endpoint || '/api/webui/extensions/:id/tab',
      status: payloadStatus,
    },
    {
      id: 'render-surface',
      label: 'Render extension surface',
      detail: 'Schema pages, service cards, iframe content, and diagnostics.',
      status: isReady || isStale ? 'done' : isError ? 'error' : 'pending',
    },
  ].map((step) => (
    step.id === 'runtime' && mode === 'request'
      ? { ...step, status: 'pending' }
      : step
  ));
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
