# H-15 — Inventar artefacte generate versionate

## Limite

Inventar read-only la 2026-07-12 după H-08 `78361285a97b24bdf1c505da6ae0e8b86092ac47`.
Au fost consultate numai path, dimensiune, MIME, metadata Git, hash-uri de asset
și referințe de cod. Nu a fost citit, copiat sau afișat conținut business.

## Rezumat

- 430 fișiere tracked; 64 candidați; 0 fișiere tracked peste 512 KiB.
- Candidați: 3,534,432 bytes în HEAD; aproximativ 3,999,861 bytes istorici.
- 22 `reports/**` sunt artefacte generate, 1-2 revizii/path, fără consumator
  runtime găsit; păstrarea manuală necesită decizia ownerului business.

## Artefacte propuse pentru purge coordonat

| Path | Bytes | Type | Classification | Producer | Runtime consumer | Human-opened | Git history | Recommended action |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- |
| `reports/incentive-iunie-2026-pe-produs.xlsx` | 81052 | XLSX | business report | offline probable | none found | yes | 1 | MOVE_TO_GOVERNED_STORAGE + purge |
| `reports/retail-analyst-2026-06.html` | 93007 | HTML | business report | offline probable | none found | yes | 1 | MOVE_TO_GOVERNED_STORAGE + purge |
| `reports/retail-bucuresti-2026-06.html` | 74575 | HTML | business report | offline probable | none found | yes | 1 | MOVE_TO_GOVERNED_STORAGE + purge |
| `reports/retail-cohort-2026-06.html` | 73049 | HTML | business report | offline probable | none found | yes | 2 | MOVE_TO_GOVERNED_STORAGE + purge |
| `reports/retail-zone-detailed-2026-06.html` | 54675 | HTML | business report | offline probable | none found | yes | 1 | MOVE_TO_GOVERNED_STORAGE + purge |
| `reports/unihub-retail-database-analysis.html` | 47327 | HTML | business report | offline probable | none found | yes | 1 | MOVE_TO_GOVERNED_STORAGE + purge |
| `reports/timesfm/**` (16 paths below) | metadata-only | CSV/JSON/XLSX | forecast artifact | forecast scripts | none found | mixed | 1 each | REMOVE_HEAD_AND_COORDINATED_HISTORY_PURGE |

Exact `reports/timesfm/**` paths:

- `timesfm-july-2026-by-asm-231647.csv`
- `timesfm-july-2026-by-firma-231647.csv`
- `timesfm-july-2026-by-regional-231647.csv`
- `timesfm-july-2026-daily-20260630-231647.csv`
- `timesfm-july-2026-daily-total-231647.csv`
- `timesfm-july-2026-forecast-20260630-231647.xlsx`
- `timesfm-july-2026-monthly-20260630-232243-asm.csv`
- `timesfm-july-2026-monthly-20260630-232243-raw.json`
- `timesfm-july-2026-monthly-20260630-232243-stores.csv`
- `timesfm-july-2026-monthly-20260630-232243.xlsx`
- `timesfm-july-2026-raw-20260630-231647.json`
- `timesfm-july-2026-summary-20260630-231647.csv`
- `timesfm-xreg-monthly-20260630-234656-raw.json`
- `timesfm-xreg-monthly-20260630-234656-rows.csv`
- `timesfm-xreg-monthly-20260630-234656-summary.csv`
- `timesfm-xreg-monthly-20260630-234656.xlsx`

## Păstrare și backup

- `public.bak-logo-20260626-155400/**`: 8 PNG, 1 revision, 0 hash-uri egale
  cu fișiere omonime din `public/`; static backup, `REMOVE_HEAD_ONLY` după
  confirmarea ownerului de brand.
- Cele 4 XLS/XLSX din `docs/Campanii-promo/**`: `KEEP_SOURCE`, livrabile
  manuale de campanie.
- `docs/archive/**`: 30 Markdown-uri incluse fals de filtrul directory;
  `KEEP_SOURCE`.
- Fixture-urile/configurațiile legitime: `KEEP_SOURCE`/`KEEP_SYNTHETIC_FIXTURE`.

## Reguli preventive active

Nu există consumer runtime pentru `reports/**`. Generatorul offline identificat
în inventar scrie în `backend/outputs/`, nu în repository. `.gitignore` și
testul de igienă blochează `reports/` și `public.bak-*`, fără globuri generale
pentru XLSX/CSV/JSON.

## Curățare HEAD executată

La 2026-07-12 au fost eliminate din Git HEAD exact 22 `reports/**` și 8 PNG
din `public.bak-logo-20260626-155400/**` (30 total), după arhivare din commitul
`43e39f3efd36b91dadd847d3279523021e166069`. Arhiva securizată este
`/opt/Mobiup/secure-archive/unihub-retail/h15/unihub-retail-h15-head-43e39f3efd36.tar.gz`,
SHA-256 `568a43ed5e9f6d23e3fe7ba8b97e8209af558e354e336b083173e7f34a6e15c7`,
owner `root:root`, mode `0600`; gzip și 30 intrări au fost verificate.
Campanii-promo și docs/archive au rămas tracked.

## Storage guvernat și history purge

La 2026-07-14, după aprobarea explicită a ownerului business, arhiva HEAD,
bundle-urile Git pre/post-purge și hărțile de commit/ref au fost copiate în
storage local și NAS cu permisiuni owner-only, checksum-uri verificate,
manifest de audit și retenție minimă 90 de zile. Namespace-ul istoric complet
`reports/` — 34 path-uri în 8 commituri — a fost eliminat din `main`, clonele
locale și runner fără schimbarea tree-ului final. Detaliile și limitarea
refs-urilor PR administrate de GitHub sunt în
`docs/engineering/h15-history-purge-plan.md`.

Ownerul business a acceptat explicit la 2026-07-14 riscul rezidual al
refs-urilor PR read-only: repository-ul este privat, are un singur colaborator,
nu are forkuri, iar refs-urile nu sunt folosite de runtime sau deploy. Curățarea
lor prin GitHub Support este opțională și nu mai reprezintă o dependență de
închidere. H-15 este închis.
