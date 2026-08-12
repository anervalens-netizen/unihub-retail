# ADR-006 — Livrare runtime exclusiv din artefact verificat exact-SHA

**Status:** Accepted
**Date:** 2026-08-07
**Decision owner:** Retail Business și Operations
**Supersedes:** partea runtime din ADR-005

## Context

UniHub Retail execută importuri autoritative, operații Grile, calcule salariale,
P&L și migrări PostgreSQL. Pentru aceste suprafețe, diferența dintre codul testat
și codul livrat nu este acceptabilă. Calea local-first din ADR-005 permitea
commit și deploy înainte de CI pentru schimbări considerate obișnuite; această
clasificare este prea subiectivă pentru un runtime cu procese multiple și date
materiale.

Repository-ul are deja mecanismul corect: CI pe SHA exact, artefact imutabil,
`SOURCE_SHA`, `SHA256SUMS`, verificare de manifest, lock global și workflow de
deploy care consumă runul CI exact.

## Decizie

Orice modificare care poate schimba runtime-ul sau datele urmează obligatoriu:

```text
branch/PR
→ verificări locale
→ CI exact-SHA verde
→ review
→ merge în main
→ CI manual exact pe noul main SHA
→ artefactul acelui run
→ verificare digest și migration manifest
→ backup/migration gate
→ deploy workflow
→ probe locale și publice
```

Se consideră runtime:

- Python, TypeScript, build frontend și pachete;
- migrări, schema și granturi;
- systemd, workers, observabilitate și proxy;
- importuri, exporturi, Grile, salarii, P&L și forecast;
- scripts sau config folosite de deploy ori producție.

Calea rapidă fără artefact rămâne permisă numai pentru documentație care nu
intră în artefactul runtime și nu schimbă procedura operațională.

## Break-glass

Break-glass este permis numai pentru incident activ în care calea GitHub este
indisponibilă și indisponibilitatea produce impact mai mare decât riscul
hotfixului. Necesită simultan:

- owner explicit și audit handle;
- commit local identificabil, diff și rezultate salvate;
- manifest hash-uit și backup verificat;
- fără migrări, auth, permissions, importuri, salarii, Grile destructive,
  proxy, secrete sau release tooling;
- reconciliere ulterioară obligatorie: push, CI exact și egalitate între live
  SHA și GitHub.

Break-glass nu este o alternativă de comoditate.

## Consecințe

- `main` nu este tratat ca mediu de dezvoltare;
- serverul nu reconstruiește sursa după CI;
- deployul normalizează permisiunile sursei după modurile din indexul Git și
  instalează frontendul cu un contract read-only pentru identitatea web;
- agentul operațional poate executa autonom întregul flux autorizat, dar nu
  poate sări peste dovada exact-SHA;
- ADR-005 rămâne istoric pentru principiul autorizării prin conversație, însă
  nu mai autorizează deploy runtime nevalidat formal.
