# Design: Error Tracking Intern UniHub

**Date:** 2026-04-15
**Status:** Approved

## Problema

Erorile negestionate în backend și frontend nu sunt capturate sistematic.
Diagnosticul depinde de rapoarte manuale sau căutare în `journalctl`.
Nu există vizibilitate centralizată, alertă activă, sau context structurat per eroare.

## Soluție

Error tracking intern, zero dependențe externe:
- Tabel `error_logs` în PostgreSQL (deja rulat)
- Handler Python async care capturează `logger.error/exception` → INSERT în PG
- Hook-uri JS globale (`window.onerror`, `onunhandledrejection`) → `POST /api/errors`
- Badge roșu activ pe iconița Settings (admin) când există erori nevăzute
- Pagină dedicată în Settings → tab "Erori sistem"

## Schema

```sql
CREATE TABLE error_logs (
    id          SERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    source      TEXT NOT NULL CHECK (source IN ('backend', 'frontend')),
    level       TEXT NOT NULL CHECK (level IN ('error', 'warning')),
    message     TEXT NOT NULL,
    traceback   TEXT,
    path        TEXT,
    user_id     INT REFERENCES users(id) ON DELETE SET NULL,
    extra       JSONB,
    seen        BOOLEAN NOT NULL DEFAULT false
);

CREATE INDEX idx_error_logs_ts   ON error_logs(ts DESC);
CREATE INDEX idx_error_logs_seen ON error_logs(seen) WHERE seen = false;
```

Retenție: 30 zile. Curățare rulată la boot (șterge rânduri cu `ts < now() - interval '30 days'`).

## Arhitectură

### Backend — DBErrorHandler

`logging_config.py` primește un nou `logging.Handler` (`DBErrorHandler`) care:
- Se activează doar dacă pool-ul DB e disponibil (după boot)
- Pune înregistrările într-o coadă `asyncio.Queue`
- Un worker asyncio (`_db_error_worker`) consumă coada și face INSERT în batch
- Non-blocking: nu afectează latența request-urilor
- Capturează: `record.getMessage()`, `formatException(record.exc_info)`, `record.name` ca path

Înregistrat în `setup_logging()` pentru nivelul `logging.ERROR`.
Activat explicit după `init_db_pool()` în lifespan via `attach_db_error_handler(pool)`.

### Frontend — hook-uri globale

În `src/main.tsx`, înainte de `createRoot`:

```typescript
window.onerror = (message, source, lineno, colno, error) => {
    postFrontendError({ message, path: window.location.pathname,
                        traceback: error?.stack, extra: { source, lineno, colno } })
}
window.onunhandledrejection = (event) => {
    postFrontendError({ message: String(event.reason),
                        path: window.location.pathname,
                        traceback: event.reason?.stack })
}
```

`ErrorBoundary.tsx` existent — extins să apeleze același `postFrontendError`.

`postFrontendError` trimite `POST /api/errors` cu retry 0 (fire-and-forget, nu blochează UX).
User ID inclus dacă tokenul JWT e disponibil în memorie la momentul erorii.

### Rate limiting frontend

`POST /api/errors` — fără auth (eroarea poate apărea pre-login).
Rate limit: sliding window 10 req/min per IP, implementat în memorie (dict + timestamp).
Payload maxim: 8KB. Dacă depășește, trunchiază `traceback`.

## API

| Endpoint | Auth | Descriere |
|----------|------|-----------|
| `POST /api/errors` | fără | Ingestie erori frontend |
| `GET /api/admin/error-logs` | admin | Listă paginată, filtre: source/level/seen/date |
| `POST /api/admin/error-logs/mark-seen` | admin | Marchează toate ca `seen=true` |
| `DELETE /api/admin/error-logs/old` | admin | Șterge înregistrări mai vechi de 30 zile |

`GET /api/admin/error-logs` params: `source`, `level`, `seen` (bool), `from_date`, `to_date`, `page` (default 1), `page_size` (default 50).

Răspuns badge (folosit de polling): `GET /api/admin/error-logs?seen=false&page_size=1` returnează `total` în header sau body.

Endpoint dedicat pentru badge: `GET /api/admin/error-logs/unseen-count` → `{"count": N}`.

## UI

### Badge activ

`MainLayout.tsx` — pentru useri cu rol `admin`:
- `useEffect` cu `setInterval(60_000)` apelează `GET /api/admin/error-logs/unseen-count`
- Dacă `count > 0`: badge roșu cu numărul pe iconița Settings din sidebar
- La click pe Settings → badge dispare vizual (poll-ul confirmă după mark-seen)

### Tab "Erori sistem" în Settings

`Settings.tsx` primește un nou sub-tab "Erori sistem" (vizibil doar admin).

Componentă nouă: `ErrorLogsTab.tsx`

Layout:
- Filtre sus: dropdown Source (Toate/Backend/Frontend), dropdown Level (Toate/Error/Warning), checkbox "Doar nevăzute", date range
- Buton "Marchează toate ca văzute" (disabled dacă count=0)
- Tabel: Timestamp / Sursă / Nivel / Mesaj (truncat 80 chars) / Path / User
- Click pe rând → modal/drawer cu detalii complete (traceback formatat monospace)
- Paginare jos

## Fișiere noi / modificate

1. `backend/db/schema_v2.sql` — adaugă `error_logs`
2. `backend/logging_config.py` — adaugă `DBErrorHandler` + `attach_db_error_handler(pool)`
3. `backend/main.py` — apelează `attach_db_error_handler` după `init_db_pool`
4. `backend/routers/errors.py` (nou) — `POST /api/errors` cu rate limiting
5. `backend/routers/admin.py` — adaugă endpoints `GET/POST/DELETE error-logs`
6. `src/main.tsx` — hook-uri globale `window.onerror` + `onunhandledrejection`
7. `src/components/ErrorBoundary.tsx` — extins cu `postFrontendError`
8. `src/api/errors.ts` (nou) — `postFrontendError`, `getUnseenCount`, `markAllSeen`, `getErrorLogs`
9. `src/components/ErrorLogsTab.tsx` (nou) — UI tab erori
10. `src/components/Settings.tsx` — adaugă tab + import `ErrorLogsTab`
11. `src/components/MainLayout.tsx` — badge polling pentru admin

## Criterii de succes

- [ ] `logger.error("test")` în backend apare în `error_logs` în <2s
- [ ] JS error în frontend (throw în console) apare în `error_logs`
- [ ] Badge roșu apare în sidebar în max 60s după o eroare nouă
- [ ] "Marchează toate ca văzute" → badge dispare
- [ ] Rate limit: al 11-lea request în același minut returnează 429
- [ ] Erori mai vechi de 30 zile șterse la boot
- [ ] pytest trece (noi teste pentru rate limiter + endpoints)
- [ ] Cu DB down, `DBErrorHandler` nu crașează backend-ul (eroare silențioasă în handler)
