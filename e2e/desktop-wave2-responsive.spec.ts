import type { BrowserContext, Page } from '@playwright/test';

import { expect, test } from './fixtures';
import { mockAuthenticatedSession } from './helpers';
import type { CampaignsPromotionsResponse } from '../src/api/generated/runtime-types';

const MONTHS = ['2026-05', '2026-04', '2026-03'];
const FILTER_OPTIONS = {
  firme: ['Mobiup', 'Mobicell'],
  regionali: ['Nord'],
  asmi: ['ASM Nord'],
  magazine: [{ site_code: 'UNIRII', locatie: 'Magazin Unirii', firma: 'Mobiup', regional: 'Nord', asm: 'ASM Nord' }],
  agenti: [{ agent: 'Ana Popescu', site_code: 'UNIRII', locatie: 'Magazin Unirii', firma: 'Mobiup', regional: 'Nord', asm: 'ASM Nord' }],
};
const DASHBOARD_ALL = { summary: { month: "2026-05", total_sales: 150000, total_target: 200000, target_progress_pct: 75, forecast_sales: 180000, forecast_target_progress_pct: 90, total_quantity: 500, total_receipts: 300, proc_bon2acc: 60, prc_focus_acc_qty: 25, total_stores: 1, total_agents: 2, working_days: 22, daily_average: 6818, is_month_final: false, last_sale_date: "2026-05-06", imported_day_of_month: 6, days_in_month: 31, cartele_qty: 10 }, agents: [], stores: [], daily: [], special_cards: [], period_comparison: null, category_mix: [], receipt_bucket_mix: [], focus_subcategory_mix: [], brand_mix: [], promo_incentive: { promo_qty: 0, promo_impact: 0, incentive_qty: 0, incentive_value: 0 }, regionals: [], asms: [] };
const EXPORT_CATALOG = {
  datasets: [{ key: 'agents', label: 'Agenți', description: 'Date agenți', dimensions: [{ key: 'agent', label: 'Agent', type: 'text', group: 'Identificare' }] }],
  metrics: [{ key: 'total_sales', label: 'Vânzări', type: 'currency', group: 'KPI' }],
  monthly_metrics: [{ key: 'monthly_sales', label: 'Vânzări lunare', type: 'currency', group: 'Lunar' }],
  daily_metrics: [{ key: 'daily_sales', label: 'Vânzări zilnice', type: 'currency', group: 'Zilnic' }],
  comparison_levels: [{ key: 'general', label: 'General' }],
};
const IMPORT_HISTORY = [{
  id: 'import-2026-05', import_month: '2026-05', filename: 'vanzari_mai.xlsx', status: 'completed',
  rows_imported: 250, is_month_final: true, created_at: '2026-05-06T10:00:00', duration_seconds: 12.4,
  coverage_report: { active_store_coverage_pct: 100, missing_active_store_count: 0 },
}];

const PNL_OVERVIEW = {
  start_month: '2026-04', end_month: '2026-05', company: null, site_code: null, site_company: null, regional: null,
  summary: { revenue: 120000, cogs: 30000, gross_margin: 90000, operating_costs: 50000, ebitda: 40000, depreciation: 5000, ebit: 35000 },
  monthly: [
    { month: '2026-04', is_estimated: false, revenue: 50000, cogs: 12000, gross_margin: 38000, operating_costs: 22000, ebitda: 16000, depreciation: 2500, ebit: 13500 },
    { month: '2026-05', is_estimated: true, revenue: 70000, cogs: 18000, gross_margin: 52000, operating_costs: 28000, ebitda: 24000, depreciation: 2500, ebit: 21500 },
  ],
  categories: { v1: 70000, v11: 50000, c1: -30000, c3: -20000, a1: -5000 },
  stores: [{ company: 'Mobiup', site_code: 'UNIRII', source_site_code: 'UNIRII', location: 'Magazin Unirii', regional: 'Nord', has_estimates: true, revenue: 120000, cogs: 30000, gross_margin: 90000, operating_costs: 50000, ebitda: 40000, depreciation: 5000, ebit: 35000 }],
  reconciliation: [{ month: '2026-05', pnl_revenue: 70000, retail_sales_gross: 90000, retail_sales_net: 75000, difference_to_net: 12000, pnl_to_net_sales_pct: 93.3 }],
};
const PNL_ANNUAL = [{ year: '2026', store_count: 1, month_count: 2, is_estimated: true, revenue: 120000, cogs: 30000, gross_margin: 90000, operating_costs: 50000, ebitda: 40000, depreciation: 5000, ebit: 35000 }];

const PROMO_RESPONSE: CampaignsPromotionsResponse = {
  promotions: [{ key: 'promo-mai-2026', label: 'Promo Mai 2026' }, { key: 'promo-iunie-2026', label: 'Promo Iunie 2026' }],
  selected_promotion_key: 'promo-mai-2026', promo_title: 'Promo Mai 2026', promo_description: 'Campanie promo cu perioadă parțial verificată.',
  promo_qty: 28, promo_total_qty: 28, promo_category_qty: 16, promo_impact: 240, promo_qualifying_bons: 12, promo_discounted_units: 28, promo_discount_value: 240, promo_active_stores: 1, promo_active_agents: 1,
  incentive_title: 'Incentive Mai 2026', incentive_description: 'Bonus pentru produsele eligibile.', incentive_qty: 20, incentive_sold_qty: 28, incentive_value: 100, incentive_potential: 120, incentive_qualified_qty: 20, incentive_qualified_stores: 1, incentive_qualified_stores_full: 1, incentive_qualified_stores_half: 0, incentive_qualified_agents: 1, incentive_qualified_agents_full: 1, incentive_qualified_agents_half: 0, incentive_product_count: 2,
  incentive_categories: [{ label: 'Accesorii', qty: 20, value: 100 }], incentive_periods: [{ label: 'Mai', start_date: '2026-05-01', end_date: '2026-05-31', product_count: 2, reward_values: [5], qty: 20, potential: 120, value: 100 }], incentive_category_breakdown: [{ label: 'Accesorii', qty: 20, qualified_qty: 16, potential: 120, value: 100 }],
  has_active_promotion: true, promo_calculation_status: 'partial', incentive_calculation_status: 'complete', calculation_warnings: ['Raportul promo este disponibil doar până la ziua 20.'],
  top_stores: [{ store_name: 'Mobiup - Magazin Unirii', qty: 28, total_qty: 28, category_qty: 16, promo_bons: 12, incentive_value: 100, incentive_potential: 120, achievement: 1, firma: 'Mobiup' }],
  promo_agents: [{ agent_name: 'Ana Popescu', store_name: 'Mobiup - Magazin Unirii', firma: 'Mobiup', promo_bons: 12 }],
  top_agents: [{ agent_name: 'Ana Popescu', store_name: 'Mobiup - Magazin Unirii', firma: 'Mobiup', qty_sold: 28, val_incentive: 100, incentive_potential: 120, achievement: 1 }],
};

const VIEWPORTS = [
  { width: 1023, height: 768 }, { width: 1024, height: 768 }, { width: 1366, height: 768 },
  { width: 1440, height: 900 }, { width: 1920, height: 1080 }, { width: 2560, height: 1440 }, { width: 390, height: 844 },
];

async function jsonRoute(context: BrowserContext, method: string, pattern: RegExp, response: unknown) {
  await context.route(pattern, (route) => route.request().method() === method
    ? route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(response) })
    : route.fallback());
}

async function setScreen(context: BrowserContext) {
  await mockAuthenticatedSession(context);
  await jsonRoute(context, "GET", /\/api\/filters\/months$/, MONTHS);
  await jsonRoute(context, "GET", /\/api\/filters\/options(?:\?|$)/, FILTER_OPTIONS);
  await jsonRoute(context, "GET", /\/api\/store-pnl\/permissions$/, { can_view: true });
  await jsonRoute(context, "GET", /\/api\/dashboard\/all(?:\?|$)/, DASHBOARD_ALL);
  await jsonRoute(context, "GET", /\/api\/dashboard\/history(?:\?|$)/, { months: [], rows: [] });
  await jsonRoute(context, "GET", /\/api\/hr\/manager-overview(?:\?|$)/, []);
}

async function installPnlRoutes(context: BrowserContext) {
  await setScreen(context);
  await jsonRoute(context, 'GET', /\/api\/store-pnl\/months$/, { months: [{ month: '2026-04', has_actual: true, has_estimated: false }, { month: '2026-05', has_actual: false, has_estimated: true }] });
  await jsonRoute(context, 'GET', /\/api\/store-pnl\/stores(?:\?|$)/, { stores: [{ company_name: 'Mobiup', site_code: 'UNIRII', location: 'Magazin Unirii', regional: 'Nord', scope_company: 'Mobiup' }] });
  await jsonRoute(context, 'GET', /\/api\/store-pnl\/regions(?:\?|$)/, { regions: ['Nord'] });
  await jsonRoute(context, 'GET', /\/api\/store-pnl\/annual(?:\?|$)/, { annual: PNL_ANNUAL });
  await jsonRoute(context, 'GET', /\/api\/store-pnl\/overview(?:\?|$)/, PNL_OVERVIEW);
}

async function installSettingsRoutes(context: BrowserContext) {
  await setScreen(context);
  await jsonRoute(context, 'GET', /\/api\/import\/history$/, IMPORT_HISTORY);
  await jsonRoute(context, 'GET', /\/api\/exports\/catalog$/, EXPORT_CATALOG);
  await jsonRoute(context, 'POST', /\/api\/exports\/preview$/, {
    columns: [{ key: 'agent', label: 'Agent', type: 'text', group: 'Identificare' }],
    rows: [{ agent: 'Ana Popescu' }],
    total_rows: 1,
    truncated: false,
  });
  await context.route(/\/api\/exports\/download$/, (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    return route.fulfill({
      status: 200,
      headers: {
        'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'Content-Disposition': 'attachment; filename="wave2-export.xlsx"',
      },
      body: 'wave2-xlsx',
    });
  });
  await jsonRoute(context, 'POST', /\/api\/import\/sales$/, { job_id: 'job-sales', status: 'queued' });
  await jsonRoute(context, 'POST', /\/api\/import\/promo-actuals$/, { status: 'ok', import_month: '2026-05', rows_imported: 1 });
  await jsonRoute(context, 'POST', /\/api\/import\/erp-reconciliation$/, { status: 'ok', rows_imported: 1 });
}

async function installPromoRoutes(context: BrowserContext) {
  await setScreen(context);
  await context.route(/\/api\/campaigns\/promotions-incentives(?:\?|$)/, (route) => {
    if (route.request().method() !== 'GET') return route.fallback();
    const selected = new URL(route.request().url()).searchParams.get('promotion_key') ?? 'promo-mai-2026';
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ...PROMO_RESPONSE, selected_promotion_key: selected, promo_title: selected === 'promo-iunie-2026' ? 'Promo Iunie 2026' : 'Promo Mai 2026' }) });
  });
}

async function assertNoHorizontalOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);
}

for (const viewport of VIEWPORTS) {
  test.describe('Wave 2 P&L responsive ' + viewport.width + 'x' + viewport.height, () => {
    test.use({ viewport });
    test.beforeEach(async ({ context }) => { await installPnlRoutes(context); });

    test('keeps P&L readable without page overflow', async ({ page }) => {
      await page.goto('/');
      await page.getByRole('button', { name: 'Management' }).first().click();
      await page.getByRole('tab', { name: 'P&L' }).click();
      await expect(page.getByRole('heading', { name: 'Profit & Loss' })).toBeVisible();
      await expect(page.getByText('Intervalul conține luni estimate.')).toBeVisible();
      await expect(page.getByText('Reconciliere de verificat')).toBeVisible();
      await assertNoHorizontalOverflow(page);
      const filters = page.locator('select');
      await expect(filters).toHaveCount(5);
      await filters.nth(0).selectOption('2026-04');
      if (viewport.width >= 1280) {
        const monthly = await page.getByRole('heading', { name: 'Evoluție lunară' }).locator('..').boundingBox();
        const annual = await page.getByRole('heading', { name: 'Evoluție anuală' }).locator('..').boundingBox();
        expect(monthly).not.toBeNull();
        expect(annual).not.toBeNull();
        expect(Math.abs((monthly?.y ?? 0) - (annual?.y ?? 0))).toBeLessThanOrEqual(12);
        expect(Math.abs((monthly?.x ?? 0) - (annual?.x ?? 0))).toBeGreaterThan(200);
        await expect(page.locator('[class*="xl:grid-cols-5"]').first()).toBeVisible();
      }
    });
  });
}

for (const viewport of VIEWPORTS) {
  test.describe('Wave 2 Settings + Promo responsive ' + viewport.width + 'x' + viewport.height, () => {
    test.use({ viewport });
    test.beforeEach(async ({ context }) => {
      await installSettingsRoutes(context);
      await context.route(/\/api\/campaigns\/promotions-incentives(?:\?|$)/, (route) => {
        if (route.request().method() !== 'GET') return route.fallback();
        const selected = new URL(route.request().url()).searchParams.get('promotion_key') ?? 'promo-mai-2026';
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ...PROMO_RESPONSE, selected_promotion_key: selected, promo_title: selected === 'promo-iunie-2026' ? 'Promo Iunie 2026' : 'Promo Mai 2026' }) });
      });
    });
    test('keeps Settings and Promo operator surfaces responsive', async ({ page }) => {
      await page.goto('/');
      await page.getByRole('button', { name: /Setari/i }).first().click();
      const settingsIntro = page.getByRole('heading', { name: 'Setări', exact: true, level: 1 });
      if (viewport.width < 1024) {
        await expect(settingsIntro).toBeVisible();
      } else {
        await expect(settingsIntro).toHaveCount(0);
      }
      await expect(page.getByRole('heading', { name: 'Import fișier vânzări' })).toBeVisible();
      await expect(page.getByRole('heading', { name: 'Verificare raport detaliat ERP' })).toBeVisible();
      await expect(page.getByRole('heading', { name: 'Import tabel promo firmă' })).toBeVisible();
      await expect(page.getByRole('heading', { name: 'Istoric importuri' })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Validează fișierul' })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Verifică raportul fără import' })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Importă raport promo' })).toBeVisible();
      await expect(page.getByText('Coverage magazine active 100%')).toBeVisible();
      const sales = await page.getByRole('heading', { name: 'Import fișier vânzări' }).locator('..').locator('..').boundingBox();
      const erp = await page.getByRole('heading', { name: 'Verificare raport detaliat ERP' }).locator('..').locator('..').boundingBox();
      expect(sales).not.toBeNull();
      expect(erp).not.toBeNull();
      if (viewport.width >= 1280) expect(Math.abs((sales?.x ?? 0) - (erp?.x ?? 0))).toBeGreaterThan(200);
      else expect(Math.abs((sales?.y ?? 0) - (erp?.y ?? 0))).toBeGreaterThan(20);
      await page.getByRole('button', { name: 'Focus' }).first().click();
      const focusIntro = page.getByRole('heading', { name: 'Focus', exact: true, level: 1 });
      if (viewport.width < 1024) {
        await expect(focusIntro).toBeVisible();
      } else {
        await expect(focusIntro).toHaveCount(0);
      }
      await page.getByRole('tab', { name: 'Promo', exact: true }).click();
      await expect(page.getByRole('status')).toContainText('Raportul promo este disponibil');
      await expect(page.getByRole('status')).toHaveClass(/bg-amber-50/);
      const promoStores = page.locator('main span').filter({ hasText: 'Magazine' });
      const promoAgents = page.locator('main span').filter({ hasText: 'Agenti' });
      await expect(promoStores).toBeVisible();
      await expect(promoAgents).toBeVisible();
      const storesBox = await promoStores.locator('..').locator('..').boundingBox();
      const agentsBox = await promoAgents.locator('..').locator('..').boundingBox();
      expect(storesBox).not.toBeNull();
      expect(agentsBox).not.toBeNull();
      if (viewport.width >= 1280) {
        expect(Math.abs((storesBox?.x ?? 0) - (agentsBox?.x ?? 0))).toBeGreaterThan(200);
        expect(Math.abs((storesBox?.y ?? 0) - (agentsBox?.y ?? 0))).toBeLessThanOrEqual(16);
      } else expect(Math.abs((storesBox?.y ?? 0) - (agentsBox?.y ?? 0))).toBeGreaterThan(20);
      await expect(page.getByRole('button', { name: 'Excel' }).first()).toBeVisible();
      await assertNoHorizontalOverflow(page);
    });
  });
}

test.describe('Wave 2 Settings desktop workflow', () => {
  test.use({ viewport: { width: 1920, height: 1080 } });
  test.beforeEach(async ({ context }) => { await installSettingsRoutes(context); });

  test('uses two desktop columns while preserving import operator flow', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: /Setari/i }).first().click();
    await expect(page.getByRole('heading', { name: 'Setări', exact: true, level: 1 })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Import fișier vânzări' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Verificare raport detaliat ERP' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Import tabel promo firmă' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Istoric importuri' })).toBeVisible();
    await expect(page.getByText('Coverage magazine active 100%')).toBeVisible();
    await assertNoHorizontalOverflow(page);
    const sales = await page.getByRole('heading', { name: 'Import fișier vânzări' }).locator('..').locator('..').boundingBox();
    const erp = await page.getByRole('heading', { name: 'Verificare raport detaliat ERP' }).locator('..').locator('..').boundingBox();
    expect(sales).not.toBeNull();
    expect(erp).not.toBeNull();
    expect(Math.abs((sales?.x ?? 0) - (erp?.x ?? 0))).toBeGreaterThan(200);
  });

  test('keeps Export stepper 1 to 4 unique and usable', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: /Setari/i }).first().click();
    await page.getByRole('tab', { name: 'Exporturi' }).click();
    const actions = page.locator('.export-mobile-actions');
    await expect(page.getByRole('navigation', { name: 'Pași export Excel' })).toBeVisible();
    await expect(actions.getByText('Pasul 1 din 4')).toBeVisible();
    await actions.getByRole('button', { name: 'Continuă' }).click();
    await expect(actions.getByText('Pasul 2 din 4')).toBeVisible();
    await expect(actions.getByRole('button', { name: 'Continuă' })).toBeEnabled();
    await actions.getByRole('button', { name: 'Continuă' }).click();
    await expect(actions.getByText('Pasul 3 din 4')).toBeVisible();
    await actions.getByRole('button', { name: 'Continuă' }).click();
    await expect(actions.getByText('Pasul 4 din 4')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Preview si export' })).toBeVisible();
    await page.getByRole('button', { name: 'Preview', exact: true }).click();
    await expect(page.getByText('1 randuri')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Export Excel' })).toBeEnabled();
    const exportDownload = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Export Excel' }).click();
    expect((await exportDownload).suggestedFilename()).toBe('export_retail_agents_2026-05.xlsx');
    await expect(actions.getByRole('button', { name: 'Înapoi' })).toBeEnabled();
    await assertNoHorizontalOverflow(page);
  });
});

test.describe('Wave 2 Promo operator flow', () => {
  test.use({ viewport: { width: 1920, height: 1080 } });
  test.beforeEach(async ({ context }) => { await installPromoRoutes(context); });

  test('keeps partial status amber and preserves selection, sort and Excel action', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'Focus' }).first().click();
    await page.getByRole('tab', { name: 'Promo', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Promo Mai 2026', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Promo Mai 2026' })).toBeVisible();
    const warning = page.getByRole('status');
    await expect(warning).toContainText('Raportul promo este disponibil');
    await expect(warning).toHaveClass(/bg-amber-50/);
    await page.getByRole('button', { name: 'Promo Iunie 2026' }).click();
    await expect(page.getByRole('heading', { name: 'Promo Iunie 2026', exact: true })).toBeVisible();
    await page.getByRole('button', { name: /Bonuri/ }).first().click();
    const promoDownload = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Excel' }).first().click();
    expect((await promoDownload).suggestedFilename()).toMatch(/focus-promo-magazine-.*\.xlsx$/);
    await assertNoHorizontalOverflow(page);
  });
});
