# Implementare verificată — remedierea forensic UniHub Retail

**Bază:** `main` la `76e67145d73ac74e6b1ac9fe3a0ab5a3118754d2`
**Branch:** `agent/forensic-remediation-final-20260807`
**Contract păstrat:** importul lunar de vânzări rămâne snapshot autoritativ complet și îl înlocuiește atomic pe cel anterior.

## Ce este implementat

### Grile

- contracte Pydantic și TypeScript explicite;
- refresh per magazin ca operație persistentă asincronă;
- polling bounded și fail-closed pentru backend indisponibil, timeout sau stare necunoscută;
- calcul determinist pentru luna solicitată;
- separarea proiecției business de sănătatea providerului;
- prag provider stale configurabil prin `GRILE_PROVIDER_STALE_AFTER_SECONDS` (5 minute–7 zile);
- generații/fencing pentru observații și erori;
- Google I/O într-un proces copil killable;
- outcome și phase latency metrics cu cardinalitate fixă;
- migrarea `062_grile_v2_read_contract.sql`.

### Exporturi

- rendererele complexe rulează per operație în proces copil;
- timeout, AS/RSS/output caps, terminate/kill și cleanup;
- artifactul este adoptat numai după path containment, size și SHA-256;
- operațiile durabile și anularea rămân autoritative în DB.

### Observabilitate

- Prometheus multiprocess pentru cei doi workeri web;
- Prometheus rămâne în Docker bridge, iar deployul detectează și validează
  gateway-ul/subnetul real;
- endpointuri separate operations/import legate exclusiv de acel gateway,
  niciodată `0.0.0.0` sau loopback;
- `/metrics` web acceptă numai peerul direct din subnetul Prometheus și răspunde
  404 pentru loopback/LAN/Tailscale/public, fără încredere în forwarded headers;
- directoare runtime gestionate de systemd;
- unități systemd versionate pe SHA și rollback împreună cu env/fragment;
- `scrape_config_files`, `promtool` și trei targeturi UP ca porți de deploy.

### Date și contracte

- AI Forecast păstrează zilele cu zero/retur și folosește cutofful snapshotului;
- P&L păstrează banii în Decimal/integer cents;
- cererile HR folosesc tipuri `date` și constrângeri DB;
- OpenAPI este regenerat și verificat contra driftului;
- migrarea `063_leave_request_date_contract.sql`.

### Mentenabilitate și livrare

- publisherul Concurs este separat de publisherul Campanii;
- ratchet de 600 linii pentru fișiere noi;
- ratchet exact pentru funcții Python și TypeScript, cu stale allowances;
- o singură versiune TypeScript și un singur typecheck;
- lint fail-on-warning și EditorConfig;
- CI exact pe PR intern;
- artefact de release numai din run manual pe `main`;
- deploy exclusiv din run ID + SHA + digest exact.

## Ce nu este mascat drept „terminat”

Trei elemente cer decizie sau infrastructură reală și sunt tratate în
`forensic-remediation-verification-matrix-2026-08-07.md`:

1. separarea utilizatorilor Unix și ACL-urilor;
2. schimbarea bindului principal `:9898` sau firewall după inventarul
   Caddy/Docker/LAN/Tailscale; acest release schimbă numai boundary-ul metrics și
   nu modifică firewallul;
3. rescrierea completă P2/strangler Grile și registry-ul workerilor.

Acestea nu sunt omise; sunt separate intenționat de release pentru a evita o
migrare operațională oarbă sau o rescriere fără parity evidence.

## Gate-uri înainte de merge

- manifest migrări și upgrade/fresh DB;
- OpenAPI drift;
- mypy, dependency/security/secret scans;
- suita backend izolată;
- typecheck, lint, unit, build, RUM și bundle budget;
- Playwright responsive/accessibility;
- ratchet Python/TypeScript;
- review exact-SHA și diff fără workflow temporar/bootstrap.

## Gate-uri pe server

- backup și rollback/roll-forward handle;
- inventar identities/bind/firewall;
- migrări `062` și `063`;
- web + operations + import metrics;
- Grile curent/istoric/refresh/error;
- export normal/cancel/limit;
- AI Forecast zero/negativ;
- P&L reconciliat;
- HR interval inversat => 422;
- public `/metrics`, `/docs`, `/redoc`, `/openapi.json` => 404.
