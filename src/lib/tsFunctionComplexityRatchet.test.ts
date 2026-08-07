import { createRequire } from 'node:module';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { afterEach, describe, expect, it } from 'vitest';

interface RatchetConfig {
  version: number;
  default_max_function_lines: number;
  legacy_max_function_lines: Record<string, number>;
}

interface RatchetModule {
  evaluate(root: string, config: RatchetConfig): string[];
}

const require = createRequire(import.meta.url);
const ratchet = require('../../scripts/check_ts_function_complexity.cjs') as RatchetModule;
const roots: string[] = [];

function makeRoot(): string {
  const root = join(tmpdir(), `unihub-ts-ratchet-${process.pid}-${roots.length}`);
  roots.push(root);
  mkdirSync(join(root, 'src'), { recursive: true });
  return root;
}

afterEach(() => {
  while (roots.length > 0) {
    const root = roots.pop();
    if (root) rmSync(root, { recursive: true, force: true });
  }
});

describe('TypeScript function complexity ratchet', () => {
  it('rejects a new oversized function', () => {
    const root = makeRoot();
    writeFileSync(
      join(root, 'src/example.ts'),
      [
        'export function oversized() {',
        '  const first = 1;',
        '  const second = 2;',
        '  return first + second;',
        '}',
        '',
      ].join('\n'),
    );
    expect(ratchet.evaluate(root, {
      version: 1,
      default_max_function_lines: 4,
      legacy_max_function_lines: {},
    })).toEqual(['src/example.ts::oversized: 5 lines > allowed 4']);
  });

  it('freezes and retires a legacy function allowance', () => {
    const root = makeRoot();
    const source = join(root, 'src/example.ts');
    const key = 'src/example.ts::oversized';
    const config: RatchetConfig = {
      version: 1,
      default_max_function_lines: 3,
      legacy_max_function_lines: { [key]: 5 },
    };
    writeFileSync(
      source,
      ['export function oversized() {', '  const value = 1;', '  return value;', '}', ''].join('\n'),
    );
    expect(ratchet.evaluate(root, config)).toEqual([
      `${key}: legacy function allowance 5 is stale; shrink it to 4`,
    ]);

    rmSync(source);
    expect(ratchet.evaluate(root, config)).toEqual([
      `${key}: stale legacy TypeScript function allowance`,
    ]);
  });
});
