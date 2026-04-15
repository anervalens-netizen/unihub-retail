# Spec: Tabele Breakdowns în Istoric + Incentive la Magazine
**Data:** 2026-04-06
**Context:** UniHub, tab Hub — secțiunile „Luna în curs" și „Istoric"

---

## Scopul

1. **Coloana Incentive la Magazine** — adăugată atât în „Luna în curs" cât și în „Istoric" (coloana lipsea din `StoreStats` Pydantic, deși era calculată în SQL)
2. **Tabele RM / ASM / Magazine / Agenți în Istoric** — aceleași tabele ca în „Luna în curs", filtrate pe `historyMonth`, fără coloana `promo_qty`

---

## Analiză

### De ce lipsea Incentive la Magazine
`_fetch_store_stats_rows` calculează `incentive_qty` în SQL și îl atașează pe row, dar `StoreStats` (Pydantic model) nu îl declară → Pydantic îl elimină silențios. Fix: adaugă câmpul în model.

### De ce tabele History nu necesită backend nou
`getDashboardAll(buildQuery(historyMonth))` este **deja apelat** în `loadHistory` și returnează `allData.agents`, `allData.stores`, `allData.regionals`, `allData.asms`. Aceste câmpuri sunt ignorate în state. Fix: salvează-le.

---

## Modificări backend

### `backend/models.py` — `StoreStats`
Adaugă la finalul modelului:
```python
promo_qty: int = 0
incentive_qty: int = 0
```

---

## Modificări frontend

### `src/api/types.ts` — `StoreStat`
Adaugă la interfață:
```typescript
promo_qty: number;
incentive_qty: number;
```

### `src/components/Dashboard.tsx`

#### 1. `STORE_COLUMNS` — adaugă coloana Incentive
După coloana `proc_realizare_target`, înaintea `qty_total`:
```typescript
{ key: 'incentive_qty', label: 'Incentive' },
```

#### 2. 4 state-uri noi pentru Istoric
```typescript
const [historyRegionals, setHistoryRegionals] = useState<RegionalStat[]>([]);
const [historyAsms, setHistoryAsms] = useState<AsmStat[]>([]);
const [historyStores, setHistoryStores] = useState<StoreStat[]>([]);
const [historyAgents, setHistoryAgents] = useState<AgentStat[]>([]);
```

#### 3. 4 sort state-uri noi (independente față de current)
```typescript
const [historyRegionalSort, setHistoryRegionalSort] = useState<{key: RegionalSortKey; direction: SortDirection}>({ key: 'total_vanzari', direction: 'desc' });
const [historyAsmSort, setHistoryAsmSort] = useState<{key: AsmSortKey; direction: SortDirection}>({ key: 'total_vanzari', direction: 'desc' });
const [historyStoreSort, setHistoryStoreSort] = useState<{key: StoreSortKey; direction: SortDirection}>({ key: 'total_vanzari', direction: 'desc' });
const [historyAgentSort, setHistoryAgentSort] = useState<{key: AgentSortKey; direction: SortDirection}>({ key: 'total_vanzari', direction: 'desc' });
```

#### 4. 4 sorted useMemo (reutilizează funcțiile get*SortValue existente)
Identice cu `sortedRegionals` etc. dar pe state-urile history*.

#### 5. 4 coloane constante History (fără `promo_qty`)
```typescript
const HIST_REGIONAL_COLUMNS = REGIONAL_COLUMNS.filter(c => c.key !== 'promo_qty');
const HIST_ASM_COLUMNS = ASM_COLUMNS.filter(c => c.key !== 'promo_qty');
const HIST_STORE_COLUMNS = STORE_COLUMNS; // promo_qty nu există în STORE_COLUMNS
const HIST_AGENT_COLUMNS = AGENT_COLUMNS.filter(c => c.key !== 'promo_qty');
```

#### 6. `loadHistory` — salvează agents/stores/regionals/asms + extinde cache
În `.then(([histData, allData]) => { ... })`, adaugă:
```typescript
setHistoryRegionals(allData.regionals || []);
setHistoryAsms(allData.asms || []);
setHistoryStores(allData.stores);
setHistoryAgents(allData.agents);
```

În `setCachedView(historyDetailCacheKey, { ... })`, adaugă:
```typescript
regionals: allData.regionals || [],
asms: allData.asms || [],
stores: allData.stores,
agents: allData.agents,
```

În blocul de restaurare din cache (unde se citesc `cached.value.summary` etc.), adaugă:
```typescript
setHistoryRegionals(cached.value.regionals || []);
setHistoryAsms(cached.value.asms || []);
setHistoryStores(cached.value.stores || []);
setHistoryAgents(cached.value.agents || []);
```

#### 7. Tipul cache `historyDetailCacheKey` — extinde cu câmpurile noi
Adaugă în interfața inline a cached value:
```typescript
regionals: RegionalStat[];
asms: AsmStat[];
stores: StoreStat[];
agents: AgentStat[];
```

#### 8. Render tabelele în secțiunea Istoric
Sub cardurile existente (grafic zilnic, categorii+branduri), adaugă 4 carduri identice vizual cu cele din current. Coloane: conform HIST_*_COLUMNS. Celule: identice cu curent dar fără celula `promo_qty`.

**Coloana Incentive la Magazine** — în render-ul tabelului Magazine (atât current cât și history):
```tsx
<td className="px-3 py-2">{formatInt(store.incentive_qty)}</td>
```

---

## Coloane finale per tabel History

| Tabel | Coloane |
|-------|---------|
| RM | Regional / Target / Vânzări / % / Incentive / Cant. / Nr bonuri / Medie zilnică / ProcBon2Acc / Focus% |
| ASM | ASM / Target / Vânzări / % / Incentive / Cant. / Nr bonuri / Medie zilnică / ProcBon2Acc / Focus% |
| Magazine | Magazin / Firma / Target / Vânzări / % / **Incentive** / Cant. / Nr bonuri / Agenți / Zile active / Medie zilnică |
| Agenți | Agent / Magazin / Target / Vânzări / % / Incentive / Cant. / Nr bonuri / Zile lucrate / Medie zilnică / ProcBon2Acc / Focus% |

---

## Ce NU se schimbă
- Nicio rută backend nouă
- Logica de calcul incentive/promo — neatinsă
- Secțiunea „Luna în curs" — doar adaugă coloana Incentive la Magazine
- Toate celelalte view-uri

---

## Ordine implementare
1. `backend/models.py` — adaugă `promo_qty` + `incentive_qty` la `StoreStats`
2. `src/api/types.ts` — adaugă câmpurile la `StoreStat`
3. `Dashboard.tsx` — `STORE_COLUMNS` + coloana Incentive în render Magazine (current)
4. `Dashboard.tsx` — state-uri + sort + cache pentru History
5. `Dashboard.tsx` — JSX cele 4 tabele în secțiunea Istoric
6. Typecheck + build + deploy

---

## Criterii de acceptanță
- [ ] `incentive_qty` apare în cardul Magazine din „Luna în curs"
- [ ] Secțiunea Istoric afișează 4 tabele sub cardurile existente
- [ ] Tabelele History se supun filtrului `luna analizata` (historyMonth)
- [ ] Sortare pe orice coloană funcționează independent față de „Luna în curs"
- [ ] Nicio coloană `promo_qty` în tabelele History
- [ ] TypeScript 0 errors, build passing
