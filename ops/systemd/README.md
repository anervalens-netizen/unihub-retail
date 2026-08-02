# Retail systemd units

These files are the versioned source of truth for the Retail web, operations
worker, dedicated import worker and one-shot migration services. Production
copies live under `/etc/systemd/system`.

Install a reviewed unit with `sudo install -m 0644`, run
`sudo systemctl daemon-reload`, then restart only the affected service. The
migration unit remains one-shot and must never be enabled as a long-running
daemon.

Before installation:

```bash
systemd-analyze verify \
  ops/systemd/unihub-backend.service \
  unihub-worker.service \
  ops/systemd/unihub-import-worker.service \
  ops/systemd/unihub-retail-migrate.service
```

After a backend restart, `/livez` proves that the process responds and
`/readyz` proves that PostgreSQL and the BFF session backend are usable.
`/health` remains a compatibility alias for `/readyz`.

## P0 lifecycle și evidence

`unihub-retail-migrate.service` este one-shot și citește `.env.migrations`; web/worker nu execută DDL. La baseline-ul `f9c0b1efe15686bcda532d22528e6e2644925aec`, migrațiile 032–034 se verifică prin manifest înaintea oricărui restart.

Workerul operațional are `TimeoutStopSec=2460`, import workerul `1860`, backendul `75`, iar migration runnerul `TimeoutStartSec=300`. Aceste valori aliniază shutdown-ul controlat, dar nu închid benchmarkul P0.5 și nu justifică ridicarea limitelor de memorie ca substitut pentru remediere.

Recovery-ul P0 păstrează ultima generație bună: sales folosește generation head/CAS și rollback auditabil, P&L folosește pointer/pre-image shadow fără apply runtime, iar salary batch revine tranzacțional. Dacă health sau manifestul nu se reconciliază, oprește promovarea și marchează `recovery_required`.
