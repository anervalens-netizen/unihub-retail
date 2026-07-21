# Import lunar salarii oficiale HR

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

## 2. Import atomic

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
