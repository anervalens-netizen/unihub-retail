# Design: Vitest — frontend unit tests (pure utilities)

**Date:** 2026-04-15
**Branch:** `test/vitest-setup`
**Status:** Approved

## Scope

Opțiunea A: doar utilitare pure, fără React/DOM.

Fișiere acoperite:
- `src/lib/formatters.ts` — `formatCurrency`, `formatInt`, `formatPercent`
- `src/lib/viewCache.ts` — `getCachedView`, `setCachedView`, eviction la MAX_CACHE_SIZE=50

Excluse din scop acum:
- Componente React (necesită jsdom + @testing-library/react)
- API clients (necesită mock axios)
- filterValues.ts (importă AppFilters din MainLayout — dep pe React component)

## Setup

### Instalare
```bash
npm install --save-dev vitest
```
Zero dependențe adiționale — vitest rulează TypeScript direct fără jsdom.

### vite.config.ts
Adaugă bloc `test` în `defineConfig`:
```ts
test: {
  environment: 'node',
  include: ['src/**/*.test.ts'],
}
```

### package.json
```json
"test": "vitest run",
"test:watch": "vitest"
```

## Fișiere de test

- `src/lib/formatters.test.ts` — edge cases: null, NaN, 0, valori negative, valori mari
- `src/lib/viewCache.test.ts` — miss, hit fresh, hit stale, eviction la limită

## Criterii de succes

- [ ] `npm test` rulează și trece
- [ ] typecheck curat
- [ ] Fără dependențe noi în afară de vitest devDep
