# Plan: Integrare Grile native în retail.unihub.ro

> Status: **Faza 1 + Faza 2 IMPLEMENTATE și deployate (2026-05-31).** Read-only, în paralel cu aplicația veche.
> Update 2026-06-01: closeout-ul Mai 2026 s-a făcut în aplicația veche `grile-salarii`: finalize + arhivă completă + reset live spre Iunie 2026, fără schimbare de linkuri.
> Rămâne: Faza 3 (validare paralelă câteva zile) + Faza 4 (cutover read/verify). Finalize/archive/reset NU s-au mutat.
> Autori: server-Claude + review Codex. Data: 2026-05-31.
>
> **Implementat în Faza 1+2:** schema `grile_sheets`/`grile_runs`/`grile_store_status`; backend `routers/grile.py` + `services/grile.py` + `services/grile_sheets.py` + `repositories/grile.py`; job arq `grile_check_background` (concurrency 3, thread-local Google client); auto-trigger best-effort după import (`services/imports.py` + `worker.py`); subtab `GrileSubtab.tsx` în Management; seed `backend/scripts/seed_grile_sheets.py` (75 magazine). Validat end-to-end prin coada arq (run #4: 0 erori, 75 magazine, ~2 min).
> Constrângere hard rămasă: `finalize_month.py`, `archive_month.py`, `reset_month.py`, `add_store.py` și operațiile de mentenanță Google Sheets rămân în `grile-salarii` până la o decizie explicită de portare.

---

## 1. Obiectiv

Mutarea graduală a verificării grilelor salariale în retail, ca subtab nativ în **Management → Grile**, cu:
- verificare automată zilnică după importul vânzărilor (fără upload separat de target/vânzări);
- un singur buton „Rulează verificare" + status rulare + progres;
- nivel tehnic/performanță la standardul retail (job async, rezultate persistate în DB).

Strategie: **strangler / paralel, read-only**. Construim în retail lângă aplicația veche; retragem `grile-salarii` (sau doar partea de read/verify) **după** câteva zile cu rezultate identice.

## 2. Constrângeri hard (nenegociabile)

- **Nu se schimbă linkurile magazinelor.** Fiecare magazin are un Google Sheet permanent (`grile-salarii/AGENTS.md` l.24). Copiem Sheet ID-urile read-only; nu rescriem `sheets_registry.json`, nu recreăm linkuri.
- **Nu se atinge `finalize_month` / `archive_month` / `reset_month` / `add_store` / `generate_missing_grile` / `unlock_agent_name_cells` / `repair_agent1_extra_section`** — rămân în `grile-salarii`. 1 iunie 2026 a fost executat acolo.
- **Google read-only din retail:** scope-uri `spreadsheets.readonly` + `drive.metadata.readonly`, chiar dacă service account-ul are Editor. Codul retail nu are capabilitate de scriere → nu poate strica grilele.
- Cod nou în retail respectă pattern-ul 3-tier (router → service → repository) și convențiile din `CLAUDE.md`.

## 3. Constatări validate (pe date reale, 2026-05-31)

| # | Constatare | Dovadă |
|---|---|---|
| 1 | `cod_locatie` = `stores.site_code`, cheie unică neambiguă | join confirmat; elimină coliziunile de nume (Mega Mall Mobiup vs Mobicell) |
| 2 | Fișierul de vânzări = exact DB | `AccValTarget`=`store_targets.target_value`, `AccValRealizat`=`Σ reporting_item_month.total_sales` la bani (MSBFEST, ISCRFEL, MEGAMALL) |
| 3 | Grila completată corect = DB | MC-MEGAMALL: K5/L5 44000/34675 = DB 44000/34674.5 |
| 4 | Import deja async + auto-refresh | `import_sales_file` → `rebuild_reporting_month` în tranzacție (`backend/services/importer.py:324-328`), `ImportResult` cu `snapshot_id` returnat după commit (l.359) |
| 5 | Retail are deja tot ce trebuie minus Sheet ID | `store_targets`, `reporting_*`, `stores`(site_code/firma/regional/asm), `team_leaders`; subtab pattern în `src/lib/tabs.ts:4` + `Management.tsx:9` |
| 6 | Diferența 76 vs 75 | retail are 76 targete (iunie), grile 75 — diferența = `SUNPLZ`/Sun Plaza, deja exclus din grile |

**Concluzie:** partea „expected" se construiește din retail DB pe `site_code`. Singurul lucru lipsă în retail = **Sheet ID per magazin**.

## 4. Decizii de design

1. **Decuplare citire/rulare.** Buton → enqueue arq job → job face munca lentă Google în background → rezultate în DB. UI citește din DB (sub-100ms), niciodată Google la page load. (Pattern-ul import existent.)
2. **O singură rulare unificată.** Contopim `monitor` (completare %) + `target_check` (K5/L5) într-un singur job: o citire Google per magazin → calculează ȘI completarea ȘI verificarea target/vânzări.
3. **Ierarhia + expected din DB live**, fără sidecar `store_metadata.json` → bug-ul de drift ASM (ex. Adrian Badea/Mega Mall) devine **structural imposibil**.
4. **Trigger după commit, nu mid-import.** Enqueue la apelant, după ce `import_sales_file()` returnează succes — în flow sync (`services/imports.py`) ȘI în `worker.py` `import_sales_background`. Pasează `snapshot_id`.
5. **Luna intern `YYYY-MM`** (`2026-06`). UI afișează românește, DB/API rămân pe format retail.
6. **Fără subprocess pe aplicația veche.** Portăm regulile de analiză într-un serviciu retail testabil. `grile-salarii/monitor_grile.py:50` (batch read per sheet) + `target_check.py:237` (comparație cu toleranță) = sursă de reguli, nu runtime.
7. **Google client e sync** → în job async folosim `asyncio.to_thread` cu pool limitat 5–8 (sau secvențial controlat). Nu blocăm event loop-ul worker-ului.
8. **Filtre independente** (decizia Andrei): subtab-ul Grile NU primește filtrul global retail; are propriul filtru local (lună + status), ca tab-ul Vizite. Butonul de filtru global se ascunde pe subtab-ul Grile.

## 5. Model de date (retail DB, schema_v2.sql)

```sql
grile_sheets(
  site_code     TEXT PRIMARY KEY REFERENCES stores(site_code),
  sheet_id      TEXT UNIQUE NOT NULL,
  registry_key  TEXT,            -- "Company/Store" original, audit
  is_active     BOOLEAN NOT NULL DEFAULT true,
  source_hash   TEXT,            -- hash registry → detectează drift la reseed
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

grile_runs(
  id            SERIAL PRIMARY KEY,
  run_month     TEXT NOT NULL,                       -- YYYY-MM
  source_snapshot_id INT REFERENCES import_snapshots(id),
  status        TEXT NOT NULL,                       -- queued|running|completed|failed
  source        TEXT NOT NULL,                       -- manual|auto
  progress_current INT NOT NULL DEFAULT 0,
  progress_total   INT NOT NULL DEFAULT 0,
  ok_count      INT NOT NULL DEFAULT 0,
  problem_count INT NOT NULL DEFAULT 0,
  error_count   INT NOT NULL DEFAULT 0,
  duration_ms   INT,
  triggered_by_email TEXT,
  started_at    TIMESTAMPTZ,
  finished_at   TIMESTAMPTZ
);

grile_store_status(
  run_id        INT NOT NULL REFERENCES grile_runs(id) ON DELETE CASCADE,
  site_code     TEXT NOT NULL,
  completion_pct NUMERIC,
  last_edit     TIMESTAMPTZ,
  grila_target  NUMERIC,         -- K5
  grila_sales   NUMERIC,         -- L5
  db_target     NUMERIC,         -- store_targets.target_value
  db_sales_mtd  NUMERIC,         -- Σ reporting_item_month.total_sales
  db_max_sale_date DATE,         -- ultima zi din DB (pt. status IN_URMA)
  fill_status   TEXT,            -- NECOMPLETAT|COMPLETAT
  target_status TEXT,            -- OK|DIFERENTA
  sales_status  TEXT,            -- OK|DIFERENTA|IN_URMA
  tolerance     NUMERIC,
  error_code    TEXT,
  error_message TEXT,
  raw_summary   JSONB,           -- snapshot brut pt. debugging
  PRIMARY KEY (run_id, site_code)
);
```

## 6. Backend

- `backend/routers/grile.py` → `backend/services/grile.py` → `backend/repositories/grile.py`.
- `backend/services/grile_sheets_client.py` — client Google read-only (scope minim), batch K5/L5 + metadata `last edit`, `asyncio.to_thread` + semafor 5–8.
- Endpoints:
  - `GET /api/grile/overview?month=YYYY-MM` — ultimul run + arbore ASM→TL→Firmă→Magazin din DB.
  - `POST /api/grile/run?month=YYYY-MM` — enqueue manual, returnează `run_id`.
  - `GET /api/grile/run/{id}` — status + progres (poll).
- Job arq `grile_check_background(month, snapshot_id, triggered_by)` în `worker.py`: per magazin cu `sheet_id` → citește K5/L5 → compară cu `store_targets` + `Σ reporting_item_month` → upsert `grile_store_status`, update progres pe `grile_runs`.
- Secrete: `config/google/service-account.json` (copie, chmod 600, gitignored). Share-ul pe cele 75 sheet-uri există deja.

## 7. Frontend

- `src/lib/tabs.ts:4`: `'grile'` în `ManagementTab` + `MGMT_SUBTABS` + labels.
- `src/components/Management.tsx:9`: tab nou + `<GrileSubtab/>`.
- `src/components/GrileSubtab.tsx`:
  - **Card status:** „Ultima rulare pt. importul din {data} · {ok}/{total} OK · {probleme} probleme · sursă auto/manual" + buton unic **„Rulează verificare"** (spinner + `progress_current/total`) + badge „Rulează automat zilnic după importul vânzărilor".
  - **Arbore** ASM→TL→Firmă→Magazin (din DB). Per magazin: completare %, last edit, target (OK/dif), vânzări (OK/dif/în urmă), link Sheet.
  - **Filtre locale independente** (lună + status): Necompletat / În urmă / Dif. target / Dif. vânzări / Eroare Google. Filtrul global retail nu se aplică (ca Vizite); butonul de filtru global ascuns pe acest subtab.
  - **Drawer per magazin:** K5/L5 vs DB target/vânzări, `db_max_sale_date`, last edit, link direct la Sheet.
- Status semantic clar (mai bun decât „MISMATCH" global de azi):
  - **NECOMPLETAT** — grila goală/0.
  - **ÎN URMĂ** — completată, dar `db_max_sale_date` > ziua completării (grila e în urma vânzărilor).
  - **DIFERENȚĂ** — completată, dar K5/L5 ≠ DB peste toleranță.

## 8. Trigger automat zilnic

- În flow-ul sync (`backend/services/imports.py`) și în `backend/worker.py` `import_sales_background`: după ce `import_sales_file()` returnează succes (tranzacția a făcut commit), enqueue `grile_check_background(import_month, snapshot_id, triggered_by)`.
- `source='auto'`, `source_snapshot_id=snapshot_id` în `grile_runs` → trasabilitate + dedup la dublu-upload în aceeași zi.
- Plus butonul manual on-demand (`source='manual'`).

## 9. Secvențiere (faze)

| Fază | Conținut | Risc |
|------|----------|------|
| 0 | Închis pe 2026-06-01: finalize + arhivă + reset Mai→Iunie în `grile-salarii`, fără schimbare de linkuri. | 0 |
| 1 | Migrație 3 tabele + seed `grile_sheets` din registry (read-only) + 3-tier + job + subtab. Buton manual. | mic (read-only) |
| 2 | Auto-trigger după commit import (sync + worker), cu `snapshot_id`. | mic |
| 3 (curent) | Rulare paralelă câteva zile; diff retail vs grile-salarii (trebuie identice). | 0 |
| 4 | Cutover read/verify pe retail. `finalize/archive/reset/...` rămân în grile-salarii. | mediu (decizie) |

Retragere completă `grile-salarii` = ulterioară, doar după ce decidem să portăm și mașinăria de payroll (sau o declarăm out-of-scope).

## 9.1. Stare operațională 2026-06-01

În `grile-salarii` s-au executat operațiile de final de lună pentru Mai 2026:

- `outputs/Tabel Salarii - Mai 2026.xlsx` generat cu `--skip-monitor-necompletat`; au intrat cei 4 ASM cu grile completate, iar Bogdan Radu + Bogdana Costan au fost ignorați pentru salarii.
- Arhiva completă standard refăcută: `75/75` grile, `0` erori, ZIP complet + ZIP-uri pe toți cei 6 ASM.
- Export suplimentar pentru handoff: `ASM-completate/` cu 4 ZIP-uri pentru managerii completați și `Pontaj-ASM-completate/` cu `49` fișiere values-only, câte un sheet `Pontaj`, împărțite pe ASM.
- `model grila` oficial (`1TNuz_PX5AYVOQQVxLG_5nORxC34Ia504a52yG_1RsrI`) și toate cele 75 grile au fost reparate pentru Agent 1 `B11:G14` (`D11/G11/G12:G14` formule + etichete lipsă).
- Reset live spre Iunie 2026: `75/75` grile, `0` erori; verificare separată Google: `0` valori rămase în range-urile resetate. Linkurile permanente nu au fost schimbate.

Documentație operațională detaliată: `/opt/Mobiup/grile-salarii/RUNBOOK.md`.

## 10. Riscuri / de confirmat la implementare

- **Timing grila vs DB:** magazin care a completat L5 ieri arată „în urmă" dacă azi DB are încă o zi → util ca semnal; status dedicat `IN_URMA`, nu `DIFERENTA`.
- **Cartele:** `reporting_*` exclude cartele; potrivirea la bани sugerează excludere identică în grilă/fișier — reconfirmat pe câteva magazine după resetul de 1 iunie.
- **Quota Google:** buton manual + 1 auto/zi = ok; fără spam.
- **76 vs 75:** verificăm doar magazinele cu `sheet_id` activ în `grile_sheets` (SUNPLZ exclus).
- **`source_hash` pe `grile_sheets`:** la reseed din registry, detectăm dacă s-au schimbat linkuri (nu ar trebui) și alertăm în loc să suprascriem orb.

## 11. Referințe cod

- Retail import: `backend/services/importer.py:324-369`, `backend/worker.py:9`, `backend/services/imports.py`
- Retail subtab: `src/lib/tabs.ts:4`, `src/components/Management.tsx:9`
- Retail DB: `store_targets`, `reporting_item_month`, `stores`, `team_leaders`, `import_snapshots`
- Reguli sursă (NU runtime) din grile-salarii: `monitor_grile.py:50`, `target_check.py:237`, `grile_common.py` (registry/normalize), `server/routers/overview.py` (enrichment TL din retail DB)
