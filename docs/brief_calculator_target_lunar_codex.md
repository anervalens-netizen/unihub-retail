# Brief tehnic pentru Codex: Calculator automat de target lunar pe magazine

## Status implementare 2026-06-27

Implementarea aleasă în aplicație este `seasonal_blended_multiyear_v1`.

- Cardul de calcul are switch `Anul trecut` / `Multi-year`; `Multi-year` este
  default.
- Formula pornește de la forecastul lunii curente și aplică factor sezonier
  blended magazin / manager curent / rețea.
- Multi-year folosește până la 3 ani, cu ponderi mai mari pentru anul recent;
  anii fără date suficiente sunt săriți automat.
- Lunile istorice sunt citite din `reporting_agent_month`, cu fallback pe
  `historical_monthly_sales` pentru perioadele importate vechi; reporting-ul
  curent are prioritate ca să nu se dubleze aceeași lună/magazin.
- Dacă lipsește Y-1 pentru magazin, dar există Y-2/Y-3, calculatorul marchează
  `LOW_RECENT_HISTORY` și mută ponderea spre manager/rețea.
- Dacă targetul total introdus depășește suma cap-urilor operaționale calculate,
  calculul este respins cu mesaj explicit; nu se mai salvează drafturi în care
  propunerea totală rămâne sub buget.
- Tabelul și exportul arată factorul folosit, factorul last-year, factorul
  multi-year, trendul, floor/cap și flag-urile principale.
- Rezumatul pe manager arată creșterea propunerii față de forecastul lunii
  curente și creșterea observată anul trecut între luna bază și luna target
  (ex. iulie 2025 vs iunie 2025 pentru target iulie 2026).
- Cohorta Calculator Target exclude magazinele închise prin
  `target_calculator_store_exclusions`; primele intrări sunt `CRFVUL` (Mobiup
  Carrefour Vulcan) și `CRFARENA` (MobiCell Grand Arena), effective din
  `2026-07`.
- Cap-ul este introdus ca limită de propunere, cu default operațional; managerii
  pot în continuare completa `Final manager`, iar finalizarea cere suma exactă a
  targetului total.

## 1. Context business

Utilizatorul gestionează mai multe magazine de vânzare accesorii GSM și stabilește lunar targetul pentru fiecare magazin.

Fluxul actual este:

1. Se stabilește mai întâi o valoare generală/top-down pentru total rețea/zonă.
2. Această valoare este împărțită între magazine.
3. La împărțire se ține cont de:
   - forecastul lunii curente;
   - luna corespondentă din anul trecut;
   - luna anterioară din anul trecut;
   - prag minim;
   - uneori floor/cap față de luna anterioară, pentru a evita creșteri sau scăderi prea bruște.

Exemplu discutat:
- pentru targetul de **iulie 2026**, se iau în calcul:
  - forecast iunie 2026;
  - vânzări iunie 2025;
  - vânzări iulie 2025.

Notă: în discuția inițială a apărut probabil o eroare de exprimare: pentru target iulie 2026, luna istorică relevantă este **iulie 2025**, nu iulie 2026.

---

## 2. Problema metodei actuale

Metoda actuală folosește o medie ponderată între cele trei repere:
- forecast luna curentă;
- luna trecută/anul trecut;
- luna target/anul trecut.

Problema identificată: **media ponderată aplatizează sezonalitatea**.

În retailul GSM/accesorii, sezonalitatea contează mult:
- magazinele stradale pot evolua diferit față de mall-uri;
- locațiile de tranzit/turistice pot crește puternic vara;
- magazinele din zone diferite pot avea comportamente sezoniere diferite;
- unele magazine cresc natural din iunie în iulie, altele pot stagna sau scădea.

De aceea, dinamica dintre luna curentă și luna target trebuie tratată ca **multiplicator sezonier**, nu doar ca o altă valoare introdusă într-o medie.

---

## 3. Ideea principală validată în discuție

Pentru fiecare magazin trebuie izolat comportamentul sezonier din anul precedent:

```text
Factor_sezonier_magazin = Vânzări_luna_target_anul_trecut / Vânzări_luna_curentă_anul_trecut
```

Pentru exemplul iulie 2026:

```text
Factor_sezonier_magazin = Vânzări_iulie_2025 / Vânzări_iunie_2025
```

Apoi se aplică acest factor pe realitatea curentă a magazinului:

```text
Estimare_iulie_2026 = Forecast_iunie_2026 × Factor_sezonier_magazin
```

Exemplu:

```text
Forecast iunie 2026 = 100.000 lei
Iunie 2025 = 100.000 lei
Iulie 2025 = 130.000 lei

Factor sezonier = 130.000 / 100.000 = 1,30
Estimare iulie 2026 = 100.000 × 1,30 = 130.000 lei
```

Dacă alt magazin are același forecast curent, dar anul trecut a scăzut din iunie în iulie:

```text
Forecast iunie 2026 = 100.000 lei
Iunie 2025 = 100.000 lei
Iulie 2025 = 90.000 lei

Factor sezonier = 90.000 / 100.000 = 0,90
Estimare iulie 2026 = 100.000 × 0,90 = 90.000 lei
```

Astfel, două magazine cu același forecast curent pot primi targeturi diferite, corect ajustate sezonier.

---

## 4. De ce factorul sezonier simplu nu este suficient

Formula simplă:

```text
Forecast_iunie_2026 × (Iulie_2025 / Iunie_2025)
```

este logică, dar poate deveni riscantă dacă datele istorice au anomalii.

Exemple de anomalii:
- magazin închis câteva zile/săptămâni în iunie anul trecut;
- lipsă stoc;
- lipsă personal;
- echipă nouă;
- renovare;
- campanie locală excepțională;
- vânzări corporate/one-off;
- schimbare de trafic în zonă;
- modificare de program;
- eroare de raportare.

Exemplu problematic:

```text
Iunie 2025 = 20.000 lei
Iulie 2025 = 45.000 lei

Factor sezonier = 45.000 / 20.000 = 2,25
```

Matematic rezultă +125%, dar poate nu este o sezonalitate reală, ci o anomalie în iunie 2025.

De aceea, modelul recomandat trebuie să fie mai robust.

---

## 5. Model recomandat: factor sezonier blended

În loc să se folosească doar factorul sezonier al magazinului, se recomandă un factor combinat între:

1. sezonalitatea magazinului;
2. sezonalitatea zonei/ASM-ului;
3. sezonalitatea întregii rețele.

### 5.1. Factor magazin

```text
IS_magazin = Vânzări_luna_target_anul_trecut_magazin / Vânzări_luna_curentă_anul_trecut_magazin
```

Pentru iulie 2026:

```text
IS_magazin = Iulie_2025_magazin / Iunie_2025_magazin
```

### 5.2. Factor zonă

```text
IS_zonă = Total_vânzări_luna_target_anul_trecut_zonă / Total_vânzări_luna_curentă_anul_trecut_zonă
```

Pentru iulie 2026:

```text
IS_zonă = Total_Iulie_2025_zonă / Total_Iunie_2025_zonă
```

### 5.3. Factor rețea

```text
IS_rețea = Total_vânzări_luna_target_anul_trecut_rețea / Total_vânzări_luna_curentă_anul_trecut_rețea
```

Pentru iulie 2026:

```text
IS_rețea = Total_Iulie_2025_rețea / Total_Iunie_2025_rețea
```

### 5.4. Factor sezonier final

Formula recomandată inițial:

```text
IS_final = 50% × IS_magazin + 30% × IS_zonă + 20% × IS_rețea
```

Exemplu:

```text
IS_magazin = 1,50
IS_zonă = 1,22
IS_rețea = 1,15

IS_final = 1,50 × 0,50 + 1,22 × 0,30 + 1,15 × 0,20
IS_final = 1,346
```

Asta înseamnă că în loc să aplicăm +50% direct pe magazin, aplicăm +34,6%, mai echilibrat și mai realist.

---

## 6. Ajustare în funcție de calitatea datelor

Pentru magazine stabile, cu istoric relevant:

```text
50% magazin
30% zonă
20% rețea
```

Pentru magazine cu date slabe, istorice suspecte sau anomalii:

```text
30% magazin
40% zonă
30% rețea
```

Pentru magazine noi sau cu istoric insuficient:

```text
0% magazin
60% zonă
40% rețea
```

Sau, dacă zona este și ea instabilă:

```text
0% magazin
40% zonă
60% rețea
```

Este important ca aplicația să permită configurarea acestor ponderi global și eventual override per magazin/zonă.

---

## 7. Dacă există 2-3 ani de istoric

Dacă aplicația are date pe mai mulți ani, factorul sezonier devine mai robust.

Pentru 2 ani de istoric:

```text
IS_magazin = 70% × (Iulie_2025 / Iunie_2025)
           + 30% × (Iulie_2024 / Iunie_2024)
```

Pentru 3 ani de istoric:

```text
IS_magazin = 50% × (Iulie_2025 / Iunie_2025)
           + 30% × (Iulie_2024 / Iunie_2024)
           + 20% × (Iulie_2023 / Iunie_2023)
```

Principiul:
- anul cel mai recent primește pondere mai mare;
- anii mai vechi ajută la reducerea efectului unor anomalii.

Același principiu se poate aplica și la nivel de zonă și rețea.

---

## 8. Limitarea factorului sezonier

Pentru a evita rezultate aberante, factorul sezonier trebuie limitat.

Propunere conservatoare:

```text
IS_min = 0,70
IS_max = 1,70
```

Formula:

```text
IS_limitat = MIN(MAX(IS_final, 0,70), 1,70)
```

Claude propusese un interval mai larg:

```text
0,50 - 2,00
```

Recomandarea finală:
- pentru început: 0,70 - 1,70;
- pentru magazine sezoniere puternice, ex. litoral/turism/tranzit: se poate permite 0,50 - 2,00;
- aceste valori trebuie să fie configurabile.

---

## 9. Ajustarea pe trend actual YoY

Pe lângă sezonalitate, trebuie văzut dacă magazinul este mai puternic sau mai slab anul acesta față de anul trecut.

```text
Trend_actual = Forecast_lună_curentă_an_curent / Vânzări_lună_curentă_an_trecut
```

Pentru exemplul iulie 2026:

```text
Trend_actual = Forecast_iunie_2026 / Vânzări_iunie_2025
```

Dar acest trend nu trebuie aplicat integral, pentru că forecastul curent este deja baza calculului. Se recomandă o ajustare parțială:

```text
Ajustare_trend = 1 + ((Trend_actual - 1) × 0,30)
```

Exemplu:

```text
Forecast iunie 2026 = 120.000
Iunie 2025 = 100.000

Trend_actual = 1,20

Ajustare_trend = 1 + ((1,20 - 1) × 0,30)
Ajustare_trend = 1,06
```

Deci magazinul primește +6% extra pentru faptul că este peste anul trecut, nu +20%.

Ajustarea recomandată inițial:

```text
Coeficient trend = 30%
```

Acesta trebuie să fie configurabil.

---

## 10. Formula brută recomandată

Pentru fiecare magazin:

```text
Estimare_brută = Forecast_lună_curentă
                × IS_limitat
                × Ajustare_trend
```

Pentru exemplul iulie 2026:

```text
Estimare_brută_iulie_2026 = Forecast_iunie_2026
                           × IS_limitat
                           × Ajustare_trend
```

Aceasta este estimarea logică a potențialului magazinului în luna target, înainte de alocarea targetului general.

---

## 11. Alocarea top-down a targetului general

Utilizatorul vrea să păstreze controlul managerial asupra targetului total.

De aceea, după ce se calculează estimările brute pentru toate magazinele:

```text
Total_estimări_brute = SUMA(Estimare_brută pentru toate magazinele)
```

Se calculează ponderea fiecărui magazin:

```text
Pondere_magazin = Estimare_brută_magazin / Total_estimări_brute
```

Apoi targetul general este împărțit proporțional:

```text
Target_teoretic_magazin = Target_total × Pondere_magazin
```

Asta permite ca:
- targetul total să fie setat manual/top-down;
- împărțirea între magazine să fie bazată pe sezonalitate, trend și potențial curent;
- magazinele sezoniere să primească o felie corectă din target;
- magazinele care natural scad/stagnează să nu fie împinse nerealist.

---

## 12. Prag minim, floor și cap

Utilizatorul are deja două tipuri de constrângeri suplimentare:
1. prag minim;
2. uneori floor/cap față de luna anterioară, ca să nu existe creșteri sau scăderi prea bruște.

Acestea trebuie păstrate în noul model.

### 12.1. Prag minim absolut

Exemplu:

```text
Prag_minim_magazin = 25.000 lei
```

Formula:

```text
Target_dupa_prag_minim = MAX(Target_teoretic, Prag_minim_magazin)
```

Pragul minim poate fi:
- global;
- pe zonă;
- pe magazin;
- pe tip magazin.

### 12.2. Floor față de luna curentă/luna anterioară

Exemplu: targetul lunii target nu poate scădea sub 90% din forecastul lunii curente.

```text
Floor_relativ = Forecast_lună_curentă × 0,90
```

Formula:

```text
Target_dupa_floor = MAX(Target_dupa_prag_minim, Floor_relativ)
```

Setări recomandate:

```text
Floor normal = 85% - 90% din forecast luna curentă
```

### 12.3. Cap față de luna curentă/luna anterioară

Exemplu: targetul lunii target nu poate depăși 140% din forecastul lunii curente.

```text
Cap_relativ = Forecast_lună_curentă × 1,40
```

Formula:

```text
Target_dupa_cap = MIN(Target_dupa_floor, Cap_relativ)
```

Setări recomandate:

```text
Cap normal = 130% - 140% din forecast luna curentă
Cap special magazine sezoniere = 160% - 180%
```

---

## 13. Problema critică: după prag/floor/cap totalul nu mai bate

Dacă se aplică praguri, floor și cap după targetul teoretic, suma targeturilor pe magazine poate deveni diferită de targetul general.

Exemplu:

```text
Target total dorit = 500.000 lei
```

După calculul teoretic:

```text
SUMA(Target_teoretic) = 500.000 lei
```

Dar după prag minim și floor:

```text
SUMA(Target_dupa_constrangeri) = 515.000 lei
```

Sau după cap-uri:

```text
SUMA(Target_dupa_constrangeri) = 485.000 lei
```

Aici este nevoie de redistribuire controlată.

---

## 14. Redistribuire controlată

După aplicarea constrângerilor, magazinele trebuie împărțite în două categorii:

### 14.1. Magazine blocate/fixe

Sunt magazinele al căror target a fost forțat de:
- prag minim;
- floor;
- cap;
- ajustare manuală;
- blocare explicită de către manager.

Acestea nu mai trebuie modificate în etapa de redistribuire.

### 14.2. Magazine flexibile

Sunt magazinele care:
- nu sunt blocate de prag/floor/cap;
- pot primi plus sau minus;
- pot fi ajustate fără să încalce limitele configurate.

### 14.3. Formula de redistribuire

Se calculează:

```text
Target_rămas_de_distribuit = Target_total - SUMA(Targeturi_magazine_blocate)
```

Apoi se distribuie doar între magazinele flexibile, proporțional cu estimarea brută:

```text
Target_final_magazin_flexibil =
Estimare_brută_magazin / SUMA(Estimări_brute_magazine_flexibile)
× Target_rămas_de_distribuit
```

După redistribuire, trebuie verificat din nou dacă vreun magazin flexibil a încălcat floor/cap-ul. Dacă da, acel magazin se blochează și redistribuirea se repetă iterativ până când:

```text
SUMA(Target_final) = Target_total
```

sau până când toate magazinele sunt blocate.

---

## 15. Algoritm recomandat, pas cu pas

### Input necesar per magazin

```text
store_id
store_name
zone_id / asm_id
store_type / seasonality_type optional
sales_current_month_last_year
sales_target_month_last_year
forecast_current_month_current_year
previous_month_actual_or_forecast
minimum_target
floor_percent
cap_percent
manual_adjustment optional
manual_lock optional
data_quality_flag optional
```

Pentru target iulie 2026:

```text
sales_current_month_last_year = vânzări iunie 2025
sales_target_month_last_year = vânzări iulie 2025
forecast_current_month_current_year = forecast iunie 2026
```

### Pasul 1: calculează IS magazin

```text
IS_magazin = sales_target_month_last_year / sales_current_month_last_year
```

Dacă denominatorul este 0 sau prea mic:
- nu folosi IS magazin;
- fallback către IS zonă/rețea;
- marchează magazinul cu `data_quality_flag`.

### Pasul 2: calculează IS zonă

```text
IS_zonă = total_sales_target_month_last_year_zone / total_sales_current_month_last_year_zone
```

### Pasul 3: calculează IS rețea

```text
IS_rețea = total_sales_target_month_last_year_network / total_sales_current_month_last_year_network
```

### Pasul 4: calculează IS blended

Default:

```text
IS_blended = 0,50 × IS_magazin + 0,30 × IS_zonă + 0,20 × IS_rețea
```

Pentru date slabe:

```text
IS_blended = 0,30 × IS_magazin + 0,40 × IS_zonă + 0,30 × IS_rețea
```

Pentru magazin nou:

```text
IS_blended = 0,60 × IS_zonă + 0,40 × IS_rețea
```

### Pasul 5: limitează IS

```text
IS_limitat = MIN(MAX(IS_blended, IS_min), IS_max)
```

Default:

```text
IS_min = 0,70
IS_max = 1,70
```

### Pasul 6: calculează trend YoY

```text
Trend_actual = forecast_current_month_current_year / sales_current_month_last_year
```

Dacă sales_current_month_last_year este 0 sau prea mic:
- nu aplica trend;
- folosește `Ajustare_trend = 1`.

### Pasul 7: ajustează trendul parțial

```text
Ajustare_trend = 1 + ((Trend_actual - 1) × trend_weight)
```

Default:

```text
trend_weight = 0,30
```

Recomandare: și ajustarea trendului ar trebui limitată pentru a evita anomalii:

```text
Ajustare_trend_min = 0,90
Ajustare_trend_max = 1,15
```

Exemplu:

```text
Ajustare_trend_limitată = MIN(MAX(Ajustare_trend, 0,90), 1,15)
```

### Pasul 8: calculează estimarea brută

```text
Estimare_brută = forecast_current_month_current_year × IS_limitat × Ajustare_trend_limitată
```

### Pasul 9: alocare top-down

```text
Total_estimări_brute = SUMA(Estimare_brută)
Pondere_magazin = Estimare_brută / Total_estimări_brute
Target_teoretic = Target_total × Pondere_magazin
```

### Pasul 10: aplică prag minim

```text
Target_1 = MAX(Target_teoretic, minimum_target)
```

### Pasul 11: aplică floor

```text
Floor_value = forecast_current_month_current_year × floor_percent
Target_2 = MAX(Target_1, Floor_value)
```

### Pasul 12: aplică cap

```text
Cap_value = forecast_current_month_current_year × cap_percent
Target_3 = MIN(Target_2, Cap_value)
```

### Pasul 13: aplică ajustări manuale

Dacă managerul introduce ajustare manuală:

```text
Target_manual = Target_3 + manual_adjustment
```

Dacă managerul bifează `manual_lock = true`, targetul devine fix și nu mai intră la redistribuire.

### Pasul 14: redistribuire diferență

```text
Target_rămas = Target_total - SUMA(Targeturi_blocate)
```

Magazinele flexibile primesc targetul rămas proporțional cu estimările brute.

Repetă redistribuirea dacă în urma redistribuirii un magazin depășește floor/cap.

### Pasul 15: rotunjire finală

Targeturile pot fi rotunjite:
- la 100 lei;
- la 500 lei;
- la 1.000 lei.

După rotunjire trebuie recalculată diferența și ajustată pe magazinele flexibile, ca suma finală să rămână egală cu targetul total.

---

## 16. Pseudocod recomandat

```pseudo
function calculateTargets(stores, targetTotal, config):
    # 1. Calculate network seasonality
    networkCurrentLY = sum(store.salesCurrentMonthLY for store in stores)
    networkTargetLY = sum(store.salesTargetMonthLY for store in stores)
    IS_network = safeDivide(networkTargetLY, networkCurrentLY, default=1)

    # 2. Calculate zone seasonality
    for each zone:
        zoneCurrentLY = sum(stores in zone salesCurrentMonthLY)
        zoneTargetLY = sum(stores in zone salesTargetMonthLY)
        IS_zone[zone] = safeDivide(zoneTargetLY, zoneCurrentLY, default=IS_network)

    # 3. Calculate raw estimate per store
    for store in stores:
        IS_store = safeDivide(
            store.salesTargetMonthLY,
            store.salesCurrentMonthLY,
            default=null
        )

        weights = chooseWeights(store.dataQualityFlag, store.isNewStore)

        IS_blended = weightedAverage([
            (IS_store, weights.store),
            (IS_zone[store.zone], weights.zone),
            (IS_network, weights.network)
        ])

        IS_limited = clamp(IS_blended, config.IS_min, config.IS_max)

        trend = safeDivide(
            store.forecastCurrentMonthCY,
            store.salesCurrentMonthLY,
            default=1
        )

        trendAdjustment = 1 + ((trend - 1) * config.trendWeight)
        trendAdjustment = clamp(
            trendAdjustment,
            config.trendAdjustmentMin,
            config.trendAdjustmentMax
        )

        store.rawEstimate = store.forecastCurrentMonthCY * IS_limited * trendAdjustment

    # 4. Initial top-down allocation
    totalRawEstimate = sum(store.rawEstimate for store in stores)

    for store in stores:
        store.theoreticalTarget = targetTotal * store.rawEstimate / totalRawEstimate

    # 5. Apply constraints
    for store in stores:
        minTarget = store.minimumTarget
        floorValue = store.forecastCurrentMonthCY * store.floorPercent
        capValue = store.forecastCurrentMonthCY * store.capPercent

        constrained = max(store.theoreticalTarget, minTarget, floorValue)
        constrained = min(constrained, capValue)

        if store.manualAdjustment exists:
            constrained = constrained + store.manualAdjustment

        store.finalTarget = constrained

        if constrained != store.theoreticalTarget or store.manualLock:
            store.locked = true
        else:
            store.locked = false

    # 6. Iterative redistribution
    repeat:
        lockedStores = stores where locked == true
        flexibleStores = stores where locked == false

        remainingTarget = targetTotal - sum(finalTarget of lockedStores)
        flexibleRawTotal = sum(rawEstimate of flexibleStores)

        changed = false

        for store in flexibleStores:
            proposed = remainingTarget * store.rawEstimate / flexibleRawTotal

            floorValue = store.forecastCurrentMonthCY * store.floorPercent
            capValue = store.forecastCurrentMonthCY * store.capPercent

            if proposed < floorValue:
                store.finalTarget = floorValue
                store.locked = true
                changed = true
            else if proposed > capValue:
                store.finalTarget = capValue
                store.locked = true
                changed = true
            else:
                store.finalTarget = proposed

    until changed == false or no flexibleStores remain

    # 7. Rounding
    round targets according to config.roundingStep
    adjust rounding difference on flexible stores

    return stores with finalTarget and explanation fields
```

---

## 17. Explicații care ar trebui afișate în aplicație

Pentru transparență managerială, fiecare target ar trebui să aibă un mic breakdown:

```text
Forecast iunie 2026: 100.000 lei
IS magazin: 1,30
IS zonă: 1,18
IS rețea: 1,12
IS final blended: 1,224
IS limitat: 1,224
Trend YoY: 1,10
Ajustare trend: 1,03
Estimare brută: 126.072 lei
Pondere în total estimări: 12,6%
Target teoretic: 63.000 lei
Prag minim: 25.000 lei
Floor: 90.000 lei
Cap: 140.000 lei
Target final: 90.000 lei
Motiv ajustare: ridicat de floor vs forecast lună curentă
```

Este foarte important ca managerul să poată vedea **de ce** un target a crescut/scăzut.

---

## 18. Câmpuri recomandate în UI/config

### Config global

```text
target_total
target_month
current_month
seasonality_store_weight
seasonality_zone_weight
seasonality_network_weight
IS_min
IS_max
trend_weight
trend_adjustment_min
trend_adjustment_max
default_floor_percent
default_cap_percent
rounding_step
```

### Config per zonă

```text
zone_id
zone_name
custom_floor_percent optional
custom_cap_percent optional
custom_IS_min optional
custom_IS_max optional
custom_seasonality_weights optional
```

### Config per magazin

```text
store_id
store_name
zone_id
is_new_store
data_quality_flag
minimum_target
floor_percent override optional
cap_percent override optional
manual_adjustment
manual_lock
notes
```

---

## 19. Statusuri/flag-uri utile

Aplicația ar trebui să marcheze automat magazinele cu probleme de date:

```text
LOW_HISTORY
ZERO_OR_LOW_BASE_LAST_YEAR
EXTREME_SEASONALITY
NEW_STORE
MANUAL_LOCK
FLOOR_APPLIED
CAP_APPLIED
MINIMUM_TARGET_APPLIED
TREND_ADJUSTMENT_CAPPED
SEASONALITY_CAPPED
```

Aceste flag-uri ajută managerul să știe unde trebuie verificat manual.

---

## 20. Exemplu numeric complet

Target total rețea:

```text
500.000 lei
```

Magazine:

```text
Magazin A:
Forecast iunie 2026 = 100.000
Iunie 2025 = 100.000
Iulie 2025 = 130.000
IS magazin = 1,30

Magazin B:
Forecast iunie 2026 = 100.000
Iunie 2025 = 100.000
Iulie 2025 = 90.000
IS magazin = 0,90
```

Presupunem simplificat că IS final = IS magazin și nu aplicăm trend.

```text
Estimare A = 100.000 × 1,30 = 130.000
Estimare B = 100.000 × 0,90 = 90.000

Total estimări = 220.000
```

Ponderi:

```text
Pondere A = 130.000 / 220.000 = 59,09%
Pondere B = 90.000 / 220.000 = 40,91%
```

Targeturi:

```text
Target A = 500.000 × 59,09% = 295.455
Target B = 500.000 × 40,91% = 204.545
```

Deși magazinele aveau același forecast curent, targetul final diferă în funcție de sezonalitatea reală.

---

## 21. Model hibrid alternativ

Dacă utilizatorul vrea să păstreze parțial logica actuală cu medie ponderată, se poate construi un model hibrid:

```text
Scor_final =
70% × Model_sezonier_multiplicativ
20% × Benchmark_istoric_luna_target_anul_trecut
10% × Forecast_simplu_luna_curentă
```

Totuși, recomandarea principală este ca baza să fie:

```text
Forecast curent × sezonalitate blended × trend ajustat
```

Media ponderată istorică poate rămâne doar ca semnal secundar, nu ca formulă principală.

---

## 22. Recomandarea finală pentru implementare

Codex ar trebui să implementeze calculatorul în următoarea logică:

```text
1. Managerul introduce/selectează:
   - luna target;
   - targetul total;
   - forecast luna curentă;
   - setările globale de prag/floor/cap.

2. Sistemul extrage automat:
   - vânzări luna curentă anul trecut;
   - vânzări luna target anul trecut;
   - totaluri pe zonă;
   - totaluri pe rețea.

3. Sistemul calculează:
   - IS magazin;
   - IS zonă;
   - IS rețea;
   - IS blended;
   - IS limitat;
   - trend actual;
   - ajustare trend;
   - estimare brută.

4. Sistemul alocă targetul general top-down proporțional cu estimările brute.

5. Sistemul aplică:
   - prag minim;
   - floor;
   - cap;
   - ajustări manuale;
   - blocări manuale.

6. Sistemul redistribuie diferența astfel încât:
   - suma finală să fie egală cu targetul total;
   - constrângerile să fie respectate;
   - magazinele blocate să nu fie modificate.

7. Sistemul afișează breakdown-ul de calcul și flag-urile pentru fiecare magazin.
```

---

## 23. Rezumat executiv

Obiectivul nu este doar să se împartă targetul general după ponderi istorice, ci să se creeze un calculator care înțelege:

```text
Cât poate face magazinul luna viitoare, ținând cont de ritmul actual și de comportamentul sezonier real?
```

Formula de bază recomandată:

```text
Estimare_brută =
Forecast_lună_curentă
× Factor_sezonier_blended_limitat
× Ajustare_trend_limitată
```

Apoi:

```text
Target_teoretic =
Target_total
× Estimare_brută_magazin / Total_estimări_brute
```

Apoi:

```text
Target_final =
Target_teoretic ajustat cu prag minim, floor, cap, manual lock și redistribuire
```

Această logică:
- respectă sezonalitatea locală;
- păstrează controlul managerial asupra targetului total;
- evită targeturile aberante;
- protejează magazinele de scăderi/creșteri prea bruște;
- poate fi automatizată curat în aplicație;
- permite explicații clare pentru fiecare target calculat.
