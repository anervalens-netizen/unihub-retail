import { describe, expect, it } from 'vitest';
import { buildScopedMonthQuery } from './filterQueries';
import { ALL_FIRMS, ALL_SCOPE, ALL_STORES } from './filterValues';
import type { AppFilters } from '../components/MainLayout';

function makeFilters(overrides: Partial<AppFilters> = {}): AppFilters {
  return {
    firma: ALL_FIRMS,
    rm: ALL_SCOPE,
    magazin: ALL_STORES,
    agent: ALL_SCOPE,
    ...overrides,
  };
}

describe('buildScopedMonthQuery', () => {
  it('returns only month when all filters are default', () => {
    const q = buildScopedMonthQuery('2026-05', makeFilters());
    expect(q).toEqual({ month: '2026-05' });
  });

  it('includes firma when not ALL_FIRMS', () => {
    const q = buildScopedMonthQuery('2026-05', makeFilters({ firma: 'MobiCell' }));
    expect(q.firma).toBe('MobiCell');
    expect(q.regional).toBeUndefined();
  });

  it('includes regional when rm is set', () => {
    const q = buildScopedMonthQuery('2026-05', makeFilters({ rm: 'Elena Popescu' }));
    expect(q.regional).toBe('Elena Popescu');
  });

  it('ignores a legacy asm value', () => {
    const filters = { ...makeFilters(), asm: 'Mihai Condorateanu' };
    const q = buildScopedMonthQuery('2026-05', filters);
    expect(q.asm).toBeUndefined();
  });

  it('includes site_code when magazin is set', () => {
    const q = buildScopedMonthQuery('2026-05', makeFilters({ magazin: 'CRELECTROP' }));
    expect(q.site_code).toBe('CRELECTROP');
  });

  it('includes agent when set', () => {
    const q = buildScopedMonthQuery('2026-05', makeFilters({ agent: 'Ion Ionescu' }));
    expect(q.agent).toBe('Ion Ionescu');
  });

  it('includes multiple filters simultaneously', () => {
    const q = buildScopedMonthQuery('2026-05', makeFilters({
      firma: 'Mobiup',
      rm: 'Maria',
      magazin: 'STORE01',
      agent: 'Agent1',
    }));
    expect(q.firma).toBe('Mobiup');
    expect(q.regional).toBe('Maria');
    expect(q.asm).toBeUndefined();
    expect(q.site_code).toBe('STORE01');
    expect(q.agent).toBe('Agent1');
    expect(q.month).toBe('2026-05');
  });
});
