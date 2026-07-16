# Retail privileged deployment source

`deploy-retail-artifact.sh` and `approve-retail-release.sh` are the reviewed
sources for the root-owned production boundary. CI must never install them.
Provisioning is a separate privileged operation that copies the reviewed files
to `/opt/Mobiup/ops/scripts/`, makes the files and parent directory root-owned
and non-writable by the runner, and verifies the installed SHA-256 values match
the reviewed sources exactly.

Run the sandbox without production access:

```bash
ops/test-deploy-retail-artifact.sh
```

Validate an already downloaded CI artifact without deploying it:

```bash
ops/deploy-retail-artifact.sh validate <artifact.tar.gz> <40-char-main-sha>
```

GitHub required reviewers are not available for this private repository without
GitHub Enterprise. The replacement is not an unapproved manual deployment: the
human creates a root-owned, 30-minute, one-time approval for the exact successful
CI run ID, `main` SHA and artifact SHA-256. The deploy entrypoint atomically
claims that approval before any application mutation and records it as consumed
or failed. A consumed, failed, expired, mismatched or duplicate approval cannot
authorize another attempt.

After the final CI artifact is verified, the human approver runs interactively:

```bash
sudo /opt/Mobiup/ops/scripts/approve-retail-release.sh \
  <ci-run-id> <40-char-main-sha> <64-char-artifact-sha256>
```

The prompt requires the literal `APPROVE_RETAIL_PRODUCTION`. Never place this
command in Actions, a script run by the deploy identity, or an unattended
scheduler.

Production invocation is allowed only through the workflow and the dedicated
`unihub-deploy` OS identity. Install `unihub-deploy.sudoers` only after validating
it with `visudo -cf`. Do not grant that identity general sudo, Docker access,
interactive login credentials, permission to run the approval creator, or
permission to invoke manual rollback. Set
`PRODUCTION_DEPLOY_APPROVALS_ENFORCED=true` only after the root-owned approval
store, exact sudo policy and dedicated runner are verified.

Manual and post-migration automatic rollback are allowed only when the target
commit has the exact same immutable migration manifest as the deployed commit.
The entrypoint performs this check before stopping either service. A target
with missing, added or changed migrations is refused without touching the live
checkout or frontend. Recover such a release by reviewed roll-forward; restore
the database backup only in a coordinated maintenance operation that also
accounts for every consumer and any writes after the backup.
