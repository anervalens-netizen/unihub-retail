# HANDOVER — Campanii Iunie 2026 (Retail)

**Data:** 2026-05-30 (lucrat peste noapte, Andrei AFK)
**App:** UniHub Retail — `retail.unihub.ro` (port 9898, `unihub-backend.service`)
**Status:** ✅ Toate cele 3 livrabile sunt **LIVE**. Codex a verificat fixurile, a actualizat documentația și a primit OK pentru commit/push pe `main` în 2026-05-31.

---

## TL;DR (ce să verifici de dimineață)

1. Deschide `retail.unihub.ro` → tab **Focus**. Acum are 4 sub-secțiuni: **Incentive · Promo · Concurs · Focus** (înainte erau „Campanii" + „Focus").
2. ⚠️ **Luna 2026-06 NU apare încă în selector** — by design (vezi „Findings Codex" #1). Lista de luni = doar importuri finalizate; iunie n-are date. Pune **2026-05** ca să vezi structura/comportamentul cu date reale; iunie apare automat la primul import de vânzări iunie.
3. Codul este pregătit pentru commit/push pe `main`; push-ul declanșează runner-ul CI și redeploy-ul automat.
4. Cifrele reale (promo, excludere incentive, clasament concurs) apar **după primul import de vânzări iunie**.

## Findings Codex (review pre-commit) — status

- **#1 „Iunie nu e selectabilă în UI"** → **NU e bug, by-design.** Lista de luni vine din `import_snapshots.status='completed'` — exact invariantul din incidentul 2026-05-06 (un agent a spart retail forțând luni fără date prin UNION). Iunie apare automat la primul import. Formularea mea inițială „selectează 2026-06" era greșită — corectată mai sus. **Niciun cod schimbat** (a hardcoda/UNION-ui lista ar reintroduce bug-ul).
- **#2 „Tab Promo din Focus măsura cantitate simplă, nu co-purchase"** → **REPARAT.** Endpoint-ul `promotions-incentives` lua `promo_qty` din `reporting_item_day` (sumă `positive_quantity` = 710 buc pe mai) în loc de bonuri co-purchase (314). Acum tab-ul Focus „Promo" afișează metrici co-purchase (Bonuri calificate / Produse reduse / Magazine / Agenți) + Top Magazine pe bonuri calificate per magazin — consistent cu cardul Hub. Validat pe date reale (calea completă Focus): **promo_qualifying_bons = 314**, top magazin = 17 bonuri. Am adăugat câmpuri dedicate (`promo_qualifying_bons/discounted_units/active_stores/active_agents`) fără să ating `_fetch_promo_incentive_summary` (partajat cu KPI-ul Hub-summary + coloanele Hub simple).

## Audit final Codex (2026-05-31)

- Config live promo: **47 coduri unice**, `2026-06-01` → `2026-06-30`.
- Incentive iunie vs mai: **967 produse**, total reward **5.945 RON**, zero diferențe de cod/reward.
- Scope concurs: `asm='Andrei Stancu'` = **23 magazine active non-TR**; `regional='Andrei Stancu'` ar fi 38, deci `asm` este corect.
- Validare co-purchase pe date reale mai cu config mutat temporar pe mai: `promo_qty` simplu = **710**, dar metricul Focus corect `promo_qualifying_bons` = **314**; top magazin = **17 bonuri**.
- Serviciu concurs iunie pe DB real: `store_count=23`, leaderboard gol fără date iunie.
- Verificări rulate după fix: `pytest` **330 passed, 7 skipped**, `vitest` **78 passed**, `tsc --noEmit` OK, `mypy` OK, `npm run build` OK, `/health` OK.

---

## Ce ai cerut (din mailuri + conversație)

### A. Incentive iunie
- „Rămâne la fel ca în mai, cu o singură modificare legată de promoție."
- Clarificat: lista + valorile incentive rămân **identice** cu mai. Modificarea = **regulă**, nu schimbare de listă: un produs din incentive vândut **în promoție** (cu reducere, pe bon promo) **nu se incentivează**; vândut normal → se incentivează ca de obicei.

### B. Promoție iunie (mail „Campanie IUNIE")
- „Cumpără orice accesoriu și beneficiezi de 20% reducere la produsele selectate" — 01–30.06.2026.
- Reducerea pe **un singur** produs din listă per bon (cel mai ieftin), pe **același bon fiscal** (`bon_nr`), declanșată de cumpărarea oricărui accesoriu.
- Cele 2 Excel din `~/Downloads/` (47 produse, listă identică) → codurile promo.
- Decizii confirmate de tine: declanșatorul **exclude cartela** (e „accesoriu", aliniat cu Bon2Acc); măsurare **co-purchase** (nu simplu); preț redus detectat **determinist din co-purchase** (nu după preț, fiindcă prețurile variază natural).

### C. Concurs iunie (mail „concurs")
- Doar zona ta **Andrei Stancu (23 locații)**, 01–30 iunie, **la nivel de agent**, **fără** condiție de target.
- Punctaj: **+1** produs focus · **+1** bon promo · **+1** produs > 150 lei (se cumulează: un produs poate aduce până la 3p).
- Premii: loc 1 = boxă **M7 Plus**; locurile 2–3 = **BoomX**; locurile 4–6 = **Macaron**.
- Decizii confirmate: punct promo **per bon** (nu per produs); focus & >150 **per unitate (cantitate)**; preț pe `unit_price` efectiv; arhitectură **config-driven** (reutilizabilă).

---

## Ce am făcut

### 1. Promoții iunie — `data/hub_specials.json` (gitignored, live config)
Config-ul live are acum promoții selectabile prin `key`/`promotion_key`:
- `promotie-actuala-mihai` — promoția existentă cu 47 coduri, `2026-06-01` → `2026-06-30`, păstrată pe regula veche.
- `folii-ecran-camera-iunie` — `2026-06-10` → `2026-06-30`, citește `docs/Campanii-promo/campanie-folii-iunie/Promotie folie ecran si reducere 20% la folie camera.xlsx`, sheet-uri `Folii ecran` și `Folii Camera`.
- `capace-huse-cellara-iunie` — `2026-06-10` → `2026-06-30`, citește `docs/Campanii-promo/campanie-huse-iunie/Promotie capac protectie si reducere 20% la huse universale de telefoane.xlsx`, sheet-uri `Capac protectie` și `Husa Universala`.

Tabul **Focus -> Promo** afișează butoane pentru promoțiile active din lună și reîncarcă datele pentru cheia selectată. Cardul promo Hub rămâne pe prima promoție activă din config.

### 2. Reguli co-purchase — `backend/services/promo_copurchase.py` (helper partajat)
- **Cheia bonului** = `(sale_date, site_code, agent, bon_nr)` — identică cu logica existentă de bonuri din `reporting_refresh.py`. (`bon_nr` singur NU e unic: ex. „174" apare în 3 magazine — de aceea cheia e compozită.) Coloana de ingest = **„Nr"** (7 cifre).
- `selected_item_copurchase`: bon calificat = ≥1 produs din lista promo **ȘI** ≥2 unități pozitive totale (a doua poate fi orice alt accesoriu non-cartelă). Unitatea redusă = produsul din listă cu cel mai mic `unit_price` pe bon.
- `same_model_screen_camera`: bon calificat = folie ecran + folie cameră pe același bon, cu intersecție de model telefon extrasă din `ItemName`; unitatea redusă = folia de cameră eligibilă cu cel mai mic `unit_price`.
- `trigger_discounted`: bon calificat = produs declanșator + produs redus pe același bon; unitatea redusă = produsul redus cu cel mai mic `unit_price`. Folosit pentru capac Cellara + husă universală.
- Toate regulile exclud cartele + locații `TR %` și numără maxim o unitate redusă per bon.

### 3. Incentive iunie — clonă exactă a lunii mai (în DB)
- `incentive_campaigns` + `incentive_products`, `month='2026-06'`: **967 produse**, tiere **5/10/25 RON** (total reward 5945) — identic cu mai.
- **Excludere**: unitatea redusă (vândută în promo) se scade din `net_quantity` la calculul incentive. Aplicat în:
  - `backend/services/dashboard/specials_data.py` — cardul Incentive din Hub.
  - `backend/services/campaigns.py` — tab Focus: top_agenți, top_magazine, categorii pe tier, + headline `incentive_value`/`incentive_qty`.
  - Se aplică **doar** pe luni cu promo activ. Lunile fără promo (ex. mai) rămân 100% neschimbate.
  - Coloanele `promo_qty`/`incentive_qty` din **tabelele Hub** rămân pe agregatul simplu (neajustate) — exact cum ai cerut.
- Cardul promo Hub: highlight = **Bonuri calificate**; metrici = Produse reduse / Magazine / Agenți.

### 4. Concurs — config-driven
- **Config:** `data/contests.json` (gitignored, live). Concurs `iunie-2026-stancu`: scope `{"asm":"Andrei Stancu"}`, reguli focus/promo/price_above(150), premii top 6. Reutilizabil: poți adăuga concursuri viitoare schimbând doar JSON-ul (perioadă, zonă, reguli, praguri, premii).
- **Backend nou (3-tier):** `routers/contests.py`, `services/contests.py`, `services/contests_config.py`, `repositories/contests.py` + modele în `models.py`. Endpoint: `GET /api/contests/active?month=2026-06`.
- **Scope verificat exact:** `asm='Andrei Stancu'` + non-TR = **23 magazine** (toate active). ⚠️ `regional='Andrei Stancu'` dă 38 — am folosit `asm`, care dă fix 23.
- **Punctaj per agent** (în cele 23 magazine, vânzări pozitive, non-cartelă): focus (Σ cantitate produse din `focus_products`) + promo (nr. bonuri promo calificate) + >150 (Σ cantitate `unit_price>150`). Clasament desc, premii pe rang. Leaderboard-ul **ignoră filtrul global** (scoped server-side din config).

### 5. Frontend — restructurare tab Focus
- `src/components/Campaigns.tsx`: sub-secțiunile `campaigns`+`focus` → **Incentive · Promo · Concurs · Focus**. „Campanii" (care amesteca promo+incentive) a fost spart în Incentive separat + Promo separat. Adăugat `ContestView` (leaderboard cu rang, puncte pe categorie, badge premii top 6).
- `src/App.tsx`: tipul secțiunii + migrare automată din vechiul `'campaigns'` (localStorage) → `'incentive'`.
- `src/api/contests.ts` + tipuri în `src/api/types.ts`. Cardul Hub „Promo & incentive" duce acum la sub-secțiunea Promo.

---

## Verificări făcute

| Verificare | Rezultat |
|---|---|
| Teste backend (pytest) | **330 passed**, 7 skipped (+10 contest, +teste promo co-purchase) |
| Teste frontend (vitest) | **78 passed** |
| TypeScript `tsc --noEmit` | **0 erori** |
| mypy (fișiere noi + modificate) | **curat** |
| SQL co-purchase pe date reale (mai) | **314 bonuri calificate** — confirmat independent cu query manual (314 = 314) |
| Serviciu concurs pe DB real | iunie: store_count=**23**, leaderboard gol (fără date iunie); simulare mai: 47 agenți clasați corect |
| Card Hub (iunie + mai) | iunie promo+incentive `no_data`; mai incentive neschimbat (52.725 RON) |
| Deploy | build OK, `unihub-backend` **active**, `/health`=ok, `/api/contests/active`→401 (auth, înregistrat), loguri startup curate |

---

## Ce rămâne operational

1. **Date iunie** — cifrele reale apar după primul import de vânzări iunie. Până atunci totul e „pregătit, 0 date".
2. **Config gitignored** — `data/hub_specials.json` și `data/contests.json` rămân doar pe server; nu intră în commit.
3. **Tie-break premii concurs** — la egalitate de puncte, rangul se departajează determinist după nume agent. Dacă vrei altă regulă la egalitățile de pe locurile premiate, schimbă regula înainte de acordarea premiilor.
4. **Prelungire promoție** — dacă se prelungește peste 30 iunie, schimb `end_date` în `data/hub_specials.json` (+ eventual `contests.json`).

---

## Fișiere cheie (referință rapidă)
- Promo config: `data/hub_specials.json`
- Concurs config: `data/contests.json`
- Co-purchase: `backend/services/promo_copurchase.py`
- Incentive excludere: `backend/services/dashboard/specials_data.py`, `backend/services/campaigns.py`
- Selector Focus -> Promo: `src/components/Campaigns.tsx`
- Concurs backend: `backend/{routers,services,repositories}/contests.py`, `backend/services/contests_config.py`
- Frontend: `src/components/Campaigns.tsx` (ContestView), `src/api/contests.ts`
- Docs actualizate: `CLAUDE.md`, `CODEX.md`, `README.md`, `APP_ARCHITECTURE.md`, `LOCAL_SETUP.md`, acest handover.
