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
});
