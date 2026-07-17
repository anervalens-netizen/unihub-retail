# Runbook campanii Promo, Incentive și Concursuri

Acest document descrie contractul operațional curent. Configurațiile concrete,
listele de produse și valorile comerciale nu se copiază în documentație sau
loguri.

## Surse de adevăr

| Domeniu | Sursă |
| --- | --- |
| Incentive | PostgreSQL `incentive_campaigns` și `incentive_products` |
| Promo | `data/hub_specials.json` și anexele referite de configurație |
| Promo actuals | fișierele POS importate sub `data/promo_actuals/` |
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

În payload:

- `incentive_sold_qty` = unități vândute;
- `incentive_qty` = unități eligibile după promo;
- `incentive_qualified_qty` = unități eligibile în magazine calificate;
- `incentive_value` = incentive calculat acum;
- `incentive_potential` = valoare de simulare folosită numai unde este etichetată
  explicit ca potențial.

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
- `promo_active_stores` — magazine cu activitate;
- `promo_active_agents` — agenți cu activitate.

`promo_qty` din reporting rămâne agregatul operațional simplu și nu este
sinonim cu bonurile calificate.

Toate promoțiile active ale lunii contribuie la excluderea unităților reduse
din Incentive, indiferent de promoția selectată vizual în Focus.

## Mecanisme Incentive în aceeași lună

`incentive_products.valid_from` și `valid_to` permit mai multe mecanisme în
aceeași lună. Pentru fiecare vânzare se folosește lista și recompensa activă la
data tranzacției; rezultatele perioadelor se însumează înainte de
multiplicatorul lunar.

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

Importul POS validează sheetul și metadatele înainte de a păstra fișierul sub
`data/promo_actuals/`. Până la cutoff, sursa POS corectează calculul promo și
excluderea Incentive; după cutoff, calculul continuă din regulile pe bonuri.

Dacă sursa lipsește, aplicația poate folosi fallbackul configurat numai dacă
regula este completă și rezultatul nu devine financiar fail-open. Orice
inconsistență trebuie raportată fără a expune bonuri, agenți sau valori
comerciale în log.

Verificarea read-only a raportului detaliat ERP din `Setări -> Importuri` nu
înlocuiește importul POS și nu certifică Promo/Incentive. Ea limitează calculele
Retail la 1-cutoff-ul din `ZileTrecute` și poate reconcilia totalurile Focus
prezente în raport; valorile Promo/Incentive rămân informative deoarece fișierul
agregat nu conține coduri de produs, identitatea bonului și unități promo.

## Concursuri

Concursurile sunt config-driven și scoped server-side. Configurația definește:

- cheia și perioada;
- scope-ul organizațional;
- regulile de punctaj;
- clasamentul și premiile.

Filtrele globale nu trebuie să extindă sau să restrângă accidental scope-ul
oficial al concursului. Răspunsul backend este autoritativ.

## Flux de schimbare

1. pornește dintr-un fișier/config nou sau o revizie explicită, nu edita
   retroactiv o perioadă închisă;
2. verifică duplicatele, intervalele, codurile și metadatele;
3. rulează calculul read-only pe o lună cu fixture sintetic sau snapshot local;
4. compară separat bonurile promo, unitățile reduse, unitățile Incentive și
   plata;
5. rulează testele backend și frontend relevante;
6. verifică exporturile și cele patru valori ale cardului;
7. livrează prin calea proporțională cu riscul din ADR-005; dacă se deschide PR,
   agentul îl duce prin CI, merge, deploy și verificare fără o aprobare repetată;
8. verifică live fără a afișa date comerciale în output.

## Verificări minime

```bash
pytest backend/tests/test_campaigns_promos.py \
  backend/tests/test_import_promo_actuals.py \
  backend/tests/test_campaigns.py -q
npm run test -- src/components/Campaigns.test.ts
npm run typecheck
npm run build
```

Pentru o schimbare de contract sau de calcul, rulează și suita completă conform
`AGENTS.md`. Testele trebuie să includă promoții suprapuse, cutoff, duplicate,
retururi, magazine necalificate și lipsa sursei corective.

## Reguli de siguranță

- nu loga bonuri, nume de agenți, liste comerciale sau valori financiare;
- nu muta semantica între câmpuri existente;
- nu modifica date business live pentru acceptanță;
- nu introduce fallback financiar care transformă o eroare în zero;
- păstrează exporturile private/no-store;
- păstrează calculele în service/repository, nu în router sau componenta UI.
