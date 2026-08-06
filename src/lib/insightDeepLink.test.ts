import { describe, expect, it } from 'vitest';

import { parseInsightDeepLink } from './insightDeepLink';

describe('Insight contextual deep links', () => {
  it('restores the Retail surface, period and a single-store scope', () => {
    expect(
      parseInsightDeepLink({
        pathname: '/hub',
        search:
          '?source_context=insight&section=history&period=2026-08&firma=Mobicell&rm=Nord&magazin=S001&agent=Agent%20Test',
      } as Location),
    ).toEqual({
      tab: 'hub',
      hubSection: 'history',
      period: '2026-08',
      filters: { firma: 'Mobicell', rm: 'Nord', magazin: 'S001', agent: 'Agent Test' },
    });
  });

  it.each([
    ['/focus', 'section=promo', { tab: 'focus', campaignSection: 'promo', filters: {} }],
    ['/agenti', 'section=grile', { tab: 'agents', agentsSection: 'grile', filters: {} }],
    ['/management', 'subtab=salarii', { tab: 'management', managementSubtab: 'salarii', filters: {} }],
    ['/management/pnl', '', { tab: 'management', managementSubtab: 'pnl', filters: {} }],
  ] as const)('maps %s to the requested operational surface', (pathname, query, expected) => {
    expect(
      parseInsightDeepLink({
        pathname,
        search: `?source_context=insight${query ? `&${query}` : ''}`,
      } as Location),
    ).toEqual(expected);
  });

  it('does not let a multi-store scope silently become one selected store', () => {
    expect(
      parseInsightDeepLink({
        pathname: '/agenti',
        search: '?source_context=insight&stores=S001,S002,S001',
      } as Location)?.filters,
    ).toEqual({});
  });

  it('ignores ordinary Retail URLs and malformed context', () => {
    expect(parseInsightDeepLink({ pathname: '/hub', search: '?period=2026-08' } as Location)).toBeNull();
    expect(
      parseInsightDeepLink({
        pathname: '/hub',
        search: '?source_context=insight&period=2026-99&section=unknown',
      } as Location),
    ).toEqual({ tab: 'hub', hubSection: 'current', filters: {} });
  });
});
