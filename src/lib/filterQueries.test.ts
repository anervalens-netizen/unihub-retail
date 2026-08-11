import { describe, expect, it } from 'vitest';
import { buildCurrentDashboardQuery, buildScopedMonthQuery } from './filterQueries';
import { ALL_FIRMS, ALL_SCOPE } from './filterValues';
import type { AppFilters } from './appFilters';

function makeFilters(overrides: Partial<AppFilters> = {}): AppFilters {
  return {
    firma: ALL_FIRMS,
    rm: ALL_SCOPE,
    magazin: [],
    agent: [],
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
    const q = buildScopedMonthQuery('2026-05', makeFilters({ magazin: ['CRELECTROP'] }));
    expect(q.site_code).toEqual(['CRELECTROP']);
  });

  it('includes agent when set', () => {
    const q = buildScopedMonthQuery('2026-05', makeFilters({ agent: ['Ion Ionescu'] }));
    expect(q.agent).toEqual(['Ion Ionescu']);
  });

  it('includes multiple filters simultaneously', () => {
    const q = buildScopedMonthQuery('2026-05', makeFilters({
      firma: 'Mobiup',
      rm: 'Maria',
      magazin: ['STORE01'],
      agent: ['Agent1'],
    }));
    expect(q.firma).toBe('Mobiup');
    expect(q.regional).toBe('Maria');
    expect(q.asm).toBeUndefined();
    expect(q.site_code).toEqual(['STORE01']);
    expect(q.agent).toEqual(['Agent1']);
    expect(q.month).toBe('2026-05');
  });
});

describe('buildCurrentDashboardQuery', () => {
  it('always uses the active current organization scope', () => {
    expect(buildCurrentDashboardQuery('2026-07', makeFilters({ rm: 'Bogdana Costan' }))).toEqual({
      month: '2026-07',
      regional: 'Bogdana Costan',
      current_scope: true,
      include_closed_stores: false,
    });
  });
});
