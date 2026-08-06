import { expect, test } from './fixtures';
import { MOCK_DASHBOARD_ALL, mockApiRoute, retailWire, setupBaseMocks } from './helpers';
import type { ImportHistoryEntry } from '../src/api/generated/runtime-types';

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
        body: JSON.stringify(
          retailWire('get_dashboard_all_api_dashboard_all_get', {
            ...MOCK_DASHBOARD_ALL,
            regionals,
            stores,
          }),
        ),
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

  test('keeps Focus navigation clean and Agent analysis controls compact', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'Focus' }).first().click();
    await expect(page.getByText('Glisează pentru toate secțiunile →')).toHaveCount(0);
    await expect(page.getByRole('tab', { name: 'Focus', exact: true })).toBeVisible();

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

  test('keeps ERP reconciliation details within the mobile viewport', async ({ page, context }) => {
    const history: ImportHistoryEntry[] = [{
      id: 213, import_month: '2026-08', filename: 'vanzari_august.xlsx', status: 'completed',
      upload_date: '2026-08-04', rows_in_file: 4226, rows_imported: 4226, is_month_final: false,
      error_message: null, created_at: '2026-08-04T08:46:55Z', finished_at: '2026-08-04T08:47:01Z',
      duration_seconds: 6, coverage_report: {
        active_store_count_before: null, active_store_coverage_pct: null, company_count: null,
        incoming_store_count: null, metadata_change_count: null, missing_active_store_count: null,
        missing_prior_store_count: null, new_store_count: null, prior_snapshot_coverage_pct: null,
        prior_snapshot_store_count: null, store_activity_writes: null,
      },
    }];
    await mockApiRoute(context, 'GET', /\/api\/import\/history$/, history);
    const erpResult = {
      status: 'differences',
      import_month: '2026-08',
      report_cutoff_date: '2026-08-03',
      retail_cutoff_date: '2026-08-03',
      cutoff_matches: true,
      filename: 'RaportDetaliat.xls',
      file_digest: 'a'.repeat(64),
      report_store_count: 71,
      retail_store_count: 71,
      report_agent_count: 132,
      retail_agent_count: 132,
      metrics: [{
        key: 'target', label: 'Target', report_value: 4400000, retail_value: 4400000,
        difference: 0, unit: 'RON', status: 'ok', note: null,
      }],
      app_only_metrics: [],
      issues: [{
        severity: 'warning', scope: 'store', site_code: 'STORE-001', entity: 'Magazin foarte lung',
        metric: 'Vânzări accesorii', report_value: 380774, retail_value: 380700,
        difference: 74, note: 'Diferență de verificat',
      }],
      issue_count: 1,
      omitted_issue_count: 0,
      notes: [],
    };
    await mockApiRoute(
      context,
      'POST',
      /\/api\/import\/erp-reconciliation$/,
      retailWire('reconcile_erp_report_file_api_import_erp_reconciliation_post', {
        job_id: 'erp-reconciliation-e2e',
        job_kind: 'erp_reconciliation',
        status: 'complete',
        error: null,
        result: null,
        promo_result: null,
        erp_result: erpResult,
      }),
    );

    await page.goto('/');
    await page.getByRole('button', { name: /Setari/i }).first().click();
    await page.locator('#upload-erp-reconciliation-file').setInputFiles({
      name: 'RaportDetaliat.xls', mimeType: 'application/vnd.ms-excel', buffer: Buffer.from('xls'),
    });
    await page.getByRole('button', { name: 'Verifică raportul fără import' }).click();
    await expect(page.getByText('1 diferențe de detaliu de verificat')).toBeVisible();

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBe(0);
  });
});
