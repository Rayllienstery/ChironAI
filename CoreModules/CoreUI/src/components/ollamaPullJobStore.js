import { streamOllamaPull } from '../services/api';

const listeners = new Set();

let state = {
  running: false,
  completed: false,
  error: '',
  model: '',
  progress: null,
  startedAt: null,
  finishedAt: null,
  promise: null,
};

/** @type {AbortController | null} */
let pullAbortController = null;

function emit() {
  listeners.forEach((listener) => listener(state));
}

export function subscribeOllamaPullJob(listener) {
  listeners.add(listener);
  listener(state);
  return () => listeners.delete(listener);
}

export function getOllamaPullJobSnapshot() {
  return state;
}

export function cancelOllamaPullJob() {
  if (pullAbortController) {
    try {
      pullAbortController.abort();
    } catch {
      /* ignore */
    }
    pullAbortController = null;
  }
}

export function formatOllamaBytes(value) {
  const bytes = Number(value || 0);
  if (!Number.isFinite(bytes) || bytes <= 0) return '';
  const gb = bytes / (1024 ** 3);
  if (gb >= 0.95) return `${gb.toFixed(gb >= 10 ? 1 : 2)} GB`;
  const mb = bytes / (1024 ** 2);
  if (mb >= 0.95) return `${mb.toFixed(mb >= 10 ? 1 : 2)} MB`;
  const kb = bytes / 1024;
  if (kb >= 0.95) return `${kb.toFixed(kb >= 10 ? 1 : 2)} KB`;
  return `${Math.round(bytes)} B`;
}

export function ollamaPullProgressText(progress) {
  if (!progress) return 'Preparing download';
  if (progress.cancelled) return 'Download cancelled';
  if (progress.error) return progress.error;
  if (progress.done) {
    const total = formatOllamaBytes(progress.total);
    return total ? `Downloaded ${total}` : 'Downloaded';
  }
  const completed = formatOllamaBytes(progress.completed);
  const total = formatOllamaBytes(progress.total);
  if (completed && total) return `Downloaded ${completed} / ${total}`;
  if (completed) return `Downloaded ${completed}`;
  return 'Preparing download';
}

export function pullProgressFromEvent(event, modelName, previousLayers = {}) {
  const digest = String(event?.digest || '');
  const eventTotal = Number(event?.total || 0);
  const eventCompleted = Number(event?.completed || 0);
  const layers = { ...(previousLayers || {}) };
  if (digest && (eventTotal > 0 || eventCompleted > 0)) {
    const prev = layers[digest] || { total: 0, completed: 0 };
    layers[digest] = {
      total: Math.max(Number(prev.total || 0), Number.isFinite(eventTotal) ? eventTotal : 0),
      completed: Math.max(Number(prev.completed || 0), Number.isFinite(eventCompleted) ? eventCompleted : 0),
    };
  }
  const layerValues = Object.values(layers);
  const total = layerValues.reduce((sum, layer) => sum + Number(layer?.total || 0), 0);
  const completed = layerValues.reduce((sum, layer) => {
    const layerTotal = Number(layer?.total || 0);
    const layerCompleted = Number(layer?.completed || 0);
    return sum + (layerTotal > 0 ? Math.min(layerCompleted, layerTotal) : layerCompleted);
  }, 0);
  const percent = total > 0 && completed >= 0
    ? Math.max(0, Math.min(100, Math.round((completed / total) * 100)))
    : null;
  const rawStatus = String(event?.status || '');
  const status = event?.ok
    ? 'Pulled'
    : total > 0
      ? 'Downloading model'
      : rawStatus && !/^pulling\s+[a-f0-9]{8,}$/i.test(rawStatus)
        ? rawStatus
        : 'Preparing download';
  return {
    model: String(event?.model || modelName || ''),
    status,
    digest,
    layers,
    total,
    completed,
    percent,
    done: Boolean(event?.ok === true || event?.status === 'success'),
    error: event?.error ? String(event.error) : '',
    cancelled: false,
  };
}

function isAbortError(e) {
  const name = e && typeof e === 'object' ? e.name : '';
  if (name === 'AbortError') return true;
  const msg = String(e?.message || e || '').toLowerCase();
  return msg.includes('abort') || msg.includes('aborted');
}

export function startOllamaPullJob(modelName) {
  const model = String(modelName || '').trim();
  if (!model) throw new Error('pull_model_name is required');
  if (state.running) {
    if (state.model === model && state.promise) return state.promise;
    throw new Error(`Ollama is already pulling ${state.model}`);
  }

  cancelOllamaPullJob();
  pullAbortController = new AbortController();
  const signal = pullAbortController.signal;

  const initial = {
    model,
    status: 'Starting pull',
    digest: '',
    layers: {},
    total: 0,
    completed: 0,
    percent: null,
    done: false,
    error: '',
    cancelled: false,
  };
  state = {
    running: true,
    completed: false,
    error: '',
    model,
    progress: initial,
    startedAt: new Date().toISOString(),
    finishedAt: null,
    promise: null,
  };
  emit();

  const promise = streamOllamaPull(model, (event) => {
    state = {
      ...state,
      progress: pullProgressFromEvent(event, model, state.progress?.layers),
    };
    emit();
  }, { signal })
    .then((last) => {
      pullAbortController = null;
      const latest = state.progress || pullProgressFromEvent(last, model);
      state = {
        ...state,
        running: false,
        completed: true,
        error: '',
        finishedAt: new Date().toISOString(),
        progress: {
          ...latest,
          done: true,
          status: 'Pulled',
        },
        promise: null,
      };
      emit();
      return { ok: true, message: `Pull completed for ${model}`, details: state.progress };
    })
    .catch((e) => {
      pullAbortController = null;
      if (isAbortError(e) || signal.aborted) {
        const latest = state.progress || initial;
        state = {
          ...state,
          running: false,
          completed: false,
          error: '',
          finishedAt: new Date().toISOString(),
          progress: {
            ...latest,
            cancelled: true,
            done: false,
            status: 'Cancelled',
          },
          promise: null,
        };
        emit();
        return { ok: false, cancelled: true, message: `Pull cancelled for ${model}` };
      }
      const message = String(e?.message || e);
      state = {
        ...state,
        running: false,
        completed: false,
        error: message,
        finishedAt: new Date().toISOString(),
        progress: {
          ...(state.progress || initial),
          error: message,
          done: false,
        },
        promise: null,
      };
      emit();
      throw e;
    });

  state = { ...state, promise };
  emit();
  return promise;
}
