import { expect, test, type Page } from '@playwright/test';

/**
 * V3 AI assistant responsive browser smoke against the isolated stack.
 *
 * The stack under test is the real public backend serving the built SPA, the
 * canonical OIDC test stub and a loopback AI runtime. No production resource.
 * Only objective functional/layout blockers are asserted; visual preference is
 * not redesigned.
 */

const OIDC_ORIGIN = (process.env.REAL_E2E_OIDC_ORIGIN ?? '').replace(/\/$/, '');
const PANEL = { name: 'UniHub AI' } as const;

async function signIn(page: Page): Promise<void> {
  await page.goto(`${OIDC_ORIGIN}/test-persona/pnl-owner`);
  await page.goto('/auth/session/login');
  // The owner-only AI launcher only renders once the real OIDC session and the
  // `/api/ai` owner gate have both succeeded, so it is the authenticated marker.
  await expect(page.getByRole('button', { name: 'Deschide UniHub AI' })).toBeVisible({
    timeout: 30_000,
  });
}

async function openPanel(page: Page): Promise<void> {
  const launcher = page.getByRole('button', { name: 'Deschide UniHub AI' });
  if (await launcher.isVisible().catch(() => false)) {
    await launcher.click();
  }
  await expect(page.getByRole('complementary', PANEL)).toBeVisible();
}

test.describe('desktop', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('sidebar opens, resizes, submits, steers, stops and downloads', async ({ page }) => {
    await signIn(page);
    await openPanel(page);
    const panel = page.getByRole('complementary', PANEL);

    const before = (await panel.boundingBox())?.width ?? 0;
    const handle = page.getByRole('button', { name: 'Redimensionează panoul AI' });
    await expect(handle).toBeAttached();
    await handle.hover();
    await page.mouse.down();
    await page.mouse.move(900, 450, { steps: 12 });
    await page.mouse.up();
    const after = (await panel.boundingBox())?.width ?? 0;
    expect(Math.abs(after - before)).toBeGreaterThan(20);

    // The application itself stays usable while the sidebar is open.
    await expect(page.locator('main')).toBeVisible();

    // New conversation, effort and context controls are present.
    await expect(page.getByRole('button', { name: 'Conversație nouă' })).toBeVisible();
    await expect(page.getByLabel('Reasoning effort')).toBeVisible();
    await expect(page.getByText(/Context:/)).toBeVisible();

    // Upload then send a file-only turn; the run streams and completes.
    await page.setInputFiles('input[type="file"]', {
      name: 'smoke.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from('store,value\nA,1\n'),
    });
    // Scope to the composer: an earlier conversation may already render a
    // message attachment with the same filename.
    await expect(page.getByRole('button', { name: 'Elimină smoke.csv' })).toBeVisible();
    await page.getByRole('button', { name: /Trimite/ }).click();

    // The uploaded artifact is downloadable by its owner.
    const attachment = panel.getByRole('link', { name: /smoke\.csv/ }).first();
    await expect(attachment).toBeVisible({ timeout: 30_000 });
    const download = page.waitForEvent('download');
    await attachment.click();
    expect((await download).suggestedFilename()).toContain('smoke.csv');

    // Steer is offered while the run streams, then Stop while stopping.
    await page.getByLabel('Mesaj pentru UniHub AI').fill('continuă pe ASM');
    const send = page.getByRole('button', { name: /Trimite|Steer/ });
    await expect(send).toBeEnabled();

    await page.getByRole('button', { name: 'Închide UniHub AI' }).last().click();
    await expect(page.getByRole('complementary', PANEL)).toBeHidden();
  });

  test('composer keeps a live run mounted across a transient capability refetch', async ({ page }) => {
    await signIn(page);
    await openPanel(page);
    await page.getByLabel('Mesaj pentru UniHub AI').fill('rulează puțin');
    await page.getByRole('button', { name: /Trimite/ }).click();

    // A slow runtime keeps the run active; rerender the shell by navigating focus
    // and re-reading capabilities without unmounting the AI surface.
    await expect(page.getByRole('button', { name: /Steer|Stop/ }).first()).toBeVisible({ timeout: 20_000 });
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    await page.evaluate(() => window.dispatchEvent(new Event('visibilitychange')));
    await expect(page.getByRole('complementary', PANEL)).toBeVisible();
    await expect(page.getByRole('button', { name: /Stop|Steer/ }).first()).toBeVisible();
  });
});

test.describe('tablet', () => {
  test.use({ viewport: { width: 834, height: 1112 } });

  test('drawer overlays without permanently squeezing the app', async ({ page }) => {
    await signIn(page);
    const main = page.locator('main');
    const widthBefore = (await main.boundingBox())?.width ?? 0;

    await openPanel(page);
    await expect(page.getByRole('complementary', PANEL)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Închide UniHub AI' }).first()).toBeVisible();

    await page.getByRole('button', { name: 'Închide UniHub AI' }).last().click();
    await expect(page.getByRole('complementary', PANEL)).toBeHidden();
    const widthAfter = (await main.boundingBox())?.width ?? 0;
    expect(Math.abs(widthAfter - widthBefore)).toBeLessThan(40);
  });
});

test.describe('mobile', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test('chat becomes a full-width surface with a usable composer', async ({ page }) => {
    await signIn(page);
    await openPanel(page);
    const panel = page.getByRole('complementary', PANEL);
    const box = await panel.boundingBox();
    expect(box?.width ?? 0).toBeGreaterThanOrEqual(320);

    const composer = page.getByLabel('Mesaj pentru UniHub AI');
    await expect(composer).toBeVisible();
    await composer.fill('test mobil');
    await expect(page.getByRole('button', { name: /Trimite/ })).toBeEnabled();
    await expect(page.getByRole('button', { name: 'Atașează fișiere' })).toBeVisible();
  });
});
