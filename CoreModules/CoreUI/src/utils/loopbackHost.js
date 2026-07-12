/** True when the WebUI is opened on the host machine (loopback hostname). */
export function isLoopbackHost() {
  if (typeof window === 'undefined') return true;
  const host = window.location.hostname || '';
  return (
    host === '127.0.0.1' ||
    host === 'localhost' ||
    host === '::1' ||
    host === '[::1]'
  );
}
