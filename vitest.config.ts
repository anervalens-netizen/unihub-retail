import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
    environment: 'node',
    setupFiles: ['./src/test/setup.ts'],
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.test.{ts,tsx}',
        'src/test/**',
        'src/api/generated/contracts.ts',
        'src/api/generated/runtime-schemas.ts',
      ],
      reporter: ['text', 'json', 'json-summary', 'lcov'],
      reportsDirectory: 'coverage/frontend',
      thresholds: {
        statements: 46,
        branches: 36,
        functions: 34,
        lines: 47,
      },
    },
  },
});
