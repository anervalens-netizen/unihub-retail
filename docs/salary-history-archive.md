# Istoric salarial HR — import separat

La cererea ownerului din 10 septembrie 2026, documentele istorice din Outlook
HR/Cristina sunt pastrate in `salary_history_rows`, separat de `salary_records`.
Acest flux nu este promovare de salarii oficiale si nu modifica registrul privat
al persoanelor sau mecanismul de aprobare semnata al importatorului oficial.

- Sursa unica este randul fizic `(source_sha256, source_sheet, source_row)`.
  Copiile binare sunt colapsate; componentele repetate legitime raman distincte.
- Orice `candidate_person_id` trebuie verificat prin identificator valid in sursa
  si nume unic concordant cu persoana existenta. Numele singur nu creeaza o persoana.
- Sumele sunt Decimal, net plus bonuri; nu reprezinta costul total al angajatorului.
- Perioada/firma/versiunile incerte raman arhiva de verificat. Grupurile lunare
  cu versiuni contradictorii sunt excluse integral din estimari.
- `salary_history_estimation_inputs` exclude si dinamic orice luna/firma deja
  prezenta in salariile oficiale. Nu se aduna arhiva cu acoperirea oficiala.
- Sursele Vodafone si cele cu acoperire istorica neconfirmata sunt excluse.
- Nu se completeaza lunile lipsa cu zero. Pauza din 2018–2023 este explicata de
  delegarea ownerului in alta tara; nu este dovada de lipsa cheltuielii salariale.
- Arhiva poate fi consultata numai prin accesul salarial existent, in
  Management > Salarii > Istoric HR. Nu expune CNP sau cai private ale surselor.

Importatorul `backend/scripts/import_salary_history.py` primeste `--plan`,
`--expected-sha256`, `--applied-by`, optional `--apply`. Verifica planul si toate
hashurile sursa, apoi foloseste principalul de migrari si tranzactie atomica.
Repetarea aceluiasi plan nu dubleaza randurile. Reinterpretarea unui rand deja
arhivat este refuzata; necesita o revizie explicita viitoare, nu overwrite tacit.
Rolurile runtime au numai SELECT pe arhiva.

Lotul initial are hash
`f6368840e81508ac379f525638e78fc46955bc17ddcefbd5a953d0a220722564`:
12.288 randuri, 5.178 legaturi verificate la persoane existente si 5.291 randuri
eligibile pentru estimari in 45 combinatii luna/firma. 25 grupuri cu versiuni
contradictorii raman neeligibile. Artefactele si provenienta originalelor sunt
private in `/opt/Mobiup/docs/comisioane/outlook-cristina-20260910/`.

Acest lot pregateste intrari pentru estimari; nu recalculeaza si nu promoveaza
automat P&L. Estimarile viitoare trebuie sa declare acoperirea si conversia de la
net+bonuri la cost complet; sumele istorice nu inlocuiesc contabilitatea.

## Clarificare owner: provenienta HR si codul ERP

Ownerul confirma ca fisierele din mail sunt sursele oficiale HR folosite pentru
tabul salarial existent. Istoricul se afiseaza implicit in Salarii oficiale >
Istoric state HR, inclusiv pentru fosti angajati fara cod ERP. Absenta codului
ERP nu invalideaza statul. Legatura cu persoana din aplicatie ramane distincta
de provenienta oficiala a documentului. Sinteza existenta pastreaza separat
perioadele deja calculate; aceasta schimbare de prezentare nu promoveaza
randuri in salary_records si nu modifica verificarea semnata a importului.

## Iulie in tabelul lunar

Citirile overview/evolution/trend includ acum iulie2026 din randurile HR selectate,
numai daca firma/luna lipseste in salary_records. Este compozitie read-only,
nu promovare salariala; aprobarea semnata si identitatile private nu se modifica.
Cele 161 pozitii nominale HR sunt distincte; 157 ating pragul mediei. Pozitiile
fara asociere au chei locale de grupare per rand, nu person_id persistat. Numarul
global de persoane asociate exclude aceste chei; sumele le includ. Totalul
Mobiup este recalculat inclusiv randul2, omis de formula T81 din original.

## Navigare si detalii agregate

Overview este prima vizualizare, Istoric a doua. In Istoric, magazinele sunt
grupate pe cod locatie si firma, iar numele pe text normalizat si firma. Sunt
grupari de consultare, nu uniri de identitate. Totalurile si mediile pornesc
de la lunile selectate; detaliile arata separat si variantele nealese.
Ferestrele Overview/Magazine citesc strict salary_records prin campurile deja
permise rolului web. Ferestrele Istoric/Magazine si Istoric/Agenti citesc arhiva
cu filtre exacte pentru magazin sau nume si firma. Ambele endpointuri folosesc
acelasi require_salary_access; nu se extind granturile si nu se afiseaza CNP.
