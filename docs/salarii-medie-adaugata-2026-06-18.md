# Raport corectiv — Agenti > Salarii

**Data:** 2026-06-18  
**Scop:** auditarea implementarii anterioare pentru media salariala, corectarea
calculelor si realinierea tabelelor din `Agenti > Salarii`.

## Concluzia auditului

Implementarea anterioara nu putea functiona corect:

1. `/salarii/trend` declara `agent_count`, dar backend-ul il initializa cu `0`
   si nu il popula din baza de date. Coloana `Medie/Agent` afisa astfel `0`.
2. Overview-ul impartea totalul la `record_count`, in timp ce trendul incerca
   sa imparta la agenti distincti. Cele doua carduri foloseau definitii diferite
   pentru aceeasi notiune.
3. In date exista agenti cu doua randuri de plata in aceeasi luna, inclusiv
   plati impartite intre firme. Un rand nu este echivalent cu un agent-luna.
4. Exista cinci duplicate complet identice in istoricul vechi fara CNP.
   Overview-ul, graficul si tabelele le numarau dublu, in timp ce lista de
   agenti avea deja un `DISTINCT`; cardurile puteau afisa totaluri diferite.
5. Componenta comuna `SortableHeader` alinia continutul butonului la stanga
   chiar si pentru coloanele numerice marcate `text-right`.
6. Tabelul Agenti avea antetul separat de corpul cu scrollbar. Latimea
   scrollbarului producea decalaj intre antet si coloane.
7. Paginarea listei Agenti adauga pagina urmatoare peste pagina curenta, desi
   footerul indica afisarea unei singure pagini.

## Definitia folosita acum

```text
media salariala = media valorilor agent-luna >= 2.000 RON
```

- identificator principal agent: CNP;
- fallback pentru randuri istorice fara CNP: numele normalizat;
- randurile complet identice sunt deduplicate in read model;
- daca un agent are doua plati in aceeasi luna, valorile se insumeaza, iar
  pragul se aplica sumei lunare;
- valorile agent-luna sub 2.000 RON sunt tratate ca fractii si excluse numai
  din medie;
- totalurile salariale, numarul de agenti, numarul total de luni si istoricul
  raman complete.

Aceeasi definitie este folosita in:

- `Statistici Salarii`;
- `Salarii vs Vanzari`;
- `Evolutie Salarii vs Vanzari`;
- lista `Agenti`.

## Modificari backend

### `backend/repositories/salarii.py`

- overview-ul, evolutia, summary-ul si trendul lucreaza pe randuri deduplicate;
- overview-ul returneaza `agent_month_count` complet si
  `avg_agent_month_count` eligibil pentru medie;
- trendul calculeaza efectiv `agent_count` lunar;
- overview-ul, trendul, summary-ul pe locatie, lista Agenti si drawer-ul
  calculeaza media numai din valorile agent-luna de cel putin 2.000 RON;
- lista Agenti este agregata o singura data per persoana, nu separat pentru
  fiecare combinatie istorica firma-locatie;
- firma si locatia afisate in lista sunt cele din cea mai recenta luna
  disponibila in selectia filtrata;
- vanzarile din trend sunt agregate separat pe magazinele salariale eligibile,
  ca sa nu multiplice salariile sau numarul de agenti.

### `backend/services/salarii.py`

- overview-ul expune `avg_salary`;
- summary-ul pe locatie expune `avg_salary`;
- trendul expune lunar `agent_count` si `avg_salary`;
- campurile numerice sunt calculate defensiv cand numitorul este zero.

## Modificari frontend

### Card 1 — Statistici Salarii

Structura este acum 3 randuri x 2 coloane:

1. Total salarii | Medie lunara / agent
2. Perioada | Agenti unici
3. Mobiup | Mobicell

Media este afisata complet, cu separatori romanesti, nu compactata la `3K`.
Sub valoare este afisat numarul de salarii agent-luna eligibile.

### Card 2 — Salarii vs Vanzari

Coloanele sunt:

```text
Locatie | Firma | Agenti | Salarii | Medie / agent | Vanzari | %*
```

Antetul si randurile folosesc aceleasi latimi explicite. Coloanele numerice
sunt aliniate la dreapta, iar tabelul are scroll orizontal pe ecrane inguste.

### Card 3 — Evolutie Salarii vs Vanzari

Coloanele sunt:

```text
Luna | Agenti | Salarii | Medie / agent | Vanzari | %*
```

`Medie / agent` vine direct din backend, este sortabila si foloseste numai
salariile lunare de cel putin 2.000 RON.

### Card 5 — Agenti

- antetul si corpul sunt acum acelasi tabel HTML cu antet sticky;
- coloanele sunt:
  `Nume agent | Firma | Locatie curenta | Luni | Medie / luna | Total`;
- scrollbarul nu mai poate decala antetul;
- pagina urmatoare inlocuieste randurile curente, nu le concateneaza;
- badge-ul reprezinta agenti unici, nu combinatii istorice agent-firma-locatie.

## Validare pe baza live

La momentul verificarii:

| Indicator | Valoare |
|---|---:|
| Total salarii deduplicat | 11.866.232,07 RON |
| Agenti unici | 370 |
| Combinatii agent-luna | 3.314 |
| Salarii agent-luna eligibile pentru medie | 3.067 |
| Medie generala eligibila | 3.792,11 RON |
| Mai 2026 — total salarii | 646.704,46 RON |
| Mai 2026 — agenti | 166 |
| Mai 2026 — agenti eligibili pentru medie | 157 |
| Mai 2026 — medie eligibila / agent | 4.062,39 RON |

Totalul vechi de `11.876.520,07 RON` includea de doua ori cele cinci randuri
istorice identice fara CNP.

## Verificari tehnice

```bash
npm run typecheck
backend/venv/bin/python -m pytest backend/tests/test_salarii_service.py -q
npm run build
```

Validarea SQL a fost facuta si prin apelarea directa a serviciilor
`get_overview`, `get_trend`, `get_summary` si `get_agents_summary` pe baza live.

## Fisiere modificate

- `backend/repositories/salarii.py`
- `backend/services/salarii.py`
- `backend/tests/test_salarii_filter.py`
- `backend/tests/test_salarii_service.py`
- `src/api/salarii.ts`
- `src/components/SalariiSubtab.tsx`
- `src/components/SalaryDrawer.tsx`
- `src/components/dashboard/DashboardWidgets.tsx`
- `APP_ARCHITECTURE.md`
- `AGENTS.md`
- `README.md`
