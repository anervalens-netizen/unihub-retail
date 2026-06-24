# External audit snapshot — June 2026

The original multi-agent audit was useful as an investigation backlog, but it
copied runtime credential values into several reports. The raw files are
therefore not stored in Git.

Restricted original:

```text
/storage/backups/security-sensitive-audit/20260624-retail-audit-original/
```

The directory is mode `0700`, files are mode `0600`, and
`SHA256SUMS.txt` verifies all 20 original audit artifacts.

Do not restore the raw reports into the repository. Findings were independently
validated against code, database state, services and CI before implementation.
The canonical portfolio execution record is:

```text
/opt/Mobiup/docs/unihub-docs/plan/portfolio-hardening-cleanup-master.md
```

That record supersedes the audit's original severities, estimates and stale
recommendations.
