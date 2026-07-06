const STORAGE_KEY = 'chironai_onboarding_v1';
const SETTINGS_KEY = 'onboarding_state';

export const ONBOARDING_STATE_VERSION = 1;

export function createDefaultOnboardingState() {
  return {
    version: ONBOARDING_STATE_VERSION,
    firstRunCompleted: false,
    tours: {
      builds: false,
      extensions: false,
      prompts: false,
      crawler: false,
      logs: false,
    },
  };
}

function normalizeState(raw) {
  const base = createDefaultOnboardingState();
  if (!raw || typeof raw !== 'object') return base;
  return {
    version: Number(raw.version) || ONBOARDING_STATE_VERSION,
    firstRunCompleted: Boolean(raw.firstRunCompleted),
    tours: {
      ...base.tours,
      ...(raw.tours && typeof raw.tours === 'object' ? raw.tours : {}),
    },
  };
}

export function readOnboardingStateFromStorage() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return createDefaultOnboardingState();
    return normalizeState(JSON.parse(raw));
  } catch {
    return createDefaultOnboardingState();
  }
}

export function writeOnboardingStateToStorage(state) {
  const normalized = normalizeState(state);
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized));
  } catch {
    /* localStorage unavailable */
  }
  return normalized;
}

export function parseOnboardingStateFromSettings(settings) {
  const raw = settings?.[SETTINGS_KEY];
  if (!raw) return null;
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
    return normalizeState(parsed);
  } catch {
    return null;
  }
}

export function serializeOnboardingStateForSettings(state) {
  return JSON.stringify(normalizeState(state));
}

export { SETTINGS_KEY as ONBOARDING_SETTINGS_KEY };
