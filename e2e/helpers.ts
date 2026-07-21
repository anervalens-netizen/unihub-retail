import { BrowserContext } from '@playwright/test';
import type { CampaignsPromotionsResponse } from '../src/api/types';

export const MOCK_USER = {
  sub: 'test-user-123',
  email: 'test@mobiup.ro',
  name: 'Test User',
  groups: ['unihub-retail:manager'],
};

export async function mockAuthenticatedSession(context: BrowserContext) {
  await context.addInitScript(() => {
    (window as unknown as Record<string, unknown>).__E2E_USER__ = {
      profile: {
        sub: 'test-user-123',
        email: 'test@mobiup.ro',
        preferred_username: 'test-user',
        groups: ['unihub-admin'],
      },
    };
  });
}

export async function mockApiRoute(context: BrowserContext, method: string, urlPattern: string | RegExp, response: unknown) {
  await context.route(urlPattern, (route) => {
    if (route.request().method() === method.toUpperCase()) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(response),
      });
    }
    return route.continue();
  });
}

export const MOCK_MONTHS = ['2026-05', '2026-04', '2026-03', '2026-02', '2026-01'];

export const MOCK_FILTER_OPTIONS = {
  firme: ['Firma 1'],
  regionali: ['Regional 1'],
  asmi: ['ASM 1'],
  magazine: [{ site_code: 'S1', locatie: 'Magazin 1', firma: 'Firma 1', regional: 'Regional 1', asm: 'ASM 1' }],
  agenti: [{ agent: 'Agent 1', site_code: 'S1', locatie: 'Magazin 1', firma: 'Firma 1', regional: 'Regional 1', asm: 'ASM 1' }],
};

export const MOCK_DASHBOARD_ALL = {
  summary: {
    month: '2026-05',
    total_sales: 150000,
    total_target: 200000,
    target_progress_pct: 75.0,
    forecast_sales: 180000,
    forecast_target_progress_pct: 90.0,
    total_quantity: 500,
    total_receipts: 300,
    proc_bon2acc: 60.0,
    prc_focus_acc_qty: 25.0,
    total_stores: 30,
    total_agents: 120,
    working_days: 22,
    daily_average: 6818.18,
    is_month_final: false,
    last_sale_date: '2026-05-06',
    imported_day_of_month: 6,
    days_in_month: 31,
    cartele_qty: 10,
  },
  agents: [],
  stores: [],
  daily: [],
  special_cards: [],
  period_comparison: null,
  category_mix: [],
  receipt_bucket_mix: [],
  focus_subcategory_mix: [],
  brand_mix: [],
  promo_incentive: {
    promo_qty: 0,
    promo_impact: 0,
    incentive_qty: 0,
    incentive_value: 0,
  },
  regionals: [],
  asms: [],
};

export const MOCK_DASHBOARD_HISTORY = {
  history: MOCK_MONTHS.map((month) => ({
    month,
    total_sales: 120000,
    total_target: 180000,
    target_progress_pct: 66.7,
    total_quantity: 450,
    total_receipts: 280,
    proc_bon2acc: 62.0,
    prc_focus_acc_qty: 22.0,
    total_stores: 28,
    total_agents: 110,
    working_days: 22,
    daily_average: 5454.5,
  })),
};

export const MOCK_DASHBOARD_YEAR_HISTORY = {
  points: [
    {
      label: '2026',
      sort_key: '2026-00',
      total_sales: 600000,
      total_target: 900000,
      total_quantity: 2500,
      is_aggregate: false,
    },
  ],
};

export const MOCK_PROMOTIONS_RESPONSE: CampaignsPromotionsResponse = {
  promotions: [],
  selected_promotion_key: '',
  promo_title: '',
  promo_description: '',
  promo_qty: 0,
  promo_total_qty: 0,
  promo_category_qty: null,
  promo_impact: 0,
  promo_qualifying_bons: 0,
  promo_discounted_units: 0,
  promo_active_stores: 0,
  promo_active_agents: 0,
  incentive_title: '',
  incentive_description: '',
  incentive_qty: 0,
  incentive_sold_qty: 0,
  incentive_value: 0,
  incentive_potential: 0,
  incentive_qualified_qty: 0,
  incentive_qualified_stores: 0,
  incentive_qualified_stores_full: 0,
  incentive_qualified_stores_half: 0,
  incentive_qualified_agents: 0,
  incentive_qualified_agents_full: 0,
  incentive_qualified_agents_half: 0,
  incentive_product_count: 0,
  incentive_categories: [],
  incentive_periods: [],
  incentive_category_breakdown: [],
    has_active_promotion: false,
    promo_calculation_status: 'not_configured',
    incentive_calculation_status: 'not_configured',
    calculation_warnings: [],
  top_stores: [],
  promo_agents: [],
  top_agents: [],
};

export async function setupBaseMocks(context: BrowserContext) {
  await mockAuthenticatedSession(context);

  await context.route((url) => url.pathname.startsWith('/api/'), (route) => {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({}),
    });
  });

  await mockApiRoute(context, 'GET', /\/api\/filters\/months$/, MOCK_MONTHS);
  await mockApiRoute(context, 'GET', /\/api\/filters\/options/, MOCK_FILTER_OPTIONS);
  await mockApiRoute(context, 'GET', /\/api\/dashboard\/all/, MOCK_DASHBOARD_ALL);
  await context.route(/\/api\/dashboard\/all-batch$/, async (route) => {
    if (route.request().method() !== 'POST') {
      return route.fallback();
    }
    const payload = route.request().postDataJSON() as {
      queries?: Array<{ month?: string }>;
    };
    const results = (payload.queries ?? []).map((query) => ({
      ...MOCK_DASHBOARD_ALL,
      summary: {
        ...MOCK_DASHBOARD_ALL.summary,
        month: query.month ?? MOCK_DASHBOARD_ALL.summary.month,
      },
    }));
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ results }),
    });
  });
  await mockApiRoute(context, 'GET', /\/api\/dashboard\/history\b/, MOCK_DASHBOARD_HISTORY);
  await mockApiRoute(context, 'GET', /\/api\/dashboard\/history-year/, MOCK_DASHBOARD_YEAR_HISTORY);
  await mockApiRoute(context, 'GET', /\/api\/stores$/, []);
  await mockApiRoute(context, 'GET', /\/api\/hr\/asm-performance/, []);
  await mockApiRoute(context, 'GET', /\/api\/hr\/manager-overview/, []);
  await mockApiRoute(context, 'GET', /\/api\/crm\/scores/, []);
  await mockApiRoute(context, 'GET', /\/api\/campaigns\/overview/, {
    snapshot: null, focus_products: [], promo_products: [],
    has_active_promotion: false, has_active_incentive: false,
  });
  await mockApiRoute(context, 'GET', /\/api\/campaigns\/history/, { history: [] });
  await mockApiRoute(
    context,
    'GET',
    /\/api\/campaigns\/promotions-incentives/,
    MOCK_PROMOTIONS_RESPONSE,
  );
  await mockApiRoute(context, 'GET', /\/api\/import\/history/, []);
}
