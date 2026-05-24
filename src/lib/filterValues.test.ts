import { describe, expect, it } from 'vitest';
import { ALL_FIRMS, ALL_SCOPE, ALL_STORES, defaultAppFilters } from './filterValues';

describe('filter sentinel constants', () => {
  it('ALL_FIRMS is a non-empty string', () => {
    expect(ALL_FIRMS).toBe('Toate');
  });

  it('ALL_SCOPE is a non-empty string', () => {
    expect(ALL_SCOPE).toBe('Toti');
  });

  it('ALL_STORES is a non-empty string', () => {
    expect(ALL_STORES).toBe('Toate');
  });
});

describe('defaultAppFilters', () => {
  it('returns all sentinel values', () => {
    const f = defaultAppFilters();
    expect(f.firma).toBe(ALL_FIRMS);
    expect(f.rm).toBe(ALL_SCOPE);
    expect(f.asm).toBe(ALL_SCOPE);
    expect(f.magazin).toBe(ALL_STORES);
    expect(f.agent).toBe(ALL_SCOPE);
  });

  it('returns a new object each call', () => {
    expect(defaultAppFilters()).not.toBe(defaultAppFilters());
    expect(defaultAppFilters()).toEqual(defaultAppFilters());
  });
});
