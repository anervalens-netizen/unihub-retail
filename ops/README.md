# Retail privileged deployment source

## Rolul acestei căi

Acesta este mecanismul formal, cu artefact imutabil, păstrat pentru release-uri
etichetate și schimbări cu risc mare. Nu mai este calea obligatorie pentru orice
modificare. Calea rapidă autorizată prin conversația operațională este definită
în `../docs/adr/005-chat-authorized-delivery.md` și poate folosi checkoutul local,
buildul, restartul serviciilor afectate și verificarea live fără un PR sau un
approval separat.

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
GitHub Enterprise. When this formal path is selected, the administrative
session creates a root-owned, 30-minute, one-time approval for the exact
successful CI run ID, `main` SHA and artifact SHA-256. The deploy entrypoint
atomically claims that approval before any application mutation and records it
as consumed or failed. A consumed, failed, expired, mismatched or duplicate
approval cannot authorize another attempt.

After the final CI artifact is verified, the operator or execution agent acting
under the active chat authorization runs interactively:

```bash
sudo /opt/Mobiup/ops/scripts/approve-retail-release.sh \
  <ci-run-id> <40-char-main-sha> <64-char-artifact-sha256>
```

The prompt requires the literal `APPROVE_RETAIL_PRODUCTION`. The execution agent
may complete this gate without asking the operator to run the command. Never
place it in Actions, a script run by the deploy identity, or an unattended
scheduler.

Invocation of this formal artifact entrypoint is allowed only through the
workflow and the dedicated `unihub-deploy` OS identity. This restriction does
not prohibit the ADR-005 local-first path. Install `unihub-deploy.sudoers` only
after validating it with `visudo -cf`. Politica permite numai entrypointul de
artefact si operatiile `acquire`/`release` ale lockului global
`/usr/local/sbin/unihub-deploy-lock`; scriptul lock root-owned valideaza strict
tokenul `GITHUB_RUN_ID-GITHUB_RUN_ATTEMPT` si timpii. CI verifica atat sintaxa,
cat si prezenta ambelor operatii, pentru ca workflow-ul sa nu ajunga la un
prompt sudo imposibil pe runner. Do not grant that identity general sudo,
Docker access, interactive login credentials, permission to run the approval
creator, or permission to invoke manual rollback. Set
`PRODUCTION_DEPLOY_APPROVALS_ENFORCED=true` only after the root-owned approval
store, exact sudo policy and dedicated runner are verified.

Manual and post-migration automatic rollback are allowed only when the target
commit has the exact same immutable migration manifest as the deployed commit.
The entrypoint performs this check before stopping either service. A target
with missing, added or changed migrations is refused without touching the live
checkout or frontend. Recover such a release by reviewed roll-forward; restore
the database backup only in a coordinated maintenance operation that also
accounts for every consumer and any writes after the backup.

If a post-migration health check fails and the prior manifest is incompatible,
the audit handle becomes `recovery_required` while the failed approval remains
immutable. A retry needs a fresh one-time approval for the same CI run, source
SHA and artifact digest; it reruns migrations idempotently, verifies health and
archives the first approval link before recording the recovery as deployed.
