export function releaseBodyScrollLock() {
  if (typeof document === 'undefined') return;
  document.body.style.removeProperty('overflow');
}
