import { describe, expect, it } from 'vitest';
import { queryKeys } from './queryKeys';

describe('queryKeys', () => {
  it('builds stable campaigns current keys', () => {
    const query = { month: '2026-06', firma: 'Mobiup' };

    expect(queryKeys.campaigns.current('promo', '2026-06', 'cellara', query)).toEqual([
      'campaigns',
      'current',
      'promo',
      '2026-06',
      'cellara',
      query,
    ]);
  });

  it('copies month arrays for dashboard history detail keys', () => {
    const months = ['2026-06', '2026-05'];
    const key = queryKeys.dashboard.historyDetail(months, {});
    months.push('2026-04');

    expect(key[2]).toEqual(['2026-06', '2026-05']);
  });

  it('keeps dashboard current and yearly history keys separate', () => {
    const query = { current_scope: true, include_closed_stores: false, months_back: 14 };

    expect(queryKeys.dashboard.currentHistory('2026-06', query)).toEqual([
      'dashboard',
      'current-history',
      '2026-06',
      query,
    ]);
    expect(queryKeys.dashboard.yearHistory(2026, query)).toEqual([
      'dashboard',
      'year-history',
      2026,
      query,
    ]);
  });
});
