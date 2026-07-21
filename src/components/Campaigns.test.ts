import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { Campaigns } from './Campaigns';
import { buildScopedMonthQuery } from '../lib/filterQueries';
import { defaultAppFilters } from '../lib/filterValues';
import { queryKeys } from '../lib/queryKeys';
import type { CampaignsPromotionsResponse } from '../api/types';

vi.mock('../api/campaigns', () => ({
  getCampaignSnapshot: vi.fn(),
  getFocusHistory: vi.fn(),
  getPromotionsIncentives: vi.fn(),
}));

vi.mock('../api/contests', () => ({
  getActiveContests: vi.fn(),
}));

vi.mock('../api/dashboard', () => ({
  getPremiumGlassAnalysis: vi.fn(),
}));

const month = '2026-06';
const filters = defaultAppFilters();
const scopedQuery = buildScopedMonthQuery(month, filters);

function makePromoData(): CampaignsPromotionsResponse {
  return {
    promotions: [{ key: 'promo-iunie', label: 'Promo iunie' }],
    selected_promotion_key: 'promo-iunie',
    promo_title: 'Promo test',
    promo_description: 'Bonuri co-purchase',
    promo_qty: 99,
    promo_total_qty: 120,
    promo_category_qty: 80,
    promo_impact: 20,
    promo_qualifying_bons: 12,
    promo_discounted_units: 7,
    promo_active_stores: 3,
    promo_active_agents: 4,
    incentive_title: 'Incentive test',
    incentive_description: 'Cantitate incentive neta',
    incentive_qty: 18,
    incentive_sold_qty: 25,
    incentive_value: 450,
    incentive_potential: 600,
    incentive_qualified_qty: 12,
    incentive_qualified_stores: 4,
    incentive_qualified_stores_full: 3,
    incentive_qualified_stores_half: 1,
    incentive_qualified_agents: 7,
    incentive_qualified_agents_full: 5,
    incentive_qualified_agents_half: 2,
    incentive_product_count: 5,
    incentive_categories: [],
    incentive_periods: [
      { label: 'Mecanism initial', start_date: '2026-07-01', end_date: '2026-07-09', product_count: 967, reward_values: [5, 10, 25], qty: 10, potential: 250, value: 200 },
      { label: 'Mecanism actualizat', start_date: '2026-07-10', end_date: '2026-07-31', product_count: 201, reward_values: [5, 10, 15, 30], qty: 8, potential: 350, value: 250 },
    ],
    incentive_category_breakdown: [],
  has_active_promotion: true,
  promo_calculation_status: 'complete',
  incentive_calculation_status: 'complete',
  calculation_warnings: [],
    top_stores: [
      {
        store_name: 'Mobiup - Store Test',
        qty: 8,
        total_qty: 20,
        category_qty: 10,
        promo_bons: 12,
        incentive_value: 150,
        incentive_potential: 250,
        achievement: 1,
        firma: 'Mobiup',
      },
    ],
    promo_agents: [
      {
        agent_name: 'Ion Agent',
        store_name: 'Mobiup - Store Test',
        firma: 'Mobiup',
        promo_bons: 6,
      },
    ],
    top_agents: [
      {
        agent_name: 'Ana Agent',
        store_name: 'Mobiup - Store Test',
        firma: 'Mobiup',
        qty_sold: 18,
        val_incentive: 450,
        incentive_potential: 600,
        achievement: 1,
      },
    ],
  };
}

function renderCampaigns(section: 'promo' | 'incentive') {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 3 * 60_000,
      },
    },
  });
  queryClient.setQueryData(
    queryKeys.campaigns.current(section, month, '', scopedQuery),
    { promoData: makePromoData() },
  );

  return renderToStaticMarkup(
    createElement(
      QueryClientProvider,
      { client: queryClient },
      createElement(Campaigns, {
        currentMonth: month,
        months: [month],
        filters,
        preferredSection: section,
        onSectionChange: () => undefined,
      }),
    ),
  );
}

describe('Campaigns', () => {
  it('renders promo qualifying receipts separately from incentive quantity', () => {
    const html = renderCampaigns('promo');

    expect(html).toContain('Promo test');
    expect(html).toContain('bonuri calificate');
    expect(html).toContain('Unități promo efective');
    expect(html).toContain('12');
  });

  it('renders the four operational incentive values and both monthly mechanisms', () => {
    const html = renderCampaigns('incentive');

    expect(html).toContain('Incentive test');
    expect(html).toContain('unități vândute');
    expect(html).toContain('unități eligibile după promo');
    expect(html).toContain('unități în magazinele calificate');
    expect(html).toContain('incentive calculat acum');
    expect(html).not.toContain('potențial calculat');
    expect(html).not.toContain('diferență disponibilă');
    expect(html).toContain('2 mecanisme în luna selectată');
    expect(html).toContain('Mecanism initial');
    expect(html).toContain('Mecanism actualizat');
    expect(html).toContain('967 produse');
    expect(html).toContain('201 produse');
    expect(html).not.toContain('potential la calificare 100%');
    expect(html).toContain('18');
    expect(html).toContain('25');
    expect(html).toContain('magazine calificate');
    expect(html).toContain('agenti calificati');
    expect(html).toContain('Magazine · 100%+');
    expect(html).toContain('Magazine · 90–99,99%');
    expect(html).toContain('agenti la acest prag');
    expect(html).toContain('3');
    expect(html).toContain('5');
  });
});
