# Design: Tab Management (Manageri + Agenti + CRM + Tasks + HR + Calculator Target)

**Data:** 2026-04-09
**Status:** Aprobat de utilizator
**Audiență:** Manager / Proprietar (roluri `admin`, `management`)

> **Extinderi ulterioare:**
> - din 2026-05-27, Management include sub-tab-ul `Calculator Target`;
>   designul si regulile lui sunt documentate in
>   `docs/superpowers/specs/2026-05-27-target-calculator-design.md`.
> - din 2026-06-11, sub-tab-ul initial `Echipa` devine `Manageri`, iar
>   sectiunea vizibila `Magazine` este inlocuita cu `Agenti`.

---

## Context

UniHub acoperă bine vânzările, targetele, campaniile și vizitele. Lipsesc trei domenii esențiale pentru un manager care vrea tot în același tool: gestiunea oamenilor (HR), sănătatea relației cu magazinele (CRM extins) și urmărirea task-urilor operaționale.

Soluția curenta: un tab `Management` cu sub-tab-uri — Manageri, Agenti,
Tasks, HR si Calculator Target — vizibil exclusiv pentru `admin` si
`management`. Scorurile CRM de magazine raman disponibile ca logica interna si
sunt integrate in cardurile managerilor. Calculator Target este detaliat in
specificatia dedicata mentionata mai sus.

---

## Arhitectură generală

### Frontend
- Tab nou `Management` adăugat în `MainLayout.tsx`, afișat condiționat pe rol
- Componentă `Management.tsx` cu routing intern pe sub-tab-uri: `Manageri | Agenti | Calculator Target | Grile`
- Sub-componente principale: `ASMSubtab.tsx`, `AgentEvaluationSubtab.tsx`, `TargetCalculatorSubtab.tsx`, `GrileSubtab.tsx`

### Backend
- Routerele Management: `backend/routers/hr.py`, `backend/routers/agents.py`, `backend/routers/crm.py`, `backend/routers/target_calculator.py`
- Înregistrate în `main.py` cu prefixele `/api/hr`, `/api/agents`, `/api/crm`, `/api/target-calculator`
- Tabelele Management si Calculator Target din `schema_v2.sql` sunt aplicate automat la restart via `ensure_schema_current()`
- Endpoint ASM performance citește din **două surse**: PostgreSQL (vânzări, targete) + SQLite `visits.db` (vizite) combinate server-side via `run_in_executor`

---

## Sub-tab Echipă (ASM Performance)

### Context

Ierarhia: **RM** (4 regionali, inclusiv Andrei Stancu) → **ASM** (subordonați direcți care fac vizite la magazine) → **TL** → **Agenți**. ASM-ii sunt evaluați pe două dimensiuni: activitate pe teren (vizite) și performanța teritoriului gestionat (vânzări + targete).

### Funcționalitate

**Tabel ASM** — un rând per ASM, cu KPI-uri combinate:

| KPI | Sursă | Detaliu |
|-----|-------|---------|
| Total vânzări teritoriu | PostgreSQL `reporting_agent_month` | Suma vânzărilor din toate magazinele ASM-ului |
| % Target atins | PostgreSQL `store_targets` | Vânzări / sum targets magazine ASM |
| Magazine active | PostgreSQL | COUNT DISTINCT site_code cu vânzări în lună |
| Agenți activi | PostgreSQL | COUNT DISTINCT agent cu vânzări în lună |
| % Bon 2+ acc | PostgreSQL | Medie ponderată doi-pe-bon din teritoriu |
| Vizite luna curentă | SQLite `visits.db` | COUNT vizite cu `data_raport` în lună |
| % Completion vizite | SQLite | AVG `completion_pct` per ASM |
| Scor checklist | SQLite | AVG sum(curatenie+imagine+uniforma+afise+produse_promo) × 20 |
| Durată medie vizită | SQLite | AVG `durata_vizita_ore` |
| % Vizite aprobate | SQLite | COUNT(status='approved') / COUNT(*) × 100 |

**Filtrare pe regional** — RM vede implicit doar ASM-ii săi (filtru pe `regional = user.full_name`); admin vede toți.

**Drill-down per ASM** — click pe rând expandează:
- Grafic trend 6 luni: vânzări teritoriu + % target (din PostgreSQL)
- Tabel vizite recente cu detalii (din SQLite)
- Lista magazine cu probleme (scor CRM < 40)

### Tabele noi

Nicio tabelă nouă — datele vin exclusiv din surse existente.

### Endpointuri

| Metodă | Path | Descriere |
|--------|------|-----------|
| GET | `/api/hr/asm-performance?month=YYYY-MM` | Profil combinat toți ASM-ii (filtrat pe regional dacă role=management) |
| GET | `/api/hr/asm-performance/{asm_name}/history?months=6` | Trend 6-12 luni per ASM (vânzări + vizite) |

### Logica de combinare (backend)

```python
async def get_asm_performance(conn, month: str, regional: str | None) -> list[dict]:
    # 1. Citește PostgreSQL (async)
    pg_rows = await conn.fetch("""
        SELECT s.asm, s.regional,
               SUM(ram.total_sales) AS total_sales,
               COUNT(DISTINCT ram.site_code) AS active_stores,
               COUNT(DISTINCT ram.agent) AS active_agents,
               ROUND(SUM(ram.receipt_2plus_count)*100.0/NULLIF(SUM(ram.receipt_count),0),1) AS pct_bon2acc,
               COALESCE(SUM(st.target_value),0) AS total_target
        FROM reporting_agent_month ram
        JOIN stores s ON s.site_code = ram.site_code
        LEFT JOIN store_targets st ON st.site_code=ram.site_code AND st.import_month=ram.import_month
        WHERE ram.import_month = $1
          AND ($2::text IS NULL OR s.regional = $2)
        GROUP BY s.asm, s.regional
        ORDER BY total_sales DESC
    """, month, regional)

    # 2. Citește SQLite (sync în executor)
    import asyncio, sqlite3
    VISITS_DB = "/opt/Mobiup/unihub/data/visits/visits.db"
    year_month = month  # format YYYY-MM

    def query_sqlite():
        con = sqlite3.connect(VISITS_DB)
        con.row_factory = sqlite3.Row
        cur = con.execute("""
            SELECT asm,
                   COUNT(*) AS total_visits,
                   ROUND(AVG(completion_pct),1) AS avg_completion,
                   ROUND(AVG(durata_vizita_ore),2) AS avg_duration,
                   COUNT(DISTINCT magazin) AS distinct_stores,
                   ROUND(AVG(
                       (COALESCE(curatenie,0)+COALESCE(imagine,0)+COALESCE(uniforma,0)
                        +COALESCE(afise,0)+COALESCE(produse_promo,0))*20.0
                   ),1) AS checklist_score,
                   ROUND(SUM(CASE WHEN status='approved' THEN 1 ELSE 0 END)*100.0/COUNT(*),1) AS approved_pct
            FROM visits
            WHERE substr(data_raport,1,7) = ?
              AND asm IS NOT NULL AND asm != ''
            GROUP BY asm
        """, (year_month,))
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return rows

    loop = asyncio.get_event_loop()
    sqlite_rows = await loop.run_in_executor(None, query_sqlite)

    # 3. Join pe asm name
    sqlite_map = {r["asm"]: r for r in sqlite_rows}
    result = []
    for pg in pg_rows:
        asm = pg["asm"]
        sq = sqlite_map.get(asm, {})
        target_pct = round(float(pg["total_sales"])/float(pg["total_target"])*100,1) if pg["total_target"] > 0 else None
        result.append({
            "asm": asm,
            "regional": pg["regional"],
            "total_sales": float(pg["total_sales"]),
            "total_target": float(pg["total_target"]),
            "target_pct": target_pct,
            "active_stores": pg["active_stores"],
            "active_agents": pg["active_agents"],
            "pct_bon2acc": float(pg["pct_bon2acc"] or 0),
            "total_visits": sq.get("total_visits", 0),
            "avg_completion": sq.get("avg_completion", None),
            "avg_duration": sq.get("avg_duration", None),
            "distinct_stores_visited": sq.get("distinct_stores", 0),
            "checklist_score": sq.get("checklist_score", None),
            "approved_pct": sq.get("approved_pct", None),
        })
    return result
```

### UI — `ASMSubtab.tsx`

Tabel cu rânduri expandabile. Coloane principale vizibile mereu:
- Nume ASM | Vânzări teritoriu | % Target | Vizite | % Completion | Scor checklist

La expand: grafic trend + tabel vizite recente.

Badge-uri colorate pe % target: verde ≥ 90%, galben 70–89%, roșu < 70%.

---

## Sub-tab Agenti

### Context

Analiza agentilor acopera lunile intregi ianuarie-mai 2026 si inlocuieste
fisierul Excel folosit ca referinta operationala
`/opt/Mobiup/docs/unihub-docs/Analiza agenti 2026 - Bogdana.xlsx`.

Pentru ca in perioada analizata nu au existat targete reale per agent,
targetul agentului este derivat din targetul locatiei:

```text
target_agent_luna = target_locatie_luna / total_zile_lucrate_locatie * zile_lucrate_agent
```

Cand filtrul este pe `Toate lunile`, randurile sunt agregate pe agent pe
perioada ianuarie-mai 2026 si procentele sunt recalculate din totaluri, nu
mediate intre luni.

### Reguli de selectie

- Sunt inclusi doar agentii activi in ultima luna importata.
- Firma, magazinul si managerul afisate sunt alocarea curenta a agentului.
- Filtrele disponibile sunt luna, firma, manager si magazin.
- Sortarea tabelului trateaza procentele si valorile ca numere, inclusiv cand
  API-ul serializeaza `Decimal` ca string.

### Segmente si punctaj

Scorul maxim este 18 puncte: 6 segmente × 3 puncte.

| Segment | 3 puncte | 2 puncte | 1 punct | 0 puncte |
|---------|----------|----------|---------|----------|
| Target valoare | >= 100% | 90-99% | 80-89% | < 80% |
| Medie zilnica | peste media colegilor din locatie | - | - | sub medie sau fara comparatie |
| Valoare reper | >= 100 lei | 95-99 lei | 90-94 lei | < 90 lei |
| % Bonuri | >= 35% | 30-34% | 25-29% | < 25% |
| Focus | >= 8% | 7-7,9% | 6-6,9% | < 6% |
| Folii Premium | >= 50% | 40-49% | 30-39% | < 30% |

Bonus estimat:

- 18 puncte: 300 lei.
- 16-17 puncte: 200 lei.
- 14-15 puncte: 100 lei doar daca niciun segment nu are 0 puncte.

### Folii Premium

Segmentul Folii Premium foloseste aceeasi logica din `Focus -> Folii Premium`:

- baza este categoria `Folii Sticla`;
- premium inseamna nume produs care contine `SAPPHIRE`, `CERAMIC` sau
  `CORNING`;
- produsele sunt raportate doar la modelele tinta din indicatorul permanent
  `v_premium_glass_item_models`;
- procentul este `cantitate premium / cantitate totala folii eligibile pentru
  aceleasi modele`, cu linii deduplicate dupa tranzactie pentru a evita
  dublarea produselor compatibile cu mai multe modele.
- indicatorul este materializat in tabela indexata `premium_glass_item_models`
  si refresh-uit in `rebuild_reporting_month`; view-urile `v_*` sunt pastrate
  doar pentru compatibilitate.

### Endpoint

| Metodă | Path | Descriere |
|--------|------|-----------|
| GET | `/api/agents/evaluation` | Evaluare agenti ianuarie-mai 2026, cu query params optionale `month`, `firma`, `asm`, `site_code` |

---

## Sub-tab HR

### Funcționalitate

**Pontaj & Concedii**
- Vizualizare per angajat: zile concediu alocate / luate / rămase (an calendaristic curent)
- Formular cerere concediu: data start, data end, tip (odihnă / medical / altul), note opționale
- Manager aprobă sau respinge cererea din același ecran; statusul se actualizează în timp real
- Badge de notificare pe tab-ul HR când există cereri `pending`

**Performanță angajat**
- Profil agregat per angajat, construit exclusiv din date existente:
  - Vânzări lunare și % target atins → din `reporting_agent_month`
  - Salarii nete → din tabelele de salarii existente
  - Vizite efectuate → din `visits.db`
- Grafic evoluție 12 luni (același pattern Recharts ca în Dashboard)
- Nu se creează date noi — este un view de sinteză

### Tabele noi

```sql
leave_requests (
  id SERIAL PRIMARY KEY,
  agent_name TEXT NOT NULL,           -- cheie spre angajat, nu FK strict
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  leave_type TEXT NOT NULL,           -- 'odihna' | 'medical' | 'altul'
  notes TEXT,
  status TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'approved' | 'rejected'
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
)

attendance_records (
  id SERIAL PRIMARY KEY,
  agent_name TEXT NOT NULL,
  record_date DATE NOT NULL,
  status TEXT NOT NULL,               -- 'prezent' | 'absent' | 'concediu' | 'medical'
  notes TEXT,
  UNIQUE(agent_name, record_date)
)
```

### Endpointuri HR

| Metodă | Path | Descriere |
|--------|------|-----------|
| GET | `/api/hr/leave-requests` | Listă cereri (filtru: status, agent) |
| POST | `/api/hr/leave-requests` | Cerere nouă |
| PATCH | `/api/hr/leave-requests/{id}` | Aprobare / respingere |
| GET | `/api/hr/attendance` | Pontaj per agent + perioadă |
| POST | `/api/hr/attendance` | Înregistrare zilnică |
| GET | `/api/hr/performance/{agent_name}` | Profil agregat 12 luni |

---

## Sub-tab Magazine (CRM extins)

### Funcționalitate

**Scoring automat**
- Scor 0–100 calculat per magazin din date existente:
  - % target atins în luna curentă: 40 puncte
  - Trend față de luna anterioară (creștere/scădere %): 30 puncte
  - Zile active din luna curentă: 20 puncte
  - Număr vizite în ultimele 30 zile: 10 puncte
- Scorul este calculat la fiecare import nou sau la cerere (`POST /api/crm/scores/recalculate`)
- Stocat în tabelul `store_scores`; afișat ca badge colorat în tabelul de magazine:
  - Verde: 70–100
  - Galben: 40–69
  - Roșu: 0–39

**Alertă riscuri**
- Listă automată de magazine care îndeplinesc cel puțin una din condițiile:
  - Scor < 40
  - Scădere > 20% față de luna anterioară
  - Nicio vizită în ultimele 30 zile
- Fiecare alertă are buton „Creează task" → deschide formularul Tasks pre-populat cu magazinul și motivul alertei

### Tabele noi

```sql
store_scores (
  id SERIAL PRIMARY KEY,
  site_code TEXT NOT NULL,
  score_month TEXT NOT NULL,          -- format 'YYYY-MM'
  score INTEGER NOT NULL,             -- 0-100
  breakdown JSONB,                    -- detaliu pe componente
  calculated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(site_code, score_month)
)
```

### Endpointuri CRM

| Metodă | Path | Descriere |
|--------|------|-----------|
| GET | `/api/crm/scores` | Scoruri luna curentă (cu filtre) |
| POST | `/api/crm/scores/recalculate` | Recalculează scoruri pentru o lună |
| GET | `/api/crm/alerts` | Magazine cu risc activ |

---

## Sub-tab Tasks

### Funcționalitate

- Listă task-uri cu câmpuri: titlu, responsabil (dropdown agenți/TL existenți), magazin asociat (opțional), deadline, status
- Status posibil: `deschis` → `în lucru` → `închis`
- Filtrare rapidă: toate / ale mele / după magazin
- Creare rapidă din alertele CRM (pre-populare automată)
- Fără comentarii, atașamente, proiecte sau escaladare — simplitate intenționată

### Tabel nou

```sql
tasks (
  id SERIAL PRIMARY KEY,
  title TEXT NOT NULL,
  assignee TEXT,                      -- agent_name sau null
  site_code TEXT,                     -- magazin asociat sau null
  deadline DATE,
  status TEXT NOT NULL DEFAULT 'deschis',  -- 'deschis' | 'in_lucru' | 'inchis'
  source TEXT,                        -- 'manual' | 'crm_alert'
  source_meta JSONB,                  -- context alertă dacă source='crm_alert'
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
)
```

### Endpointuri Tasks

| Metodă | Path | Descriere |
|--------|------|-----------|
| GET | `/api/tasks` | Listă task-uri (filtru: status, assignee, site_code) |
| POST | `/api/tasks` | Task nou |
| PATCH | `/api/tasks/{id}` | Update status / câmpuri |
| DELETE | `/api/tasks/{id}` | Ștergere task |

---

## Securitate & roluri

- Tab-ul `Management` și toate endpointurile `/api/hr`, `/api/crm`, `/api/tasks` sunt accesibile exclusiv pentru rolurile `admin` și `management`
- Verificare identică cu pattern-ul existent din `auth.py`
- Rolul `tl` nu vede acest tab

---

## Ce NU este în scope

- Contracte, documente HR, fișe de post
- Notificări push / email
- Proiecte sau sub-task-uri
- Portal extern pentru angajați sau magazine
- Integrare cu sisteme de payroll externe

---

## Ordine sugerată de implementare

1. Schema SQL (4 tabele noi) + `ensure_schema_current()`
2. Router + endpointuri Tasks (cel mai simplu, fără dependențe)
3. Frontend TasksSubtab + Management shell initial (extins ulterior la cele 5 sub-tab-uri documentate mai sus)
4. Router + endpointuri HR (leave_requests + attendance)
5. Frontend HRSubtab (concedii + aprobare)
6. Logică scoring CRM + router
7. Frontend CRMSubtab (scoruri + alerte + buton „Creează task")
8. **Backend ASM performance** — endpoint `/api/hr/asm-performance` (PostgreSQL + SQLite combinat)
9. **Frontend ASMSubtab** — tabel cu KPI-uri combinate + drill-down per ASM
