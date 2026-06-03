# CODEX.md — UniHub Retail

Note operationale pentru Codex si alti agenti de coding care lucreaza in acest
repo. `CLAUDE.md` ramane compatibil cu agentii existenti; acest fisier fixeaza
deciziile verificate de Codex.

## Workflow local

- Repo: `/opt/Mobiup/unihub-retail`
- Branch production: `main`
- Remote: `origin` (`https://github.com/anervalens-netizen/unihub-retail.git`)
- Backend live: `unihub-backend.service`, port `9898`
- Build frontend live: `dist/` este gitignored si servit local de backend.
- Push pe `main` declanseaza runner-ul CI si redeploy automat.

Comenzi de validare folosite inainte de push:

```bash
backend/venv/bin/python -m pytest
npm test
npm run typecheck
cd backend && venv/bin/mypy . --ignore-missing-imports --explicit-package-bases
npm run build
```

## Campanii iunie 2026

Livrabilele sunt:

- Incentive iunie = clona exacta dupa mai in DB:
  **967 produse**, tiere **5/10/25 RON**, total reward **5.945 RON**.
- Promo iunie = `data/hub_specials.json`, 47 coduri, `2026-06-01` -
  `2026-06-30`.
- Concurs iunie = `data/contests.json`, scope `asm='Andrei Stancu'`, 23
  magazine non-TR, punctaj agent: focus unitati + bonuri promo + unitati
  `unit_price > 150`.

`data/hub_specials.json` si `data/contests.json` sunt gitignored. Nu apar in
commit si trebuie gestionate operational pe server.

## Regula co-purchase

Sursa comuna este `backend/services/promo_copurchase.py`.

Bon calificat:

- cheie `(sale_date, site_code, agent, bon_nr)`;
- cel putin un produs din lista promo;
- cel putin doua unitati pozitive totale non-cartela pe acelasi bon;
- exclude `is_cartela`, retururi si locatii `TR %`.

Unitatea redusa:

- maxim una per bon calificat;
- produsul din lista promo cu cel mai mic `unit_price`;
- tie-break determinist: `unit_price`, `item_code`, `id`.

Aceeasi regula este folosita de cardul Hub special, Focus -> Promo, excluderea
din incentive si punctajul de concurs.

## Metrici promo

Nu confunda:

- `promo_qty` = cantitate simpla din `reporting_item_day`, pastrata pentru
  KPI-uri/tabele Hub si compatibilitate.
- `promo_qualifying_bons` = bonuri co-purchase calificate, headline corect
  pentru Focus -> Promo.
- `promo_discounted_units` = produse reduse, 1 per bon calificat.
- `promo_active_stores` si `promo_active_agents` = magazine/agenti cu bonuri
  co-purchase.

Validare Codex pe date reale mai, cu config mutat temporar pe mai:

```text
promo_qty simplu = 710
promo_qualifying_bons = 314
top magazin = 17 bonuri
```

## Invariant luni

`/api/filters/months` listeaza doar luni din `import_snapshots` cu
`status='completed'`. Nu adauga luni configurate dar fara import prin UNION sau
hardcodare. Iunie 2026 apare in UI dupa primul import finalizat de vanzari
iunie.

## Fisiere cheie

- `backend/services/promo_copurchase.py` — regula co-purchase.
- `backend/services/dashboard/specials_data.py` — cardurile speciale Hub.
- `backend/services/campaigns.py` — Focus -> Incentive/Promo.
- `backend/services/contests.py` — scor concurs.
- `backend/services/contests_config.py` — parser `data/contests.json`.
- `src/components/Campaigns.tsx` — sub-sectiunile Focus si `ContestView`.
- `src/api/contests.ts` — client pentru `/api/contests/active`.
- `docs/HANDOVER-campanii-iunie-2026.md` — handover complet.

## Grile In Retail

Subtab-ul `Management -> Grile` este fluxul operational curent pentru grile.
Include verificarea zilnica si inchiderea de luna:

- verificare K5/L5 vs Retail DB si completare zile, cu ziua curenta exclusa;
- finalizare salarii in formatul nou;
- export arhiva XLSX/ZIP;
- reset lunar guarded, cu dry-run si reset live doar pentru admin.

Implementarea lunara ruleaza nativ in `backend/services/grile_monthly.py`,
prin worker-ul arq, folosind registry-ul `grile_sheets` + `stores` din DB si
Google scopes `spreadsheets`/`drive`. Artefactele se scriu in
`backend/outputs/grile` (gitignored).

Repo-ul vechi `/opt/Mobiup/grile-salarii` este dezafectat ca aplicatie publica.
Ramane doar arhiva/CLI pentru reparatii punctuale de template/protected ranges
sau pentru referinte istorice. Domeniul `grile.unihub.ro` si serviciul
`unihub-grile` au fost eliminate din runtime.
