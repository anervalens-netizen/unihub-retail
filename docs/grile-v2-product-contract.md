# Grile V2 nativ Retail — contract de produs

La 2026-09-07 proprietarul a ales implementarea directă în Retail. Repository-ul
standalone UniHub Grile se arhivează; pilotul Sheets din august 2026 este retras.
Acest document păstrează cerințele aprobate, fără a importa arhitectura veche.
Pilotul nou vizează luna **2026-09**, cu program începând cu **1 septembrie 2026**.
V1 rămâne fluxul oficial până la acceptarea noului flux și reconcilierea salarială.
Planul și statusul etapelor se țin într-un singur
[tracker Retail #271](https://github.com/anervalens-netizen/unihub-retail/issues/271).

Retail deține autentificarea, catalogul, vânzările, targetele și infrastructura de
joburi. Modulul nou deține explicit programul, suplimentările și proiecția comună
persoană/zi/magazin. Ecranul, totalurile, Google și Excel folosesc această proiecție.
Google nu calculează o autoritate salarială separată. Nu se adaugă un serviciu,
un sistem de autentificare sau o coadă nouă pentru acest modul.

## Reguli de business confirmate

| ID | Regulă confirmată |
|---|---|
| BR-01 | Rețeaua magazinelor permite Google Sheets, dar nu aplicația Retail/Grile și nici autentificarea într-un cont Google. Accesul agentului folosește linkul permanent, accesibil fără cont. |
| BR-02 | Lucrează exact un agent într-un magazin într-o zi de funcționare. Magazinul are de regulă doi agenți care alternează; suplimentarul lucrează tot o zi întreagă. Nu există ture împărțite în aceeași zi. |
| BR-03 | Managerul deține programul și toate corectările. Agentul nu introduce vânzarea zilnică, programul sau pontajul în Sheets. |
| BR-04 | Programul lunii următoare se pregătește cu câteva zile înainte de finalul lunii curente, folosind catalogul disponibil în luna curentă. Importul unui Excel cu toate magazinele trebuie să fie posibil; șablonul exact și reimportul după corectări rămân de decis. După import, managerul poate corecta calendarul. |
| BR-05 | În interfața Retail, magazinele sunt grupate pe manager. Deschiderea magazinului oferă trei subtaburi, în ordinea `Grile / Calendar / Pontaj`. |
| BR-06 | `Grile` arată grilele agenților de bază ai magazinului, inclusiv câștigurile lor din suplimentări în alte locații. Codul agentului rămâne stabil la transfer. |
| BR-07 | `Calendar` este un calendar lunar mare. Click pe zi deschide alegerea agentului 1, agentului 2 sau `Suplimentar`. Pentru suplimentar se selectează persoana din catalogul regional, cu nume și cod agent. Este posibil și suplimentar în magazinul propriu. |
| BR-08 | Calendarul confirmat de manager determină cine primește vânzarea fizică magazin/zi. Pentru o zi suplimentară în alt magazin, vânzarea se înregistrează sub codul Team Leader regional, iar calendarul confirmă persoana efectivă. Reatribuirea schimbă creditul personal, fără să dubleze ori să mute totalul fizic al magazinului. |
| BR-09 | Orele unei zile apar exclusiv în pontajul magazinului unde persoana a lucrat efectiv. Pontajul lunar poate avea mai mult de doi participanți, deoarece include suplimentarii. |
| BR-10 | Plata suplimentării ajunge în grila personală de la magazinul de bază, cu data și locația lucrată. Ziua nu este pontată din nou la magazinul de bază. |
| BR-11 | Fiecare alocare este legată explicit de codul agentului și de aceeași identitate stabilă a persoanei. Catalogul candidat include agenții cu vânzări în luna curentă și în luna anterioară; un agent absent dintr-o lună cere confirmare activă de la manager, deoarece absența nu înseamnă plecare. Numele afișat și magazinul nu sunt suficiente pentru reunirea persoanei. |
| BR-12 | Google Sheets are trei foi vizibile: `Grile / Calendar / Pontaj`, cu aceleași date business ca aplicația. Linkurile permanente sunt păstrate. |
| BR-13 | Închiderea lunii produce ZIP cu Excel-ul fiecărui magazin, fiecare având cele trei foi, plus fișierul salarial centralizat compatibil cu utilizarea V1. |
| BR-14 | Centralizatorul are un singur rând per agent pentru luna închisă și însumează toate orele și câștigurile din toate locațiile. Baza salarială și bonurile se includ o singură dată. |
| BR-15 | E-pay este singurul input posibil al agentului. Vânzările sunt rare; proprietarul acceptă introducerea de către manager dacă citirea din Sheets adaugă prea multă complexitate. Alegerea canalului este încă deschisă. |
| BR-16 | Produsul trebuie să rămână simplu și optimizat. Standalone se arhivează, pilotul vechi se retrage, iar V2 se construiește direct în Retail. Refolosim selectiv reguli și componente verificate. Faza R1 acoperă fundația backend; calendarul vizual este R2, iar integrarea orelor și a banilor de target urmează ulterior. |
| BR-17 | Concediul planificat în Excel și adăugarea, modificarea sau anularea concediului de către manager la mijlocul lunii urmează același flux și aceeași autoritate ca `Calendar / Pontaj`. Zilele de concediu nu sunt zile lucrate și se exclud din alocarea targetului: `target magazin / zile de vânzare magazin * zile lucrate agent`; targetul magazinului rămâne neschimbat. |

### Identitate și centralizare

Un catalog central leagă codul de agent de persoană și de magazinul de bază.
Codul sursei trebuie verificat pentru unicitate/stabilitate înainte de alegerea
cheii tehnice. Dacă o persoană are coduri diferite între surse/firme/perioade,
legătura trebuie confirmată explicit; nu se deduce din asemănarea numelor.
Catalogul trebuie să includă și agenți fără vânzări încă în luna viitoare.

O înregistrare de lucru conține persoana/codul, data, magazinul lucrat și tipul
zilei. Calendarul, pontajul, grila și centralizatorul folosesc aceeași
înregistrare. Magazinul de bază/effective-dated rămâne o asociere separată.

Exemplu sintetic de acceptanță, la politica orară încă de reconciliat cu V1:
agentul `AG001` are 154 ore în A, 22 în B și 11 în C. Pontajele arată separat
154/22/11; centralizatorul are un singur `AG001` cu 187 ore. Componentele
suplimentare sunt reunite fără a multiplica salariul de bază sau bonurile.

ZIP-ul și centralizatorul trebuie generate din aceeași revizie închisă a datelor
centrale, fără recitirea Sheets ca autoritate salarială. Totalul orelor din
centralizator trebuie să coincidă cu totalul orelor din pontajele magazinelor.
Nu însumăm salarii complete repetate în proiecțiile mai multor magazine.

### Propuneri și întrebări deschise

| ID | Punct de decis/verificat înaintea taskului dependent |
|---|---|
| D-01 | Recomandare: E-pay introdus de manager, două cantități lunare, Sheets numai pentru consultare. Alternativa este citirea limitată a acestor intrări din Sheets. Se alege o singură autoritate de editare; lipsa confirmării nu devine automat zero. |
| D-02 | Formatul exact al șablonului Excel pentru program și regulile reimportului după corectări manuale rămân de decis. Recomandare: preview cu diferențe/conflicte și aplicare confirmată, fără agent AI obligatoriu în flux. |
| D-03 | Reconcilierea formulelor, rotunjirilor, divizorului targetului, orelor/zi, concediilor și componentelor salariale din [regulile standalone arhivate](https://github.com/anervalens-netizen/unihub-grile/blob/6d933d28584c420da5fe28fe39e7117b6288bf68/docs/MOBIUP_RULE_PACK.md) cu V1. Valorile vechi documentate nu sunt o nouă aprobare salarială. |
| D-04 | Stabilitatea globală a codului agentului este confirmată, inclusiv la transfer. Rămân deschise excepțiile detaliate pentru salarizare între firme și perioadele effective-dated ale magazinului de bază; definirea firmei de salarizare evită dublarea persoanei în foile Mobiup/Mobicell. |
| D-05 | Inventarul exact al coloanelor centralizatorului V1 și modul de adăugare a codului agentului fără a strica utilizarea ulterioară a fișierului. |

Schimbul obișnuit de program și suplimentarea plătită trebuie diferențiate
explicit de manager. Nu inferăm suplimentarea din simpla modificare a zilei și
nu transformăm activitatea observată de vânzări în pontaj confirmat automat.
Codurile `TR...` reprezintă reprezentanți comerciali, nu Team Leaderi. Acestea,
codurile goale/`-` și locațiile de distribuție `TR ...` sunt excluse din catalogul
Retail; nu deducem codul Team Leaderului din prefixul `TR`.
Acestea sunt reguli de contract pentru fazele R1/R2 și următoarele; documentul
nu afirmă că implementarea este finalizată.
