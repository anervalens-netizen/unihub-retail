---
title: "P0 P&L și TVA: shadow, scope și recovery"
tags: [unihub-retail, pnl, tva, finance, p0, recovery]
status: active
created: 2026-08-03
---

# Runbook P0 — P&L și TVA

## Contract și status

Baseline-ul inițial al acestui runbook este
`f9c0b1efe15686bcda532d22528e6e2644925aec`; P0-B a fost deployat la source SHA
`5fba9d899f78b4160c39e50212071bf1b505619d`, CI `30946990852`, deploy
`30947430898`. P0 implementează staging/shadow și garduri de scope, dar nu
activează apply live Finance/TVA. Actualele Finance, estimările și scenariile
Target finalizate rămân protejate.

Registrul fiscal effective-dated este:

- 1,19 până la 2025-07-31 inclusiv;
- 1,21 de la 2025-08-01.

Regula se aplică în candidatele P0 cu Decimal și o singură rotunjire la 0,01.
Orice aplicare live necesită un lot separat, cu aprobare explicită.

## Scope obligatoriu

Scope-ul este lista exactă de perechi `(company, period)` din batch. Importul
nu șterge anul întreg, cealaltă companie sau alte luni. Bucketul
`__FINANCE_UNALLOCATED__` este înlocuit numai în aceeași pereche company-period.
Authority manifestul trebuie să declare snapshot complet, ambele companii,
revision/parent, cutoff, source SHA, coverage și control totals. O corecție
oficială completă poate elimina chei vechi; diferența este hashuită și auditată,
nu este înlocuită cu euristica „workbook mai dens”.

## Generația autoritativă Finance

`backend/scripts/import_store_pnl.py` acceptă numai aceste operații:

- `--stage --authority-manifest FILE --input-dir DIR` pentru staging immutable;
- `--apply-generation UUID --expected-manifest-sha SHA256` și
  `--rollback-generation UUID --expected-manifest-sha SHA256`, ambele blocate
  operațional în P0-B înainte de conectarea DB.

Stagingul cere `FINANCE_PNL_DATABASE_URL`, diferit de `DATABASE_URL`, și
principalul exact `unihub_finance_import_worker`, membru exclusiv al autorității
`unihub_finance_import`. Directorul de input trebuie să conțină exact
sursele declarate; parserul hash-uiește bytes înainte de parse, refuză symlink,
rename, source/hash mismatch, luni nedeclarate și mix detail/summary între
revizii. Candidatele, pre-image-ul și ledgerul sunt immutable. Apply-ul intern
verificat folosește stagingul, nu recitește filesystemul; lockurile per scope,
revision/parent și pre-image hash formează CAS-ul.

Nu crea rolul/credentialul Finance și nu rula staging/apply pe primary în acest
lot. Acestea cer decizie operațională separată. Codul și schema se verifică pe
PostgreSQL izolat cu rolul de test omonim.

## Shadow și provenance

Folosește `backend/scripts/shadow_store_pnl.py` pentru dry-run/capture. Snapshotul
DB este repeatable-read și are `input_cutoff` fix, aliniat la prima zi a lunii.
Candidatele `legacy_v2` și `effective_v3` rulează pe același snapshot.

Scriptul încarcă exclusiv `.env.worker`, cere principalul autentificat
`unihub_operations_worker` și verifică membershipul exclusiv
`unihub_operations`. Nu folosește `.env`, loginul web sau loginul Finance.
Operations poate citi numai coloanele salariale non-CNP necesare modelului;
schema `salary_private` rămâne inaccesibilă.

Generația shadow păstrează:

- scope și `scope_sha256`;
- source/input/rule/model/output hashes pentru legacy și effective;
- `fiscal_delta` separat de `input_or_model_delta`;
- rândurile candidate și pre-image-ul exact din scope;
- state `staged`, `promoted`, `superseded` sau `rolled_back`.

Pointerul shadow are revision CAS și servește doar review/rollback. Citirile
runtime P&L nu consumă pointerul, iar capture/stage nu mută
`store_pnl_monthly`.

Migrarea 040 blochează UPDATE/DELETE pe generații, rânduri și pre-image shadow.
Seal reverifică numărul de rânduri și digestul; promote/rollback mută pointerul
exclusiv prin funcțiile SQL controlate și expected revision. Nici operations,
nici Finance nu primesc write direct pe pointer.

Generațiile Finance autoritative pornesc obligatoriu `building`, sunt sealed
`staged` și devin `promoted` numai prin funcțiile controlate care verifică
manifestul, toate headurile CAS și ledgerul per scope. Grupul Finance nu are
INSERT/UPDATE/DELETE direct pe actuale, UPDATE direct pe stare sau acces la
helper-ele interne de head/ledger. `promote_store_pnl_generation` rehash-uiește
pre-image-ul și candidatul, înlocuiește numai `actual`, mută toate headurile și
închide ledgerul într-o singură tranzacție. Contractul autentificat rezervă
`unihub_finance_import_worker`, dar P1-A nu creează acel LOGIN/credential și nu
autorizează stage/apply live.

## Comenzi de verificare fără mutație Finance

~~~bash
cd /opt/Mobiup/unihub-retail
backend/venv/bin/python backend/scripts/shadow_store_pnl.py \
  --input-cutoff YYYY-MM-01 \
  --scope Mobiup:YYYY-MM --scope Mobicell:YYYY-MM
~~~

Comanda shadow este dry-run implicit. `--promote-shadow` și `--rollback-shadow` mută
numai pointerul shadow prin CAS și afișează explicit `effective_apply: BLOCKED`.
Nu există `--apply` pentru shadow. Calea
`estimate_store_pnl.py --apply --effective-vat` este blocată înainte de
conectarea DB la baseline P0.

## Evidence minim înainte de orice lot live viitor

1. Salvează source SHA, input cutoff, toate rule/model/output hashes și
   manifestul generației.
2. Rulează coverage și control totals pe fiecare `(company, period)`; confirmă
   că actualele neafectate și Target finalizat au business hash neschimbat.
3. Capturează pre-image imutabil și backup verificat; repetă comparația
   `fiscal_delta` versus `input_or_model_delta` pe același snapshot.
4. Verifică aceeași valoare brută -> net la cent în P&L, estimator, Target și
   export; nu converti la float în calcule monetare.
5. Promovează numai pointerul/generația aprobată, cu CAS și operator auditat.

## Recovery și limite

Rollbackul shadow este pointer CAS. Rollbackul unei generații Finance creează o
generație inversă nouă din pre-image și o promovează numai dacă headul și CAS-ul
încă se potrivesc; nu mută headul înapoi și nu atinge `estimated`. Nu se editează
migrațiile istorice și nu se execută down migration destructivă. Dacă snapshotul
sau hashurile nu pot fi reconciliate, apply-ul eșuează tranzacțional și rămâne
generația bună.

P0 nu demonstrează reconcilierea celor 8 grupuri salariale, nu modifică date
live și nu declară că TVA effective-dated este activ în Finance sau în Target.
Verificările locale de backend/mypy/teste sunt evidence de cod, nu aprobare
pentru production.

## Evidence P0-B deployat

- migrarea 038:
  `bac85ae88b6118e877e73ad444ed3895051a432069b460d802dc2b1144735488`;
- migrarea 039:
  `4d9f3224195bc63b09be6a4642fb585f5a8b8f3c370c76ca799f0f8620f55b9d`;
- `replace_month_snapshot(text)` absent live;
- runtime: `SELECT` pe actualele P&L, fără write, generații sau secvențe;
- zero generații Finance și rolul `unihub_finance_import` absent după deploy;
- P&L live neschimbat: 97.687 rânduri, 569.813.991,84 RON;
- artifact SHA-256:
  `d9ed25e65240f75ed17ad31d8311c7c2fa328abf4176b7bae9a9e276f0eb7550`.

Aceste dovezi închid numai implementarea și gardurile P0-B. Nu crea rolul
Finance și nu promova date fără lotul operațional separat descris mai sus.
