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
