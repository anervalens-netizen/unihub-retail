import type { BrowserContext, Locator, Page } from '@playwright/test';

import { expect, test } from './fixtures';
import {
  MOCK_FILTER_OPTIONS,
  MOCK_MONTHS,
  mockApiRoute,
  mockAuthenticatedSession,
} from './helpers';
import type { CampaignsPromotionsResponse } from '../src/api/types';

const INCENTIVE_RESPONSE: CampaignsPromotionsResponse = {
  promotions: [{ key: 'promo-mai-2026', label: 'Promo Mai 2026' }],
  selected_promotion_key: 'promo-mai-2026',
  promo_title: 'Promo Mai 2026',
  promo_description: 'Campanie promo activa',
  promo_qty: 28,
  promo_total_qty: 28,
  promo_category_qty: 16,
  promo_impact: 240,
  promo_qualifying_bons: 12,
  promo_discounted_units: 28,
  promo_active_stores: 2,
  promo_active_agents: 2,
  incentive_title: 'Incentive Mai 2026',
  incentive_description: 'Bonus pentru produsele eligibile vandute.',
  incentive_qty: 105,
  incentive_sold_qty: 120,
  incentive_value: 400,
  incentive_potential: 460,
  incentive_qualified_qty: 105,
  incentive_qualified_stores: 2,
  incentive_qualified_stores_full: 1,
  incentive_qualified_stores_half: 1,
  incentive_qualified_agents: 2,
  incentive_qualified_agents_full: 1,
  incentive_qualified_agents_half: 1,
  incentive_product_count: 3,
  incentive_categories: [{ label: 'Accesorii', qty: 105, value: 400 }],
  incentive_periods: [{
    label: 'Mai',
    start_date: '2026-05-01',
    end_date: '2026-05-31',
    product_count: 3,
    reward_values: [4],
    qty: 105,
    potential: 460,
    value: 400,
  }],
  incentive_category_breakdown: [{ label: 'Accesorii', qty: 105, potential: 460, value: 400 }],
  has_active_promotion: true,
  promo_calculation_status: 'complete',
  incentive_calculation_status: 'complete',
  calculation_warnings: [],
  top_stores: [
    {
      store_name: 'Mobiup - Magazin Unirii',
      qty: 70,
      total_qty: 70,
      category_qty: 40,
      promo_bons: 8,
      incentive_value: 300,
      incentive_potential: 340,
      achievement: 1.1,
      firma: 'Mobiup',
    },
    {
      store_name: 'Mobicell - Magazin Central',
      qty: 35,
      total_qty: 50,
      category_qty: 20,
      promo_bons: 4,
      incentive_value: 100,
      incentive_potential: 120,
      achievement: 0.95,
      firma: 'Mobicell',
    },
  ],
  promo_agents: [],
  top_agents: [
    {
      agent_name: 'Ana Popescu',
      store_name: 'Mobiup - Magazin Unirii',
      firma: 'Mobiup',
      qty_sold: 70,
      val_incentive: 300,
      incentive_potential: 340,
      achievement: 1.1,
    },
    {
      agent_name: 'Bogdan Ionescu',
      store_name: 'Mobicell - Magazin Central',
      firma: 'Mobicell',
      qty_sold: 35,
      val_incentive: 100,
      incentive_potential: 120,
      achievement: 0.95,
    },
  ],
};

const EMPTY_INCENTIVE_RESPONSE: CampaignsPromotionsResponse = {
  ...INCENTIVE_RESPONSE,
  promotions: [],
  selected_promotion_key: '',
  promo_title: '',
  promo_description: '',
  has_active_promotion: false,
  incentive_title: '',
  incentive_description: '',
  incentive_qty: null,
  incentive_value: null,
  incentive_potential: null,
  incentive_qualified_qty: null,
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
  promo_calculation_status: 'not_configured',
  incentive_calculation_status: 'not_configured',
  calculation_warnings: [],
  top_stores: [],
  promo_agents: [],
  top_agents: [],
};

const INCENTIVE_ROUTE = /\/api\/campaigns\/promotions-incentives(?:\?|$)/;

async function setupIncentiveMocks(
  context: BrowserContext,
  response: CampaignsPromotionsResponse,
  requests: string[] = [],
) {
  await mockAuthenticatedSession(context);
  await mockApiRoute(context, 'GET', /\/api\/filters\/months$/, MOCK_MONTHS);
  await mockApiRoute(context, 'GET', /\/api\/filters\/options(?:\?|$)/, MOCK_FILTER_OPTIONS);
  await mockApiRoute(context, 'GET', '**/api/store-pnl/permissions*', { can_view: false });
  await context.route(INCENTIVE_ROUTE, (route) => {
    if (route.request().method() !== 'GET') return route.fallback();
    requests.push(route.request().url());
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(response),
    });
  });
}

async function openIncentive(page: Page) {
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Hub' }).first()).toBeVisible({ timeout: 15000 });
  await page.getByRole('button', { name: 'Focus' }).first().click();
  await page.getByRole('tab', { name: 'Incentive', exact: true }).click();
}

async function visibleCount(locator: Locator): Promise<number> {
  const count = await locator.count();
  let visible = 0;
  for (let index = 0; index < count; index += 1) {
    if (await locator.nth(index).isVisible()) visible += 1;
  }
  return visible;
}

function dataTable(page: Page, rowText: string): Locator {
  return page.locator('table').filter({ hasText: rowText }).first();
}

async function assertNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBe(0);
}

const DESKTOP_VIEWPORTS = [
  { width: 1023, height: 768 },
  { width: 1024, height: 768 },
  { width: 1366, height: 768 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
  { width: 2560, height: 1440 },
];

for (const viewport of DESKTOP_VIEWPORTS) {
  test.describe(`desktop shell ${viewport.width}x${viewport.height}`, () => {
    test.use({ viewport });

    test.beforeEach(async ({ context }) => {
      await setupIncentiveMocks(context, INCENTIVE_RESPONSE);
    });

    test('keeps the shell inside the viewport and switches at lg', async ({ page }) => {
      await openIncentive(page);
      await expect(page.getByText('Incentive Mai 2026', { exact: true })).toBeVisible();
      await assertNoHorizontalOverflow(page);

      const sidebar = page.locator('aside');
      const filterButtons = page.getByRole('button', { name: 'Filtre', exact: true });
      expect(await visibleCount(filterButtons)).toBe(1);

      if (viewport.width >= 1024) {
        await expect(sidebar).toBeVisible();
      } else {
        await expect(sidebar).toBeHidden();
        await expect(page.locator('.mobile-floating-filter')).toBeVisible();
      }
    });
  });
}

test.describe('desktop Incentive dashboard geometry', () => {
  test.use({ viewport: { width: 1920, height: 1080 } });

  test.beforeEach(async ({ context }) => {
    await setupIncentiveMocks(context, INCENTIVE_RESPONSE);
  });

  test('keeps the four existing KPIs in one row and the two tables in 6+6 columns', async ({ page }) => {
    await openIncentive(page);
    await expect(page.getByText('Ana Popescu', { exact: true })).toBeVisible();
    await expect(page.getByText('Magazin Unirii', { exact: true })).toBeVisible();

    const kpiLabels = [
      'unități vândute',
      'unități eligibile după promo',
      'unități în magazinele calificate',
      'incentive calculat acum',
    ];
    const kpiBoxes = await Promise.all(
      kpiLabels.map((label) => page.getByText(label, { exact: true }).boundingBox()),
    );
    expect(kpiBoxes.every((box) => box !== null)).toBe(true);
    const kpiTop = kpiBoxes.map((box) => box?.y ?? Number.NaN);
    expect(Math.max(...kpiTop) - Math.min(...kpiTop)).toBeLessThanOrEqual(6);

    const agentsTable = dataTable(page, 'Ana Popescu');
    const storesTable = dataTable(page, 'Magazin Unirii');
    await expect(agentsTable).toBeVisible();
    await expect(storesTable).toBeVisible();
    const [agentsBox, storesBox] = await Promise.all([
      agentsTable.boundingBox(),
      storesTable.boundingBox(),
    ]);
    expect(agentsBox).not.toBeNull();
    expect(storesBox).not.toBeNull();
    expect(Math.abs((agentsBox?.y ?? 0) - (storesBox?.y ?? 0))).toBeLessThanOrEqual(8);
    expect(Math.abs((agentsBox?.x ?? 0) - (storesBox?.x ?? 0))).toBeGreaterThan(8);
    expect(agentsBox?.width ?? 0).toBeGreaterThan(300);
    expect(storesBox?.width ?? 0).toBeGreaterThan(300);
  });

  test('preserves the existing filter, sort and Excel actions', async ({ page, context }) => {
    const requests: string[] = [];
    await setupIncentiveMocks(context, INCENTIVE_RESPONSE, requests);
    await openIncentive(page);
    await expect(page.getByText('Ana Popescu', { exact: true })).toBeVisible();
    expect(requests.some((url) => new URL(url).searchParams.get('view') === 'incentive')).toBe(true);

    const filterButtons = page.getByRole('button', { name: 'Filtre', exact: true });
    let visibleFilterIndex = -1;
    for (let index = 0; index < await filterButtons.count(); index += 1) {
      if (await filterButtons.nth(index).isVisible()) {
        visibleFilterIndex = index;
        break;
      }
    }
    expect(visibleFilterIndex).toBeGreaterThanOrEqual(0);
    const filterButton = filterButtons.nth(visibleFilterIndex);
    await filterButton.click();
    await expect(page.getByRole('heading', { name: 'Filtre active' })).toBeVisible();
    await page.getByRole('button', { name: 'Inchide' }).click();

    const agentsTable = dataTable(page, 'Ana Popescu');
    const rows = agentsTable.locator('tbody tr');
    const beforeSort = await rows.allTextContents();
    await agentsTable.getByRole('button', { name: 'Val Inc.', exact: true }).click();
    await expect.poll(async () => (await rows.allTextContents())[0]).not.toBe(beforeSort[0]);

    const [download] = await Promise.all([
      page.waitForEvent('download'),
      agentsTable.locator('xpath=../..').getByRole('button', { name: 'Excel', exact: true }).click(),
    ]);
    expect(download.suggestedFilename()).toContain('focus-incentive-agenti-2026-05');
  });
});

test.describe('desktop Incentive empty and error states', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('keeps an empty Incentive neutral and does not manufacture an alert', async ({ page, context }) => {
    await setupIncentiveMocks(context, EMPTY_INCENTIVE_RESPONSE);
    await openIncentive(page);
    await expect(page.getByText('Incentive', { exact: true }).last()).toBeVisible();
    await expect(page.getByRole('alert')).toHaveCount(0);
    await expect(page.getByText('Ana Popescu', { exact: true })).toHaveCount(0);
  });

  test('keeps a failed Incentive request visibly non-successful and retryable', async ({ page, context }) => {
    await mockAuthenticatedSession(context);
    await mockApiRoute(context, 'GET', /\/api\/filters\/months$/, MOCK_MONTHS);
    await mockApiRoute(context, 'GET', /\/api\/filters\/options(?:\?|$)/, MOCK_FILTER_OPTIONS);
    await mockApiRoute(context, 'GET', '**/api/store-pnl/permissions*', { can_view: false });
    await context.route(INCENTIVE_ROUTE, (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '{',
    }));

    await openIncentive(page);
    const message = page.getByText('Datele pentru campanii si focus nu au putut fi incarcate.', { exact: true });
    await expect(message).toBeVisible({ timeout: 15000 });
    await expect(message.locator('..')).toHaveClass(/text-amber-600/);
    await expect(message.locator('..')).not.toHaveClass(/text-emerald|bg-emerald/);
    await expect(page.getByRole('button', { name: 'Reincearca' })).toBeVisible();
  });
});

test.describe('mobile sentinel', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test.beforeEach(async ({ context }) => {
    await setupIncentiveMocks(context, INCENTIVE_RESPONSE);
  });

  test('keeps the mobile navigation and stacked Incentive panels unchanged', async ({ page }) => {
    await openIncentive(page);
    await expect(page.getByText('Ana Popescu', { exact: true })).toBeVisible();
    await assertNoHorizontalOverflow(page);
    await expect(page.locator('aside')).toBeHidden();
    await expect(page.locator('.mobile-floating-filter')).toBeVisible();

    const [agentsBox, storesBox] = await Promise.all([
      dataTable(page, 'Ana Popescu').boundingBox(),
      dataTable(page, 'Magazin Unirii').boundingBox(),
    ]);
    expect(agentsBox).not.toBeNull();
    expect(storesBox).not.toBeNull();
    expect(storesBox?.y ?? 0).toBeGreaterThan((agentsBox?.y ?? 0) + (agentsBox?.height ?? 0) - 8);
  });
});
