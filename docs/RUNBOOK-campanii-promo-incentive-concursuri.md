# Runbook campanii Promo, Incentive și Concursuri

Acest document descrie contractul operațional curent. Configurațiile concrete,
listele de produse și valorile comerciale nu se copiază în documentație sau
loguri.

## Surse de adevăr

| Domeniu | Sursă |
| --- | --- |
| Incentive | PostgreSQL `incentive_campaigns` și `incentive_products` |
| Promo | generația indicată de `data/promo_generations/current.json`; `data/hub_specials.json` este seed legacy |
| Promo actuals | sursele imuabile și hashurile din manifestul generației active |
| Concursuri | `data/contests.json` |
| Vânzări | snapshotul lunar Retail și agregatele `reporting_*` |

Fișierele din `data/` sunt neversionate și sunt incluse în backupul
operațional. Anexele sursă păstrate sub `docs/Campanii-promo/` sunt inputuri
business, nu rapoarte generate și nu se șterg la curățarea repository-ului.

## Semantica Incentive

Cardul principal afișează exact:

1. **Unități vândute** — cantitatea brută a produselor din mecanismele active;
2. **Unități eligibile după promo** — cantitatea rămasă după excluderea
   unităților reduse prin promo;
3. **Unități în magazinele calificate** — partea eligibilă din magazinele care
   îndeplinesc pragul curent;
4. **Incentive calculat acum** — plata rezultată din realizarea și
   multiplicatorul curent.

Sub card rămân mecanismele active ale lunii, cu perioadele și regulile lor.
`Incentive potential` poate exista în tabelele detaliate de agenți/magazine și
în exporturi ca simulare la realizare 100%, dar nu înlocuiește niciuna dintre
cele patru valori ale cardului.

Tabelul și exportul pe agenți se reconciliază cu totalul canonic pe magazine:
același agent rămâne pe rânduri separate când vinde în magazine diferite, iar
cantitatea eligibilă pe magazin/produs/perioadă se distribuie ca întreg prin
metoda celui mai mare rest. Astfel, retururile nu produc valori negative pe
agent și nici un total mai mare decât magazinul. O diferență fără atribuire se
afișează explicit ca `Neatribuit`, fără a inventa un agent.
Publisherul read-modelului Insight păstrează aceeași regulă: totalurile promo
produse canonic sub agentul sursă `-` sunt publicate o singură dată ca
`Neatribuit`, prin API-urile publice Campaigns și fără evaluator paralel.

În payload:

- `incentive_sold_qty` = unități vândute;
- `incentive_qty` = unități eligibile după promo;
- `incentive_qualified_qty` = unități eligibile în magazine calificate;
- `incentive_value` = incentive calculat acum;
- `incentive_potential` = valoare de simulare folosită numai unde este etichetată
  explicit ca potențial.
- `incentive_category_breakdown[].qty` = unități eligibile totale din categorie;
- `incentive_category_breakdown[].qualified_qty` = subsetul eligibil din
  magazine cu realizare de minimum 90%;
- `incentive_category_breakdown[].value` = incentive calculat după
  multiplicatorul magazinului;
- `incentive_category_breakdown[].potential` = incentive total la realizare
  integrală. Interfața afișează perechile calificat/total și sortează categoriile
  descrescător după `qty`.

Nu reutiliza `promo_qualifying_bons`, `promo_discounted_units` sau
`reporting_*.incentive_qty` pentru un alt sens doar fiindcă tipul numeric este
compatibil.

## Semantica Promo

Identitatea canonică a bonului este:

```text
sale_date + site_code + normalized agent + bon_nr
```

Un `bon_nr` singur nu este o cheie unică. Implementarea comună este în
`backend/services/promo_copurchase.py` și acoperă:

- co-purchase cu produs selectat;
- produse de același model;
- produs trigger + produs redus.

Metricile dedicate sunt:

- `promo_qualifying_bons` — bonuri calificate;
- `promo_discounted_units` — unități reduse;
- `promo_discount_value` — valoarea efectivă a reducerii;
- `promo_active_stores` — magazine cu activitate;
- `promo_active_agents` — agenți cu activitate.

`promo_qty` din reporting rămâne agregatul operațional simplu și nu este
sinonim cu bonurile calificate.

Pentru sursa POS, valoarea reducerii folosește `PromoValoare Luna Curenta`
înmulțită cu rata promoției (implicit 20%). Hub afișează în aceeași coloană
`Promo` unitățile confirmate și valoarea reducerii, agregate peste toate
promoțiile active. Totalurile de magazin și RM rămân exacte; distribuția la
agent urmează aceeași alocare proporțională documentată pentru unitățile POS.
Rândurile negative reprezintă retururi valide: cantitatea și valoarea sunt
însumate net pe `(SiteCode, Cod)`, iar numai rezultatul net pozitiv contribuie
la Promo și la excluderea din Incentive.

Toate promoțiile active ale lunii contribuie la excluderea unităților reduse
din Incentive, indiferent de promoția selectată vizual în Focus.

## Mecanisme Incentive în aceeași lună

`incentive_products.valid_from` și `valid_to` permit mai multe mecanisme în
aceeași lună. Pentru fiecare vânzare se folosește lista și recompensa activă la
data tranzacției; rezultatele perioadelor se însumează înainte de
multiplicatorul lunar.

În Focus, luna curentă folosește structura organizațională curentă și exclude
implicit magazinele închise. La împărțirea unei luni în mai multe mecanisme,
sursa POS cumulativă nu se fragmentează artificial: o subperioadă care nu
acoperă integral intervalul raportat folosește regula pe bonuri, identic cu
exportul pe produs.

O schimbare de mecanism trebuie să specifice:

- perioada fără suprapuneri contradictorii;
- lista unică de coduri și recompensa per cod;
- pragurile și multiplicatorii;
- regula promo care poate exclude unități;
- data de cutoff a unei surse POS corective, dacă există.

Importul se face cu `backend/scripts/import_incentive_campaign.py`, întâi
dry-run și apoi într-o fereastră controlată. Nu modifica direct tabelele în
producție.

## Promo actuals

Importul POS citește seedul `data/hub_specials.json`, dar nu îl activează
direct. Înaintea oricărei promovări validează all-or-nothing cheile,
intervalele, suprapunerile de produse, cutoff-ul neregresiv, valorile finite și
nefractionare și materializarea masterelor de produs. Configurația, sursele și
manifestul sunt scrise într-un director de generație imutabil sub
`data/promo_generations/`.

Pointerul `current.json` se mută atomic numai sub lock și dacă hashul lui este
cel observat la începutul validării. Un writer stale primește conflict și nu
înlocuiește generația bună. Runtime-ul reverifică hashurile configului și ale
fiecărei surse înainte de utilizare.

Până la cutoff, sursa POS cumulativă corectează Promo și excluderea Incentive;
după cutoff, regula pe bonuri acoperă numai coada perioadei. Dacă o sursă
configurată lipsește sau nu corespunde hashului, pointerul rămâne nemodificat,
rezultatul este fail-closed și eroarea nu expune date comerciale în log.

Contractul runtime este fail-closed:

- `complete`: Promo și Incentive pot fi raportate oficial;
- `partial`: numai partea Promo confirmată poate fi afișată informațional;
- `invalid`: nu există fallback numeric la zero;
- orice promoție activă `partial`/`invalid` face Incentive-ul lunar neoficial,
  ascunde valorile financiare în UI și blochează exportul oficial.

Nu activa metrici Promo/Incentive zilnice. Raportul POS este cumulativ până la
cutoff și nu oferă o alocare autoritativă pe fiecare zi; totalurile și evoluția
lunară rămân granularitățile oficiale.

Verificarea read-only a raportului detaliat ERP din `Setări -> Importuri` nu
înlocuiește importul POS și nu certifică Promo/Incentive. Ea limitează calculele
Retail la 1-cutoff-ul ultimei zile disponibile în snapshotul Retail activ.
Coloanele `ZileLuna`, `ZileTrecute` și `ZileRamase` din raport sunt ignorate,
inclusiv când sunt goale. Verificarea poate reconcilia totalurile Focus prezente
în raport; valorile Promo/Incentive rămân informative deoarece fișierul
agregat nu conține coduri de produs, identitatea bonului și unități promo.

Raportul trebuie să conțină foile `Locatii` și `Agenti`. Unele versiuni ERP
expun în `Locatii` numai procentele Focus; în acest caz Retail agregă valorile
absolute `AccFocusQtty`, `Audio`, `Battery`, `Suporti`, `FoliiQtty`,
`Folii Sticla`, `Folii TPU`, `Still&Protectie` și `Incarcare&Transfer` din
`Agenti`, grupat după `CodLocatie`. Coloanele absolute prezente în `Locatii`
rămân autoritative pentru validare și trebuie să aibă același total cu
`Agenti`; o diferență oprește verificarea ca raport inconsistent.
Foaia `Locatii` trebuie să includă antetul și rândurile detaliate de magazine;
un export care conține numai subtotalul cache-uit este incomplet și este respins
cu instrucțiunea de regenerare, fără comparație parțială sau modificare de date.

## Concursuri

Concursurile sunt config-driven și scoped server-side. Configurația definește:

- cheia și perioada;
- scope-ul organizațional;
- regulile de punctaj;
- clasamentul și premiile;
- `identity_policy`: `site_agent` sau `person_id`.

`site_agent` păstrează un participant separat pentru fiecare
`(site_code, agent normalizat)`; vânzările nu sunt transferate către un
magazin principal. `person_id` poate uni activitatea cross-store numai printr-un
link salarial confirmat; o identitate necunoscută sau neconfirmată oprește
calculul, iar omonimele nu sunt agregate implicit.

Filtrele globale nu trebuie să extindă sau să restrângă accidental scope-ul
oficial al concursului. Răspunsul backend este autoritativ.

## Flux de schimbare

1. pornește dintr-un fișier/config nou sau o revizie explicită, nu edita
   retroactiv o perioadă închisă;
2. validează toate cheile, intervalele, suprapunerile, codurile, cutoff-ul și
   configurația de identitate înainte de orice scriere;
3. stage-uiește generația și manifestul fără a muta pointerul;
4. reverifică hashurile configului, surselor și materializării;
5. promovează `current.json` numai cu lock și CAS pe hashul pointerului
   observat înainte de validare;
6. compară separat bonurile promo, unitățile reduse, unitățile Incentive și
   plata;
7. rulează testele backend și frontend relevante;
8. verifică exporturile și cele patru valori ale cardului;
9. livrează prin calea proporțională cu riscul din ADR-005; dacă se deschide PR,
   agentul îl duce prin CI, merge, deploy și verificare fără o aprobare repetată;
10. verifică live generation ID, hashuri și metrici fără a afișa date comerciale.

## Verificări minime

```bash
pytest backend/tests/test_campaigns_promos.py \
  backend/tests/test_import_promo_actuals.py \
  backend/tests/test_contests.py \
  backend/tests/test_promotion_evaluation.py \
  backend/tests/test_campaigns.py -q
npm run test -- src/components/Campaigns.test.ts
npm run typecheck
npm run build
```

Pentru o schimbare de contract sau de calcul, rulează și suita completă conform
`AGENTS.md`. Testele trebuie să includă promoții suprapuse, cutoff, duplicate,
retururi, magazine necalificate și lipsa sursei corective.

## Rollback

Generațiile sunt imuabile și backupul operațional include întregul
`data/promo_generations/`. Înainte de promovare, păstrează hashul și conținutul
pointerului curent. Pentru rollback:

1. oprește o nouă promovare concurentă și verifică hashul pointerului activ;
2. reverifică manifestul și toate hashurile generației precedente;
3. înlocuiește atomic numai `current.json` cu pointerul precedent;
4. verifică generation ID, Focus, exporturile și health; nu șterge generația
   respinsă, deoarece rămâne evidence de audit.

## Autoritatea snapshotului sales

Fișierul oficial lunar are politica `authoritative_replace`: scăderea de
rows/value/quantity/receipts, dispariția unor magazine/zile sau un cutoff mai
mic decât snapshotul precedent sunt anomalii informative păstrate în manifest,
nu veto-uri euristice. Sunt blocante numai contradicțiile interne ale
candidatului: lună mixtă/greșită, cutoff în afara lunii, rând după cutoff,
schema invalidă, candidat gol ori neconcordanță staging/manifest/digest.

Promotion ledgerul și stagingul sunt append-only DB-side. Headul se mută numai
prin funcția SQL controlată cu lease owner, revision/parent și digest rehash;
rollbackul clonează generația păstrată și publică un nou eveniment CAS. Nu se
acordă UPDATE/DELETE direct și nu se deduplică rândurile sales identice.

## Reguli de siguranță

- nu loga bonuri, nume de agenți, liste comerciale sau valori financiare;
- nu muta semantica între câmpuri existente;
- nu modifica date business live pentru acceptanță;
- nu introduce fallback financiar care transformă o eroare în zero;
- păstrează exporturile private/no-store;
- păstrează calculele în service/repository, nu în router sau componenta UI.
