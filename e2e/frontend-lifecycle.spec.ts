import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { expect, test, type BrowserContext, type Page } from '@playwright/test';
import { MOCK_MONTHS, setupBaseMocks } from './helpers';

type BrowserCase = 'allowed' | 'denied' | 'success' | '401_redirect_once' | '403_safe' | '409_retry' | 'keyboard' | 'mobile';
type Group = { id: string; cases: Record<BrowserCase, string> };

const manifest = JSON.parse(readFileSync(resolve(process.cwd(), 'scripts/frontend-critical-coverage.json'), 'utf8')) as {
  groups: Group[];
};
const browserCases: BrowserCase[] = ['allowed', 'denied', 'success', '401_redirect_once', '403_safe', '409_retry', 'keyboard', 'mobile'];

test.beforeEach(async ({ context }) => setupBaseMocks(context));

async function boot(page: Page) {
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Hub' }).first()).toBeVisible({ timeout: 15_000 });
}

async function mockSession(context: BrowserContext, groups: string[]) {
  await context.route('**/auth/session', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      profile: { sub: 'matrix-user', email: 'matrix@unihub.ro', preferred_username: 'matrix', groups },
      csrf_token: 'matrix-csrf',
    }),
  }));
}

async function runBrowserCase(caseName: BrowserCase, page: Page, context: BrowserContext) {
  if (caseName === 'allowed' || caseName === 'success') {
    await boot(page);
    await expect(page.locator('main')).toBeVisible();
  } else if (caseName === 'denied') {
    await mockSession(context, []);
    await boot(page);
    await expect(page.getByRole('button', { name: 'Management' })).toHaveCount(0);
  } else if (caseName === '401_redirect_once') {
    let redirects = 0;
    await context.route('**/auth/session', (route) => route.fulfill({ status: 401, body: '' }));
    await context.route('**/auth/session/login', (route) => {
      redirects += 1;
      return route.fulfill({ status: 200, contentType: 'text/html', body: '<main>Login</main>' });
    });
    await page.goto('/');
    await expect(page).toHaveURL(/\/auth\/session\/login$/);
    expect(redirects).toBe(1);
  } else if (caseName === '403_safe') {
    await context.route(/\/api\/filters\/months$/, (route) => route.fulfill({
      status: 403, contentType: 'application/json', body: JSON.stringify({ detail: 'Acces interzis.' }),
    }));
    await page.goto('/');
    await expect(page.getByText(/Sesiunea a expirat/)).toBeVisible({ timeout: 15_000 });
  } else if (caseName === '409_retry') {
    let attempts = 0;
    await context.route(/\/api\/filters\/months$/, (route) => {
      attempts += 1;
      if (attempts === 1) return route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: 'Conflict temporar.' }) });
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_MONTHS) });
    });
    await boot(page);
    expect(attempts).toBe(2);
  } else if (caseName === 'keyboard') {
    await boot(page);
    const focus = page.getByRole('button', { name: 'Focus' }).first();
    await focus.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByText(/Focus & Campanii/i)).toBeVisible();
  } else {
    await page.setViewportSize({ width: 390, height: 844 });
    await boot(page);
    await expect(page.locator('.mobile-bottom-nav')).toBeVisible();
    await expect(page.locator('body')).not.toHaveCSS('overflow', 'hidden');
  }
}

for (const group of manifest.groups) {
  for (const caseName of browserCases) {
    test(group.cases[caseName], async ({ page, context }) => runBrowserCase(caseName, page, context));
  }
}
