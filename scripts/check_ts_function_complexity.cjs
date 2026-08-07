#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const DEFAULT_ROOT = path.resolve(__dirname, '..');
const DEFAULT_CONFIG = path.join(__dirname, 'ts-function-complexity-ratchet.json');
const IGNORED = new Set([
  'node_modules',
  'generated',
  'dist',
  'build',
  'coverage',
  'playwright-report',
  'test-results',
]);
const TEST_PATTERN = /\.(test|spec)\.(ts|tsx)$/;

function parseArgs(argv) {
  const args = { root: DEFAULT_ROOT, config: DEFAULT_CONFIG, writeBaseline: false, limit: 120 };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === '--root') args.root = path.resolve(argv[++index]);
    else if (value === '--config') args.config = path.resolve(argv[++index]);
    else if (value === '--write-baseline') args.writeBaseline = true;
    else if (value === '--limit') args.limit = Number(argv[++index]);
    else throw new Error(`Unknown argument: ${value}`);
  }
  if (!Number.isInteger(args.limit) || args.limit < 1) throw new Error('Invalid function limit');
  return args;
}

function* files(directory) {
  if (!fs.existsSync(directory)) return;
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const absolute = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      if (!IGNORED.has(entry.name)) yield* files(absolute);
    } else if (/\.(ts|tsx)$/.test(entry.name) && !TEST_PATTERN.test(entry.name)) {
      yield absolute;
    }
  }
}

function relative(root, absolute) {
  return path.relative(root, absolute).split(path.sep).join('/');
}

function nodeName(node, source, stack) {
  if (ts.isConstructorDeclaration(node)) return [...stack, 'constructor'].join('.');
  if (node.name) return [...stack, node.name.getText(source)].join('.');
  const parent = node.parent;
  if (
    ts.isVariableDeclaration(parent)
    || ts.isPropertyDeclaration(parent)
    || ts.isPropertyAssignment(parent)
  ) {
    return [...stack, parent.name.getText(source)].join('.');
  }
  return [...stack, '<anonymous>'].join('.');
}

function isFunction(node) {
  return ts.isFunctionDeclaration(node)
    || ts.isMethodDeclaration(node)
    || ts.isConstructorDeclaration(node)
    || ts.isGetAccessorDeclaration(node)
    || ts.isSetAccessorDeclaration(node)
    || ts.isArrowFunction(node)
    || ts.isFunctionExpression(node);
}

function scanFile(root, absolute) {
  const sourceText = fs.readFileSync(absolute, 'utf8');
  const source = ts.createSourceFile(
    absolute,
    sourceText,
    ts.ScriptTarget.Latest,
    true,
    absolute.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
  const results = [];
  function walk(node, stack) {
    let childStack = stack;
    if (ts.isClassDeclaration(node) && node.name) childStack = [...stack, node.name.text];
    if (isFunction(node)) {
      const qualname = nodeName(node, source, stack);
      const start = source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
      const end = source.getLineAndCharacterOfPosition(node.end).line + 1;
      results.push({
        key: `${relative(root, absolute)}::${qualname}`,
        lineCount: end - start + 1,
      });
      childStack = [...stack, qualname.split('.').at(-1), '<locals>'];
    }
    ts.forEachChild(node, (child) => walk(child, childStack));
  }
  walk(source, []);
  return results;
}

function scan(root) {
  const functions = [];
  for (const absolute of files(path.join(root, 'src'))) {
    functions.push(...scanFile(root, absolute));
  }
  return functions;
}

function evaluate(root, config) {
  const defaultLimit = Number(config.default_max_function_lines ?? 120);
  const legacy = config.legacy_max_function_lines || {};
  const observed = new Set();
  const failures = [];
  for (const fn of scan(root)) {
    observed.add(fn.key);
    const hasLegacy = Object.prototype.hasOwnProperty.call(legacy, fn.key);
    const legacyLimit = hasLegacy ? Number(legacy[fn.key]) : null;
    const allowed = legacyLimit ?? defaultLimit;
    if (fn.lineCount > allowed) {
      failures.push(`${fn.key}: ${fn.lineCount} lines > allowed ${allowed}`);
    } else if (legacyLimit !== null && fn.lineCount < legacyLimit) {
      failures.push(
        fn.lineCount <= defaultLimit
          ? `${fn.key}: legacy function allowance ${legacyLimit} is stale; remove it`
          : `${fn.key}: legacy function allowance ${legacyLimit} is stale; shrink it to ${fn.lineCount}`,
      );
    }
  }
  for (const key of Object.keys(legacy).sort()) {
    if (!observed.has(key)) failures.push(`${key}: stale legacy TypeScript function allowance`);
  }
  return failures;
}

function buildBaseline(root, limit) {
  const legacy = {};
  for (const fn of scan(root)) {
    if (fn.lineCount > limit) legacy[fn.key] = fn.lineCount;
  }
  return {
    version: 1,
    default_max_function_lines: limit,
    legacy_max_function_lines: Object.fromEntries(Object.entries(legacy).sort()),
  };
}

function main(argv = process.argv.slice(2)) {
  const args = parseArgs(argv);
  if (args.writeBaseline) {
    fs.writeFileSync(args.config, `${JSON.stringify(buildBaseline(args.root, args.limit), null, 2)}\n`);
    console.log(`Wrote TypeScript function complexity baseline: ${args.config}`);
    return 0;
  }
  const config = JSON.parse(fs.readFileSync(args.config, 'utf8'));
  const failures = evaluate(args.root, config);
  if (failures.length > 0) {
    console.error('TypeScript function complexity ratchet failed:');
    for (const failure of failures) console.error(`- ${failure}`);
    return 1;
  }
  console.log('TypeScript function complexity ratchet passed.');
  return 0;
}

if (require.main === module) process.exitCode = main();

module.exports = { buildBaseline, evaluate, main, scan, scanFile };
