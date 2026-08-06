import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  clearCachedViews,
  getCachedView,
  removeCachedView,
  setCachedView,
} from './viewCache';

// Chei unice per test — evită shared state din modulul singleton
let keyCounter = 0;
function nextKey() {
  return `test-key-${++keyCounter}`;
}

describe('getCachedView', () => {
  it('clears session-scoped cached views on logout', () => {
    const key = nextKey();
    setCachedView(key, 'private');
    clearCachedViews();
    expect(getCachedView(key, 5000).value).toBeNull();
  });

  it('invalidates one permission-scoped view without clearing the rest', () => {
    const removedKey = nextKey();
    const retainedKey = nextKey();
    setCachedView(removedKey, 'private');
    setCachedView(retainedKey, 'safe');
    removeCachedView(removedKey);
    expect(getCachedView(removedKey, 5000).value).toBeNull();
    expect(getCachedView(retainedKey, 5000).value).toBe('safe');
  });

  it('returns null + not fresh for unknown key', () => {
    const { value, isFresh } = getCachedView(nextKey(), 5000);
    expect(value).toBeNull();
    expect(isFresh).toBe(false);
  });

  it('returns stored value and marks as fresh immediately after set', () => {
    const key = nextKey();
    setCachedView(key, { x: 42 });
    const { value, isFresh } = getCachedView<{ x: number }>(key, 5000);
    expect(value).toEqual({ x: 42 });
    expect(isFresh).toBe(true);
  });

  it('marks as stale when maxAgeMs has elapsed', () => {
    const key = nextKey();
    // Setăm timestamp-ul în trecut via mock Date.now
    const past = Date.now() - 10_000; // 10 secunde în urmă
    vi.spyOn(Date, 'now').mockReturnValueOnce(past);
    setCachedView(key, 'stale-value');
    vi.restoreAllMocks();

    const { value, isFresh } = getCachedView<string>(key, 5000); // maxAge 5s
    expect(value).toBe('stale-value'); // valoarea e prezentă
    expect(isFresh).toBe(false);       // dar stale
  });

  it('overwrites existing value on repeated set', () => {
    const key = nextKey();
    setCachedView(key, 'first');
    setCachedView(key, 'second');
    const { value } = getCachedView<string>(key, 5000);
    expect(value).toBe('second');
  });
});

describe('setCachedView eviction', () => {
  beforeEach(() => {
    // Populează cache-ul aproape de limită cu chei proprii
    // (MAX_CACHE_SIZE = 50; keyCounter garantează unicitate)
  });

  it('evicts oldest entry when cache reaches 50 entries', () => {
    // Umple cache-ul cu 50 intrări la timestamp-uri crescătoare
    const oldestKey = nextKey();
    vi.spyOn(Date, 'now').mockReturnValueOnce(1000);
    setCachedView(oldestKey, 'oldest');
    vi.restoreAllMocks();

    // Adaugă 49 intrări suplimentare (ajungem la 50 total)
    for (let i = 0; i < 49; i++) {
      setCachedView(nextKey(), `fill-${i}`);
    }

    // La a 51-a intrare (cache plin), oldestKey trebuie evictat
    const newKey = nextKey();
    setCachedView(newKey, 'newest');

    // oldestKey evictat — getCachedView returnează null
    const { value } = getCachedView(oldestKey, 999_999);
    expect(value).toBeNull();

    // Noua intrare e prezentă
    const { value: newest } = getCachedView(newKey, 5000);
    expect(newest).toBe('newest');
  });
});
