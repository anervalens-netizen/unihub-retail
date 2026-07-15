# Audit UX mobil — 2026-07-15

## Rezumat

Auditul a acoperit 19 suprafețe funcționale la 390 × 844 px, după publicarea pachetului UX desktop. Niciun ecran verificat nu produce overflow orizontal la nivelul documentului sau al zonei principale. Navigarea de jos rămâne disponibilă, iar ierarhia generală a cardurilor este coerentă.

Riscurile principale sunt densitatea din Istoric Hub și Analiza agenți, lipsa unui indiciu că taburile Focus se pot derula orizontal, numărul mare de acțiuni sub 44 px și competiția dintre butonul flotant de filtre, bara de acțiuni și navigarea de jos.

Numărul de controale sub 44 px este un indicator de risc, nu o listă automată de defecte: include și chipuri, sortări de tabel sau acțiuni secundare rare.

## Status implementare

Recomandările P0–P2 au fost implementate după audit:

- filtrul global rămâne flotant și discret, cu badge pentru starea activă, iar bara de jos și panourile folosesc safe areas;
- taburile lungi au snap, fade și indiciu vizibil de glisare;
- Hub Istoric este împărțit în Sumar, Trend și Detalii, iar contextul AI Forecast este responsive;
- mecanismul Incentive este pliat implicit, iar Folii premium are Sumar/Modele/Magazine/Agenți;
- Analiza agenți folosește drawer de filtre și carduri mobile, cu comparația veche ca mod secundar;
- Grile folosește un selector compact de stare pe mobil;
- Salarii folosește carduri responsive pentru magazine, trend și agenți;
- Calculator Target și Export au progres compact și acțiuni sticky coordonate cu navigarea;
- P&L păstrează perioada și scope-ul într-un sumar sticky;
- tema apare numai în Preferințe, nu și în Importuri;
- acțiunile frecvente au minimum 44 px pe mobil.

## Priorități recomandate

### P0 — fluxuri care trebuie simplificate

1. **Focus — navigare:** taburile sunt tăiate după primele patru opțiuni și nu comunică faptul că se pot derula. Se recomandă un indicator de continuare (fade), snap la derulare și un meniu „Mai multe” pentru secțiunile rare.
2. **Analiza agenți:** filtrele și explicația mecanismului ocupă aproape primul ecran complet. Pe mobil, rezultatul trebuie să înceapă cu un sumar și carduri de agent; filtrele intră într-un drawer, comparația veche într-o acțiune secundară, iar tabelul complet rămâne pentru desktop.
3. **Hub — Istoric:** preseturi, KPI-uri, grafic, selectoare și detalii sunt prea dense. Se recomandă trei niveluri: Sumar, Trend și Detalii, cu tabelele încărcate doar la cerere.
4. **Acțiuni flotante:** butonul de filtre și barele sticky trebuie coordonate cu navigarea de jos și cu `safe-area-inset-bottom`. Filtrul ar trebui mutat în antetul paginii sau afișat numai pe ecranele unde schimbă efectiv datele.

### P1 — lizibilitate și operare

1. Standard de minimum 44 px pentru acțiunile frecvente. Cele mai dense suprafețe sunt Istoric Hub (43 controale mici), AI Forecast (26), Analiza agenți (20), Salarii și Folii premium (câte 13).
2. Creșterea etichetelor navigării de jos de la 9 px la 10–11 px, fără pierderea denumirilor accesibile.
3. **Salarii:** carduri de agent/magazin ca prezentare implicită; tabelele complete rămân în Detalii sau Export.
4. **Calculator Target:** un singur pas activ vizibil, progres orizontal compact și acțiunea principală sticky.
5. **Setări:** eliminarea cardului Temă din Importuri, deoarece există deja în Preferințe. În Export, bara Continuă/Înapoi trebuie să împartă corect spațiul cu navigarea de jos.
6. **Folii premium:** sumarul rămâne primul, iar Model/Magazin/Agent devin secțiuni tip accordion.

### P2 — rafinări

1. **AI Forecast:** statusul Model/Sursă/Generat într-o grilă 2 × 2 sau într-un panou compact extensibil.
2. **Grile:** filtrele secundare într-un dropdown sau bottom sheet; stările principale rămân chipuri vizibile.
3. **P&L:** sumar sticky al perioadei și scope-ului pe paginile lungi.
4. **Vizite:** acoperirea rămâne primul indicator; căutarea locală după Team Leader este potrivită pentru mobil.
5. **Manageri:** structura actuală cu overview și detalii expandabile funcționează bine; sunt necesare doar touch target-uri uniforme.

## Rezultate pe suprafețe

| Suprafață | Overflow pagină | Controale sub 44 px | Observație principală |
|---|---:|---:|---|
| Hub — Overview | 0 | 0 | Structură curată; încărcarea inițială trebuie să păstreze skeleton-ul stabil. |
| Hub — AI Forecast | 0 | 26 | Mult context și multe controale într-un singur ecran. |
| Hub — Istoric | 0 | 43 | Cea mai densă suprafață; necesită progressive disclosure. |
| Hub — Vizite | 0 | 3 | Stare goală și ierarhie clare. |
| Focus — Incentive | 0 | 5 | Card lung; mecanismul de calificare poate fi pliat implicit. |
| Focus — Promo | 0 | 5 | Metricile sunt separate corect; navigarea Focus rămâne problema comună. |
| Focus — Concurs | 0 | 5 | Selectorul permanent este corect; trebuie făcut mai ușor de descoperit. |
| Focus — Folii premium | 0 | 13 | Prea multe dimensiuni simultane pentru primul ecran. |
| Focus — Focus | 0 | 6 | Selectorul lunar este clar și ușor de urmărit. |
| Agenți — Overview | 0 | 12 | Ancorele interne ajută; etichetele pot fi mărite. |
| Agenți — Grile | 0 | 10 | Statusul este clar; filtrele ocupă spațiu. |
| Agenți — Analiză | 0 | 20 | Filtre și explicații prea sus; rezultatele trebuie prioritizate. |
| Management — Manageri | 0 | 5 | Overview-ul se adaptează bine și detaliile sunt progresive. |
| Management — Calculator Target | 0 | 9 | Stepper-ul trebuie simplificat pe mobil. |
| Management — Salarii | 0 | 13 | Sumar bun; tabelele trebuie transformate în carduri. |
| Management — P&L | 0 | 4 | Cardurile financiare sunt lizibile; pagina este lungă. |
| Setări — Importuri | 0 | 9 | Confirmarea este clară; Tema este duplicată. |
| Setări — Exporturi | 0 | 9 | Fluxul în patru pași funcționează; zona sticky este aglomerată. |
| Setări — Preferințe | 0 | 7 | Simplu și coerent; locul potrivit pentru Temă. |

## Ordinea propusă pentru implementarea mobilă

1. Shell mobil: taburi Focus, navigare de jos, filtre flotante și safe areas.
2. Hub Istoric și AI Forecast.
3. Analiza agenți și Salarii în carduri responsive.
4. Calculator Target și Export cu acțiuni sticky coordonate.
5. Folii premium, Grile și rafinările P&L/Vizite/Manageri.

## Metodă de verificare

- viewport 390 × 844 px;
- 19 trasee funcționale cu date controlate;
- măsurare automată a overflow-ului documentului și zonei principale;
- inventarierea controalelor interactive sub 44 px;
- inspecție vizuală a ierarhiei, taburilor, filtrelor, barelor sticky și navigării de jos.

Implementarea este acoperită de `e2e/mobile-responsive.spec.ts`, inclusiv filtrul mobil, overflow zero, Hub Istoric, navigarea Focus, Analiza agenți și fluxul Export.
