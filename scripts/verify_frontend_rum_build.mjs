import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { loadEnv } from 'vite';

const distDir = path.resolve(process.env.RETAIL_DIST_DIR || 'dist');
const fileEnv = loadEnv(process.env.NODE_ENV || 'production', process.cwd(), '');
const expectedDsn = process.env.VITE_FRONTEND_GLITCHTIP_DSN
  || fileEnv.VITE_FRONTEND_GLITCHTIP_DSN
  || '';

if (!expectedDsn) {
  throw new Error('frontend RUM verification requires VITE_FRONTEND_GLITCHTIP_DSN');
}

const assetsDir = path.join(distDir, 'assets');
const assets = (await readdir(assetsDir, { withFileTypes: true }))
  .filter((entry) => entry.isFile() && entry.name.endsWith('.js'))
  .map((entry) => path.join(assetsDir, entry.name));

if (assets.length === 0) {
  throw new Error(`frontend RUM verification found no JavaScript assets in ${assetsDir}`);
}

const rumCompiled = (
  await Promise.all(assets.map(async (asset) => (await readFile(asset, 'utf8')).includes(expectedDsn)))
).some(Boolean);

if (!rumCompiled) {
  throw new Error('frontend RUM DSN is not compiled into the production bundle');
}

process.stdout.write(`frontend RUM verified in ${assets.length} JavaScript assets\n`);
