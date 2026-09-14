# Grile V2 Google Sheets pilot — September 2026

Production uses `unihub-grile-worker.service`. Its `grile_v2_sync_runtime` loop checks every 300 seconds after the previous iteration completes. `grile_v2_sheet_exports` is the enabled registry: 43 September 2026 stores: 21 Andrei Stancu, 12 Bogdana Costan and 10 Mihai Condorateanu. Mihai was added after the owner supplied the workbook with company mappings. Ambiguous store-days were deliberately left for manager correction; they must not be silently filled by the publisher.

The publisher reads the same canonical calendar/earnings projection as Retail; it does not recalculate salary formulas in Sheets. Published sales cutoff is required. Each store content hash includes calendar, target settings, earnings and format version. Unchanged files cause no Sheets I/O. Changed files publish all three tabs in one batchUpdate, retaining stable IDs. A PostgreSQL session advisory lock serializes writers; failures preserve the last good publication and retry on the next sweep. Last success/error is persisted separately. Google 429 ends the sweep and retries later.

`backend/services/grile_v2_sheet_template.json` retains the approved native styles and geometry without old cell values. Original native MODEL is `1jCc2YBpb_3B70cmYwzxYx9_dXcR78y-3PYa36eq1S_A`. Grila KPI merges and Pontaj frozen-column header merges must be preserved rather than recreated: Google rejects recreating a merge spanning frozen columns.

Owner's Drive root: `1lYgYDPSAi2-Bbp9_Js7Yvh22hGJYOvIc`.
Index: `1QFhcwOSh9CP0pOegCMLjGWCoQlKLqXodbNknK1y4p7U`.
Store files use anyone-with-link reader permissions explicitly authorized by the owner. Folder/index membership remains unchanged. All store tabs are protected; only the owner and existing synchronization service account can edit them.

Migrations 084 and 085 add the registry and narrow operations source-read privileges. The `unihub-grile` OS account has read/traverse ACLs on `data/promo_generations`, including a default ACL on its root so future immutable generations remain readable. ACL backup: `/tmp/grile-v2-promo-acl-before.txt`. Repository file backups: `/tmp/grile-v2-pilot-backup-20260914`.

The pilot is month-scoped. A new month requires an explicitly seeded registry and corresponding calendar; September files are not silently reset to another month. Full first publication for 33 stores took about five minutes; later unchanged sweeps take about one second. Reads/writes share Google project quotas with V1; pace verification at no more than 40 read requests/minute and never retry 429 in a tight loop.

Validation: the initial operations-account publication updated all 33 Andrei/Bogdana files, failed 0. After adding Mihai, all 43 registry entries had a successful publication on 2026-09-14. The initial worker sweep logged updated 0 / unchanged 33 / failed 0 at 14:35 Europe/Bucharest. These are historical checks, not a guarantee of current queue health. Inspect the registry success/error state and worker logs for current status. The local per-cell verification artifact is outputs/grile-v2-pilot/verify_live.py.
