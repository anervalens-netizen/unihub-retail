type CacheEntry<T> = {
  value: T;
  timestamp: number;
};

const MAX_CACHE_SIZE = 50;
const cache = new Map<string, CacheEntry<unknown>>();

export function getCachedView<T>(
  key: string,
  maxAgeMs: number
): { value: T | null; isFresh: boolean } {
  const entry = cache.get(key) as CacheEntry<T> | undefined;
  if (!entry) {
    return { value: null, isFresh: false };
  }

  const age = Date.now() - entry.timestamp;
  return {
    value: entry.value,
    isFresh: age <= maxAgeMs,
  };
}

export function setCachedView<T>(key: string, value: T) {
  // Evict oldest entries when cache exceeds max size
  if (cache.size >= MAX_CACHE_SIZE && !cache.has(key)) {
    let oldestKey: string | null = null;
    let oldestTime = Infinity;
    for (const [k, v] of cache) {
      if (v.timestamp < oldestTime) {
        oldestTime = v.timestamp;
        oldestKey = k;
      }
    }
    if (oldestKey) cache.delete(oldestKey);
  }

  cache.set(key, {
    value,
    timestamp: Date.now(),
  });
}

