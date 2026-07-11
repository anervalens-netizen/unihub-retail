# H-12 spreadsheet writer inventory

| Path | API | Runtime/offline/test | Input | Output opened by humans? | Decision |
| --- | --- | --- | --- | --- | --- |
| `backend/services/exports.py` | `Workbook.save` | Runtime | Reporting rows and request metadata | Yes | Remediated: every dynamic row uses `append_openpyxl_row`. |
| `backend/services/target_calculator.py` | `Workbook.save` | Runtime | Scenario, notes and warnings | Yes | Remediated: every dynamic row uses `append_openpyxl_row`. |
| `backend/services/grile_monthly.py` | `Workbook.save` | Runtime | Google/HR-derived rows and metadata | Yes | Remediated: central boundary; only two source-owned `TrustedFormula` values. |
| `backend/scripts/generate_may_old_vs_new_grid.py` | `pandas.ExcelWriter/to_excel` | Offline analytical report | DB/archive-derived DataFrames | Yes | Remediated: text columns pass through `sanitize_dataframe_text` before export. |
| `backend/scripts/generate_salary_grid_simulation.py` | `pandas.ExcelWriter/to_excel` | Offline analytical report | DB/archive/HR DataFrames | Yes | Remediated: text columns pass through `sanitize_dataframe_text` before every sheet export. |
| `backend/scripts/match_agent_codes_to_salary_names.py` | `csv.DictWriter` | Offline reconciliation report | DB/salary matching strings | Yes | Remediated: each CSV field passes `csv_cell_value`. |
| `backend/scripts/run_ai_forecast_xreg.py` | `csv.DictWriter` | Offline forecast artifact | API/DB forecast rows | Yes | Remediated: each CSV field passes `csv_cell_value`. |
| `backend/scripts/import_historical_monthly_sales.py` | `openpyxl` import | Offline import reader | Supplied XLSX | No | Read-only importer; no human-facing output writer. |
| `backend/scripts/import_annual_summary.py` | `openpyxl` import | Offline import reader | Supplied XLSX | No | Read-only importer; no human-facing output writer. |
| `backend/services/reporting_refresh.py` | `load_workbook` | Runtime import/refresh | Supplied XLSX | No | Reader only. |
| `src/lib/tableExport.ts` | custom XLSX XML builder | Frontend export | Visible table text | Yes | Existing XML-level tests show text is written as inline strings, not formula tags; no change required. |
| `backend/tests/test_*.py` and `src/lib/tableExport.test.ts` | workbook/CSV fixtures | Test | Synthetic fixtures | No | Test-only fixture creation; not a product export surface. |

Google operations in the listed runtime surfaces are reads, exported remote XLSX
downloads, or `batchClear`; no `values.update`, `values.append` or mixed-value
writer exists in scope. If one is introduced, untrusted values must use
`google_sheets_value` with `valueInputOption=RAW`.

## Runtime append inventory

The three runtime modules have no raw `Worksheet.append` call. Their remaining
`.append(...)` hits build Python lists only: `exports.py` builds column/table
data, `target_calculator.py` builds calculation collections, and
`grile_monthly.py` builds validation/report collections. Dynamic direct-cell
assignments were also reviewed; output data goes through the central row
boundary, while remaining assignments are styling/chart/layout operations.
