# H-12 spreadsheet writer inventory

## Runtime writers remediated

| Surface | Classification | H-12 handling |
| --- | --- | --- |
| `backend/services/exports.py` | Local XLSX from DB/reporting data | Central OpenPyXL writer for report, configuration, comparison and daily sheets. |
| `backend/services/target_calculator.py` | Local XLSX from scenario/DB data | Central OpenPyXL writer for final targets, manager summary and parameters. |
| `backend/services/grile_monthly.py` | Local XLSX from Google/HR metadata | Central OpenPyXL writer; only Total salariu and Salariu Cash use explicit trusted formulas. |

## Other findings

- `src/lib/tableExport.ts` writes inline strings and has XML-level tests; it
  does not generate formula tags for table text, so no rewrite was needed.
- Google operations in `grile_monthly.py` are reads, exports and `batchClear`;
  no active `values.update`, `append` or mixed value write exists in scope.
- CSV/ExcelWriter occurrences under `backend/scripts/` are offline analytical
  or import-support scripts, not production download paths. They remain
  inventory items for a dedicated script-governance pass and were not invoked
  with business data in H-12.
- Test fixtures that create XLSX source files are false positives; they do not
  publish user-visible exports.

## Remaining raw writer justification

No raw `ws.append` remains in the three runtime H-12 writer surfaces. Script
and test occurrences are documented above; no active CSV runtime consumer was
found.
