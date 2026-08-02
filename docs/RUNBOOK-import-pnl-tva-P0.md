---
title: "P0 P&L și TVA: shadow, scope și recovery"
tags: [unihub-retail, pnl, tva, finance, p0, recovery]
status: active
created: 2026-08-03
---

# Runbook P0 — P&L și TVA

## Contract și status

Baseline-ul acestui runbook este `f9c0b1efe15686bcda532d22528e6e2644925aec`.
P0 implementează numai staging/shadow și garduri de scope. Nu există apply live
Finance/TVA activat prin acest lot. Actualele Finance, estimările și scenariile
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
Coverage-ul curent este comparat cu candidatele, iar scăderea unei chei
existente blochează promovarea.

## Shadow și provenance

Folosește `backend/scripts/shadow_store_pnl.py` pentru dry-run/capture. Snapshotul
DB este repeatable-read și are `input_cutoff` fix, aliniat la prima zi a lunii.
Candidatele `legacy_v2` și `effective_v3` rulează pe același snapshot.

Generația shadow păstrează:

- scope și `scope_sha256`;
- source/input/rule/model/output hashes pentru legacy și effective;
- `fiscal_delta` separat de `input_or_model_delta`;
- rândurile candidate și pre-image-ul exact din scope;
- state `staged`, `promoted`, `superseded` sau `rolled_back`.

Pointerul shadow are revision CAS și servește doar review/rollback. Citirile
runtime P&L nu consumă pointerul, iar capture/stage nu mută
`store_pnl_monthly`.

## Comenzi de verificare fără mutație Finance

~~~bash
cd /opt/Mobiup/unihub-retail
backend/venv/bin/python backend/scripts/shadow_store_pnl.py \
  --input-cutoff YYYY-MM-01 \
  --scope Mobiup:YYYY-MM --scope Mobicell:YYYY-MM
~~~

Comanda este dry-run implicit. `--promote-shadow` și `--rollback-shadow` mută
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

Rollbackul P0 este pointer CAS către generația anterioară sau restore din
pre-image într-un lot separat; nu se editează migrațiile istorice și nu se
execută down migration destructivă. Dacă snapshotul sau hashes nu pot fi
reconciliate, starea este `recovery_required` și rămâne generația bună.

P0 nu demonstrează reconcilierea celor 8 grupuri salariale, nu modifică date
live și nu declară că TVA effective-dated este activ în Finance sau în Target.
Verificările locale de backend/mypy/teste sunt evidence de cod, nu aprobare
pentru production.
