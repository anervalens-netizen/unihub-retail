# Matrice de verificare — remedierea forensic UniHub Retail

**Data:** 7 august 2026
**Bază cod:** `main` la `76e67145d73ac74e6b1ac9fe3a0ab5a3118754d2`
**Branch candidat:** `agent/forensic-remediation-final-20260807`
**Regulă:** nicio afirmație din această matrice nu se bazează pe auditul vechi; fiecare statut este legat de codul și testele candidatului curent.

## Semnificația statutelor

- **DONE — cod:** implementat și verificabil înainte de deploy.
- **SERVER GATE:** codul este pregătit, dar închiderea cere inventar sau probe pe infrastructura reală.
- **PARTIAL — roadmap:** recomandare arhitecturală validă, dar nu este un defect blocant și nu trebuie ascuns într-un release amplu.
- **NOT APPLICABLE:** înlocuit de o decizie mai sigură ori de arhitectura existentă.

## Matrice

| ID plan | Statut | Implementare/dovadă | Ce mai rămâne |
|---|---|---|---|
| P0-01 Refresh Grile frontend–backend | **DONE — cod** | API Pydantic, operație persistentă 202, status endpoint, polling bounded, stări `unknown`/backend indisponibil fără retry orb, erori acționabile în UI și teste backend/frontend | probă live pe un magazin real |
| P0-02 Lună istorică Grile | **DONE — cod** | `completed_days_for_month`, `completion_as_of`, versiune semantică, migrare aditivă și teste pentru lună închisă/curentă/future | probă live pe cel puțin o lună închisă |
| P0-03 Business state vs provider state | **DONE — cod** | ultima proiecție validă rămâne separată de ultima încercare Google; `fresh/error/stale/unknown`, vârstă și ultimul succes/ultimul eșec; prag configurabil și bounded; outcome/latency metrics | validare controlată a unei erori Google în mediu real |
| P0-04 Prometheus multiproces | **DONE — cod / SERVER GATE live** | registry multiprocess pentru web, directoare runtime curate, porturi worker separate, scrape config și teste de topologie | aplicare scrape config și verificarea absenței seriilor duplicate/resetate |
| P1-01 Executor Google | **DONE — cod** | proces copil spawn per request, timeout, output cap, terminate/kill, process group, protocol JSON finit, retry doar pentru read-uri tranzitorii | probă live de timeout/cancel și monitorizare RSS |
| P1-02 Utilizatori Unix separați | **SERVER GATE** | nu s-au schimbat orb unitățile; planul cere inventarul real al fișierelor, secretelor și directoarelor write | agentul de server decide și execută o migrare separată numai după ACL/preflight/rollback; până atunci riscul rămâne acceptat explicit |
| P1-03 Bind și frontieră de rețea | **SERVER GATE** | rutele publice sensibile rămân 404; scriptul de probe verifică localhost/public | inventar Caddy/Docker/LAN/Tailscale/firewall înainte de schimbarea `0.0.0.0`; nu se presupune că `127.0.0.1` este compatibil |
| P1-04 Export XLSX killable | **DONE — cod** | proces per operație, AS/RSS/output caps, timeout dur, hash/size attestation, cleanup/orphan handling, anulare și teste fault-path | export maxim și anulare validate live sub limitele serverului |
| P1-05 Contracte API/DB | **DONE pentru suprafețele afectate; PARTIAL global** | Grile tipizat, date HR `date`, `MonthStr` extins pe suprafețele auditate, OpenAPI generat/drift gate | migrarea tuturor endpointurilor legacy rămâne graduală; nu este blocantă pentru remedierea curentă |
| P2-01 Arhitectură țintă Grile | **PARTIAL — roadmap** | au fost introduse `domain`, `adapters`, `api`, read model versionat și proces provider izolat | serviciul legacy încă orchestrează o parte din flux; mutarea completă în `application/read_model` este o etapă separată cu parity tests |
| P2-02–P2-05 State machine/strangler/parity complet | **PARTIAL — roadmap** | stările provider și operațiile persistente sunt explicite; codul vechi rămâne compatibil | rescrierea completă nu se amestecă cu acest release fără nevoie demonstrată; se face incremental după telemetrie |
| P2 hotspot exports | **DONE pentru obiectivul auditului** | package modular, renderer separat, durable operations, proces izolat | refactor suplimentar numai când un modul depășește ratchet-ul |
| P2 hotspot Dashboard | **DONE pentru obiectivul auditului** | scheduler, orchestration, performance/history/views separate și limite globale testate | `queries.py` rămâne hotspot legacy înghețat; se micșorează incremental |
| P2 hotspot Target Calculator | **DONE pentru obiectivul auditului** | package backend și feature frontend modularizate, reguli/scenarii/profitability/export separate | modulele legacy mari sunt înghețate prin ratchet, nu rescrise inutil |
| P2 hotspot Campaigns | **DONE pentru obiectivul auditului** | API public canonic, publisher Campanii și publisher Concurs separate, fără al doilea pool/service path | refactor ulterior numai pe bază de măsurători |
| P2 worker registry declarativ | **PARTIAL — roadmap** | payloadurile legacy sunt respinse, workers au roluri și cozi separate | `worker.py` rămâne hotspot legacy; registry complet este o schimbare separată cu risc operațional |
| P3-01 AI Forecast actual coverage | **DONE — cod** | cutoff oficial al snapshotului, zile zero/negative păstrate, zile viitoare marcate fără actual, teste | probă live pe o lună cu retur/zero |
| P3-02 P&L Decimal | **DONE — cod** | Decimal/integer-cent până la boundary, teste de reconciliere/rotunjire | comparație live pe o perioadă cunoscută |
| P3-03 Formatare/lint | **DONE pentru gate; PARTIAL pentru formatter global** | EditorConfig, lint cu zero warnings, fără formatare masivă amestecată în PR | adoptarea unui formatter global se face într-un commit exclusiv de stil |
| P3-04 Complexity | **DONE — cod** | prag 600 pentru fișiere noi, ratchet exact pentru hotspoturi și funcții Python/TypeScript, stale allowances și teste | allowance-urile trebuie doar micșorate/eliminate, niciodată mărite fără decizie explicită |
| P3-05 Toolchain | **DONE — cod** | o singură versiune TypeScript, typecheck unic, lockfile actualizat, audit npm/pip | actualizările majore viitoare rămân deliberate |
| P3 release exact-SHA | **DONE — cod/proces** | ADR exact-SHA, CI pe PR intern, artifact numai din run manual `main`, deploy consumă SHA/run/digest exact | merge, artifact și probe live pe infrastructura reală |
| Semnare/branch rules | **PARTIAL — control repository** | artifact cu digest și exact-SHA; PR formal | branch protection și semnarea commiturilor depind de setările GitHub/chei și se activează separat |

## Verdict de release

Candidatul nu necesită rescriere totală. Remedierea curentă poate fi integrată după toate gate-urile automate și server-side. Elementele marcate **PARTIAL — roadmap** nu trebuie prezentate ca defecte ascunse și nu justifică blocarea acestui release; elementele marcate **SERVER GATE** trebuie verificate explicit înainte sau imediat după deploy, conform runbookului.
