# ADR-006 — Livrare runtime exclusiv din artefact verificat exact-SHA

**Status:** Accepted  
**Date:** 2026-08-07  
**Decision owner:** Retail Business și Operations  
**Supersedes:** partea runtime din ADR-005

## Context

UniHub Retail execută importuri autoritative, operații Grile, calcule salariale,
P&L și migrări PostgreSQL. Pentru **producție**, diferența dintre codul livrat și
artefactul verificat nu este acceptabilă.

Repository-ul are două etape care nu trebuie confundate:

1. **dezvoltare / merge** — dovedește că schimbarea poate intra sigur în `main`;
2. **release / deploy** — produce și promovează artefactul exact care va intra în
   producție.

Istoric, textul ADR putea fi citit ca și cum fiecare merge runtime ar necesita
imediat încă un FULL pe noul `main`, chiar dacă nu se făcea release. Această
interpretare produce verificare redundantă și nu este intenția contractului.

## Decizie

### 1. Merge fără release imediat

O schimbare runtime poate fi dezvoltată și merge-uită fără a produce imediat un
release de producție.

Fluxul normal este:

```text
branch/PR
→ verificări locale proporționale
→ repository-native PR verification
→ review când este cerut/justificat
→ merge în main
→ required post-merge policy checks
→ STOP dacă release/deploy nu este în scope
```

`PR-DEEP` se execută numai când politica nativă îl cere sau există un risc
concret nerezolvat care îl justifică. `FULL` nu se execută automat după merge și
nu se lanțuiește automat după PR-DEEP.

Dacă merge commit-ul are exact același tree ca HEAD-ul candidatului certificat,
nu există conținut nou de aplicație care să justifice repetarea testelor doar
pentru că SHA-ul commitului de merge este diferit.

### 2. Release/deploy în producție

Când ownerul cere explicit release/deploy sau task-ul are producția în scope,
artefactul care intră live trebuie produs și verificat pe exact `main`:

```text
certified main
→ manual exact-main FULL/release CI
→ immutable release artifact + SOURCE_SHA + manifests/provenance
→ digest + migration-manifest verification
→ backup/migration gate când se aplică
→ deploy workflow
→ health + changed-path probes
```

Aici FULL are un rezultat distinct și necesar: **creează și certifică artefactul
imutabil de producție**. Nu este o recertificare ceremonială a PR-ului.

Nu reutiliza un artefact construit pentru alt SHA și nu reconstrui sursa pe
server.

## Ce se consideră runtime pentru producție

- Python, TypeScript, frontend build și pachete;
- migrări, schema și granturi;
- systemd, workers, observabilitate și proxy;
- importuri, exporturi, Grile, salarii, P&L și forecast;
- scripts/config folosite de deploy ori producție.

Documentația non-runtime nu cere artefact release.

## Break-glass

Break-glass este permis numai pentru incident activ în care calea GitHub este
indisponibilă și indisponibilitatea produce impact mai mare decât riscul
hotfixului. Necesită simultan:

- owner explicit și audit handle;
- commit identificabil, diff și rezultate salvate;
- manifest hash-uit și backup verificat;
- fără migrări, auth, permissions, importuri, salarii, Grile destructive,
  proxy, secrete sau release tooling;
- reconciliere ulterioară: push, verificare și egalitate între identitatea live
  și GitHub.

Break-glass nu este o alternativă de comoditate.

## Regula de eficiență

`docs/engineering/verification-efficiency-policy.md` este autoritatea pentru
costul/routing-ul verificării. Înainte de PR-DEEP, FULL sau replay de suită
mare trebuie identificat riscul concret și evidence-ul nou produs.

Nu executa un release doar pentru a valida un merge. Nu executa FULL doar pentru
că a existat un merge. Execută release CI atunci când chiar trebuie produs sau
certificat un artefact de producție.

## Consecințe

- `main` nu este tratat ca mediu de dezvoltare directă;
- merge-ul și release-ul sunt etape separate;
- serverul nu reconstruiește sursa după CI;
- producția primește numai artefact exact-main verificat;
- agentul poate executa autonom fluxul deja autorizat, dar nu extinde singur
  scope-ul de la „merge” la „deploy”;
- ADR-005 rămâne istoric pentru principiul autorizării prin conversație, însă nu
  autorizează deploy runtime nevalidat formal.