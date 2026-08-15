#!/usr/bin/env node
/* global console, process */

import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { basename, dirname, relative, resolve } from 'node:path';
import ts from 'typescript';

const root = resolve(import.meta.dirname, '..');
const excludedParts = new Set(['node_modules', 'generated', 'dist', 'build', 'coverage', 'test-results', 'playwright-report']);
const testPattern = /\.(?:test|spec)\.(?:ts|tsx)$/;

function parseArgs(argv) {
  const result = { manifest: 'scripts/frontend-critical-coverage.json', evidence: null };
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    if (!['--manifest', '--evidence'].includes(key) || !argv[index + 1]) throw new Error(`Unknown or incomplete argument: ${key}`);
    result[key.slice(2)] = argv[++index];
  }
  return result;
}

function* sourceFiles(directory) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const absolute = resolve(directory, entry.name);
    if (entry.isDirectory()) {
      if (!excludedParts.has(entry.name)) yield* sourceFiles(absolute);
    } else if (/\.(?:ts|tsx)$/.test(entry.name) && !testPattern.test(entry.name)) yield absolute;
  }
}

function relativePath(absolute) { return relative(root, absolute).replaceAll('\\', '/'); }
function lineCount(text) { return text === '' ? 0 : text.split(/\r?\n/).length; }
function functionName(node, source) {
  if (node.name) return node.name.getText(source);
  const parent = node.parent;
  if (ts.isVariableDeclaration(parent) || ts.isPropertyAssignment(parent) || ts.isPropertyDeclaration(parent)) return parent.name.getText(source);
  return '<anonymous>';
}
function isFunction(node) {
  return ts.isFunctionDeclaration(node) || ts.isMethodDeclaration(node) || ts.isConstructorDeclaration(node)
    || ts.isGetAccessorDeclaration(node) || ts.isSetAccessorDeclaration(node)
    || ts.isArrowFunction(node) || ts.isFunctionExpression(node);
}

function scanFile(absolute) {
  const text = readFileSync(absolute, 'utf8');
  const source = ts.createSourceFile(absolute, text, ts.ScriptTarget.Latest, true, absolute.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const functions = [];
  const forbiddenPresenterEffects = [];
  function walk(node) {
    if (isFunction(node)) {
      const start = source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
      const end = source.getLineAndCharacterOfPosition(node.end).line + 1;
      functions.push({ name: functionName(node, source), start, end, lines: end - start + 1 });
    }
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === 'fetch') forbiddenPresenterEffects.push('fetch');
    if (ts.isIdentifier(node) && ['localStorage', 'sessionStorage'].includes(node.text)) forbiddenPresenterEffects.push(node.text);
    if (ts.isBinaryExpression(node) && node.operatorToken.kind >= ts.SyntaxKind.FirstAssignment && node.operatorToken.kind <= ts.SyntaxKind.LastAssignment) {
      const left = node.left.getText(source);
      if (/^(?:window|document|globalThis)\./.test(left)) forbiddenPresenterEffects.push(`global mutation ${left}`);
    }
    ts.forEachChild(node, walk);
  }
  walk(source);
  return { lines: lineCount(text), functions, forbiddenPresenterEffects: [...new Set(forbiddenPresenterEffects)] };
}

function validateManifest(manifest) {
  const failures = [];
  const files = new Set();
  const requiredCases = Object.entries(manifest.lifecycle_case_definitions ?? {}).filter(([, value]) => value.required).map(([key]) => key).sort();
  for (const group of manifest.groups ?? []) {
    const cases = Object.keys(group.cases ?? {}).sort();
    if (JSON.stringify(cases) !== JSON.stringify(requiredCases)) failures.push(`${group.id}: lifecycle cases are incomplete`);
    for (const [caseName, testId] of Object.entries(group.cases ?? {})) {
      if (testId !== `fe.${group.id}.${caseName}`) failures.push(`${group.id}/${caseName}: non-canonical lifecycle test id ${testId}`);
    }
    for (const filename of group.files ?? []) {
      files.add(filename);
      if (!existsSync(resolve(root, filename))) failures.push(`manifest source missing: ${filename}`);
    }
  }
  return { failures, criticalFiles: [...files].sort() };
}

function readLockedRatchets() {
  const fileRatchet = JSON.parse(readFileSync(resolve(root, 'scripts/complexity-ratchet.json'), 'utf8'));
  const functionRatchet = JSON.parse(readFileSync(resolve(root, 'scripts/ts-function-complexity-ratchet.json'), 'utf8'));
  return {
    frontendFiles: Object.keys(fileRatchet.legacy_max_lines ?? {}).filter((name) => name.startsWith('src/')).sort(),
    frontendFunctions: Object.keys(functionRatchet.legacy_max_function_lines ?? {}).sort(),
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
  const priority = new Set(manifest.ownership_boundaries?.priority_pages ?? []);
  const files = {};
  let functionCount = 0;
  for (const absolute of sourceFiles(resolve(root, 'src'))) {
    const filename = relativePath(absolute);
    const result = scanFile(absolute);
    functionCount += result.functions.length;
    const controller = /^use[A-Z].*\.(?:ts|tsx)$/.test(basename(filename));
    const presenter = /(?:^|\/)presenters?\.(?:ts|tsx)$/.test(filename) || /Presenter\.(?:ts|tsx)$/.test(filename);
    files[filename] = { lines: result.lines, functions: result.functions.length, controller, presenter };
    if (result.lines > 600) failures.push(`${filename}: ${result.lines} lines > 600`);
    if (controller && result.lines > 250) failures.push(`${filename}: controller ${result.lines} lines > 250`);
    if (priority.has(basename(filename)) && result.lines > 450) failures.push(`${filename}: priority page ${result.lines} lines > 450`);
    for (const fn of result.functions) if (fn.lines > 120) failures.push(`${filename}::${fn.name}: ${fn.lines} lines > 120`);
    if (presenter && result.forbiddenPresenterEffects.length) failures.push(`${filename}: presenter side effects: ${result.forbiddenPresenterEffects.join(', ')}`);
  }
  const ratchets = readLockedRatchets();
  for (const filename of ratchets.frontendFiles) failures.push(`${filename}: frontend legacy file allowance must be removed`);
  for (const key of ratchets.frontendFunctions) failures.push(`${key}: legacy TypeScript function allowance must be removed`);
  const evidence = {
    version: 1, pass: failures.length === 0, manifest: relativePath(resolve(args.manifest)),
    checked: { files: Object.keys(files).length, functions: functionCount, critical_files: validation.criticalFiles.length },
    thresholds: { file_lines: 600, function_lines: 120, controller_lines: 250, priority_page_lines: 450 },
    locked_frontend_ratchets: ratchets, files, failures,
  };
  writeEvidence(args.evidence, evidence);
  if (failures.length) {
    console.error('Frontend structure contract failed:');
    for (const failure of failures) console.error(`- ${failure}`);
    process.exitCode = 1;
  } else {
    console.log(`Frontend structure contract passed: ${evidence.checked.files} files, ${functionCount} functions.`);
  }
}

main();
