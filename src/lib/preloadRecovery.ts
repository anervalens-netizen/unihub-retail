const RECOVERY_KEY = 'unihub_preload_recovery';

export function installPreloadRecovery(target: Window = window): () => void {
  const onPreloadError = (event: Event) => {
    event.preventDefault();
    const storage = target.sessionStorage;
    if (storage.getItem(RECOVERY_KEY) === 'attempted') return;
    storage.setItem(RECOVERY_KEY, 'attempted');
    target.location.reload();
  };

  target.addEventListener('vite:preloadError', onPreloadError);

  const clearRecoveryMarker = target.setTimeout(() => {
    target.sessionStorage.removeItem(RECOVERY_KEY);
  }, 10_000);

  return () => {
    target.removeEventListener('vite:preloadError', onPreloadError);
    target.clearTimeout(clearRecoveryMarker);
  };
}
