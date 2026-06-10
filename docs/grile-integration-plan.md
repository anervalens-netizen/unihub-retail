# Plan: Integrare Grile native in retail.unihub.ro

> Status: **CUTOVER COMPLET (2026-06-03).** `Management -> Grile` este fluxul operational curent pentru verificare, finalizare salarii, arhiva si reset lunar.
> Update 2026-06-03: `grile.unihub.ro` si `unihub-grile.service` au fost dezafectate. Retail ruleaza lunar nativ, fara proxy catre aplicatia veche.
> Autori: server-Claude + review Codex. Data: 2026-05-31.
>
> **Implementat:** schema `grile_sheets`/`grile_runs`/`grile_store_status`; verificare async `grile_check_background`; auto-trigger dupa import; subtab `GrileSubtab.tsx`; panou lunar collapsible `GrileMonthlyPanel.tsx`; operatii lunare native in `services/grile_monthly.py`; output-uri in `backend/outputs/grile`.
> `grile-salarii` ramane doar arhiva/CLI pentru reparatii punctuale de template/protected ranges si referinte istorice.
> Update 2026-06-10: verificarea Grile declanseaza si sync read-only pentru targetele reale per agent in `agent_targets`, numai pentru managerii activati. Zonele excluse sau randurile nemapate raman pe fallback-ul Retail existent.

---

## 1. Obiectiv

Mutarea grilelor salariale in retail, ca subtab nativ in **Management -> Grile**, cu:
- verificare automata zilnica dupa importul vanzarilor, fara upload separat de target/vanzari;
- sincronizare targete agent din grile pentru zonele activate, cu fallback automat cand lipseste targetul sau mapping-ul;
- buton manual "Ruleaza verificare" + status rulare + progres;
- rezultate persistate in DB;
- operatii lunare native: finalizare salarii, arhiva XLSX/ZIP, reset lunar dry-run/live.

Strategia initiala a fost strangler/read-only in paralel. Dupa validare,
cutover-ul a fost facut pe 2026-06-03, iar runtime-ul public vechi a fost scos.

## 2. Constrangeri hard

- **Nu se schimba linkurile magazinelor.** Fiecare magazin are un Google Sheet permanent. Retail foloseste Sheet ID-urile salvate in `grile_sheets`.
- **Verificarea ramane non-distructiva.** Citeste K5/L5 si completarea zilelor; ziua curenta este exclusa din numarul de zile asteptate.
- **Operatiile write sunt limitate la inchiderea de luna.** `finalize` si `archive` exporta local; `reset` sterge doar range-urile editabile definite in cod si este disponibil admin-only, cu dry-run. Din 2026-06-10, `Pontaj!C8:AG31` este manual si intra in reset; formulele de total din `Pontaj!AH` nu se sterg.
- Codul retail respecta pattern-ul `router -> service -> repository` si conventiile din `CLAUDE.md`.

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

1. **Decuplare citire/rulare.** Buton -> enqueue arq job -> job face munca lenta Google in background -> rezultate in DB. UI citeste din DB, niciodata Google la page load.
2. **O singura rulare unificata.** `monitor` (completare %) + `target_check` (K5/L5) intr-un singur job.
3. **Ierarhia + expected din DB live**, fara sidecar operational `store_metadata.json`.
4. **Trigger dupa commit, nu mid-import.** Enqueue dupa ce `import_sales_file()` returneaza succes, cu `snapshot_id`.
5. **Luna intern `YYYY-MM`** (`2026-06`). UI afiseaza romaneste, DB/API raman pe format retail.
6. **Fara proxy pe aplicatia veche.** Regulile ruleaza in servicii retail testabile.
7. **Google client sync in worker.** Operatiile lente ruleaza in background, nu in request.
8. **Filtre independente.** Subtab-ul Grile nu primeste filtrul global retail; are propriul filtru local.
9. **Panou lunar collapsible.** Inchiderea de luna este integrata in cardul principal "Verificare grile salariale", dar ascunsa implicit in sectiune extensibila.

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
- `backend/services/grile_sheets.py` — client Google pentru verificare K5/L5 + completare, cu scope-uri read-only.
- `backend/services/grile_monthly.py` — operatii lunare native: finalizare salarii, arhiva XLSX/ZIP, reset guarded.
- Endpoints:
  - `GET /api/grile/overview?month=YYYY-MM` — ultimul run + arbore ASM→TL→Firmă→Magazin din DB.
  - `POST /api/grile/run?month=YYYY-MM` — enqueue manual, returnează `run_id`.
  - `GET /api/grile/run/{id}` — status + progres (poll).
  - `POST /api/grile/monthly/run` — enqueue finalize/archive/reset, admin-only.
  - `GET /api/grile/monthly/job/{id}` — poll job lunar.
  - `GET /api/grile/monthly/download/{final|archive}/{YYYY-MM}` — descarca artefacte locale.
- Job arq `grile_check_background(month, snapshot_id, triggered_by)` în `worker.py`: per magazin cu `sheet_id` → citește K5/L5 → compară cu `store_targets` + `Σ reporting_item_month` → upsert `grile_store_status`, update progres pe `grile_runs`.
- Dupa verificare, `services/grile_agent_targets.py` citeste read-only `Grila!D2/D8/D16/D22` pentru managerii din `GRILE_AGENT_TARGET_ENABLED_MANAGERS` si inlocuieste override-urile `agent_targets` doar pentru sheet-urile citite cu succes. Implicit sunt activati Andrei Stancu, Adrian Badea, Mihai Condorateanu si Elena Minca. Daca targetul lipseste sau agentul nu se mapeaza sigur, randul ramane fara override si UI foloseste fallback-ul `store_targets / agenti activi`.
- `GRILE_AGENT_TARGET_DISABLED_MANAGERS` are prioritate peste lista activata; implicit Bogdan Radu si Bogdana Costan raman nesincronizati.
- Sync-ul nu cere ca suma targetelor agentilor sa fie egala cu targetul magazinului; diferentele sunt permise pentru inlocuitori, TL sau agenti suplimentari.
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
| 3 | Rulare paralela si validare diferente. | 0 |
| 4 | Cutover read/verify pe retail. | mediu |
| 5 | Portare finalize/archive/reset in Retail si dezafectare `grile.unihub.ro`. | mediu |

Fazele 3-5 sunt inchise pe 2026-06-03.

## 9.1. Stare operațională 2026-06-01

În `grile-salarii` s-au executat operațiile de final de lună pentru Mai 2026:

- `outputs/Tabel Salarii - Mai 2026.xlsx` generat cu `--skip-monitor-necompletat`; au intrat cei 4 ASM cu grile completate, iar Bogdan Radu + Bogdana Costan au fost ignorați pentru salarii.
- Arhiva completă standard refăcută: `75/75` grile, `0` erori, ZIP complet + ZIP-uri pe toți cei 6 ASM.
- Export suplimentar pentru handoff: `ASM-completate/` cu 4 ZIP-uri pentru managerii completați și `Pontaj-ASM-completate/` cu `49` fișiere values-only, câte un sheet `Pontaj`, împărțite pe ASM.
- `model grila` oficial (`1TNuz_PX5AYVOQQVxLG_5nORxC34Ia504a52yG_1RsrI`) și toate cele 75 grile au fost reparate pentru Agent 1 `B11:G14` (`D11/G11/G12:G14` formule + etichete lipsă).
- Reset live spre Iunie 2026: `75/75` grile, `0` erori; verificare separată Google: `0` valori rămase în range-urile resetate. Linkurile permanente nu au fost schimbate.

Documentație operațională detaliată: `/opt/Mobiup/grile-salarii/RUNBOOK.md`.

## 9.2. Cutover 2026-06-03

- `grile.unihub.ro` a fost scos din Caddy si din monitorizarea Prometheus.
- `unihub-grile.service` a fost oprit si dezactivat.
- Retail a preluat inchiderea de luna nativ, fara apel HTTP catre portul 47000.
- Test smoke pe `Park Lake`:
  - `finalize_month(... only='Park Lake')` a generat tabelul de salarii;
  - `archive_month(... only='Park Lake')` a generat ZIP complet + ZIP ASM;
  - `reset_month(... dry_run=True, force=True, only='Park Lake')` a validat resetul.
- Formatul tabelului salarii curent:
  `Nr`, `Manager`, `Magazin`, `Agent`, `Salariu baza`, `Comision vanzare`,
  `Flip`, `Comision vanzare zile suplimentare`, `Incentive lunar`,
  `Plata ore suplimentare`, `Total salariu`, `Salariu Cash`, `Bonuri`,
  `Data angajarii`, `Data plecarii`, `Nr. Ore lucrate`,
  `Zile CO luna in curs`.

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
