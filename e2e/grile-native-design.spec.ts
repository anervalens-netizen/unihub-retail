import AxeBuilder from '@axe-core/playwright';
import { expect, test } from './fixtures';
import { setupBaseMocks, mockApiRoute } from './helpers';

test.use({ locale: 'ro-RO' });

for (const viewport of [{ width: 360, height: 800 }, { width: 390, height: 844 }, { width: 1440, height: 1000 }]) {
  test(`Grile V2 filters and calendar at ${viewport.width}px`, async ({ page, context }, testInfo) => {
    await page.setViewportSize(viewport);
    await setupBaseMocks(context);
    await context.addInitScript(() => { if (location.protocol === 'http:') sessionStorage.setItem('agents_mainTab', JSON.stringify('grile')); });
    const stores = [
      { site_code: 'S1', locatie: 'BÂRLAD CARREFOUR', firma: 'MobiCell', regional: 'Adrian Badea', asm: 'Andreea David' },
      { site_code: 'S2', locatie: 'BUZĂU AURORA', firma: 'Mobiup', regional: 'Adrian Badea', asm: 'Andreea David' },
      { site_code: 'S3', locatie: 'BRAȘOV AFI', firma: 'Mobiup', regional: 'Maria Ionescu', asm: '' },
    ];
    await mockApiRoute(context, 'GET', /\/api\/stores$/, stores);
    await mockApiRoute(context, 'GET', /\/api\/grile\/overview/, { month: '2026-09', total_sheets: 0, run: null, summary: { business_ok: 0, business_problems: 0, business_unknown: 0, provider_errors: 0, provider_stale: 0 }, managers: [] });
    await mockApiRoute(context, 'GET', /\/api\/grile\/calendar\/\d{4}-\d{2}$/, { month: '2026-09', roster: [{ month: '2026-09', agent_code: 'AG1', display_name: 'Ana Popescu', identity_status: 'confirmed', home_site_code: 'S1', active: true, revision: 1 }], days: [{ agent_code: 'AG1', work_date: '2026-09-01', site_code: 'S1', status: 'work', supplemental: false, revision: 1 }], attendance: [], projection_revision: 'a'.repeat(64), store_hours: [], attendance_days: [], attendance_by_store: {} });
    await mockApiRoute(context, 'GET', /\/api\/grile\/calendar\/.*\/candidates$/, []);
    await page.goto('/');
    await page.getByRole('button', { name: 'Agenti', exact: true }).first().click();
    await page.getByRole('tab', { name: 'Grile', exact: true }).click();
    await page.getByRole('tab', { name: 'Program V2', exact: true }).click();
    await page.getByLabel('Luna programului').fill('2026-09');
    await expect(page.getByRole('heading', { name: 'Programul echipei' })).toBeVisible();
    await page.getByLabel('Manager program').selectOption('Adrian Badea');
    await expect(page.getByRole('button', { name: /BÂRLAD CARREFOUR/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /BRAȘOV AFI/ })).toHaveCount(0);
    await page.getByRole('heading', { name: 'Programul echipei' }).click();
    await page.screenshot({ path: testInfo.outputPath('overview.png'), fullPage: true });
    await page.getByLabel('Firmă program').selectOption('Mobiup');
    await expect(page.getByRole('button', { name: /BÂRLAD CARREFOUR/ })).toHaveCount(0);
    await page.getByLabel('Caută magazin').fill('inexistent');
    await expect(page.getByText('Niciun magazin găsit')).toBeVisible();
    await page.getByRole('button', { name: 'Resetează filtrele' }).click();
    await page.getByLabel('Manager program').selectOption('Adrian Badea');
    await page.getByRole('button', { name: /BÂRLAD CARREFOUR/ }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.getByRole('button', { name: 'Editează 2026-09-01' }).click();
    await expect(page.getByLabel('Agent pentru zi')).toHaveValue('AG1');
    await expect(page.getByRole('button', { name: 'Salvează ziua' })).toBeEnabled();
    expect(await page.getByRole('dialog').evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath('calendar.png'), fullPage: true });
    expect((await new AxeBuilder({ page }).include('dialog').withTags(['wcag2a', 'wcag2aa']).analyze()).violations).toEqual([]);
    await page.getByRole('button', { name: 'Închide magazinul' }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    if (viewport.width === 390) {
      await page.evaluate(() => document.documentElement.classList.add('dark'));
      await page.getByRole('heading', { name: 'Programul echipei' }).scrollIntoViewIfNeeded();
      await page.screenshot({ path: testInfo.outputPath('dark.png'), fullPage: true });
      expect((await new AxeBuilder({ page }).include('.native-calendar').withTags(['wcag2a', 'wcag2aa']).analyze()).violations).toEqual([]);
      await page.getByRole('button', { name: /BÂRLAD CARREFOUR/ }).click();
      await page.getByRole('button', { name: 'Editează 2026-09-01' }).click();
      await page.screenshot({ path: testInfo.outputPath('dark-calendar.png'), fullPage: true });
      expect((await new AxeBuilder({ page }).include('dialog').withTags(['wcag2a', 'wcag2aa']).analyze()).violations).toEqual([]);
    }
  });
}
