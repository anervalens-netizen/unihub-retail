import { expect, test } from './fixtures';
import { MOCK_DASHBOARD_ALL, mockApiRoute, setupBaseMocks } from './helpers';

test.describe('E2E: responsive mobile', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test.beforeEach(async ({ context }) => {
    await setupBaseMocks(context);
    await mockApiRoute(context, 'GET', /\/api\/agents\/evaluation-v2/, {
      months: [], firmas: [], asms: [], stores: [], rows: [],
    });
    await mockApiRoute(context, 'GET', /\/api\/agents\/evaluation\b/, {
      months: [], firmas: [], asms: [], stores: [], rows: [],
    });
    await mockApiRoute(context, 'GET', /\/api\/exports\/catalog/, {
      datasets: [{ key: 'agents', label: 'Agenți', description: 'Date agenți', dimensions: [{ key: 'agent', label: 'Agent', type: 'text', group: 'Identificare' }] }],
      metrics: [{ key: 'total_sales', label: 'Vânzări', type: 'currency', group: 'KPI' }],
      monthly_metrics: [],
      daily_metrics: [],
      comparison_levels: [{ key: 'general', label: 'General' }],
    });
  });

  test('uses a subtle floating filter and keeps the page inside the viewport', async ({ page }) => {
    await page.goto('/');
    const filterButton = page.getByRole('button', { name: 'Filtre' }).first();
    await expect(filterButton).toBeVisible();
    const box = await filterButton.boundingBox();
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBe(0);

    await filterButton.click();
    await expect(page.getByRole('heading', { name: 'Filtre active' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Inchide' })).toBeVisible();
  });

  test('keeps interactive Hub breakdown rows compact', async ({ page }) => {
    const regionals = Array.from({ length: 6 }, (_, index) => ({
      regional: `Regional ${index + 1}`,
      target: 100000 - index * 1000,
      total_vanzari: 50000 - index * 1000,
      proc_realizare_target: 50,
      forecast_target_pct: 95,
      qty_total: 100,
      nr_bonuri: 50,
      proc_bon2acc: 20,
      prc_focus_acc_qty: 10,
    }));
    const stores = Array.from({ length: 12 }, (_, index) => ({
      site_code: `S${index + 1}`,
      locatie: `Magazin ${index + 1}`,
      firma: index % 2 === 0 ? 'Mobiup' : 'Mobicell',
      target: 50000,
      total_vanzari: 25000,
      proc_realizare_target: 50,
      forecast_target_pct: 100,
      qty_total: 50,
      nr_bonuri: 25,
      return_receipt_count: 0,
      nr_agenti: 2,
      zile_active: 10,
    }));
    await page.route(/\/api\/dashboard\/all(?:\?|$)/, (route) => {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ...MOCK_DASHBOARD_ALL,
          regionals,
          stores,
        }),
      });
    });

    await page.goto('/');
    const regionalTable = page.locator('.compact-data-table').first();
    await expect(regionalTable.locator('tbody tr')).toHaveCount(6);

    const measurements = await regionalTable.evaluate((table) => {
      const rows = [...table.querySelectorAll('tbody tr')];
      const detailButton = table.querySelector<HTMLButtonElement>('tbody button');
      return {
        rowHeights: rows.map((row) => row.getBoundingClientRect().height),
        buttonMinHeight: detailButton ? getComputedStyle(detailButton).minHeight : null,
        scrollHeight: table.scrollHeight,
        clientHeight: table.clientHeight,
      };
    });

    expect(Math.max(...measurements.rowHeights)).toBeLessThanOrEqual(32);
    expect(measurements.buttonMinHeight).toBe('0px');
    expect(measurements.scrollHeight).toBeLessThanOrEqual(measurements.clientHeight + 1);
  });

  test('splits Hub history into summary, trend and details on mobile', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('tab', { name: 'Istoric', exact: true }).click();
    await expect(page.getByRole('tab', { name: 'Sumar' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Trend' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Detalii' })).toBeVisible();
    await page.getByRole('tab', { name: 'Trend' }).click();
    await expect(page.getByText('Evolutie lunara')).toBeVisible();
  });

  test('exposes long Focus navigation and compact Agent analysis controls', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'Focus' }).first().click();
    await expect(page.getByText('Glisează pentru toate secțiunile →')).toBeVisible();

    await page.getByRole('button', { name: 'Agenti' }).first().click();
    await page.getByRole('tab', { name: 'Analiză agenți' }).click();
    await expect(page.getByRole('button', { name: 'Filtre', exact: true }).last()).toBeVisible();
    await expect(page.getByRole('paragraph').filter({ hasText: 'Fără agenți pentru filtrele selectate.' })).toBeVisible();
  });

  test('keeps theme only in Preferences and shows compact Export progress', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: /Setari/i }).first().click();
    await expect(page.getByRole('heading', { name: 'Import fișier vânzări' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Temă' })).toHaveCount(0);

    await page.getByRole('tab', { name: 'Exporturi' }).click();
    await expect(page.getByRole('navigation', { name: 'Pași export Excel' }).getByText('Pasul 1 din 4')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);
  });
});
