import type { BrowserContext, Page } from '@playwright/test';

import { expect, test } from './fixtures';
import {
  MOCK_DASHBOARD_ALL,
  MOCK_DASHBOARD_HISTORY,
  MOCK_DASHBOARD_YEAR_HISTORY,
  MOCK_FILTER_OPTIONS,
  MOCK_MONTHS,
  mockAuthenticatedSession,
} from './helpers';

const VIEWPORTS = [
  { width: 1023, height: 768 },
  { width: 1024, height: 768 },
  { width: 1280, height: 800 },
  { width: 1366, height: 768 },
  { width: 1440, height: 900 },
  { width: 1600, height: 900 },
  { width: 1920, height: 1080 },
  { width: 2560, height: 1440 },
  { width: 390, height: 844 },
];

const HUB_ALL = {
  ...MOCK_DASHBOARD_ALL,
  daily: [
    { sale_date: '2026-05-01', total_sales: 18000, total_quantity: 55, receipt_count: 34 },
    { sale_date: '2026-05-02', total_sales: 22000, total_quantity: 71, receipt_count: 42 },
    { sale_date: '2026-05-03', total_sales: 20500, total_quantity: 66, receipt_count: 39 },
  ],
  daily_last_year: [
    { sale_date: '2025-05-01', total_sales: 16500, total_quantity: 50, receipt_count: 32 },
    { sale_date: '2025-05-02', total_sales: 19000, total_quantity: 60, receipt_count: 36 },
    { sale_date: '2025-05-03', total_sales: 18500, total_quantity: 59, receipt_count: 35 },
  ],
  receipt_bucket_mix: [
    { bucket: '0 accesorii', receipt_count: 120, share_pct: 40 },
    { bucket: '1 accesoriu', receipt_count: 105, share_pct: 35 },
    { bucket: '2+ accesorii', receipt_count: 75, share_pct: 25 },
  ],
  focus_subcategory_mix: [
    { category: 'Protectie', sales_total: 32000, quantity_total: 210, share_pct: 42 },
    { category: 'Incarcare', sales_total: 28000, quantity_total: 170, share_pct: 34 },
    { category: 'Audio', sales_total: 19500, quantity_total: 120, share_pct: 24 },
  ],
  category_mix: [
    { category: 'Huse si folii', sales_total: 54000, quantity_total: 240, share_pct: 43 },
    { category: 'Incarcatoare', sales_total: 41000, quantity_total: 165, share_pct: 33 },
    { category: 'Castile audio', sales_total: 30000, quantity_total: 95, share_pct: 24 },
  ],
  brand_mix: [
    { brand: 'Apple', sales_total: 48000, quantity_total: 150, share_pct: 38 },
    { brand: 'Samsung', sales_total: 44000, quantity_total: 180, share_pct: 35 },
    { brand: 'Xiaomi', sales_total: 34000, quantity_total: 170, share_pct: 27 },
  ],
  period_comparison: {
    current: {
      label: 'Curent', month: '2026-05', day_range: '01-06', total_sales: 150000,
      total_quantity: 500, total_receipts: 300, cartele_qty: 10, working_days: 6,
      daily_average: 25000, avg_receipt_value: 500, medie_produs: 300,
      proc_bon2acc: 60, prc_focus_acc_qty: 25,
    },
    previous: {
      label: 'Luna trecuta', month: '2026-04', day_range: '01-06', total_sales: 135000,
      total_quantity: 460, total_receipts: 280, cartele_qty: 8, working_days: 6,
      daily_average: 22500, avg_receipt_value: 482, medie_produs: 293,
      proc_bon2acc: 55, prc_focus_acc_qty: 22,
    },
    year_over_year: {
      label: 'Anul trecut', month: '2025-05', day_range: '01-06', total_sales: 120000,
      total_quantity: 420, total_receipts: 260, cartele_qty: 7, working_days: 6,
      daily_average: 20000, avg_receipt_value: 462, medie_produs: 286,
      proc_bon2acc: 52, prc_focus_acc_qty: 20,
    },
  },
  premium_glass: null,
  agents: [{
    import_month: '2026-05', agent: 'Ana Popescu', site_code: 'UNIRII', locatie: 'Magazin Unirii', firma: 'Firma 1',
    regional: 'Regional 1', asm: 'ASM 1', acc_qty_realizat: 120, nr_bonuri: 80, nr_bon2acc: 20, proc_bon2acc: 25,
    total_vanzari: 12000, zile_lucrate: 20, medie_zilnica: 600, medie_produs: 50, acc_focus_qty: 40,
    prc_focus_acc_qty: 33, target: 15000, proc_realizare_target: 80, promo_qty: 8, promo_discount_value: 20,
    incentive_qty: 2, return_receipt_count: 0,
  }],
  stores: [{
    import_month: '2026-05', site_code: 'UNIRII', locatie: 'Magazin Unirii', firma: 'Firma 1', regional: 'Regional 1', asm: 'ASM 1',
    total_vanzari: 12000, qty_total: 120, nr_bonuri: 80, nr_agenti: 1, zile_active: 20, target: 15000,
    proc_realizare_target: 80, forecast_target_pct: 85, medie_produs: 50, promo_qty: 8, promo_discount_value: 20,
    incentive_qty: 2, return_receipt_count: 0, proc_bon2acc: 25, prc_focus_acc_qty: 33,
  }],
  regionals: [{
    regional: 'Regional 1', total_vanzari: 12000, qty_total: 120, nr_bonuri: 80, nr_agenti: 1, zile_active: 20, target: 15000,
    proc_realizare_target: 80, forecast_target_pct: 85, promo_qty: 8, promo_discount_value: 20, incentive_qty: 2,
    medie_zilnica: 600, medie_produs: 50, proc_bon2acc: 25, prc_focus_acc_qty: 33, return_receipt_count: 0,
  }],
};

const VISIT_REPORT = {
  month: '2026-05', total_vizite: 1, magazine_unice: 1, avg_completion: 100,
  rows: [{ magazin: 'Magazin Unirii', asm: 'ASM 1', regional: 'Regional 1', firma: 'Firma 1', nr_vizite: 1,
    avg_completion: 100, curatenie_pct: 100, imagine_pct: 100, uniforma_pct: 100, afise_pct: 100,
    produse_promo_pct: 100, last_visit: '2026-05-06' }],
};
const VISIT_TREE = {
  team_leaders: [{ team_leader: 'Ana Popescu', nr_vizite: 1, months: [{ month: '2026-05', nr_vizite: 1,
    days: [{ date: '2026-05-06', nr_vizite: 1, visits: [{ id: 'visit-1', magazin: 'Magazin Unirii', locatie: 'Magazin Unirii', ora: '10:00', completion_pct: 100, firma: 'Firma 1', has_photos: false }] }] }] }],
};
const AGENTS_OVERVIEW = { active_count: 1, new_count: 0, reactivated_count: 0, left_this_month_count: 0, retention_rate: 100,
  total_unique_agents: 1, avg_seniority_months: 12, stability_rate: 100, churned_total_count: 0 };
const AGENTS_MOVEMENT = { history: [{ month: '2026-05', active: 1, new: 0, reactivated: 0, churned: 0, net_growth: 0, is_baseline: false }] };
const AGENTS_LIST = { items: [{ agent: 'Ana Popescu', store_name: 'Magazin Unirii', firma: 'Firma 1', active_in_month: true,
  is_new: false, is_reactivated: false, total_sales: 12000, total_quantity: 120, current_status: 'active' }] };
const AGENTS_COVERAGE = { active_stores_count: 1, uncovered_stores_count: 0, closed_stores_count: 0, modified_stores_count: 0,
  items: [{ site_code: 'UNIRII', locatie: 'Magazin Unirii', firma: 'Firma 1', regional: 'Regional 1', asm: 'ASM 1', status: 'covered',
    agent_count: 1, has_changes: false, previous_agent_count: 1, added_agents_count: 0, removed_agents_count: 0, change_reason: null }] };
const AGENT_PROFILE = { agent: 'Ana Popescu', first_seen_month: '2025-05', last_seen_month: '2026-05', active_months_count: 12,
  distinct_store_count: 1, distinct_firma_count: 1, distinct_regional_count: 1, distinct_asm_count: 1, months_since_last_seen: 0,
  reactivation_count: 0, longest_active_streak: 12, career_total_sales: 12000, career_total_quantity: 120,
  avg_monthly_sales: 1000, best_month: '2026-05', best_month_sales: 12000, current_status: 'active' };
const AGENT_HISTORY = { history: [{ month: '2026-05', total_sales: 12000, total_quantity: 120, receipt_count: 80, active_store_count: 1, is_active: true }] };
const GRILE = { month: '2026-05', total_sheets: 0, run: null, managers: [] };
const MANAGERS = [{ manager: 'Mihai Condorateanu', regional: 'Regional 1', month: '2026-05', reporting_available: true,
  active_stores: 1, active_agents: 1, previous_active_agents: 1, agent_delta: 0, agents_added: 0, agents_left: 0,
  stores_without_agents: 0, agents_per_store: 1, visits_available: true, total_visits: 1, visited_stores: 1,
  visit_coverage_pct: 100, avg_visit_completion: 100, checklist_score: 100, approved_pct: 100,
  stores: [{ site_code: 'UNIRII', locatie: 'Magazin Unirii', firma: 'Firma 1', active_agents: 1, previous_active_agents: 1, agent_delta: 0 }] }];
const ASM_SALARY = {
  asm: 'Mihai Condorateanu', month: '2026-05', is_forecast: false, forecast_factor: 1, fixed_salary: 0,
  zone: { total_sales: 0, total_target: 0, target_pct: null, forecast_sales: 0, forecast_target_pct: null,
    pct_used: null, commission: 0 },
  islands: [], islands_commission: 0,
  homogeneity: { islands_count: 0, qualifying_count: 0, qualifying_pct: 0, min_pct: 99, eligible: false,
    commission: 0 },
  acc_focus: { pct: 0, commission: 0 }, total_salary: 0,
};

const TARGET_CONTEXT = { latest_sales_month: '2026-05', suggested_target_month: '2026-06', suggested_cohort_month: '2026-05',
  suggested_total_target: 15000, default_min_floor: 1000, default_previous_month_floor_pct: 80, default_previous_month_cap_pct: 120,
  default_seasonality_years: 3, active_store_count: 1, regionals: [], can_finalize: false };
const PNL_OVERVIEW = {
  start_month: '2026-05', end_month: '2026-05', company: null, site_code: null, site_company: null, regional: null,
  summary: { revenue: 0, cogs: 0, gross_margin: 0, operating_costs: 0, ebitda: 0, depreciation: 0, ebit: 0 },
  monthly: [], categories: {}, stores: [], reconciliation: [],
};

async function jsonRoute(context: BrowserContext, method: string, pattern: RegExp, response: unknown) {
  await context.route(pattern, (route) => route.request().method() === method
    ? route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(response) })
    : route.fallback());
}

async function installRoutes(context: BrowserContext) {
  await mockAuthenticatedSession(context);
  await context.route('https://errors.unihub.ro/api/*/envelope/**', (route) =>
    route.fulfill({ status: 200, body: '' }));
  await jsonRoute(context, 'GET', /\/api\/filters\/months$/, MOCK_MONTHS);
  await jsonRoute(context, 'GET', /\/api\/filters\/options(?:\?|$)/, MOCK_FILTER_OPTIONS);
  await jsonRoute(context, 'GET', /\/api\/store-pnl\/permissions(?:\?|$)/, { can_view: true });
  await jsonRoute(context, 'GET', /\/api\/dashboard\/all(?:\?|$)/, HUB_ALL);
  await jsonRoute(context, 'GET', /\/api\/dashboard\/history(?:\?|$)/, MOCK_DASHBOARD_HISTORY);
  await jsonRoute(context, 'GET', /\/api\/dashboard\/history-year(?:\?|$)/, MOCK_DASHBOARD_YEAR_HISTORY);
  await jsonRoute(context, 'POST', /\/api\/dashboard\/history-details-batch$/, { results: [HUB_ALL] });
  await jsonRoute(context, 'GET', /\/api\/dashboard\/premium-glass(?:\?|$)/, { run: null, summary: null, managers: [], stores: [], daily: [] });
  await jsonRoute(context, 'GET', /\/api\/dashboard\/performance-detail(?:\?|$)/, { level: 'store', key: 'UNIRII', selected: null, peers: [] });
  await jsonRoute(context, 'GET', /\/api\/visits-report(?:\?|$)/, VISIT_REPORT);
  await jsonRoute(context, 'GET', /\/api\/visits-report\/tree(?:\?|$)/, VISIT_TREE);
  await jsonRoute(context, 'GET', /\/api\/visits-report\/filters(?:\?|$)/, { firms: ['Firma 1'], regionals: ['Regional 1'], stores: ['Magazin Unirii'] });
  await jsonRoute(context, 'GET', /\/api\/agents\/overview(?:\?|$)/, AGENTS_OVERVIEW);
  await jsonRoute(context, 'GET', /\/api\/agents\/movement(?:\?|$)/, AGENTS_MOVEMENT);
  await jsonRoute(context, 'GET', /\/api\/agents\/list(?:\?|$)/, AGENTS_LIST);
  await jsonRoute(context, 'GET', /\/api\/agents\/stores-coverage(?:\?|$)/, AGENTS_COVERAGE);
  await jsonRoute(context, 'GET', /\/api\/agents\/evaluation(?:\?|$)/, { months: [], firmas: [], asms: [], stores: [], rows: [] });
  await jsonRoute(context, 'GET', /\/api\/agents\/evaluation-v2(?:\?|$)/, { months: [], firmas: [], asms: [], stores: [], rows: [] });
  await jsonRoute(context, 'GET', /\/api\/store-pnl\/months$/, { months: [{ month: '2026-05', has_actual: true, has_estimated: false }] });
  await jsonRoute(context, 'GET', /\/api\/store-pnl\/stores(?:\?|$)/, { stores: [] });
  await jsonRoute(context, 'GET', /\/api\/store-pnl\/regions(?:\?|$)/, { regions: [] });
  await jsonRoute(context, 'GET', /\/api\/store-pnl\/annual(?:\?|$)/, { annual: [] });
  await jsonRoute(context, 'GET', /\/api\/store-pnl\/overview(?:\?|$)/, PNL_OVERVIEW);
  await jsonRoute(context, 'GET', /\/api\/agents\/profile(?:\?|$)/, AGENT_PROFILE);
  await jsonRoute(context, 'GET', /\/api\/agents\/history(?:\?|$)/, AGENT_HISTORY);
  await jsonRoute(context, 'GET', /\/api\/grile\/overview(?:\?|$)/, GRILE);
  await jsonRoute(context, 'GET', /\/api\/grile\/run-status(?:\?|$)/, { run: null });
  await jsonRoute(context, 'GET', /\/api\/grile\/monthly\/permissions$/, { can_run: false });
  await jsonRoute(context, 'GET', /\/api\/hr\/manager-overview(?:\?|$)/, MANAGERS);
  await jsonRoute(context, 'GET', /\/api\/hr\/asm-salary\/.+(?:\?|$)/, ASM_SALARY);
  await jsonRoute(context, 'GET', /\/api\/hr\/asm-performance(?:\?|$)/, []);
  await jsonRoute(context, 'GET', /\/api\/target-calculator\/context$/, TARGET_CONTEXT);
  await jsonRoute(context, 'GET', /\/api\/target-calculator\/scenarios$/, []);
  await jsonRoute(context, 'GET', /\/salarii\/overview(?:\?|$)/, { total: 0, by_company: [], record_count: 0, agent_count: 0, agent_month_count: 0, avg_agent_month_count: 0, avg_salary: 0, months_span: null });
  await jsonRoute(context, 'GET', /\/salarii\/evolution(?:\?|$)/, []);
  await jsonRoute(context, 'GET', /\/salarii\/summary(?:\?|$)/, { month: null, items: [] });
  await jsonRoute(context, 'GET', /\/salarii\/trend(?:\?|$)/, []);
  await jsonRoute(context, 'GET', /\/salarii\/agents\/summary(?:\?|$)/, { items: [], total: 0 });
  await jsonRoute(context, 'GET', /\/api\/stores$/, []);
  await jsonRoute(context, 'GET', /\/api\/crm\/scores(?:\?|$)/, []);
  await jsonRoute(context, 'GET', /\/api\/campaigns\/overview(?:\?|$)/, { snapshot: null, focus_products: [], promo_products: [], has_active_promotion: false, has_active_incentive: false });
  await jsonRoute(context, 'GET', /\/api\/campaigns\/history(?:\?|$)/, { history: [] });
}

async function assertNoPageOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
}

async function assertResponsiveHubLayout(page: Page, viewportWidth: number) {
  const summary = page.getByTestId('hub-summary-panel');
  const donutCards = page.getByTestId('hub-donut-grid').locator(':scope > div');
  const [summaryBox, firstDonutBox, secondDonutBox] = await Promise.all([
    summary.boundingBox(),
    donutCards.nth(0).boundingBox(),
    donutCards.nth(1).boundingBox(),
  ]);
  expect(summaryBox).not.toBeNull();
  expect(firstDonutBox).not.toBeNull();
  expect(secondDonutBox).not.toBeNull();

  if (viewportWidth >= 1500) {
    expect(Math.abs((summaryBox?.y ?? 0) - (firstDonutBox?.y ?? 0))).toBeLessThanOrEqual(8);
  } else {
    expect(firstDonutBox?.y ?? 0).toBeGreaterThanOrEqual(
      (summaryBox?.y ?? 0) + (summaryBox?.height ?? 0) - 4,
    );
  }

  if (viewportWidth >= 1280) {
    expect(Math.abs((firstDonutBox?.y ?? 0) - (secondDonutBox?.y ?? 0))).toBeLessThanOrEqual(8);
  } else {
    expect(secondDonutBox?.y ?? 0).toBeGreaterThan(
      (firstDonutBox?.y ?? 0) + (firstDonutBox?.height ?? 0) - 4,
    );
  }

  const comparisonChildren = page.getByTestId('hub-period-comparison-layout').locator(':scope > div');
  const chartChildren = page.getByTestId('hub-chart-layout').locator(':scope > div');
  const [overviewCardBox, comparisonCardBox, comparisonLayoutBox, chartLayoutBox, tableBox, deltasBox, dailyBox, secondaryChartsBox, periodTableFontSize, deltaValueFontSize, deltaCardAlignment] = await Promise.all([
    page.getByTestId('hub-overview-card').boundingBox(),
    page.getByTestId('hub-period-comparison-card').boundingBox(),
    page.getByTestId('hub-period-comparison-layout').boundingBox(),
    page.getByTestId('hub-chart-layout').boundingBox(),
    comparisonChildren.nth(0).boundingBox(),
    comparisonChildren.nth(1).boundingBox(),
    chartChildren.nth(0).boundingBox(),
    chartChildren.nth(1).boundingBox(),
    page.getByTestId('hub-period-table').evaluate((element) => parseFloat(getComputedStyle(element).fontSize)),
    page.getByTestId('hub-delta-value').first().evaluate((element) => parseFloat(getComputedStyle(element).fontSize)),
    page.getByTestId('hub-delta-card').first().evaluate((element) => {
      const styles = getComputedStyle(element);
      return [styles.alignItems, styles.justifyContent, styles.textAlign];
    }),
  ]);

  expect(Math.abs((overviewCardBox?.x ?? 0) - (comparisonCardBox?.x ?? 0))).toBeLessThanOrEqual(2);
  expect(Math.abs((overviewCardBox?.width ?? 0) - (comparisonCardBox?.width ?? 0))).toBeLessThanOrEqual(2);
  expect(Math.abs((chartLayoutBox?.width ?? 0) - (comparisonCardBox?.width ?? 0))).toBeLessThanOrEqual(2);
  expect(deltaValueFontSize).toBeGreaterThanOrEqual(20);
  expect(deltaCardAlignment).toEqual(['center', 'center', 'center']);

  if (viewportWidth >= 1500) {
    expect(comparisonLayoutBox?.width ?? 0).toBeLessThanOrEqual(1210);
    expect(periodTableFontSize).toBeGreaterThanOrEqual(17);
    expect(Math.abs((tableBox?.y ?? 0) - (deltasBox?.y ?? 0))).toBeLessThanOrEqual(8);
    expect(Math.abs((dailyBox?.y ?? 0) - (secondaryChartsBox?.y ?? 0))).toBeLessThanOrEqual(8);
    expect(Math.abs((tableBox?.height ?? 0) - (deltasBox?.height ?? 0))).toBeLessThanOrEqual(4);
    expect(Math.abs((dailyBox?.height ?? 0) - (secondaryChartsBox?.height ?? 0))).toBeLessThanOrEqual(4);
  } else {
    expect(deltasBox?.y ?? 0).toBeGreaterThanOrEqual((tableBox?.y ?? 0) + (tableBox?.height ?? 0) - 4);
    expect(secondaryChartsBox?.y ?? 0).toBeGreaterThanOrEqual((dailyBox?.y ?? 0) + (dailyBox?.height ?? 0) - 4);
  }

  expect(await page.locator('[data-testid="hub-overview-layout"], [data-testid="donut-legend-layout"], [data-testid="hub-period-comparison-layout"], [data-testid="hub-chart-layout"]').evaluateAll((elements) =>
    elements.every((element) => element.scrollWidth <= element.clientWidth + 1),
  )).toBe(true);
}

for (const viewport of VIEWPORTS) {
  test.describe(`Wave 3 responsive ${viewport.width}x${viewport.height}`, () => {
    test.use({ viewport });
    test.beforeEach(async ({ context }) => { await installRoutes(context); });

    test('keeps Hub, Agents and Management operator flows available without page overflow', async ({ page }) => {
      await page.goto('/');
      await expect(page.getByRole('button', { name: 'Hub' }).first()).toBeVisible({ timeout: 15000 });

      await page.getByRole('button', { name: 'Hub' }).first().click();
      await expect(page.locator('main h1')).toHaveCount(0);
      await expect(page.getByRole('tab', { name: 'Luna în curs', exact: true })).toHaveAttribute('aria-selected', 'true');
      await assertNoPageOverflow(page);
      await assertResponsiveHubLayout(page, viewport.width);
      const rmPanel = page.getByRole('heading', { name: 'RM — Regional Manager', exact: true })
        .locator('xpath=ancestor::div[contains(@class, "glass")][1]');
      const storesPanel = page.getByRole('heading', { name: 'Magazine', exact: true })
        .locator('xpath=ancestor::div[contains(@class, "glass")][1]');
      const agentsPanel = page.getByRole('heading', { name: /^Agenti -/ })
        .locator('xpath=ancestor::div[contains(@class, "glass")][1]');
      const [rmBox, storesBox, agentsBox] = await Promise.all([
        rmPanel.boundingBox(),
        storesPanel.boundingBox(),
        agentsPanel.boundingBox(),
      ]);
      expect(rmBox).not.toBeNull();
      expect(storesBox).not.toBeNull();
      expect(agentsBox).not.toBeNull();
      expect((storesBox?.y ?? 0)).toBeGreaterThan(rmBox?.y ?? 0);
      expect((agentsBox?.y ?? 0)).toBeGreaterThan(storesBox?.y ?? 0);
      expect(Math.abs((rmBox?.width ?? 0) - (storesBox?.width ?? 0))).toBeLessThanOrEqual(40);
      expect(Math.abs((storesBox?.width ?? 0) - (agentsBox?.width ?? 0))).toBeLessThanOrEqual(40);
      const agentsTable = agentsPanel.locator('table');
      await agentsTable.getByRole('button', { name: 'Agent', exact: true }).click();
      await expect(agentsTable).toBeVisible();
      const [download] = await Promise.all([
        page.waitForEvent('download'),
        agentsPanel.getByRole('button', { name: 'Excel', exact: true }).click(),
      ]);
      expect(download.suggestedFilename()).toMatch(/hub_2026-05_agenti\.xlsx$/);
      await page.getByRole('tab', { name: 'Istoric', exact: true }).click();
      await expect(page.getByRole('tab', { name: 'Istoric', exact: true })).toHaveAttribute('aria-selected', 'true');
      await assertNoPageOverflow(page);
      if (viewport.width >= 1024) {
        const historyRm = page.getByRole('heading', { name: 'RM', exact: true })
          .locator('xpath=ancestor::div[contains(@class, "glass")][1]');
        const historyStores = page.getByRole('heading', { name: 'Magazine', exact: true })
          .locator('xpath=ancestor::div[contains(@class, "glass")][1]');
        const historyAgents = page.getByRole('heading', { name: 'Agenti', exact: true })
          .locator('xpath=ancestor::div[contains(@class, "glass")][1]');
        const [historyRmBox, historyStoresBox, historyAgentsBox] = await Promise.all([
          historyRm.boundingBox(),
          historyStores.boundingBox(),
          historyAgents.boundingBox(),
        ]);
        expect((historyStoresBox?.y ?? 0)).toBeGreaterThan(historyRmBox?.y ?? 0);
        expect((historyAgentsBox?.y ?? 0)).toBeGreaterThan(historyStoresBox?.y ?? 0);
      }
      await page.getByRole('tab', { name: 'Vizite', exact: true }).click();
      await expect(page.getByRole('tab', { name: 'Vizite', exact: true })).toHaveAttribute('aria-selected', 'true');
      await expect(page.getByText('Vizite pe Team Leader', { exact: true })).toBeVisible();
      await assertNoPageOverflow(page);

      await page.getByRole('button', { name: 'Agenti' }).first().click();
      await expect(page.locator('main h1')).toHaveCount(0);
      await page.getByRole('tab', { name: 'Lista agenților', exact: true }).click();
      await page.getByRole('button', { name: /^Ana Popescu/ }).last().click();
      await expect(page.getByText('Profil agent', { exact: true })).toBeVisible();
      await page.locator('div.fixed.inset-0').getByRole('button').click();
      await expect(page.getByText('Profil agent', { exact: true })).toHaveCount(0);
      await page.getByRole('tab', { name: 'Acoperire magazine', exact: true }).click();
      await expect(page.getByText('Magazin Unirii', { exact: true }).first()).toBeVisible();
      await page.getByRole('tab', { name: 'Grile', exact: true }).click();
      await expect(page.getByText(/^Nicio rulare pentru luna selectată\./)).toBeVisible();
      await expect(page.getByRole('button', { name: 'Rulează verificare', exact: true })).toBeVisible();
      await assertNoPageOverflow(page);

      await page.getByRole('tab', { name: 'Analiză agenți', exact: true }).click();
      await expect(page.getByRole('tab', { name: 'Analiză agenți', exact: true })).toHaveAttribute('aria-selected', 'true');
      await page.getByRole('tab', { name: 'Prezentare generală', exact: true }).click();
      await page.getByRole('button', { name: 'Management' }).first().click();
      await expect(page.locator('main h1')).toHaveCount(0);
      await expect(page.getByRole('tab', { name: 'Manageri', exact: true })).toHaveAttribute('aria-selected', 'true');
      await expect(page.getByLabel('Luna overview manageri')).toBeVisible();
      const managerButton = page.getByRole('button', { name: /Mihai Condorateanu/ });
      await expect(managerButton).toBeVisible();
      await managerButton.click();
      await expect(managerButton).toHaveAttribute('aria-expanded', 'true');
      await page.getByRole('tab', { name: 'Calculator Target', exact: true }).click();
      await expect(page.getByRole('tab', { name: 'Calculator Target', exact: true })).toHaveAttribute('aria-selected', 'true');
      await page.getByRole('tab', { name: 'Salarii', exact: true }).click();
      await expect(page.getByRole('tab', { name: 'Salarii', exact: true })).toHaveAttribute('aria-selected', 'true');
      await page.getByRole('tab', { name: 'P&L', exact: true }).click();
      await expect(page.getByRole('tab', { name: 'P&L', exact: true })).toHaveAttribute('aria-selected', 'true');
      await assertNoPageOverflow(page);
    });
  });
}
