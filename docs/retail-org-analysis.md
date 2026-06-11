# Retail Org Analysis Contract

Documentul fixeaza regula oficiala pentru analize Retail cand structura de
manageri, RM/ASM sau zone s-a schimbat in timp.

## Regula principala

Pentru analize comerciale normale, foloseste **current_org**.

Pentru analize care trebuie sa arate exact structura de la momentul respectiv,
foloseste **historical_org** numai cand userul cere explicit acest lucru
("cum era atunci", "structura istorica", "managerii din luna respectiva").

## Reorganizarea oficiala

Structura curenta incepe cu luna `2026-05`.

Din `2026-05`, cei 6 manageri activi sunt si RM/regional si ASM:

- Adrian Badea
- Andrei Stancu
- Bogdan Radu
- Bogdana Costan
- Elena Minca
- Mihai Condorateanu

Tabela `store_org_assignments` este sursa semantica pentru asignarea
magazinelor la structura curenta si istorica.

## Site code

`site_code` este cheia unica de magazin.

Nu deduplica si nu uni magazine dupa nume asemanator sau cod asemanator.
Exemple precum `MEGAMALL` si `MC-MEGAMALL` pot reprezenta magazine/firme
diferite in acelasi centru comercial. Daca nu exista o regula business
explicita, doua `site_code` diferite sunt doua magazine diferite.

## View-uri pentru agenti si rapoarte

Foloseste aceste view-uri in loc sa grupezi direct dupa `asm` din tabelele
istorice.

### Current org

Aceste view-uri regrupeaza istoricul magazinelor active dupa structura curenta
incepand cu `2026-05`.

- `v_retail_current_store_org`
- `v_retail_agent_month_current_org`
- `v_retail_store_month_current_org`
- `v_retail_item_month_current_org`
- `v_retail_targets_current_org`
- `v_retail_sales_current_org`

Pentru raspunsuri comerciale uzuale, default-ul este:

```sql
SELECT
    import_month,
    asm,
    SUM(total_sales) AS total_sales
FROM v_retail_store_month_current_org
GROUP BY import_month, asm
ORDER BY import_month, asm;
```

### Historical org

Aceste view-uri pastreaza structura asa cum era in luna respectiva.

- `v_retail_historical_store_org`
- `v_retail_agent_month_historical_org`
- `v_retail_store_month_historical_org`
- `v_retail_item_month_historical_org`
- `v_retail_sales_historical_org`

Foloseste-le doar cand se cere explicit structura istorica:

```sql
SELECT
    import_month,
    asm,
    SUM(total_sales) AS total_sales
FROM v_retail_store_month_historical_org
WHERE import_month = '2026-04'
GROUP BY import_month, asm
ORDER BY asm;
```

## Diferenta importanta

`current_org` raspunde la intrebarea:

> Cum arata performanta istorica a magazinelor active, regrupata dupa managerii
> actuali?

`historical_org` raspunde la intrebarea:

> Cum arata performanta in structura manageriala existenta atunci?

Managerii vechi raman in istoric, dar nu trebuie sa apara in analizele
curente daca userul nu cere explicit asta.

## Reguli pentru totaluri Retail

- Pentru totaluri Retail foloseste agregatele de reporting, nu raw
  `sales_transactions`.
- Reporting-ul exclude `is_cartela = true`.
- Reporting-ul exclude locatiile de distributie `stores.locatie ILIKE 'TR %'`.
- Pentru analize de produse pe structura curenta foloseste
  `v_retail_item_month_current_org`.
- Pentru targete pe structura curenta foloseste
  `v_retail_targets_current_org`.
- Pentru KPI operationali foloseste aceleasi formule ca in Hub/Agents:
  `proc_bon2acc = receipt_2plus_count * 100 / receipt_count`,
  `prc_focus_acc_qty = focus_quantity * 100 / total_quantity`,
  `daily_average = total_sales / zile active`, iar `avg_receipt_value =
  total_sales / receipt_count`.
- Pentru categorii si tipuri de produse foloseste `category`, `subcategory`,
  `brand_group`, `brand`, `item_code`, `item_name`.
- Pentru analize de pret foloseste `sales_transactions` cu filtre explicite:
  `is_cartela = false`, locatie diferita de `TR %`, `unit_price`,
  `total_value` si `quantity`.

## Operare viitoare

Daca apare o reorganizare noua:

1. inchide assignment-ul curent prin `valid_to_month`;
2. adauga assignment-uri noi cu `valid_from_month`;
3. marcheaza noile randuri `is_current = true`;
4. verifica sa existe un singur rand `is_current` per `site_code`.

Nu rescrie tabelele de vanzari si nu modifica randurile istorice din
`reporting_*` doar pentru o reorganizare. Schimbarea se face in stratul
semantic `store_org_assignments` + view-uri.
