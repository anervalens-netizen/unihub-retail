# Artifact conventions

The sandbox is expected to produce finished deliverables, not merely code snippets describing how to produce them.

## Workspace

- `/workspace/input` — owner uploads copied into the conversation workspace.
- `/workspace/work` — intermediate scripts, extracts, notebooks/data files and scratch output.
- `/workspace/output` — finished deliverables that UniHub should surface back into chat.

Do not overwrite an owner upload in `input/`. Copy/edit it under `work/` or create a new finished file under `output/`.

## Preferred deliverables

Use the format that best serves the request:

- `.xlsx` for tabular analysis, reconciliations and operational reports;
- `.pptx` for presentation-ready management summaries;
- `.pdf` or print-quality `.html` for narrative briefings;
- `.png`/`.jpg` for charts or visual exports;
- `.csv`/`.parquet` for large machine-oriented extracts;
- other useful formats when explicitly requested or clearly superior.

## Quality

- Give files clear Romanian/English names matching the user's language and task.
- Include source period/filter context in the workbook/report when relevant.
- For Excel, use readable headers, sensible widths, number/date/percent formats, frozen headers and filters where helpful. Add formulas/charts only when they improve the deliverable.
- For PPTX, use concise slide titles, readable charts/tables and a short source/context note rather than dense text walls.
- For PDF/HTML, optimize for reading/printing and keep tables from becoming unusable.
- If calculations are non-trivial, keep a reproducible script or intermediate data in `work/` while placing only finished artifacts in `output/`.

When the owner asks to inspect or edit an uploaded file, actually open/parse it in the sandbox, perform the requested work, and return the resulting file when appropriate.