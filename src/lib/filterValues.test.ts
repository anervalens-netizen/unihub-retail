import { describe, expect, it } from 'vitest';
import { ALL_FIRMS, ALL_SCOPE, ALL_STORES, defaultAppFilters, normalizeAppFilters } from './filterValues';

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
    expect(f.magazin).toEqual([]);
    expect(f.agent).toEqual([]);
  });

  it('returns a new object each call', () => {
    expect(defaultAppFilters()).not.toBe(defaultAppFilters());
    expect(defaultAppFilters()).toEqual(defaultAppFilters());
  });
});

describe('normalizeAppFilters', () => {
  it('keeps supported filters and drops a legacy asm filter', () => {
    expect(normalizeAppFilters({
      firma: 'Mobiup',
      rm: 'Maria',
      asm: 'Mihai',
      magazin: ['STORE01'],
      agent: ['Agent1'],
    })).toEqual({
      firma: 'Mobiup',
      rm: 'Maria',
      magazin: ['STORE01'],
      agent: ['Agent1'],
    });
  });

  it('migrates legacy CSV session state once', () => {
    expect(normalizeAppFilters({ magazin: 'S1,S2', agent: 'A1,A2' })).toMatchObject({
      magazin: ['S1', 'S2'],
      agent: ['A1', 'A2'],
    });
  });

  it('canonicalizes arrays without splitting values that contain commas', () => {
    expect(normalizeAppFilters({
      magazin: [' B, Nord ', 'B, Nord', '', 7],
      agent: [' Popescu, Ana ', 'Popescu, Ana'],
    })).toMatchObject({
      magazin: ['B, Nord'],
      agent: ['Popescu, Ana'],
    });
  });

  it('maps legacy all sentinels and invalid selections to empty arrays', () => {
    expect(normalizeAppFilters({ magazin: ALL_STORES, agent: ALL_SCOPE })).toMatchObject({
      magazin: [],
      agent: [],
    });
    expect(normalizeAppFilters({ magazin: 7, agent: null })).toMatchObject({
      magazin: [],
      agent: [],
    });
  });
});
