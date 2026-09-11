import { describe, expect, it } from 'vitest';

import { defaultAppFilters } from './filterValues';
import { buildRetailContextUrl, parseInsightDeepLink } from './insightDeepLink';

function parseBuiltUrl(url: string) {
  const parsed = new URL(url, 'https://retail.test');
  return parseInsightDeepLink({ pathname: parsed.pathname, search: parsed.search } as Location);
}

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
      filters: { firma: 'Mobicell', rm: 'Nord', magazin: ['S001'], agent: ['Agent Test'] },
    });
  });

  it.each([
    ['/focus', 'section=promo', { tab: 'focus', campaignSection: 'promo', filters: {} }],
    ['/agenti', 'section=grile', { tab: 'agents', agentsSection: 'grile', filters: {} }],
    ['/management', 'subtab=salarii', { tab: 'management', managementSubtab: 'salarii', filters: {} }],
    ['/management/pnl', '', { tab: 'management', managementSubtab: 'pnl', filters: {} }],
    ['/settings', '', { tab: 'settings', filters: {} }],
  ] as const)('maps %s to the requested operational surface', (pathname, query, expected) => {
    expect(
      parseInsightDeepLink({
        pathname,
        search: `?source_context=insight${query ? `&${query}` : ''}`,
      } as Location),
    ).toEqual(expected);
  });

  it('preserves and deduplicates a multi-store scope', () => {
    expect(
      parseInsightDeepLink({
        pathname: '/agenti',
        search: '?source_context=insight&stores=S001,S002,S001',
      } as Location)?.filters,
    ).toEqual({ magazin: ['S001', 'S002'] });
  });

  it('accepts generated Retail context links while rejecting ordinary or unknown context', () => {
    expect(
      parseInsightDeepLink({
        pathname: '/hub',
        search: '?source_context=retail&period=2026-08&section=history',
      } as Location),
    ).toEqual({
      tab: 'hub',
      hubSection: 'history',
      period: '2026-08',
      filters: defaultAppFilters(),
    });
    expect(parseInsightDeepLink({ pathname: '/hub', search: '?period=2026-08' } as Location)).toBeNull();
    expect(parseInsightDeepLink({ pathname: '/hub', search: '?source_context=unknown' } as Location)).toBeNull();
  });

  it('ignores malformed month/section values and bounds repeated selections', () => {
    const params = new URLSearchParams({
      source_context: 'retail',
      period: '2026-99',
      section: 'unknown',
    });
    for (let index = 0; index < 55; index += 1) params.append('agent', `Agent ${index}`);
    params.append('agent', 'x'.repeat(181));

    const parsed = parseInsightDeepLink({ pathname: '/hub', search: `?${params}` } as Location);
    expect(parsed?.period).toBeUndefined();
    expect(parsed?.hubSection).toBe('current');
    expect(parsed?.filters.firma).toBe('Toate');
    expect(parsed?.filters.rm).toBe('Toti');
    expect(parsed?.filters.magazin).toEqual([]);
    expect(parsed?.filters.agent).toHaveLength(50);
    expect(parsed?.filters.agent?.at(-1)).toBe('Agent 49');
  });

  it('builds a canonical shareable URL and round-trips period, section and filters', () => {
    const url = buildRetailContextUrl({
      tab: 'hub',
      period: '2026-08',
      hubSection: 'history',
      filters: {
        firma: 'Mobicell',
        rm: 'Nord',
        magazin: ['S002', 'S001', 'S002'],
        agent: ['Agent Test'],
      },
    });

    expect(url).toBe(
      '/hub?source_context=retail&period=2026-08&firma=Mobicell&rm=Nord&magazin=S002&magazin=S001&agent=Agent+Test&section=history',
    );
    expect(parseBuiltUrl(url)).toEqual({
      tab: 'hub',
      period: '2026-08',
      hubSection: 'history',
      filters: {
        firma: 'Mobicell',
        rm: 'Nord',
        magazin: ['S002', 'S001'],
        agent: ['Agent Test'],
      },
    });
  });

  it('serializes section/subtab state without treating URL state as authorization', () => {
    const filters = defaultAppFilters();
    expect(parseBuiltUrl(buildRetailContextUrl({
      tab: 'focus',
      period: '2026-05',
      campaignSection: 'promo',
      filters,
    }))).toEqual({ tab: 'focus', period: '2026-05', campaignSection: 'promo', filters });
    expect(parseBuiltUrl(buildRetailContextUrl({
      tab: 'agents',
      period: '2026-05',
      agentsSection: 'analysis',
      filters,
    }))).toEqual({ tab: 'agents', period: '2026-05', agentsSection: 'analysis', filters });
    expect(parseBuiltUrl(buildRetailContextUrl({
      tab: 'management',
      period: '2026-05',
      managementSubtab: 'pnl',
      filters,
    }))).toEqual({ tab: 'management', period: '2026-05', managementSubtab: 'pnl', filters });
    expect(buildRetailContextUrl({
      tab: 'settings',
      period: '2026-05',
      filters: { ...filters, firma: 'Must not leak' },
    })).toBe('/settings?source_context=retail');
  });
});
