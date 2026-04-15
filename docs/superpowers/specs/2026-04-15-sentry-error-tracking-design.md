# Design: Sentry Error Tracking

**Date:** 2026-04-15
**Status:** Approved

## Problema

Erorile negestionate în backend (Python exceptions) și frontend (React crashes, JS errors)
nu sunt capturate nicăieri. La un crash în producție, diagnosticul depinde de:
- `journalctl -u unihub-backend` (loguri text, fără context)
- Rapoarte manuale de la utilizatori

Nu există alertă automată, stack trace cu context de request, sau trending pe erori.

## Soluție

**Sentry cloud free tier** (5K events/month — suficient pentru un tool intern cu ~20 utilizatori).

Alternativa GlitchTip (self-hosted) necesită 5 containere Docker noi (web, worker, beat, postgres, redis)
— overhead nejustificat pentru acest volum. Sentry cloud e zero-infra, setup în 15 minute.

## Integrare

### Backend — `sentry-sdk[fastapi]`

```python
# main.py — inițializat la nivel de modul, înainte de app = FastAPI(...)
import sentry_sdk
sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN", ""),      # gol = dezactivat
    integrations=[StarletteIntegration(), FastApiIntegration(), LoggingIntegration(...)],
    traces_sample_rate=0.1,
    environment=os.getenv("UNIHUB_ENV", "development"),
)
```

`StarletteIntegration` + `FastApiIntegration` capturează automat:
- Excepții negestionate din orice endpoint
- Request path, method, status code pe fiecare eveniment
- User ID din JWT (setat manual via `sentry_sdk.set_user`)

### Frontend — `@sentry/react`

```typescript
// src/main.tsx — înainte de createRoot
if (import.meta.env.VITE_SENTRY_DSN) {
  Sentry.init({ dsn, integrations: [Sentry.browserTracingIntegration()], ... });
}
```

Capturează: JS errors negestionate, React error boundaries, network errors.

## Fișiere modificate

1. `backend/requirements.txt` — adaugă `sentry-sdk[fastapi]`
2. `backend/main.py` — `init_sentry()` la nivel de modul
3. `src/main.tsx` — `Sentry.init()` condițional
4. `package.json` — adaugă `@sentry/react`
5. `.env` — adaugă `SENTRY_DSN=` (gol implicit)

## Comportament când DSN e gol

- Backend: `sentry_sdk.init(dsn="")` → SDK se dezactivează, zero overhead
- Frontend: condiție `if (VITE_SENTRY_DSN)` → `Sentry.init` nu se apelează

## Activare

1. Creează cont pe [sentry.io](https://sentry.io) (free tier)
2. Crează două proiecte: `unihub-backend` (Python) și `unihub-frontend` (React)
3. Copiază DSN-urile în `.env`:
   ```
   SENTRY_DSN=https://xxx@oyyy.ingest.sentry.io/zzz
   VITE_SENTRY_DSN=https://xxx@oyyy.ingest.sentry.io/zzz
   ```
4. Restartează backend + rebuild frontend

## Criterii de succes

- [ ] Erori Python noi apar în Sentry dashboard în <30s
- [ ] Erori React noi apar în Sentry dashboard
- [ ] Cu `SENTRY_DSN=` gol, pytest nu eșuează, build trece
- [ ] pytest 78/78 trece
