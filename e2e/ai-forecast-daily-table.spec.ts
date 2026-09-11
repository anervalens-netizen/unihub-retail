import type { AiForecastResponse } from '../src/api/generated/runtime-types';
import { expect, test } from './fixtures';
import { retailWireForRequest, setupBaseMocks } from './helpers';

let cumulativeForecast = 0;
let cumulativeActual = 0;
const daily = Array.from({ length: 31 }, (_, index) => {
  const day = String(index + 1).padStart(2, '0');
  const forecast = 1000 + index * 10;
  const hasActual = index < 10;
  const actual = hasActual ? forecast - 50 : 0;
  cumulativeForecast += forecast;
  if (hasActual) cumulativeActual += actual;
  return {
    forecast_date: `2026-05-${day}`,
    forecast_sales: forecast,
    actual_sales: actual,
    has_actual: hasActual,
    cumulative_forecast: cumulativeForecast,
    cumulative_actual: cumulativeActual,
  };
});

const forecastResponse = {
  run: {
    id: 1,
    forecast_month: '2026-05',
    source_month: '2025-05',
    horizon: 'current_month',
    metric: 'sales_value',
    metadata: {},
    model_name: 'TimesFM 2.5',
    model_mode: 'timesfm',
    variant: 'xreg',
    generated_at: '2026-05-01T08:00:00Z',
  },
  summary: {
    forecast_month: '2026-05',
    source_month: '2025-05',
    days_in_month: 31,
    store_count: 2,
    forecast_sales: 35_650,
    expected_sales_to_date: 10_450,
    actual_sales: 9_950,
    delta_sales: -500,
    delta_pct: -4.78,
    days_elapsed: 10,
    actual_last_date: '2026-05-10',
  },
  daily,
  managers: [],
  stores: [],
} satisfies AiForecastResponse;

test('AI Forecast daily table is local, bounded and contained on mobile', async ({
  context,
  page,
}) => {
  await setupBaseMocks(context);
  let forecastRequests = 0;
  await context.route(/\/api\/ai-forecast\/current(?:\?|$)/, async (route) => {
    if (route.request().method() !== 'GET') return route.fallback();
    forecastRequests += 1;
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(retailWireForRequest(
        'GET',
        route.request().url(),
        forecastResponse,
      )),
    });
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Hub' }).first()).toBeVisible({ timeout: 15_000 });
  await page.getByRole('tab', { name: 'AI Forecast', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'AI Forecast — 2026-05' })).toBeVisible({ timeout: 15_000 });
  expect(forecastRequests).toBe(1);

  await page.getByRole('combobox', {
    name: 'Vizualizare Curba zilnica forecast',
  }).selectOption('table');

  const region = page.getByRole('region', {
    name: 'Date Curba zilnica forecast',
  });
  await expect(region).toBeVisible();
  const dimensions = await region.evaluate((element) => ({
    clientHeight: element.clientHeight,
    scrollHeight: element.scrollHeight,
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
  }));
  expect(dimensions.scrollHeight).toBeGreaterThan(dimensions.clientHeight);
  expect(dimensions.scrollWidth).toBeGreaterThan(dimensions.clientWidth);
  expect(forecastRequests).toBe(1);

  await region.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  expect(await region.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
  await expect(page.getByRole('rowheader', { name: '2026-05-31', exact: true })).toBeVisible();

  expect(await page.evaluate(() =>
    document.documentElement.scrollWidth <= document.documentElement.clientWidth,
  )).toBe(true);
});
