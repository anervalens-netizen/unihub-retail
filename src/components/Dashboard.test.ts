import { describe, expect, it } from 'vitest';
import { aggregateDashboardDetails, getDefaultHistoryMonth } from '../features/dashboard/presenters';
import type {
  AgentStat,
  DashboardAllResponse,
  DashboardSummary,
  StoreStat,
} from '../api/types';

function summary(month: string, overrides: Partial<DashboardSummary>): DashboardSummary {
  return {
    month,
    total_sales: 0,
    total_target: 0,
    target_progress_pct: null,
    forecast_sales: null,
    forecast_target_progress_pct: null,
    total_quantity: 0,
    total_receipts: 0,
    proc_bon2acc: null,
    prc_focus_acc_qty: null,
    total_stores: 0,
    total_agents: 0,
    working_days: 0,
    daily_average: null,
    medie_produs: null,
    is_month_final: true,
    last_sale_date: `${month}-28`,
    imported_day_of_month: null,
    days_in_month: 30,
    cartele_qty: 0,
    ...overrides,
  };
}

function store(month: string, siteCode: string): StoreStat {
  return {
    import_month: month,
    site_code: siteCode,
    locatie: `Store ${siteCode}`,
    firma: 'Mobiup',
    regional: 'RM',
    asm: 'ASM',
    total_vanzari: 0,
    qty_total: 0,
    nr_bonuri: 0,
    nr_agenti: 1,
    zile_active: 1,
    target: 0,
    proc_realizare_target: null,
    forecast_target_pct: null,
    medie_produs: null,
    promo_qty: 0,
    incentive_qty: 0,
    return_receipt_count: 0,
  };
}

function agent(month: string, siteCode: string, name: string): AgentStat {
  return {
    import_month: month,
    agent: name,
    site_code: siteCode,
    locatie: `Store ${siteCode}`,
    firma: 'Mobiup',
    regional: 'RM',
    asm: 'ASM',
    acc_qty_realizat: 0,
    nr_bonuri: 0,
    nr_bon2acc: 0,
    proc_bon2acc: null,
    total_vanzari: 0,
    zile_lucrate: 1,
    medie_zilnica: null,
    medie_produs: null,
    acc_focus_qty: 0,
    prc_focus_acc_qty: null,
    target: 0,
    proc_realizare_target: null,
    promo_qty: 0,
    incentive_qty: 0,
    return_receipt_count: 0,
  };
}

function response(month: string, overrides: Partial<DashboardAllResponse>): DashboardAllResponse {
  return {
    summary: summary(month, {}),
    agents: [],
    stores: [],
    regionals: [],
    asms: [],
    daily: [],
    daily_last_year: [],
    special_cards: [],
    period_comparison: null,
    category_mix: [],
    receipt_bucket_mix: [],
    focus_subcategory_mix: [],
    brand_mix: [],
    promo_incentive: {
      promo_qty: 0,
      promo_sales: 0,
      promo_impact: 0,
      incentive_qty: 0,
      incentive_value: 0,
      incentive_qualified_stores: 0,
      incentive_qualified_agents: 0,
      calculation_status: 'complete',
      calculation_warnings: [],
    },
    premium_glass: null,
    ...overrides,
  };
}

describe('aggregateDashboardDetails', () => {
  it('aggregates selected months without mixing trend-only history data', () => {
    const first = response('2026-05', {
      summary: summary('2026-05', {
        total_sales: 100,
        total_target: 200,
        forecast_sales: 120,
        total_quantity: 20,
        total_receipts: 10,
        proc_bon2acc: 50,
        prc_focus_acc_qty: 25,
        working_days: 5,
        cartele_qty: 2,
      }),
      stores: [store('2026-05', 'S1')],
      agents: [agent('2026-05', 'S1', 'Ana')],
      daily: [
        { sale_date: '2026-05-01', total_sales: 40, total_quantity: 8, receipt_count: 4 },
      ],
      daily_last_year: [
        { sale_date: '2025-05-01', total_sales: 35, total_quantity: 7, receipt_count: 3 },
      ],
    });
    const second = response('2026-06', {
      summary: summary('2026-06', {
        total_sales: 300,
        total_target: 300,
        forecast_sales: 360,
        total_quantity: 30,
        total_receipts: 30,
        proc_bon2acc: 100,
        prc_focus_acc_qty: 50,
        working_days: 10,
        cartele_qty: 3,
      }),
      stores: [store('2026-06', 'S1'), store('2026-06', 'S2')],
      agents: [agent('2026-06', 'S1', 'Ana'), agent('2026-06', 'S2', 'Ion')],
      daily: [
        { sale_date: '2026-06-01', total_sales: 60, total_quantity: 6, receipt_count: 6 },
        { sale_date: '2026-06-02', total_sales: 80, total_quantity: 8, receipt_count: 8 },
      ],
      daily_last_year: [
        { sale_date: '2025-06-01', total_sales: 55, total_quantity: 5, receipt_count: 5 },
      ],
    });

    const aggregate = aggregateDashboardDetails([first, second], ['2026-05', '2026-06']);

    expect(aggregate.summary).toMatchObject({
      month: '2026-05 - 2026-06',
      total_sales: 400,
      total_target: 500,
      target_progress_pct: 80,
      forecast_sales: 480,
      forecast_target_progress_pct: 96,
      total_quantity: 50,
      total_receipts: 40,
      proc_bon2acc: 87.5,
      prc_focus_acc_qty: 40,
      total_stores: 2,
      total_agents: 2,
      cartele_qty: 5,
    });
    expect(aggregate.dailySales).toEqual([
      { sale_date: 'zi-01', total_sales: 100, total_quantity: 14, receipt_count: 10 },
      { sale_date: 'zi-02', total_sales: 80, total_quantity: 8, receipt_count: 8 },
    ]);
    expect(aggregate.dailyLastYear).toEqual([]);
  });
});

describe('getDefaultHistoryMonth', () => {
  it('selects the latest available closed month', () => {
    expect(getDefaultHistoryMonth('2026-08', ['2026-08', '2026-06', '2026-07'])).toBe('2026-07');
  });

  it('handles the year boundary when the month list is not loaded yet', () => {
    expect(getDefaultHistoryMonth('2026-01', [])).toBe('2025-12');
  });
});
