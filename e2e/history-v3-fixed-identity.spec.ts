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
    is_month_final: true,
  },
  daily_last_year: [],
  regionals: [
    {
      regional: 'Nord', total_vanzari: 700, qty_total: 7, nr_bonuri: 6,
      nr_agenti: 1, zile_active: 10, target: 1000,
      proc_realizare_target: 70, forecast_target_pct: null,
      promo_qty: 1, promo_discount_value: 10, incentive_qty: 0,
      medie_zilnica: 70, medie_produs: 100, proc_bon2acc: 50,
      prc_focus_acc_qty: 42.86, return_receipt_count: 0,
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
}

async function openHistoryDetails(page: Page) {
  await page.goto('/');
  const hubButton = page.getByRole('button', { name: 'Hub' }).first();
  await expect(hubButton).toBeVisible({ timeout: 15_000 });
  await hubButton.click();
  await page.getByRole('tab', { name: 'Istoric', exact: true }).click();
  await page.getByRole('tablist', { name: 'Conținut istoric mobil' })
    .getByRole('tab', { name: 'Detalii', exact: true }).click();
}

function dataGridCard(page: Page, title: 'RM' | 'Magazine' | 'Agenti') {
  return page.getByRole('heading', { name: title, exact: true, level: 3 })
    .locator('xpath=ancestor::section[1]');
}

test('keeps each History identity visible during real horizontal table scrolling', async ({
  context,
  page,
}) => {
  await installHistoryMocks(context);
  await page.setViewportSize({ width: 390, height: 844 });
  await openHistoryDetails(page);

  const rmCard = dataGridCard(page, 'RM');
  const storeCard = dataGridCard(page, 'Magazine');
  const agentCard = dataGridCard(page, 'Agenti');
  const identities = [
    rmCard.getByTestId('data-grid-header-regional'),
    storeCard.getByTestId('data-grid-header-locatie'),
    agentCard.getByTestId('data-grid-header-agent'),
  ];

  for (const identity of identities) {
    await expect(identity).toHaveCSS('position', 'sticky');
    await expect(identity).toHaveCSS('left', '0px');
  }

  const rmTable = rmCard.getByRole('table', { name: 'RM' });
  const scroller = rmTable.locator('xpath=..');
  const dimensions = await scroller.evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
  }));
  expect(dimensions.scrollWidth).toBeGreaterThan(dimensions.clientWidth);

  const header = rmCard.getByTestId('data-grid-header-regional');
  const bodyIdentity = rmCard.getByTestId('data-grid-row').first().getByRole('cell').first();
  await expect(bodyIdentity).toHaveCSS('position', 'sticky');
  await expect(bodyIdentity).toHaveCSS('left', '0px');

  const before = await header.boundingBox();
  expect(before).not.toBeNull();
  await scroller.evaluate((element) => {
    element.scrollLeft = element.scrollWidth;
  });
  expect(await scroller.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
  const after = await header.boundingBox();
  expect(after).not.toBeNull();
  expect(Math.abs((after?.x ?? 0) - (before?.x ?? 0))).toBeLessThanOrEqual(1);

  expect(await page.evaluate(() =>
    document.documentElement.scrollWidth <= document.documentElement.clientWidth,
  )).toBe(true);
});
