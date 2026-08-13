#!/usr/bin/env node
/* global console, process */

import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, relative, resolve } from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { createCoverageMap } = require('istanbul-lib-coverage');
const root = resolve(import.meta.dirname, '..');

function parseArgs(argv) {
  const values = { manifest: 'scripts/frontend-critical-coverage.json', coverage: 'coverage/coverage-final.json', evidence: null };
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    if (!['--manifest', '--coverage', '--evidence'].includes(key) || !argv[index + 1]) throw new Error(`Unknown or incomplete argument: ${key}`);
    values[key.slice(2)] = argv[++index];
  }
  return values;
}

function repositoryPath(filename) {
  const absolute = resolve(filename);
  return relative(root, absolute).replaceAll('\\', '/');
}

function validateManifest(manifest) {
  const failures = [];
  const requiredCases = Object.entries(manifest.lifecycle_case_definitions ?? {})
    .filter(([, definition]) => definition.required).map(([name]) => name).sort();
  const groupIds = new Set();
  const files = new Set();
  const testIds = new Set();
  for (const group of manifest.groups ?? []) {
    if (groupIds.has(group.id)) failures.push(`duplicate group id: ${group.id}`);
    groupIds.add(group.id);
    const actualCases = Object.keys(group.cases ?? {}).sort();
    if (JSON.stringify(actualCases) !== JSON.stringify(requiredCases)) failures.push(`${group.id}: lifecycle case keys do not match required manifest keys`);
    for (const caseName of requiredCases) {
      const testId = group.cases?.[caseName];
      const expected = `fe.${group.id}.${caseName}`;
      if (testId !== expected) failures.push(`${group.id}/${caseName}: expected test id ${expected}, received ${String(testId)}`);
      if (testIds.has(testId)) failures.push(`duplicate lifecycle test id: ${testId}`);
      testIds.add(testId);
    }
    for (const filename of group.files ?? []) {
      if (files.has(filename)) failures.push(`critical file appears in multiple groups: ${filename}`);
      files.add(filename);
      if (!existsSync(resolve(root, filename))) failures.push(`critical file missing: ${filename}`);
    }
  }
  const matrixGroups = [...(manifest.browser_matrix?.groups ?? [])].sort();
  if (JSON.stringify(matrixGroups) !== JSON.stringify([...groupIds].sort())) failures.push('browser matrix groups do not exactly match lifecycle groups');
  const componentCases = [...(manifest.browser_matrix?.component_runner?.required_cases ?? [])].sort();
  if (JSON.stringify(componentCases) !== JSON.stringify(requiredCases)) failures.push('component runner cases do not exactly match lifecycle definitions');
  return { failures, files: [...files].sort(), groupIds: [...groupIds].sort(), requiredCases, testIds: [...testIds].sort() };
}

function coverageIndex(raw) {
  const map = createCoverageMap(raw);
  const byPath = new Map();
  for (const filename of map.files()) {
    const key = repositoryPath(filename);
    byPath.set(key, map.fileCoverageFor(filename));
  }
  return { map, byPath };
}

function metric(summary, name) {
  const item = summary[name];
  return { total: item.total, covered: item.covered, pct: item.total === 0 ? 100 : Number(item.pct) };
}

function changedLines(base) {
  const output = execFileSync('git', ['diff', '--unified=0', '--diff-filter=AM', base, '--', 'src'], { cwd: root, encoding: 'utf8' });
  const result = new Map();
  let current = null;
  for (const line of output.split('\n')) {
    if (line.startsWith('+++ b/')) { current = line.slice(6); continue; }
    const match = /^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@/.exec(line);
    if (!current || !match) continue;
    const start = Number(match[1]);
    const count = Number(match[2] ?? 1);
    const lines = result.get(current) ?? new Set();
    for (let number = start; number < start + count; number += 1) lines.add(number);
    result.set(current, lines);
  }
  return result;
}

function changedCriticalCoverage(base, criticalFiles, byPath) {
  const changed = changedLines(base);
  const relevant = [];
  for (const filename of criticalFiles) {
    const coverage = byPath.get(filename);
    if (!coverage) continue;
    const executable = coverage.getLineCoverage();
    for (const number of changed.get(filename) ?? []) {
      if (Object.hasOwn(executable, number)) relevant.push({ file: filename, line: number, hits: executable[number] });
    }
  }
  const covered = relevant.filter((item) => item.hits > 0).length;
  return {
    total: relevant.length,
    covered,
    pct: relevant.length === 0 ? 100 : Number((covered * 100 / relevant.length).toFixed(2)),
    uncovered: relevant.filter((item) => item.hits === 0).map((item) => `${item.file}:${item.line}`),
  };
}

function writeEvidence(filename, evidence) {
  if (!filename) return;
  const absolute = resolve(filename);
  mkdirSync(dirname(absolute), { recursive: true });
  writeFileSync(absolute, `${JSON.stringify(evidence, null, 2)}\n`);
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const manifest = JSON.parse(readFileSync(resolve(args.manifest), 'utf8'));
  const validation = validateManifest(manifest);
  const failures = [...validation.failures];
  if (!existsSync(resolve(args.coverage))) failures.push(`coverage file missing: ${args.coverage}`);
  let evidence = { version: 1, pass: false, manifest: repositoryPath(args.manifest), coverage: repositoryPath(args.coverage), failures };
  if (failures.length === 0) {
    const raw = JSON.parse(readFileSync(resolve(args.coverage), 'utf8'));
    const { map, byPath } = coverageIndex(raw);
    const globalSummary = map.getCoverageSummary();
    const global = Object.fromEntries(['statements', 'branches', 'functions', 'lines'].map((name) => [name, metric(globalSummary, name)]));
    for (const [name, minimum] of Object.entries(manifest.coverage_thresholds.global)) {
      if (global[name].pct < minimum) failures.push(`global ${name}: ${global[name].pct}% < ${minimum}%`);
    }
    const criticalFiles = {};
    for (const filename of validation.files) {
      const fileCoverage = byPath.get(filename);
      if (!fileCoverage) {
        failures.push(`${filename}: absent from coverage report`);
        criticalFiles[filename] = null;
        continue;
      }
      const summary = fileCoverage.toSummary();
      const result = { lines: metric(summary, 'lines'), branches: metric(summary, 'branches') };
      criticalFiles[filename] = result;
      if (result.lines.pct < manifest.coverage_thresholds.each_critical_file.lines) failures.push(`${filename} lines: ${result.lines.pct}% < ${manifest.coverage_thresholds.each_critical_file.lines}%`);
      if (result.branches.pct < manifest.coverage_thresholds.each_critical_file.branches) failures.push(`${filename} branches: ${result.branches.pct}% < ${manifest.coverage_thresholds.each_critical_file.branches}%`);
    }
    const changed = changedCriticalCoverage(manifest.baseline_source_sha, validation.files, byPath);
    if (changed.pct < manifest.coverage_thresholds.changed_critical_lines) failures.push(`changed critical lines: ${changed.pct}% < ${manifest.coverage_thresholds.changed_critical_lines}%`);
    evidence = {
      version: 1, pass: failures.length === 0, manifest: repositoryPath(args.manifest), coverage: repositoryPath(args.coverage),
      baseline_source_sha: manifest.baseline_source_sha, lifecycle: { groups: validation.groupIds.length, files: validation.files.length, test_ids: validation.testIds.length },
      global, critical_files: criticalFiles, changed_critical_lines: changed, failures,
    };
  }
  writeEvidence(args.evidence, evidence);
  if (failures.length) {
    console.error('Frontend critical coverage failed:');
    for (const failure of failures) console.error(`- ${failure}`);
    process.exitCode = 1;
  } else {
    console.log(`Frontend critical coverage passed: ${evidence.lifecycle.files} files, ${evidence.lifecycle.test_ids} lifecycle IDs.`);
  }
}

main();
