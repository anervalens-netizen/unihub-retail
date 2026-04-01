# CLAUDE.md — Ghid pentru sesiunile Claude

Acest fisier explica tot ce trebuie sa stii pentru a lucra eficient pe proiectul **UniHub**.
Citeste-l la inceputul fiecarei sesiuni noi.

---

## Cine esti si cu cine lucrezi

Andrei este managerul echipei Mobiup. Nu are background tehnic avansat dar este pasionat de development.
Lucreaza exclusiv cu Claude. Are bypass approvals activat — executa fara a cere confirmare pentru fiecare pas.

Tonul corect: direct, tehnic, fara padding. Explica pe scurt ce ai facut si de ce, fara liste lungi de recapitulari.

---

## Starea proiectului

- Aplicatie deployed pe server 192.168.0.68, accesibila la https://unihub.astancu.eu/
- Stack: React 19 + Vite + TypeScript (frontend) / FastAPI + asyncpg + PostgreSQL 18 (backend)
- Toate cele 5 module sunt functionale: Hub, Focus, Agenti, Vizite, Setari
- 24 pytest passing, typecheck si build passing
- Integrata cu Platforma-Mobiup (paralela) pentru vizite: SQLite la `/opt/Mobiup/Platforma-Mobiup/db/visit_reports.db`

Pornire dev:
```
npm run dev          # frontend pe :3000
npm run dev:backend  # backend pe :8000
```

Deploy productie (dupa modificari):
```bash
cd /opt/Mobiup/unihub
git pull
npm run build
sudo systemctl restart unihub-backend
```

---

## Structura importanta

### Frontend — `src/components/`
| Fisier | Rol |
|--------|-----|
| `App.tsx` | Auth + tab routing + **localStorage persistence tab activ** |
| `MainLayout.tsx` | Shell principal, navigare, filtre |
| `Dashboard.tsx` | Tab Hub — carduri Incentive/Promo, navigare catre Focus |
| `Campaigns.tsx` | Tab Focus — campanii, incentive Aprilie per-produs |
| `Agents.tsx` | Tab Agenti — include AgentDrawer, AgentDetails |
| `SalariiSubtab.tsx` | Sub-tab Salarii in Agenti |
| `VisiteSubtab.tsx` | Tab Vizite — **ASM accordion + drawer vizita cu poze** |
| `Settings.tsx` | Tab Setari (admin) |
| `ErrorBoundary.tsx` | Error boundary React |

### Backend — `backend/routers/`
| Router | Prefix |
|--------|--------|
| `auth` | `/api/auth` |
| `dashboard` | `/api/dashboard` |
| `campaigns` | `/api/campaigns` |
| `filters` | `/api/filters` |
| `imports` | `/api/imports` |
| `stores` | `/api/stores` |
| `visits` | `/api/visits` |
| `visits_report` | `/api/visits-report` — **citeste SQLite Platforma-Mobiup** |
| `admin` | `/api/admin` |
| `agents` | `/api/agents` |
| `salarii` | `/api/salarii` |

### Baza de date
- Schema unica: `backend/db/schema_v2.sql`
- Aplicata hash-based la boot via `ensure_schema_current()` in `backend/db/connection.py`
- **Nu modifica schema direct in DB** — editeaza `schema_v2.sql` si reporneste backend-ul
- Reporting pe agregate: `reporting_agent_*`, `reporting_item_*`, `reporting_focus_*`, `reporting_category_*`

### Integrare Platforma-Mobiup (vizite)
- SQLite read-only: `/opt/Mobiup/Platforma-Mobiup/db/visit_reports.db`
- Poze: `/opt/Mobiup/Platforma-Mobiup/local-data/visit-reports/images/{visit_id}/`
- Router `visits_report.py` citeste SQLite async via `run_in_executor` (non-blocking)
- Endpoint `/api/visits-report/photo/{visit_id}/{filename}` serveste pozele cu auth (`FileResponse`)
- Frontend: componenta `AuthImage` face fetch blob cu axios + `URL.createObjectURL` (nu `<img src>` direct, nu trimite header Authorization)

### Hub Specials (incentive/promotii)
- Configuratie: `data/hub_specials.json`
- Logica: `backend/services/dashboard_specials.py`
- **Promotia Martie a fost inchisa (1 aprilie 2026)** — cheia `promotion` a fost eliminata din hub_specials.json
- **Incentive Aprilie 2026**: mecanism per-produs (nu flat rate)
  - Fisier: `data/Incentiv Mobiup-Mobicell Aprilie 2026.xlsx` (col A = cod produs, col C = valoare incentive: 5/10/25 RON)
  - Calcul: `SUM(qty × reward_per_item)` calculat in Python dupa fetch SQL
  - Cache invalidat la modificarea fisierului Excel (tuple `(filepath, mtime)`)

---

## Reguli de lucru

### Nu citi din `sales_transactions` pentru raportare
Toate query-urile de raportare merg pe agregatele `reporting_*`. Exceptie: lookup-uri administrative punctuale.

### Modele Pydantic in `backend/models.py`
Orice camp returnat de un endpoint trebuie sa fie declarat explicit in modelul Pydantic corespunzator, altfel Pydantic il elimina din raspuns.

### Filtre in frontend
Filtrul global (firma, regional, asm, magazin) din `MainLayout` este shared intre Hub si Focus.
Modulul **Agenti** are filtrele sale proprii, independente.

### Autentificare
- Roluri: `admin`, `management`, `tl`
- `admin` si `management` vad totul
- `tl` vede doar magazinele alocate lui
- Parole default (dev): `9999` pentru admin si management

### ErrorBoundary
Importat ca `import { ErrorBoundary } from './ErrorBoundary'` in `Agents.tsx`.
**Nu** mai exista `error-catcher.tsx` la radacina proiectului.

---

## Agentul MiniMax

Claude are acces la MiniMax M2.7 ca sub-agent de coding via MCP:

- Tool: `minimax_code(task, context, language)` — genereaza cod
- Tool: `minimax_fix(code, error, language)` — repara bug-uri
- Tool: `minimax_review(code, focus)` — code review
- Tool: `minimax_ask(question)` — intrebari tehnice

Foloseste MiniMax pentru task-uri de implementare mare sau cand vrei un al doilea punct de vedere pe cod.

---

## Cum sa incepi o sesiune noua

1. Citeste acest fisier
2. Citeste `HANDOFF.md` pentru detalii arhitecturale
3. Intreaba-l pe Andrei ce vrea sa lucreze azi
4. Porneste aplicatia daca e nevoie: `npm run dev` + `npm run dev:backend`

---

## Ce sa nu faci

- Nu crea fisiere temporare in radacina proiectului (`fix.py`, `patch.txt`, etc.) — curata-le dupa
- Nu modifica schema direct in DB
- Nu reseta parolele utilizatorilor fara confirmare explicita
- Nu folosi `../../error-catcher` ca import path — e mutat in `src/components/ErrorBoundary.tsx`
