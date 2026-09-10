import { expect, test } from './fixtures';
import {
  MOCK_DASHBOARD_ALL,
  retailWireForRequest,
  setupBaseMocks,
} from './helpers';

const daily = Array.from({ length: 31 }, (_, index) => {
  const day = String(index + 1).padStart(2, '0');
  return {
    sale_date: `2026-05-${day}`,
    total_sales: 1000 + index,
    total_quantity: 10 + index,
    receipt_count: 5 + index,
  };
});

const dailyLastYear = daily.map((point) => ({
  ...point,
  sale_date: point.sale_date.replace('2026-', '2025-'),
  total_sales: point.total_sales - 100,
}));

test('current daily table is bounded, scrollable and contained on mobile', async ({
  context,
  page,
}) => {
  await setupBaseMocks(context);
  await context.route(/\/api\/dashboard\/all(?:\?|$)/, async (route) => {
    if (route.request().method() !== 'GET') return route.fallback();
    const response = {
      ...MOCK_DASHBOARD_ALL,
      summary: {
        ...MOCK_DASHBOARD_ALL.summary,
        month: '2026-05',
        is_month_final: true,
        last_sale_date: '2026-05-31',
        imported_day_of_month: 31,
        days_in_month: 31,
      },
      daily,
      daily_last_year: dailyLastYear,
    };
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(retailWireForRequest(
        'GET',
        route.request().url(),
        response,
      )),
    });
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('heading', {
    name: 'Evolutie zilnica pentru 2026-05',
  })).toBeVisible({ timeout: 15_000 });

  await page.getByRole('combobox', {
    name: 'Vizualizare evolutie zilnica',
  }).selectOption('table');

  const region = page.getByRole('region', {
    name: 'Date evolutie zilnica 2026-05',
  });
  await expect(region).toBeVisible();
  const dimensions = await region.evaluate((element) => ({
    clientHeight: element.clientHeight,
    scrollHeight: element.scrollHeight,
  }));
  expect(dimensions.scrollHeight).toBeGreaterThan(dimensions.clientHeight);

  await region.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  expect(await region.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
  await expect(page.getByRole('rowheader', { name: '31', exact: true })).toBeVisible();

  expect(await page.evaluate(() =>
    document.documentElement.scrollWidth <= document.documentElement.clientWidth,
  )).toBe(true);
});
