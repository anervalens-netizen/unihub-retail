import { test, expect } from './fixtures';
import { mockApiRoute, setupBaseMocks } from './helpers';

test.describe('E2E: Management & Settings', () => {
  test.beforeEach(async ({ context }) => {
    await setupBaseMocks(context);
  });

  test('navigates to Management tab and shows sub-tabs', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Hub' }).first()).toBeVisible({ timeout: 15000 });

    await page.getByRole('button', { name: 'Management' }).first().click();

    await expect(page.getByRole('tab', { name: 'Manageri', exact: true })).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole('tab', { name: 'Calculator Target' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Salarii' })).toBeVisible();
  });

  test('Manageri renders the team and portfolio overview', async ({ page, context }) => {
    await mockApiRoute(context, 'GET', /\/api\/hr\/manager-overview/, [{
      manager: 'Mihai Condorateanu',
      regional: 'Mihai Condorateanu',
      month: '2026-05',
      reporting_available: true,
      active_stores: 10,
      active_agents: 20,
      previous_active_agents: 20,
      agent_delta: 0,
      agents_added: 0,
      agents_left: 0,
      stores_without_agents: 0,
      agents_per_store: 2,
      visits_available: false,
      total_visits: 0,
      visited_stores: 0,
      visit_coverage_pct: null,
      avg_visit_completion: null,
      checklist_score: null,
      approved_pct: null,
      stores: [],
    }]);

    await page.goto('/');
    await page.getByRole('button', { name: 'Management' }).first().click();

    await expect(page.getByRole('heading', { name: 'Overview echipe manageri' })).toBeVisible();
    await expect(page.getByText('Magazine active')).toBeVisible();
    await expect(page.getByText('Agenți activi').first()).toBeVisible();
    await expect(page.getByRole('button', { name: /Mihai Condorateanu/ })).toBeVisible();
  });

  test('shows the global filter entry on desktop for Salarii', async ({ page, context }) => {
    await mockApiRoute(context, 'GET', /\/salarii\/overview/, {
      total: 0,
      by_company: [],
      record_count: 0,
      agent_count: 0,
      agent_month_count: 0,
      avg_agent_month_count: 0,
      avg_salary: 0,
      months_span: null,
    });
    await mockApiRoute(context, 'GET', /\/salarii\/evolution/, []);
    await mockApiRoute(context, 'GET', /\/salarii\/summary/, { month: null, items: [] });
    await mockApiRoute(context, 'GET', /\/salarii\/trend/, []);
    await mockApiRoute(context, 'GET', /\/salarii\/agents\/summary/, { items: [], total: 0 });

    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Hub' }).first()).toBeVisible({ timeout: 15000 });
    await page.getByRole('button', { name: 'Management' }).first().click();
    await page.getByRole('tab', { name: 'Salarii' }).click();

    await expect(page.getByRole('button', { name: 'Filtre' })).toBeVisible();
  });

  test('P&L remains usable on mobile browsers without Array.at', async ({ page, context }) => {
    await context.addInitScript(() => {
      Reflect.deleteProperty(Array.prototype, 'at');
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await mockApiRoute(context, 'GET', /\/api\/store-pnl\/permissions$/, { can_view: true });
    await mockApiRoute(context, 'GET', /\/api\/store-pnl\/months$/, {
      months: [
        { month: '2026-01', has_actual: true, has_estimated: false },
        { month: '2026-07', has_actual: false, has_estimated: true },
      ],
    });
    await mockApiRoute(context, 'GET', /\/api\/store-pnl\/stores/, { stores: [] });
    await mockApiRoute(context, 'GET', /\/api\/store-pnl\/regions/, { regions: [] });
    await mockApiRoute(context, 'GET', /\/api\/store-pnl\/annual/, { annual: [] });
    await mockApiRoute(context, 'GET', /\/api\/store-pnl\/overview/, {
      start_month: '2026-01',
      end_month: '2026-07',
      company: null,
      site_code: null,
      site_company: null,
      regional: null,
      summary: { revenue: 100000, cogs: 30000, gross_margin: 70000, operating_costs: 50000, ebitda: 20000, depreciation: 5000, ebit: 15000 },
      monthly: [
        { month: '2026-01', is_estimated: false, revenue: 100000, cogs: 30000, gross_margin: 70000, operating_costs: 50000, ebitda: 20000, depreciation: 5000, ebit: 15000 },
      ],
      categories: { v1: 100000, c1: -30000 },
      stores: [],
      reconciliation: [],
    });

    await page.goto('/');
    await page.getByRole('button', { name: 'Management' }).first().click();
    await page.getByRole('tab', { name: 'P&L' }).click();

    await expect(page.getByRole('heading', { name: 'Profit & Loss' })).toBeVisible();
    await expect(page.getByText('Evoluție lunară')).toBeVisible();
  });

  test('navigates to Setari tab and shows import section', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Hub' }).first()).toBeVisible({ timeout: 15000 });

    await page.getByRole('button', { name: /Setari/i }).first().click();

    await expect(page.getByText(/Import fișier vânzări/i)).toBeVisible({ timeout: 10000 });
  });
});
