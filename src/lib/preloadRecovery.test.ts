import { describe, expect, it, vi } from 'vitest';

import { installPreloadRecovery } from './preloadRecovery';

function createFakeWindow() {
  const values = new Map<string, string>();
  const listeners = new Map<string, EventListener>();
  const reload = vi.fn();
  const removeEventListener = vi.fn((type: string) => listeners.delete(type));
  const target = {
    sessionStorage: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    },
    location: { reload },
    addEventListener: (type: string, listener: EventListener) => listeners.set(type, listener),
    removeEventListener,
    setTimeout: vi.fn(() => 7),
    clearTimeout: vi.fn(),
  };
  return { target: target as unknown as Window, values, listeners, reload, removeEventListener };
}

describe('installPreloadRecovery', () => {
  it('reloads once when a stale lazy chunk cannot be loaded', () => {
    const fake = createFakeWindow();
    installPreloadRecovery(fake.target);
    const preventDefault = vi.fn();
    const event = { preventDefault } as unknown as Event;

    fake.listeners.get('vite:preloadError')?.(event);
    fake.listeners.get('vite:preloadError')?.(event);

    expect(preventDefault).toHaveBeenCalledTimes(2);
    expect(fake.reload).toHaveBeenCalledTimes(1);
    expect(fake.values.get('unihub_preload_recovery')).toBe('attempted');
  });

  it('removes its listener during cleanup', () => {
    const fake = createFakeWindow();
    const cleanup = installPreloadRecovery(fake.target);

    cleanup();

    expect(fake.removeEventListener).toHaveBeenCalledWith('vite:preloadError', expect.any(Function));
    expect(fake.target.clearTimeout).toHaveBeenCalledWith(7);
  });
});
