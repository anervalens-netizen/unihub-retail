# Import lunar salarii oficiale HR

> P0 status la `f9c0b1efe15686bcda532d22528e6e2644925aec`: importul live este NO-GO până la reconcilierea HR a celor 8 grupuri. Acest runbook documentează gardurile implementate și nu autorizează mutații production.

Acest flux publica salariile oficiale primite lunar de la HR in
**Management -> Salarii** si actualizeaza, cand este necesar, legaturile folosite
de sumarul salarial al agentului din Hub.

## Surse si reguli

- Sunt obligatorii doua fisiere sursa pentru aceeasi luna: Mobiup si Mobicell.
- Originalele se pastreaza in `/opt/Mobiup/docs/comisioane/`, cu permisiuni
  owner-only. Nu se folosesc workbook-urile generate de Grile drept sursa HR.
- Luna si anul se transmit explicit importatorului; numele fisierului nu decide
  perioada importata.
- `total_salary` este `TOTAL SALARIU + BONURI MASA`.
- Importul inlocuieste atomic numai luna si firmele furnizate. Nu se importa o
  singura firma ca inchidere lunara si nu se accepta un batch gol.
- CNP-ul nu se afiseaza in rapoarte, loguri sau fisiere de verificare. El ramane
  exclusiv in limita privata de identitate salariala.

## P0 gate și limite

Dry-run-ul este obligatoriu pentru Mobiup și Mobicell. CNP-ul nu apare în manifest, loguri, exporturi sau handoff. Orice CNP gol, non-numeric, diferit de exact 13 cifre ori cu checksum invalid oprește batchul înaintea tranzacției.

Același CNP cu nume normalizate diferite, conflict cu `salary_private.people` sau provenance incomplet produce zero scrieri. Componentele salariale sunt permise pe source rows distincte; nu se impune unicitate brută person-month fără decizia HR.

## 1. Preflight si dry-run

Confirma luna din continutul ambelor fisiere, antetele obligatorii (`CNP`,
`Nume Prenume`, `Denumire locatie`, `TOTAL SALARIU`, `Bonuri masa ...`) si
totalurile HR. Ruleaza fara `--apply`:

```bash
cd /opt/Mobiup/unihub-retail
backend/venv/bin/python backend/scripts/import_salary_records.py \
  --year YYYY --month M \
  --mobiup-file "/opt/Mobiup/docs/comisioane/FISIER-MOBIUP.xls" \
  --mobicell-file "/opt/Mobiup/docs/comisioane/FISIER-MOBICELL.xls"
```

Pentru fiecare firma reconciliaza cu sursa HR:

- numarul de randuri valide;
- totalul calculat, inclusiv bonurile;
- numarul de `site_code` mapate;
- fiecare locatie fara `site_code`.

O locatie nemapata nu blocheaza totalul general, dar blocheaza atribuirea
corecta pe manager/magazin. Corecteaza aliasul in importator numai dupa
confirmarea locatiei din `stores`, apoi repeta dry-run-ul si testele importului.

Dry-run-ul trebuie să emită manifestul pentru ambele firme, cu row count, control total, locații nemapate și SHA-256 al fiecărui fișier, fără CNP. Pentru trasabilitate, fiecare rând aplicat are batch id, source file, sheet, source row și source SHA-256; cheia raw este provenance de sursă, nu unicitate person-month.

Dovezi locale relevante: `backend/scripts/run_tests_isolated.sh -q`, `backend/venv/bin/mypy backend/ --ignore-missing-imports --explicit-package-bases` și testele `backend/tests/test_salary_import.py`. Acestea verifică fail-closed, zero-write la conflict și rollback tranzacțional; nu înlocuiesc reconcilierea HR live.

## 2. Apply controlat — NO-GO la baseline P0

Comanda de mai jos este calea tehnică existentă, dar nu se execută pe date live la baseline-ul P0. Devine eligibilă numai după reconcilierea HR documentată pentru cele 8 grupuri, backup/pre-image verificat, manifest aprobat și review independent.

În caz de fault după inserarea identității, tranzacția revine integral; nu se repară manual parțial și nu se șterg duplicatele live fără sursă și aprobare.

Doar dupa reconcilierea ambelor firme, repeta exact comanda cu `--apply`.
Importatorul scrie identitatile private si `salary_records` in aceeasi
tranzactie.

```bash
backend/venv/bin/python backend/scripts/import_salary_records.py \
  --year YYYY --month M \
  --mobiup-file "/opt/Mobiup/docs/comisioane/FISIER-MOBIUP.xls" \
  --mobicell-file "/opt/Mobiup/docs/comisioane/FISIER-MOBICELL.xls" \
  --apply
```

## 3. Legaturi agent-salariu

`salary_records` alimenteaza direct tabul Salarii. `agent_salary_links`
alimenteaza sumarul salarial din Hub si necesita reevaluare cand apar agenti
noi, mutari sau nume schimbate.

Ruleaza mai intai matcherul fara `--apply-db`, pentru luna curenta de reporting:

```bash
backend/venv/bin/python backend/scripts/match_agent_codes_to_salary_names.py \
  --reporting-month YYYY-MM \
  --output backend/outputs/agent_code_name_matches-YYYY-MM.csv
```

CSV-ul este privat si gitignored. Verifica manual toate valorile `review`,
`unmatched`, candidatii globali si override-urile. Dupa corectarea cazurilor
ambigue, aplica doar rezultatul verificat:

```bash
backend/venv/bin/python backend/scripts/match_agent_codes_to_salary_names.py \
  --reporting-month YYYY-MM \
  --effective-from-month YYYY-MM \
  --output backend/outputs/agent_code_name_matches-YYYY-MM.csv \
  --apply-db
```

`--apply-db` foloseste explicit `MIGRATION_DATABASE_URL` din
`.env.migrations`; rolul runtime ramane read-only pe datele salariale.
Matcherul nu suprascrie o legatura manuala cu una automata.

## 4. Verificare finala

- In DB, pentru luna importata: ambele firme prezente, totaluri egale cu HR,
  `person_id` complet, duplicate neasteptate zero si locatii nemapate explicate.
- Ruleaza `backend/venv/bin/pytest backend/tests/test_salary_import.py
  backend/tests/test_match_agent_codes_output.py -q` dupa schimbari de cod sau
  aliasuri.
- Verifica health local si, autentificat, luna in **Management -> Salarii**,
  filtrele Firma/Manager/Magazin/Agent, istoricul unui agent si sumarul salarial
  din Hub pentru o legatura confirmata.
- Importul este citit direct din PostgreSQL; fara schimbare de cod nu necesita
  build frontend sau restart de serviciu.
- Noteaza fisierele sursa, luna, numarul de randuri, totalul pe firma,
  locatiile nemapate si rezultatul verificarii live in handoff-ul operational.
