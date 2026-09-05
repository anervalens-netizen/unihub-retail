import { expect, test } from '@playwright/test';
import type { APIRequestContext } from '@playwright/test';

/**
 * K10 (#236) — repeatable authenticated black-box security validation.
 *
 * Procedure (isolated real stack; local test identities only):
 *   1. `scripts/run_real_e2e.sh` boots pinned Postgres + Valkey containers,
 *      the local OIDC stub (`backend/scripts/oidc_e2e_stub.py`) and the real
 *      backend, seeds deterministic fixture data, then runs this spec.
 *   2. The stub mints deterministic personas (admin, authentik-admin, manager,
 *      hr, agent, team-leader, pnl-owner, pnl-owner-only) through
 *      `GET {REAL_E2E_OIDC_ORIGIN}/test-token/{persona}` (API Bearer flow) and
 *      `GET {REAL_E2E_OIDC_ORIGIN}/test-persona/{persona}` (browser cookie
 *      flow). Identities are fake and local-only.
 *   3. Every assertion traverses the real HTTP boundary: real JWKS token
 *      verification, real router permission dependencies (`backend/permissions.py`,
 *      `backend/privileged_access.py`) and the real BFF session + CSRF
 *      middleware (`backend/session_auth.py`). No permission function is
 *      called directly and no authorization decision is mocked.
 *   4. Repeat: rerun `scripts/run_real_e2e.sh`; personas, fixtures and
 *      expectations are fully deterministic.
 */

const OIDC_ORIGIN = (process.env.REAL_E2E_OIDC_ORIGIN ?? '').replace(/\/$/, '');

async function asPersona(
  request: APIRequestContext,
  persona: string,
): Promise<{ headers: Record<string, string> }> {
  const response = await request.get(`${OIDC_ORIGIN}/test-token/${persona}`);
  expect(response.status(), `persona=${persona} token mint`).toBe(200);
  const body = (await response.json()) as { access_token: string };
  return { headers: { Authorization: `Bearer ${body.access_token}` } };
}

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

test('K10-A admin boundary: sales-import surface is admin-only', async ({ request }) => {
  const allowed = await request.get('/api/import/history', await asPersona(request, 'admin'));
  expect(allowed.status()).toBe(200);

  for (const persona of ['manager', 'hr', 'agent']) {
    const denied = await request.get('/api/import/history', await asPersona(request, persona));
    expect(denied.status(), `persona=${persona}`).toBe(403);
  }
});

test('K10-B salary/HR boundary: hr+manager allowed, agent+Team Leader denied', async ({ request }) => {
  const salaryAllowedHr = await request.get('/salarii/summary', await asPersona(request, 'hr'));
  expect(salaryAllowedHr.status()).toBe(200);
  const salaryAllowedManager = await request.get('/salarii/summary', await asPersona(request, 'manager'));
  expect(salaryAllowedManager.status()).toBe(200);
  for (const persona of ['agent', 'team-leader']) {
    const salaryDenied = await request.get('/salarii/summary', await asPersona(request, persona));
    expect(salaryDenied.status(), `persona=${persona}`).toBe(403);
  }

  const hrAllowed = await request.get('/api/hr/leave-requests', await asPersona(request, 'hr'));
  expect(hrAllowed.status()).toBe(200);
  const hrDenied = await request.get('/api/hr/leave-requests', await asPersona(request, 'agent'));
  expect(hrDenied.status()).toBe(403);
});

test('K10-C business-write boundary: manager allowed, hr and agent denied', async ({ request }) => {
  const allowed = await request.post('/api/tasks', {
    ...(await asPersona(request, 'manager')),
    data: { title: 'K10 boundary task (manager)' },
  });
  expect(allowed.status()).toBe(200);

  for (const persona of ['hr', 'agent']) {
    const denied = await request.post('/api/tasks', {
      ...(await asPersona(request, persona)),
      data: { title: 'K10 boundary task (must be denied)' },
    });
    expect(denied.status(), `persona=${persona}`).toBe(403);
  }
});

test('K10-D owner-allowlist boundary: store P&L requires management plus configured owner group', async ({ request }) => {
  const allowed = await request.get('/api/store-pnl/months', await asPersona(request, 'pnl-owner'));
  expect(allowed.status()).toBe(200);

  for (const persona of ['manager', 'agent', 'pnl-owner-only']) {
    const denied = await request.get('/api/store-pnl/months', await asPersona(request, persona));
    expect(denied.status(), `persona=${persona}`).toBe(403);
  }
});

test('K10-E CSRF boundary: cookie-session mutation denied without token, allowed with it', async ({ page }) => {
  await page.goto('/auth/session/login');

  const session = await page.evaluate(async () => {
    const result = await fetch('/auth/session', { credentials: 'same-origin' });
    return { status: result.status, body: await result.json() };
  });
  expect(session.status).toBe(200);
  const csrfToken = session.body.csrf_token as string;

  const withoutToken = await page.evaluate(async () => {
    const result = await fetch('/api/tasks', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: 'K10 CSRF probe (no token)' }),
    });
    return { status: result.status, body: await result.json() };
  });
  expect(withoutToken.status).toBe(403);
  expect(withoutToken.body.detail).toBe('CSRF validation failed');

  const withToken = await page.evaluate(
    async (token) => {
      const result = await fetch('/api/tasks', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token },
        body: JSON.stringify({ title: 'K10 CSRF probe (with token)' }),
      });
      return { status: result.status, body: await result.json() };
    },
    csrfToken,
  );
  expect(withToken.status).toBe(200);
  expect(withToken.body.title).toBe('K10 CSRF probe (with token)');
});

test('K10-F export authorization boundary: management allowed, agent denied', async ({ request }) => {
  const allowed = await request.get('/api/exports/catalog', await asPersona(request, 'manager'));
  expect(allowed.status()).toBe(200);
  const denied = await request.get('/api/exports/catalog', await asPersona(request, 'agent'));
  expect(denied.status()).toBe(403);
});

test('K10-G browser boundary: low-privilege cookie session is denied salaries', async ({ page }) => {
  const persona = await page.goto(`${OIDC_ORIGIN}/test-persona/agent`);
  expect(persona?.ok()).toBeTruthy();

  const response = await page.goto('/auth/session/login');
  expect(response?.ok()).toBeTruthy();

  const session = await page.evaluate(async () => {
    const result = await fetch('/auth/session', { credentials: 'same-origin' });
    return { status: result.status, body: await result.json() };
  });
  expect(session.status).toBe(200);
  expect(session.body.profile.sub).toBe('real-e2e-agent');
  expect(session.body.profile.groups).toEqual(['unihub-agent']);

  const salary = await page.evaluate(async () => {
    const result = await fetch('/salarii/summary', { credentials: 'same-origin' });
    return { status: result.status, body: await result.json() };
  });
  expect(salary.status).toBe(403);
});

test('K10-H Authentik Admins group retains privileged allow paths', async ({ request }) => {
  const auth = await asPersona(request, 'authentik-admin');

  const importHistory = await request.get('/api/import/history', auth);
  expect(importHistory.status()).toBe(200);

  const salary = await request.get('/salarii/summary', auth);
  expect(salary.status()).toBe(200);

  const management = await request.get('/api/hr/leave-requests', auth);
  expect(management.status()).toBe(200);

  const exports = await request.get('/api/exports/catalog', auth);
  expect(exports.status()).toBe(200);

  const businessWrite = await request.post('/api/tasks', {
    ...auth,
    data: { title: 'K10 Authentik Admins alias probe' },
  });
  expect(businessWrite.status()).toBe(200);
});
