import { describe, expect, it } from 'vitest';

import { bindRetailBrowserSession, clearRetailBrowserSession } from './browserSession';

function memoryStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() { return values.size; },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => Array.from(values.keys())[index] ?? null,
    removeItem: (key) => { values.delete(key); },
    setItem: (key, value) => { values.set(key, value); },
  };
}

describe('browser session isolation', () => {
  it('removes Retail state when the authenticated subject changes', () => {
    const storage = memoryStorage();
    storage.setItem('unihub_active_tab', 'management');
    bindRetailBrowserSession('user-a', storage);
    storage.setItem('unihub_current_month', '2026-08');

    bindRetailBrowserSession('user-b', storage);

    expect(storage.getItem('unihub_current_month')).toBeNull();
    expect(storage.getItem('unihub:session-owner')).toBe('user-b');
  });

  it('clears only Retail-owned state on logout', () => {
    const storage = memoryStorage();
    storage.setItem('unihub_theme', 'dark');
    storage.setItem('other-app', 'keep');

    clearRetailBrowserSession(storage);

    expect(storage.getItem('unihub_theme')).toBeNull();
    expect(storage.getItem('other-app')).toBe('keep');
  });
});
