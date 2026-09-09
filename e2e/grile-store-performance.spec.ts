import { expect, test } from './fixtures';
import { setupBaseMocks, mockApiRoute } from './helpers';

test('store performance cards and calendar sections remain usable on desktop and mobile', async ({ page, context }, testInfo) => {
  await setupBaseMocks(context);
  await page.setViewportSize({ width: 1440, height: 1100 });
  const store = { site_code: 'CTCITYPRK', locatie: 'CONSTANTA CITY PARK', firma: 'Mobiup', regional: 'Andrei Stancu', asm: '' };
  const roster = ['MANEANI', 'GISCAN'].map((code, i) => ({ month: '2026-09', agent_code: code, display_name: ['Manea Nicoleta', 'Gisca Nela'][i], identity_status: 'confirmed', home_site_code: store.site_code, active: true, revision: 1 }));
  const calendar = { month: '2026-09', roster, days: [{ agent_code: 'MANEANI', work_date: '2026-09-01', site_code: store.site_code, status: 'work', supplemental: false, revision: 1 }], attendance: [], projection_revision: 'a'.repeat(64), store_hours: [], attendance_days: [], attendance_by_store: {} };
  const performance = { target: '40000', sales: '19000', progress: '47.5', average: '2714.28', forecast: '43428.48', forecast_progress: '108.57', scheduled_days: 16, worked_days: 7, leave_days: 0, supplemental_days: 0, daily_80: '1444.44', daily_90: '1888.88', daily_100: '2333.33', daily_120: '3222.22' };
  const agents = roster.map(r => ({ ...r, home_work_days: 16, home_target: '40000', home_sales: '19000', home_commission: '0', away_commission: '0', supplemental_pay: '0', known_earnings: '0', days: [], issues: [], performance,
    compensation: { month: '2026-09', agent_code: r.agent_code, revision: 1, salary_base: '2600', vouchers: '480', sim_quantity: 3, epay_under_50: 0, epay_over_50: 0, incentive: '410', adjustment: '0' },
    salary: { sim_pay: '9', epay_pay: '0', commission_total: '419', current_total: '3499', forecast_total: '5002', potential_120: '5339' } }));
  await mockApiRoute(context, 'GET', /\/api\/stores$/, [store]);
  await mockApiRoute(context, 'GET', /\/api\/grile\/overview/, { month: '2026-09', total_sheets: 0, run: null, summary: { business_ok: 0, business_problems: 0, business_unknown: 0, provider_errors: 0, provider_stale: 0 }, managers: [] });
  await mockApiRoute(context, 'GET', /\/api\/grile\/calendar\/\d{4}-\d{2}$/, calendar);
  await mockApiRoute(context, 'GET', /\/api\/grile\/calendar\/.*\/candidates$/, []);
  await mockApiRoute(context, 'GET', /\/api\/grile\/calendar\/.*\/earnings$/, { month: '2026-09', status: 'provisional', cutoff: '2026-09-08', calendar_revision: calendar.projection_revision, projection_revision: 'b'.repeat(64), selling_days: { CTCITYPRK: 30 }, agents, unassigned_sales: [], unavailable_components: [], stores: { CTCITYPRK: { ...performance, target: '80000', sales: '39825', forecast: '91031' } } });
  await page.goto('/');
  await page.getByRole('button', { name: 'Agenti', exact: true }).first().click();
  await page.getByRole('tab', { name: 'Grile', exact: true }).click();
  await page.getByRole('tab', { name: 'Program V2', exact: true }).click();
  await page.getByLabel('Luna programului').fill('2026-09');
  await page.getByText('TL Constanța · DAVIDDA', { exact: true }).click();
  await page.getByRole('button', { name: /CONSTANTA CITY PARK/ }).click();
  await page.getByRole('tab', { name: 'Grile', exact: true }).last().click();
  await expect(page.getByRole('heading', { name: 'Performanță magazin și echipă' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Manea Nicoleta · MANEANI' })).toBeVisible();
  await expect(page.getByText('2.600 lei', { exact: true })).toHaveCount(2);
  await page.getByRole('dialog').screenshot({ path: testInfo.outputPath('grila-desktop.png') });
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await page.getByRole('dialog').evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    await page.getByRole('tab', { name: 'Calendar', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Concedii · agenții magazinului' })).toBeAttached();
    await expect(page.getByRole('heading', { name: 'Suplimentari în această locație' })).toBeAttached();
    await page.getByRole('heading', { name: 'Concedii · agenții magazinului' }).scrollIntoViewIfNeeded();
    await page.getByRole('dialog').screenshot({ path: testInfo.outputPath(`calendar-${width}.png`) });
    await page.getByRole('tab', { name: 'Grile', exact: true }).last().click();
  }
});
