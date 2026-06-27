import { describe, expect, it } from 'vitest';
import {
  deserializePersistentValue,
  readPersistentState,
  serializePersistentValue,
  writePersistentState,
} from './usePersistentState';

class MemoryStorage {
  private values = new Map<string, string>();

  getItem(key: string) {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string) {
    this.values.set(key, value);
  }

  removeItem(key: string) {
    this.values.delete(key);
  }
}

describe('persistent state helpers', () => {
  it('keeps strings as plain localStorage values', () => {
    expect(serializePersistentValue('hub')).toBe('hub');
    expect(deserializePersistentValue('hub', 'fallback')).toBe('hub');
  });

  it('serializes and restores objects as JSON', () => {
    const storage = new MemoryStorage();

    writePersistentState('filters', { firma: 'Mobiup' }, { storage });

    expect(readPersistentState('filters', { firma: 'Toate' }, { storage })).toEqual({
      firma: 'Mobiup',
    });
  });

  it('falls back for invalid JSON when fallback is not a string', () => {
    const storage = new MemoryStorage();
    storage.setItem('bad', '{not-json');

    expect(readPersistentState('bad', { ok: true }, { storage })).toEqual({ ok: true });
  });

  it('removes values when removeWhen matches', () => {
    const storage = new MemoryStorage();
    storage.setItem('agent', 'Ion');

    writePersistentState('agent', '', {
      storage,
      removeWhen: (value) => value === '',
    });

    expect(storage.getItem('agent')).toBeNull();
  });
});
