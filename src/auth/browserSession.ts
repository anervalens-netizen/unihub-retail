const SESSION_OWNER_KEY = 'unihub:session-owner';
const RETAIL_KEY_PREFIXES = ['unihub_', 'unihub:'];

export function clearRetailSessionStorage(storage: Storage = window.sessionStorage): void {
  for (let index = storage.length - 1; index >= 0; index -= 1) {
    const key = storage.key(index);
    if (key && RETAIL_KEY_PREFIXES.some((prefix) => key.startsWith(prefix))) {
      storage.removeItem(key);
    }
  }
}

export function bindRetailBrowserSession(subject: string, storage: Storage = window.sessionStorage): void {
  const previous = storage.getItem(SESSION_OWNER_KEY);
  if (previous !== null && previous !== subject) clearRetailSessionStorage(storage);
  storage.setItem(SESSION_OWNER_KEY, subject);
}

export function clearRetailBrowserSession(storage: Storage = window.sessionStorage): void {
  clearRetailSessionStorage(storage);
}
