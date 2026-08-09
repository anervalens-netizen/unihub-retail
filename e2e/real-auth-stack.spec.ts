import { expect, test } from '@playwright/test';

test('real OIDC BFF session reaches the built dashboard', async ({ page, request }) => {
  const response = await page.goto('/auth/session/login');
  expect(response?.ok()).toBeTruthy();
  await expect(page.getByRole('button', { name: 'Hub' }).first()).toBeVisible();

  const session = await request.get('/auth/session');
  expect(session.status()).toBe(401);

  const browserSession = await page.evaluate(async () => {
    const result = await fetch('/auth/session', { credentials: 'same-origin' });
    return { status: result.status, body: await result.json() };
  });
  expect(browserSession.status).toBe(200);
  expect(browserSession.body.profile.sub).toBe('real-e2e-owner');
  expect(browserSession.body.profile.groups).toContain('unihub-admin');
  expect(browserSession.body.csrf_token).toMatch(/^[A-Za-z0-9_-]{43}$/);
});
