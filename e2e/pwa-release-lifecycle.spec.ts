import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { extname, join, normalize, resolve } from 'node:path';

import { expect, test, type Page } from '@playwright/test';

type ReleaseArtifact = {
  dist: string;
  label: 'N' | 'N+1';
  worker: string;
  workerSha256: string;
};

function loadArtifact(label: ReleaseArtifact['label'], directory: string | undefined): ReleaseArtifact {
  if (!directory) throw new Error(`PWA_${label === 'N' ? 'PREVIOUS' : 'CANDIDATE'}_DIST is required`);
  const dist = resolve(directory);
  const worker = readFileSync(join(dist, 'sw.js'), 'utf8');
  return {
    dist,
    label,
    worker,
    workerSha256: createHash('sha256').update(worker).digest('hex'),
  };
}

const previousArtifact = loadArtifact('N', process.env.PWA_PREVIOUS_DIST);
const candidateArtifact = loadArtifact('N+1', process.env.PWA_CANDIDATE_DIST);

function releaseWorker(artifact: ReleaseArtifact): string {
  const identity = { release: artifact.label, workerSha256: artifact.workerSha256 };
  return `${artifact.worker}\nself.addEventListener('message', event => {\n`
    + `  if (event.data === 'retail-release') event.ports[0].postMessage(${JSON.stringify(identity)});\n`
    + `});\n`;
}

async function closeServer(server: Server): Promise<void> {
  await new Promise<void>((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())));
}

async function activeRelease(page: Page): Promise<{ release: string; workerSha256: string }> {
  return page.evaluate(async () => {
    const registration = await navigator.serviceWorker.ready;
    const worker = navigator.serviceWorker.controller ?? registration.active;
    if (!worker) throw new Error('active Workbox worker missing');
    return new Promise<{ release: string; workerSha256: string }>((resolve, reject) => {
      const channel = new MessageChannel();
      const timer = window.setTimeout(() => reject(new Error('Workbox release response timed out')), 5_000);
      channel.port1.onmessage = (event) => { window.clearTimeout(timer); resolve(event.data); };
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

async function checkForNoopUpdate(page: Page): Promise<void> {
  await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.getRegistration();
    if (!registration) throw new Error('Workbox registration missing');
    await registration.update();
  });
}

test('generated Workbox worker handles upgrade, rollback, and unchanged releases', async ({ browser }) => {
  expect(previousArtifact.worker).toContain('precacheAndRoute');
  expect(candidateArtifact.worker).toContain('precacheAndRoute');
  let artifact = previousArtifact;
  const server = createServer((request, response) => {
    const pathname = new URL(request.url ?? '/', 'http://localhost').pathname;
    if (pathname === '/sw.js') {
      response.writeHead(200, {
        'Cache-Control': 'no-store',
        'Content-Type': 'application/javascript; charset=utf-8',
        'Service-Worker-Allowed': '/',
      });
      response.end(releaseWorker(artifact));
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
      const body = readFileSync(join(artifact.dist, relative));
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
    await expect.poll(() => activeRelease(page)).toEqual({
      release: 'N',
      workerSha256: previousArtifact.workerSha256,
    });
    if (candidateArtifact.workerSha256 === previousArtifact.workerSha256) {
      await checkForNoopUpdate(page);
      await expect.poll(() => activeRelease(page)).toEqual({
        release: 'N',
        workerSha256: previousArtifact.workerSha256,
      });
      return;
    }
    artifact = candidateArtifact;
    await updateWorker(page);
    await expect.poll(() => activeRelease(page)).toEqual({
      release: 'N+1',
      workerSha256: candidateArtifact.workerSha256,
    });
    artifact = previousArtifact;
    await updateWorker(page);
    await expect.poll(() => activeRelease(page)).toEqual({
      release: 'N',
      workerSha256: previousArtifact.workerSha256,
    });
  } finally {
    await context.close();
    await closeServer(server);
  }
});
