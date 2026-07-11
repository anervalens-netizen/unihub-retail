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

## Următorul pas

Nu există consumer runtime de schimbat pentru `reports/**`, dar e necesară
decizie business înainte de eliminare. Recomandări `.gitignore` neaplicate:
`/reports/`, `/public.bak-*/`, `/backend/outputs/`; nu globuri globale pentru
XLSX/CSV/JSON. Storage țintă: object storage guvernat cu retention/audit;
arhivă server securizată doar temporar. Nu s-a creat, mutat sau copiat nimic.
