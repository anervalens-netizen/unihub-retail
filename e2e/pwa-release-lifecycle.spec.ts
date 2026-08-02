import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';

import { expect, test, type Page } from '@playwright/test';

async function closeServer(server: Server): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    server.close((error) => (error ? reject(error) : resolve()));
  });
}

async function updateServiceWorker(page: Page): Promise<void> {
  await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.getRegistration();
    if (!registration) {
      throw new Error('service worker registration missing');
    }

    await new Promise<void>((resolve, reject) => {
      const timer = window.setTimeout(
        () => reject(new Error('service worker controller did not change')),
        10_000,
      );
      navigator.serviceWorker.addEventListener(
        'controllerchange',
        () => {
          window.clearTimeout(timer);
          resolve();
        },
        { once: true },
      );
      void registration.update().catch((error: unknown) => {
        window.clearTimeout(timer);
        reject(error);
      });
    });
  });
}

test('service worker upgrades N to N+1 and can roll back to N', async ({ browser }) => {
  let release = 'N';
  const server = createServer((request, response) => {
    if (request.url === '/sw.js') {
      response.writeHead(200, {
        'Cache-Control': 'no-store',
        'Content-Type': 'application/javascript; charset=utf-8',
        'Service-Worker-Allowed': '/',
      });
      response.end(`
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', (event) => {
  if (event.request.mode === 'navigate') {
    event.respondWith(new Response(
      '<!doctype html><html><body><div id="release">${release}</div></body></html>',
      { headers: { 'Content-Type': 'text/html; charset=utf-8' } },
    ));
  }
});
`);
      return;
    }

    response.writeHead(200, {
      'Cache-Control': 'no-store',
      'Content-Type': 'text/html; charset=utf-8',
    });
    response.end(`
<!doctype html>
<html>
  <body>
    <div id="release">boot</div>
    <script>navigator.serviceWorker.register('/sw.js', { updateViaCache: 'none' });</script>
  </body>
</html>
`);
  });

  await new Promise<void>((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });

  const address = server.address() as AddressInfo;
  const context = await browser.newContext({ serviceWorkers: 'allow' });
  const page = await context.newPage();

  try {
    await page.goto(`http://127.0.0.1:${address.port}`);
    await page.evaluate(() => navigator.serviceWorker.ready);
    await expect.poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true);
    await page.reload();
    await expect(page.locator('#release')).toHaveText('N');

    release = 'N+1';
    await updateServiceWorker(page);
    await page.reload();
    await expect(page.locator('#release')).toHaveText('N+1');

    release = 'N';
    await updateServiceWorker(page);
    await page.reload();
    await expect(page.locator('#release')).toHaveText('N');
  } finally {
    await context.close();
    await closeServer(server);
  }
});
