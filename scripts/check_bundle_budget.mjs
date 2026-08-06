/* global console, process */

import { gzipSync } from 'node:zlib';
import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join, relative } from 'node:path';

const root = process.cwd();
const distDir = join(root, 'dist');
const baselinePath = join(root, 'scripts', 'bundle-budget-baseline.json');
const toleranceBytes = 4096;

function assetFiles() {
  const assetsDir = join(distDir, 'assets');
  return readdirSync(assetsDir)
    .filter((name) => /\.(?:js|css)$/.test(name))
    .map((name) => join(assetsDir, name));
}

function sizeOf(files) {
  return files.reduce((result, file) => {
    const contents = readFileSync(file);
    result.raw += contents.byteLength;
    result.gzip += gzipSync(contents, { level: 9 }).byteLength;
    return result;
  }, { raw: 0, gzip: 0 });
}

function matching(files, pattern) {
  return files.filter((file) => pattern.test(file.split('/').pop()));
}

function precacheFiles() {
  const serviceWorker = readFileSync(join(distDir, 'sw.js'), 'utf8');
  const urls = [...serviceWorker.matchAll(/url:"([^"]+)"/g)].map((match) => match[1]);
  return urls
    .map((url) => join(distDir, url))
    .filter((file) => existsSync(file));
}

function collectBudget() {
  const files = assetFiles();
  const budget = {
    entry_js: sizeOf(matching(files, /^index-[^/]+\.js$/)),
    initial_css: sizeOf(matching(files, /^index-[^/]+\.css$/)),
    vendor: sizeOf(matching(files, /^vendor-[^/]+\.js$/)),
    ui: sizeOf(matching(files, /^ui-[^/]+\.js$/)),
    charts: sizeOf(matching(files, /^charts-[^/]+\.js$/)),
    precache_total: sizeOf(precacheFiles()),
  };
  return {
    generated_from: relative(root, distDir),
    tolerance_bytes: toleranceBytes,
    budget,
  };
}

const current = collectBudget();
const update = process.argv.includes('--update-baseline');
if (update || !existsSync(baselinePath)) {
  writeFileSync(baselinePath, `${JSON.stringify(current, null, 2)}\n`);
  console.log(`Bundle baseline written: ${relative(root, baselinePath)}`);
  console.log(JSON.stringify(current.budget, null, 2));
  process.exit(0);
}

const baseline = JSON.parse(readFileSync(baselinePath, 'utf8'));
const failures = [];
for (const [name, value] of Object.entries(current.budget)) {
  const previous = baseline.budget?.[name];
  if (!previous) {
    failures.push(`${name}: missing baseline`);
    continue;
  }
  for (const metric of ['raw', 'gzip']) {
    const delta = value[metric] - previous[metric];
    if (delta > current.tolerance_bytes) {
      failures.push(`${name}.${metric}: +${delta} bytes (baseline ${previous[metric]}, current ${value[metric]})`);
    }
  }
}

console.log(JSON.stringify({ current: current.budget, baseline: baseline.budget, failures }, null, 2));
if (failures.length) {
  console.error('Bundle budget exceeded. Use --update-baseline only with a reviewed justification.');
  process.exit(1);
}
