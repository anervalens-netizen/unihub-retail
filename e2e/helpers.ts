import { Page, BrowserContext } from '@playwright/test';

export const MOCK_USER = {
  sub: 'test-user-123',
  email: 'test@mobiup.ro',
  name: 'Test User',
  groups: ['unihub-retail:manager'],
};

export async function mockAuthenticatedSession(context: BrowserContext) {
  const expiresAt = Math.floor(Date.now() / 1000) + 3600;
  const tokenPayload = {
    iss: 'https://auth.unihub.ro/application/o/unihub-retail/',
    sub: MOCK_USER.sub,
    aud: '4yiNauwNNzIoIE3Mq9IFnylxtdih9jFSqSKGw93t',
    exp: expiresAt,
    iat: Math.floor(Date.now() / 1000),
    email: MOCK_USER.email,
    name: MOCK_USER.name,
    groups: MOCK_USER.groups,
  };
  const base64Encode = (obj: Record<string, unknown>) =>
    Buffer.from(JSON.stringify(obj)).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  const fakeToken = `${base64Encode({ alg: 'RS256', typ: 'JWT' })}.${base64Encode(tokenPayload)}.fake_signature`;

  await context.addInitScript((token) => {
    localStorage.setItem(
      'oidc.user:https://auth.unihub.ro/application/o/unihub-retail/:4yiNauwNNzIoIE3Mq9IFnylxtdih9jFSqSKGw93t',
      JSON.stringify({
        id_token: token,
        access_token: token,
        token_type: 'Bearer',
        scope: 'openid profile email',
        profile: { sub: 'test-user-123', email: 'test@mobiup.ro', name: 'Test User' },
        expires_at: Math.floor(Date.now() / 1000) + 3600,
      })
    );
  }, fakeToken);
}

export async function mockApiRoute(context: BrowserContext, method: string, urlPattern: string | RegExp, response: unknown) {
  await context.route(urlPattern, (route) => {
    if (route.request().method() === method.toUpperCase()) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(response),
      });
    }
    return route.continue();
  });
}

export const MOCK_MONTHS = ['2026-05', '2026-04', '2026-03', '2026-02', '2026-01'];

export const MOCK_FILTER_OPTIONS = {
  firme: [{ label: 'Firma 1', value: 'Firma 1' }],
  regionali: [{ label: 'Regional 1', value: 'Regional 1' }],
  asmi: [{ label: 'ASM 1', value: 'ASM 1' }],
  magazine: [{ label: 'Magazin 1', value: 'Magazin 1' }],
  agenti: [{ label: 'Agent 1', value: 'Agent 1' }],
};

export const MOCK_DASHBOARD_ALL = {
  daily: [],
  regionals: [],
  asms: [],
  summary: {
    total_sales: 150000,
    total_target: 200000,
    achievement_pct: 75.0,
    liquidations_count: 45,
    promotion_qty: 120,
    average_receipt: 85.5,
    store_count: 30,
    agent_count: 120,
    best_store: 'Magazin Central',
    best_store_sales: 25000,
  },
  stores: [],
  categories: [],
  brands: [],
  receipt_buckets: [],
  special_cards: [],
};

export const MOCK_DASHBOARD_HISTORY = {
  history: MOCK_MONTHS.map((month) => ({
    import_month: month,
    total_sales: 120000 + Math.random() * 30000,
    total_target: 180000,
    achievement_pct: 65 + Math.random() * 20,
    liquidation_count: 35,
    promo_qty: 90,
    agent_count: 110,
  })),
};

export const MOCK_DASHBOARD_YEAR_HISTORY = {
  points: MOCK_MONTHS.map((month) => ({
    import_month: month,
    total_sales: 120000 + Math.random() * 30000,
    total_target: 180000,
    achievement_pct: 65 + Math.random() * 20,
    liquidations_count: 35,
    promo_qty: 90,
    agent_count: 110,
  })),
};
