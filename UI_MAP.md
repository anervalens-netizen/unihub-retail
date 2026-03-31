# UniHub — Harta UI Frontend

Harta completa a taburilor, sub-taburilor, cardurilor si elementelor UI.
Cand vrei sa lucrezi la ceva, specifica **Tab > Sub-Tab > Card/Element**.

---

## PINSCREEN (Login)

- `PinScreen` — formular login
  - Field: **Username** (input, pre-completat "admin")
  - Field: **PIN / Parola** (input password, pre-completat "9999")
  - **Error banner** (conditional, autentificare esuata)
  - Button: **Intra in aplicatie**

---

## TAB 1: HUB (`Dashboard.tsx`)

### Sub-Tab: Luna in curs

| Card/Element | Continut |
|---|---|
| **Overview** | Target, Realizat, Previziune, progress bar dual |
| **KPI Performance** (grid 2) | ProcBon2Acc (donut), PrcFocus/AccQtty (donut) |
| **Operational Metrics** (grid 4x2) | Bonuri, Accesorii, Magazine, Agenti, Zile lucrate, Med. zilnica, Val. medie bon, Cartele |
| **Comparatie perioade** | 3 PeriodBlock (curent, precedent, anul trecut) + 2 DeltaCard |
| **Promo & Incentive** | CampaignMiniCard: Promo, Incentive → link catre Focus |
| **Evolutie zilnica** | ComposedChart (Bar sales + Line qty) |
| **Top categorii si branduri** | 2 CompactPieSection (donut + legend) |
| **RM — Regional Manager** (tabel) | Col: Regional, Target, Vanzari, Procent, Promo, Incentive, Cantitate, Nr bonuri, Medie zilnica, ProcBon2Acc, Focus% |
| **ASM — Area Sales Manager** (tabel) | Col: ASM, Regional, Target, Vanzari, Procent, Promo, Incentive, Cantitate, Nr bonuri, Medie zilnica, ProcBon2Acc, Focus% |
| **Magazine** (tabel) | Col: Magazin, Site, Target, Vanzari, Procent, Cantitate, Nr bonuri, Agenti, Zile active, Medie zilnica |
| **Agenti - Toti agentii** (tabel) | Col: Magazin, Agent, Target, Vanzari, Procent, Promo, Incentive, Cantitate, Nr bonuri, Zile lucrate, Medie zilnica, ProcBon2Acc, Focus% |

### Sub-Tab: Istoric

| Card/Element | Continut |
|---|---|
| **Luna analizata** | Month Selector dropdown |
| **Overview — {luna}** | La fel ca "Luna in curs" dar cu date istorice |
| **Evolutie lunara** | ComposedChart (Bar sales + Line target + Line progress%) + "Best month" badge |
| **Trend vanzari vs target** | AreaChart |
| **Promo & Incentive** | CampaignMiniCard: Promo, Incentive |
| **Evolutie zilnica** | ComposedChart (Bar sales + Line qty) |
| **Top categorii si branduri** | 2 CompactPieSection |

### Sub-Tab: Vizite (renders `VisiteSubtab`)

| Card/Element | Continut |
|---|---|
| **KPI Cards** (grid 3) | Vizite (count), Magazine (count), Completare (%) |
| **Conformitate medie** | Progress bars: Cur, Img, Unif, Afise, Promo |
| **Detaliu pe magazin** (tabel) | Col: Magazin, ASM, Viz, Comp%, Cur, Img, Unif, Afise, Promo, Ultima vizita |

---

## TAB 2: FOCUS (`Campaigns.tsx`)

### Sub-Tab: Campanii

| Card/Element | Continut |
|---|---|
| **Header Banner** | "Campanii in curs" + luna curenta |
| **Special Cards Grid** | SpecialHubCard (promo / incentive) — icon, titlu, status badge, valoare highlight |

### Sub-Tab: Focus

| Card/Element | Continut |
|---|---|
| **Header Banner** | "Focus Products" + headline dinamic |
| **Stat Cards** (grid 2x2) | Vanzari focus, Cantitate focus, Share focus, Magazine active |
| **Luna de referinta** | Month Selector dropdown |
| **Istoric focus** | AreaChart (sales + share%) |
| **Metrics** (grid 2x2) | Vanzari focus, Cantitate focus, Pondere in volum, Magazine active |
| **Top produse focus** (tabel) | item_name, item_code, sales_total, qty_total, store_count |

---

## TAB 3: AGENTI (`Agents.tsx`)

### Sub-Tab: Prezentare Generala

| Card/Element | Continut |
|---|---|
| **Snapshot** (grid 5) | Activi, Noi, Reactivati, Plecati, Retentie |
| **Sanatate Echipa** (grid 4) | Total Unici, Vechime Medie, Stabilitate, Iesiti istoric |
| **Miscare de personal** | ComposedChart (Bar new + Bar reactivated + Line active + Line net_growth) |
| **Magazine si Flux** (grid 3) | Cu Agent, Fara Agent, Inactive + scrollable lists |
| **Lista Agenti** | Sub-tabs: Activi / Miscari / Inactiv-Risc / Toti |
| → **Search** | Cauta dupa nume agent... |
| → **Firma filter** | Dropdown Toate firmele |
| → **Magazin filter** | Dropdown Toate |
| → **Agent rows** | name, store, status badge, badges (Nou/Reactivat), sales + qty |
| → Click agent → **AgentDrawer** (slide-in) | Header (nume, X close) |
| | Grid 4: Prima luna, Luni Active, Vanzari Carier, Cea mai buna luna |
| | Grid 4: Magazine, Firme, Reactivari, Streak max |
| | Istoric Vanzari chart (Bar + tooltip) |

### Sub-Tab: Salarii (renders `SalariiSubtab`)

| Card/Element | Continut |
|---|---|
| **Statistici Salarii** (grid 2x2) | Total Salarii, Perioada, Mobiup, Mobicell |
| **Salarii vs Vanzari** | Month selector + tabel: Locatie, Firma, Salariu, Vanzari, % |
| **Evolutie Salarii vs Vanzari** (tabel) | Luna, Salarii, Vanzari, % |
| **Evolutie Salarii Lunara** | AreaChart (total, mobicell, mobiup) |
| **Agenti** | Search + Firma filter + Magazin filter + Reseteaza |
| | Tabel: Nume, Magazin, Nr Luni, Total |
| | Pagination (la >50 agenti) |
| → Click agent → **SalaryDrawer** (slide-in) | Header (nume, CNP mascat, companie, locatie) |
| | Stats: Total RON, Luni, Medie RON |
| | Evolutie Lunara chart (BarChart) |
| | Detalii Lunare tabel: Luna, Companie, Locatie, Salariu |

---

## TAB 4: AI (`AIChat.tsx`)

| Card/Element | Continut |
|---|---|
| **Header** | "UniHub" + Bot icon + "Asistent AI" + status (Neconectat) |
| **Messages Area** | Bubble-uri: Assistant (indigo, Bot icon) / User (indigo-600, User icon) + timestamp |
| | Typing indicator (3 dots animate) |
| **Input Area** | Textarea (auto-resize) + Send button + hint "Enter trimite" |

---

## TAB 5: SETARI (`Settings.tsx`)

| Card/Element | Continut |
|---|---|
| **Tema aplicatie** | Grid 2x2: Light Standard, Light Mint, Light Olive, Dark Standard |
| **Status cont** | Utilizator, Rol, Cheia de filtrare |
| **Import fisier vanzari** (admin only) | File input (.xlsx/.xls) + Button "Importa fisier" + message banner |
| **Utilizatori** (admin only) | Form: username, nume complet, parola, role (TL/Management/Admin) |
| | Button "Creeaza utilizator" |
| | User list: username, nume, rol, status, magazine alocate |
| **Alocari TL** (admin only) | TL user selector + checkbox list magazine + Button "Salveaza" |
| **Istoric importuri** (admin only) | Scrollable list (max 8): luna, filename, rows, status, timestamp |

---

## FILTRE GLOBALE (MainLayout)

Deschise prin butonul floating (icon Filter) disponibil pe Hub, Focus, Agenti.

| Filter | Descriere |
|---|---|
| **Firma** | Dropdown (Toate firmele / firme) |
| **Regional** | Dropdown (Toti / regionals) |
| **ASM** | Dropdown (Toti / ASMs) |
| **Magazin** | Dropdown (Toate / magazine "locatie (site_code)") |
| **Agent** | Dropdown (Toti / agenti) |
| Button **Reseteaza** | Reseteaza toate filtrele |
| Button **Aplica** | Aplica filtrele |

---

## Bottom Tab Bar (MainLayout)

| Tab | Icon | Componenta |
|---|---|---|
| Hub | LayoutDashboard | Dashboard.tsx |
| Focus | Sparkles | Campaigns.tsx |
| Agenti | Users | Agents.tsx |
| AI | Bot | AIChat.tsx |
| Setari | Settings | Settings.tsx |

---

## Cum sa referi un element

Exemplu: *"In **Hub > Luna in curs > RM** tabel vreau sa adaug o coloana noua"*
Sau: *"In **Agenti > Prezentare Generala > Lista Agenti** vreau sa filtrez dupa firma"*
Sau: *"In **Setari > Utilizatori** vreau sa adaug un buton de stergere"*

Foloseste formatul: **Tab > Sub-Tab > Card/Element > Element specific**
