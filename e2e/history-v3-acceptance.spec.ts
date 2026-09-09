import type { BrowserContext, Page } from '@playwright/test';

import { expect, test } from './fixtures';
import {
  MOCK_DASHBOARD_ALL,
  retailWireForRequest,
  setupBaseMocks,
} from './helpers';

const HISTORY_DETAILS = {
  ...MOCK_DASHBOARD_ALL,
  summary: {
    ...MOCK_DASHBOARD_ALL.summary,
    month: '2026-04',
    total_sales: 2500,
    total_target: 3000,
    target_progress_pct: 83.33,
    forecast_sales: 2500,
    forecast_target_progress_pct: 83.33,
    total_quantity: 25,
    total_receipts: 20,
    total_stores: 2,
    total_agents: 1,
    working_days: 20,
    daily_average: 125,
    is_month_final: true,
    last_sale_date: '2026-04-30',
    imported_day_of_month: 30,
    days_in_month: 30,
  },
  daily: [
    { sale_date: '2026-04-01', total_sales: 1100, total_quantity: 11, receipt_count: 9 },
    { sale_date: '2026-04-02', total_sales: 1400, total_quantity: 14, receipt_count: 11 },
  ],
  daily_last_year: [],
  receipt_bucket_mix: [
    { bucket: '1', receipt_count: 12, share_pct: 60 },
    { bucket: '2', receipt_count: 8, share_pct: 40 },
  ],
  focus_subcategory_mix: [
    { category: 'Protectie', sales_total: 1500, quantity_total: 15, share_pct: 60 },
    { category: 'Incarcare', sales_total: 1000, quantity_total: 10, share_pct: 40 },
  ],
  category_mix: [
    { category: 'Huse', sales_total: 1500, quantity_total: 15, share_pct: 60 },
    { category: 'Incarcatoare', sales_total: 1000, quantity_total: 10, share_pct: 40 },
  ],
  brand_mix: [
    { brand: 'Apple', sales_total: 1500, quantity_total: 15, share_pct: 60 },
    { brand: 'Samsung', sales_total: 1000, quantity_total: 10, share_pct: 40 },
  ],
  regionals: [
    {
      regional: 'Nord', total_vanzari: 700, qty_total: 7, nr_bonuri: 6,
      nr_agenti: 1, zile_active: 10, target: 1000,
      proc_realizare_target: 70, forecast_target_pct: null,
      promo_qty: 1, promo_discount_value: 10, incentive_qty: 0,
      medie_zilnica: 70, medie_produs: 100, proc_bon2acc: 50,
      prc_focus_acc_qty: 42.86, return_receipt_count: 0,
    },
    {
      regional: 'Sud', total_vanzari: 1800, qty_total: 18, nr_bonuri: 14,
      nr_agenti: 0, zile_active: 10, target: 2000,
      proc_realizare_target: 90, forecast_target_pct: null,
      promo_qty: 2, promo_discount_value: 20, incentive_qty: 1,
      medie_zilnica: 180, medie_produs: 100, proc_bon2acc: 57.14,
      prc_focus_acc_qty: 38.89, return_receipt_count: 1,
    },
  ],
  stores: [
    {
      import_month: '2026-04', site_code: 'S-NORD', locatie: 'Promenada',
      firma: 'Mobiup', regional: 'Nord', asm: 'ASM Nord',
      total_vanzari: 700, qty_total: 7, nr_bonuri: 6, nr_agenti: 1,
      zile_active: 10, target: 1000, proc_realizare_target: 70,
      forecast_target_pct: null, medie_produs: 100, promo_qty: 1,
      promo_discount_value: 10, incentive_qty: 0, return_receipt_count: 0,
      proc_bon2acc: 50, prc_focus_acc_qty: 42.86,
    },
    {
      import_month: '2026-04', site_code: 'S-SUD', locatie: 'Baneasa',
      firma: 'MobiCell', regional: 'Sud', asm: 'ASM Sud',
      total_vanzari: 1800, qty_total: 18, nr_bonuri: 14, nr_agenti: 0,
      zile_active: 10, target: 2000, proc_realizare_target: 90,
      forecast_target_pct: null, medie_produs: 100, promo_qty: 2,
      promo_discount_value: 20, incentive_qty: 1, return_receipt_count: 1,
      proc_bon2acc: 57.14, prc_focus_acc_qty: 38.89,
    },
  ],
  agents: [
    {
      import_month: '2026-04', agent: 'Ana Popescu', site_code: 'S-NORD',
      locatie: 'Promenada', firma: 'Mobiup', regional: 'Nord', asm: 'ASM Nord',
      acc_qty_realizat: 7, nr_bonuri: 6, nr_bon2acc: 3, proc_bon2acc: 50,
      total_vanzari: 700, zile_lucrate: 10, medie_zilnica: 70,
      medie_produs: 100, acc_focus_qty: 3, prc_focus_acc_qty: 42.86,
      target: 1000, proc_realizare_target: 70, promo_qty: 1,
      promo_discount_value: 10, incentive_qty: 0, return_receipt_count: 0,
    },
  ],
};

const PERFORMANCE_DETAIL = {
  context_summary: null,
  daily: [],
  history: [],
  key: 'S-NORD',
  level: 'store',
  month: '2026-04',
  note: 'Date demonstrative pentru acceptanta V3.',
  peer_rows: [],
  risks: [],
  score: 78,
  score_breakdown: {
    bon2acc_points: 25,
    focus_points: 20,
    target_points: 33,
  },
  score_label: 'Bun',
  strengths: ['Target stabil'],
  subtitle: 'Mobiup · Nord',
  summary: {
    ...HISTORY_DETAILS.summary,
    month: '2026-04',
  },
  title: 'Promenada',
};

async function installHistoryMocks(context: BrowserContext) {
  await setupBaseMocks(context);

  await context.route(/\/api\/dashboard\/history-details-batch(?:\?|$)/, async (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    const payload = route.request().postDataJSON() as {
      queries?: Array<{ month?: string }>;
    };
    const queries = payload.queries?.length ? payload.queries : [{ month: '2026-04' }];
    const results = queries.map((query) => ({
      ...HISTORY_DETAILS,
      summary: {
        ...HISTORY_DETAILS.summary,
        month: query.month ?? '2026-04',
      },
    }));
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(retailWireForRequest(
        'POST',
        route.request().url(),
        { results },
      )),
    });
  });

  await context.route(/\/api\/dashboard\/performance-detail(?:\?|$)/, (route) => {
    if (route.request().method() !== 'GET') return route.fallback();
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(retailWireForRequest(
        'GET',
        route.request().url(),
        PERFORMANCE_DETAIL,
      )),
    });
  });
}

async function openHistory(page: Page) {
  await page.goto('/');
  const hubButton = page.getByRole('button', { name: 'Hub' }).first();
  await expect(hubButton).toBeVisible({ timeout: 15_000 });
  await hubButton.click();
  await page.getByRole('tab', { name: 'Istoric', exact: true }).click();
  await expect(page.getByRole('tab', { name: 'Istoric', exact: true }))
    .toHaveAttribute('aria-selected', 'true');
}

function dataGridCard(page: Page, title: 'RM' | 'Magazine') {
  return page.getByRole('heading', { name: title, exact: true, level: 3 })
    .locator('xpath=ancestor::section[1]');
}

async function expectNoPageOverflow(page: Page) {
  expect(await page.evaluate(() =>
    document.documentElement.scrollWidth <= document.documentElement.clientWidth,
  )).toBe(true);
}

test.describe('V3 Hub history acceptance', () => {
  test.beforeEach(async ({ context }) => {
    await installHistoryMocks(context);
  });

  test('proves DataGrid filters, multi-sort, columns, export, drill-down and legacy Agents on desktop', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await openHistory(page);

    const rmCard = dataGridCard(page, 'RM');
    const storeCard = dataGridCard(page, 'Magazine');
    const rmTable = rmCard.getByRole('table', { name: 'RM' });
    const storeTable = storeCard.getByRole('table', { name: 'Magazine' });
    const agentsHeading = page.getByRole('heading', { name: 'Agenti', exact: true });
    const agentsCard = agentsHeading.locator('xpath=ancestor::div[contains(@class, "glass")][1]');

    await expect(rmTable).toBeVisible();
    await expect(storeTable).toBeVisible();
    await expect(agentsCard.getByRole('table', { name: 'Agenti' })).toBeVisible();
    await expect(rmCard.getByTestId('data-grid-row')).toHaveCount(2);
    await expect(storeCard.getByTestId('data-grid-row')).toHaveCount(2);
    await expect(agentsCard).toContainText('Ana Popescu');

    const regionalFilter = rmCard.getByRole('searchbox', { name: 'Filtrează Regional' });
    await regionalFilter.fill('nord');
    await expect(rmCard.getByTestId('data-grid-row')).toHaveCount(1);
    await expect(rmCard.getByTestId('data-grid-row')).toContainText('Nord');
    await rmCard.getByRole('button', { name: 'Șterge filtrele (1)' }).click();

    await rmCard.getByRole('spinbutton', { name: 'Minim Target' }).fill('1500');
    await expect(rmCard.getByTestId('data-grid-row')).toHaveCount(1);
    await expect(rmCard.getByTestId('data-grid-row')).toContainText('Sud');
    await rmCard.getByRole('button', { name: 'Șterge filtrele (1)' }).click();

    await rmCard.getByRole('button', { name: 'Sortează după Regional' }).click();
    await rmCard.getByRole('button', { name: 'Sortează după Target' })
      .click({ modifiers: ['Shift'] });
    await expect(rmCard.getByTestId('data-grid-sort-priority-regional')).toHaveText('1');
    await expect(rmCard.getByTestId('data-grid-sort-priority-target')).toHaveText('2');

    await rmCard.getByText('Coloane', { exact: true }).click();
    await rmCard.getByRole('checkbox', { name: 'Afișează Target' }).uncheck();
    await expect(rmCard.getByTestId('data-grid-header-target')).toHaveCount(0);
    await rmCard.getByRole('button', { name: 'Resetează coloanele' }).click();
    await expect(rmCard.getByTestId('data-grid-header-target')).toBeVisible();
    await rmCard.getByText('Coloane', { exact: true }).click();

    await regionalFilter.fill('nord');
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      rmCard.getByRole('button', { name: 'Excel', exact: true }).click(),
    ]);
    expect(download.suggestedFilename()).toBe('hub_2026-04_istoric_rm.xlsx');
    await rmCard.getByRole('button', { name: 'Șterge filtrele (1)' }).click();

    const chartType = page.getByRole('combobox', { name: 'Tip grafic KPI' });
    await expect(chartType).toHaveValue('area');
    await chartType.selectOption('line');
    await expect(chartType).toHaveValue('line');
    await expectNoPageOverflow(page);

    await expect(storeCard.getByTitle('Mobiup')).toBeVisible();
    const detailRequestPromise = page.waitForRequest((request) =>
      new URL(request.url()).pathname === '/api/dashboard/performance-detail',
    );
    await storeTable.getByRole('button', { name: /Promenada/ }).click();
    const detailRequest = await detailRequestPromise;
    const detailParams = new URL(detailRequest.url()).searchParams;
    expect(detailParams.get('level')).toBe('store');
    expect(detailParams.get('key')).toBe('S-NORD');
    expect(detailParams.get('month')).toBe('2026-04');
    expect(detailParams.get('current_scope')).toBe('true');
    expect(detailParams.get('include_closed_stores')).toBe('false');
    const drawer = page.getByRole('dialog');
    await expect(drawer).toBeVisible();
    await expect(drawer).toContainText('Promenada');
    await drawer.getByRole('button', { name: 'Inchide', exact: true }).click();
    await expect(drawer).toHaveCount(0);
  });

  test('keeps the local KPI chart choice while moving between mobile history sections', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openHistory(page);

    const mobileSections = page.getByRole('tablist', { name: 'Conținut istoric mobil' });
    await mobileSections.getByRole('tab', { name: 'Trend', exact: true }).click();
    const chartType = page.getByRole('combobox', { name: 'Tip grafic KPI' });
    await expect(chartType).toBeVisible();
    await expect(chartType).toHaveValue('area');
    await chartType.selectOption('line');
    await expect(chartType).toHaveValue('line');

    await mobileSections.getByRole('tab', { name: 'Detalii', exact: true }).click();
    await expect(dataGridCard(page, 'RM')).toBeVisible();
    await expect(dataGridCard(page, 'Magazine')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Agenti', exact: true })).toBeVisible();
    await expect(page.locator('select[aria-label="Tip grafic KPI"]')).toHaveValue('line');

    await mobileSections.getByRole('tab', { name: 'Trend', exact: true }).click();
    await expect(page.getByRole('combobox', { name: 'Tip grafic KPI' })).toHaveValue('line');
    await expectNoPageOverflow(page);
  });
});
