import { isLoopbackHost } from '../utils/loopbackHost.js';

/** Must match Python ``webui_trusted_client.REVEAL_PIN_HEADER``. */
const REVEAL_PIN_HEADER = 'X-Chiron-Reveal-Pin';

let sessionPin = '';

/** Store the reveal PIN in memory for this browser tab (never localStorage). */
export function setRemoteRevealPin(pin) {
  sessionPin = String(pin || '').trim();
}

export function getRemoteRevealPin() {
  return sessionPin;
}

export function clearRemoteRevealPin() {
  sessionPin = '';
}

/** Attach reveal PIN header for non-loopback WebUI requests when PIN is set. */
export function withRemoteRevealPinInit(init = {}) {
  if (isLoopbackHost() || !sessionPin) {
    return init;
  }
  const headers = new Headers(init.headers || {});
  headers.set(REVEAL_PIN_HEADER, sessionPin);
  return { ...init, headers };
}

export function needsRemoteRevealPin() {
  return !isLoopbackHost();
}
