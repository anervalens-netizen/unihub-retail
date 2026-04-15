# Spec: Incentive Cards Redesign — Top Agenti + Top Magazine
**Data:** 2026-04-06  
**Context:** UniHub, tab Focus > Campanii

---

## Scopul

Cardurile "Top Agenti" si "Top Magazine" din sectiunea Incentive trebuie extinse cu:
- Toate randurile (nu doar top 10), card cu inaltime fixa si scroll intern
- Coloane noi: `%Prev.` (previziune realizare target), `Cant.` (bucati incentive), `Val Inc.` (bonus RON)
- Capete de tabel sortabile pe fiecare coloana
- Badge firma (M rosu / M albastru) la magazine

---

## Logica de business

### Eligibilitate incentive (deja implementata in backend)
- `≥ 99%` din target → multiplier `1.0` → bonus 100%
- `89–99%` din target → multiplier `0.5` → bonus 50%
- `< 89%` din target → multiplier `0.0` → bonus 0%

### `%Prev.` — cum se calculeaza
**Per magazin:** `store_achievements[site_code]` — deja calculat in `_get_store_incentive_multipliers` din `dashboard.py`. Foloseste previziune (proiectie pana la sfarsitul lunii) cand luna nu e finalizata.

**Per agent:** agentul e hardcodat pe un singur magazin → `achievement` al agentului = `store_achievements[site_code]` al magazinului sau. Nu e nevoie de query separat.

**Nota:** `%Prev.` poate fi `None` daca magazinul nu are target configurat — se afiseaza `—`.

### Agenti cu bonus 0
Agentii cu `achievement < 89%` au `multiplier = 0` → `bonus = 0`. Se **includ** in lista (vizibilitate pentru management). Se afiseaza `0 RON` la Val Inc. si rosu la `%Prev.`.

---

## Modificari backend

### 1. `backend/models.py` — `IncentiveTopAgent`
**Inainte:**
```python
class IncentiveTopAgent(BaseModel):
    agent_name: str
    qty: int  # bonus RON (misnamed)
```
**Dupa:**
```python
class IncentiveTopAgent(BaseModel):
    agent_name: str
    qty_sold: int        # bucati incentive vandute
    val_incentive: float # bonus RON
    achievement: float | None  # ratio 0–N, None = fara target
```

### 2. `backend/models.py` — `PromoTopStore`
Adaug campul `firma: str = ""`.

### 3. `backend/routers/campaigns.py` — build `top_agents`
In bucla pe `agent_item_rows`, acumul:
- `agent_qty: dict[str, int]` — suma `qty` per agent (bucati incentive)
- `agent_bonus: dict[str, float]` — bonus RON (exista deja)
- `agent_site: dict[str, str]` — `site_code` per agent (pentru lookup achievement)

La constructia `top_agents`:
```python
top_agents = [
    IncentiveTopAgent(
        agent_name=agent,
        qty_sold=agent_qty.get(agent, 0),
        val_incentive=round(bonus, 2),
        achievement=store_achievements.get(agent_site.get(agent, ""))
    )
    for agent, bonus in sorted(agent_bonus.items(), key=lambda x: -x[1])
]
# Fara [:10] — toti agentii
```

### 4. `backend/routers/campaigns.py` — build `top_stores`
Adaug `firma` in query-ul care construieste `top_stores`. `firma` e disponibila in `reporting_agent_month` (alias `agg.firma`). Se adauga in SELECT si in constructia `PromoTopStore(...)`.

Scot `[:10]` — toate magazinele.

---

## Modificari frontend

### `src/components/Campaigns.tsx`

#### Componenta `SortableTable` (noua, locala)
O componenta simpla care primeste `columns` + `rows` + state sort local si randeaza:
- `thead` cu sageata sortare per coloana (▲ / ▼ / neutru)
- `tbody` sortat client-side
- Container `div` cu `max-h-[360px] overflow-y-auto` si scrollbar subtil
- Header `sticky top-0`

Nu se creeaza fisier separat — componenta ramane in `Campaigns.tsx` (e folosita doar acolo).

#### Card "Top 10 Agenti" → "Top Agenti"
Coloane:
| Key | Label | Align | Default sort |
|-----|-------|-------|--------------|
| `rank` | # | left | — (nu sortabil) |
| `agent_name` | Agent | left | — |
| `achievement` | %Prev. | right | desc (initial) |
| `qty_sold` | Cant. | right | — |
| `val_incentive` | Val Inc. | right | desc |

Sort initial: `val_incentive` descendent.

Culori `%Prev.`:
- `≥ 0.99` → `text-emerald-600 font-black`
- `≥ 0.89` → `text-amber-500 font-semibold`
- `< 0.89` → `text-red-500`
- `null` → `text-slate-400` afiseaza `—`

Format: `Math.round(achievement * 100) + "%"`

#### Card "Top Magazine"
Coloane:
| Key | Label | Align |
|-----|-------|-------|
| `rank` | # | left |
| `store_name` | Magazin | left (cu badge firma) |
| `achievement` | %Prev. | right |
| `qty` | Cant. | right |
| `incentive_value` | Val Inc. | right |

Sort initial: `incentive_value` descendent.

Badge firma (inline SVG / span):
```tsx
const badgeColor = firma.toLowerCase().includes('mobicell') ? '#3b82f6'
                 : firma.toLowerCase().includes('mobiup')   ? '#ef4444'
                 : '#9ca3af';
```
- `14×14px`, `border-radius: 3px`, litera `M`, `font-size: 8px font-weight: 900`
- Afiseaza `firma` ca tooltip (`title` attribute)

Numele magazinului: `max-w-[90px] truncate` cu `title` complet ca tooltip.

#### Curatare IncentiveCard
Scot sectiunile `Top 10 Agenti` si `Top Magazine` din interiorul `IncentiveCard` (deja mutate in carduri externe in sesiunea anterioara).

---

## Ce NU se schimba
- Logica de calcul bonus/multiplier — ramane identica
- Pie chart categorii din `IncentiveCard` — neafectat
- Cardul amber "Top Magazine" (cu promotie activa) — neafectat
- Toate celelalte view-uri

---

## Ordine implementare
1. `models.py` — extinde `IncentiveTopAgent`, adauga `firma` in `PromoTopStore`
2. `campaigns.py` — acumul `agent_qty` + `agent_site`, adauga `firma` in stores, scot limitele `[:10]`
3. `Campaigns.tsx` — `SortableTable` + refac cele 2 carduri
4. Typecheck + build + deploy

---

## Criterii de acceptanta
- [ ] Toti agentii apar (nu doar 10)
- [ ] Toate magazinele apar (nu doar 10)
- [ ] Cardurile au inaltime fixa si scroll intern
- [ ] Click pe header coloana sorteaza ASC/DESC cu toggle
- [ ] `%Prev.` verde/portocaliu/rosu conform pragurilor
- [ ] Badge M rosu/albastru la magazine
- [ ] Agentii cu bonus 0 sunt inclusi si vizibili
- [ ] Typecheck curat, build passing
