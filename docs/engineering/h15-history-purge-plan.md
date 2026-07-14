# H-15 — History purge și storage guvernat

## Stare la 2026-07-14

Ownerul business a aprobat explicit rescrierea istoricului Git. Namespace-ul
`reports/` a fost eliminat cu `git-filter-repo` într-o clonă mirror izolată,
apoi `main` a fost actualizat prin force-push cu lease exact pe vechiul SHA.

- vechiul `main`: `de289cd4cb092dc7b34ee2a66183089ecc9d89f7`;
- primul `main` rescris: `f3388b4e8931e44d443c65151f0e37d84d3799e3`;
- tree final neschimbat: `2fb7fbb1152782734f5ac0fcf0fc03ab3c31fbed`;
- 34 path-uri istorice `reports/**`, în 8 commituri;
- 0 path-uri sau obiecte `reports/**` accesibile din `main` după rescriere;
- 0 forks GitHub;
- toate branchurile/tagurile locale vechi și refs-urile temporare Codex au fost
  eliminate după backup și verificare.

Cele 8 PNG din `public.bak-logo-20260626-155400/**` nu au fost incluse în
history purge: inventarul nu a identificat date sensibile, iar eliminarea lor
din HEAD rămâne suficientă.

## Backup și retenție

Înainte de force-push au fost verificate și publicate într-o generație
guvernată:

- bundle complet pre-purge, incluzând toate refs locale și stash-ul istoric;
- bundle post-purge;
- arhiva celor 30 de artefacte eliminate din HEAD;
- commit/ref maps și manifest SHA-256;
- permisiuni `0700` pentru directoare și `0600` pentru fișiere;
- retenție minimă 90 de zile, cu eliminare numai după aprobare manuală.

Copiile canonice sunt locale sub
`/opt/Mobiup/secure-archive/unihub-retail/h15/` și pe NAS sub
`/storage/backups/server-68/governed/unihub-retail/h15/`. Checksum-urile au
fost verificate local și remote fără citirea conținutului business.

## Limitare GitHub administrată extern și acceptarea riscului rezidual

Force-push-ul nu poate modifica refs-urile read-only `refs/pull/*/head`.
Auditul după rescriere a găsit 89 refs PR interne; 79 păstrează direct vechiul
istoric care conține `reports/`. Rularea de suport cu
`git-filter-repo --sensitive-data-removal` raportează 89 PR-uri afectate și
primul commit schimbat
`00555607a21542425b3ad5f4c4d0e8c61fa8779b`.

Eliminarea acestor refs, cached views și obiecte server-side poate fi făcută
numai de GitHub Support. Dacă se solicită ulterior această igienizare
suplimentară, ticketul trebuie să includă repository-ul
`anervalens-netizen/unihub-retail`, 89 PR-uri afectate, primul commit schimbat
de mai sus și faptul că nu există forks sau obiecte LFS. Procedura oficială:
<https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository>.

La 2026-07-14, ownerul business a acceptat explicit riscul rezidual după
confirmarea că repository-ul este privat, are un singur colaborator, nu are
forkuri, iar refs-urile PR interne nu au expunere publică și nu sunt folosite
de runtime sau de calea de deploy. Purge-ul din `main`, clonele locale și runner
este complet. Curățarea server-side prin GitHub Support rămâne o opțiune de
igienizare viitoare, nu o dependență de închidere. Findingul H-15 este închis.
