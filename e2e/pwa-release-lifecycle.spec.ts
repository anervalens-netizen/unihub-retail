import { readFileSync } from 'node:fs';
import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { extname, join, normalize } from 'node:path';

import { expect, test, type Page } from '@playwright/test';

const dist = join(process.cwd(), 'dist');
const generatedWorkbox = readFileSync(join(dist, 'sw.js'), 'utf8');

function releaseWorker(release: string): string {
  return `${generatedWorkbox}\nself.addEventListener('message', event => {\n`
    + `  if (event.data === 'retail-release') event.ports[0].postMessage(${JSON.stringify(release)});\n`
    + `});\n`;
}

async function closeServer(server: Server): Promise<void> {
  await new Promise<void>((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())));
}

async function activeRelease(page: Page): Promise<string> {
  return page.evaluate(async () => {
    const registration = await navigator.serviceWorker.ready;
    const worker = navigator.serviceWorker.controller ?? registration.active;
    if (!worker) throw new Error('active Workbox worker missing');
    return new Promise<string>((resolve, reject) => {
      const channel = new MessageChannel();
      const timer = window.setTimeout(() => reject(new Error('Workbox release response timed out')), 5_000);
      channel.port1.onmessage = (event) => { window.clearTimeout(timer); resolve(String(event.data)); };
      worker.postMessage('retail-release', [channel.port2]);
    });
  });
}

async function updateWorker(page: Page): Promise<void> {
  await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.getRegistration();
    if (!registration) throw new Error('Workbox registration missing');
    await new Promise<void>((resolve, reject) => {
      const timer = window.setTimeout(() => reject(new Error('Workbox controller did not change')), 10_000);
      navigator.serviceWorker.addEventListener('controllerchange', () => {
        window.clearTimeout(timer);
        resolve();
      }, { once: true });
      void registration.update().catch(reject);
    });
  });
}

test('generated Workbox worker upgrades N to N+1 and rolls back to N', async ({ browser }) => {
  expect(generatedWorkbox).toContain('precacheAndRoute');
  let release = 'N';
  const server = createServer((request, response) => {
    const pathname = new URL(request.url ?? '/', 'http://localhost').pathname;
    if (pathname === '/sw.js') {
      response.writeHead(200, {
        'Cache-Control': 'no-store',
        'Content-Type': 'application/javascript; charset=utf-8',
        'Service-Worker-Allowed': '/',
      });
      response.end(releaseWorker(release));
      return;
    }
    if (pathname === '/') {
      response.writeHead(200, { 'Cache-Control': 'no-store', 'Content-Type': 'text/html; charset=utf-8' });
      response.end("<!doctype html><script>navigator.serviceWorker.register('/sw.js', {updateViaCache:'none'})</script>");
      return;
    }
    const relative = normalize(pathname).replace(/^[/\\]+/, '');
    if (relative.includes('..')) { response.writeHead(404).end(); return; }
    try {
      const body = readFileSync(join(dist, relative));
      const contentType = extname(relative) === '.js' ? 'application/javascript' : 'application/octet-stream';
      response.writeHead(200, { 'Content-Type': contentType });
      response.end(body);
    } catch {
      response.writeHead(404).end();
    }
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
    await expect.poll(() => activeRelease(page)).toBe('N');
    release = 'N+1';
    await updateWorker(page);
    await expect.poll(() => activeRelease(page)).toBe('N+1');
    release = 'N';
    await updateWorker(page);
    await expect.poll(() => activeRelease(page)).toBe('N');
  } finally {
    await context.close();
    await closeServer(server);
  }
});
