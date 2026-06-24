# Design: JSON Structured Logging

**Date:** 2026-04-15
**Branch:** `obs/json-logging`
**Status:** Approved

## Problema

Log-urile curente sunt text plain (format uvicorn default). Pe server de producție
unde log-urile sunt colectate de journald / Loki, JSON structurat permite filtrare
și indexare directă (`jq`, `journalctl -o json`, Grafana Loki label parsing).

## Soluție: JSONFormatter pe stdlib logging

Zero dependențe noi. Se integrează transparent cu uvicorn/FastAPI care folosesc
stdlib `logging`. Structlog ar adăuga valoare doar dacă am propaga contexte
cross-request (request-id, user-id) — out of scope acum.

## Implementare

### `backend/logging_config.py` (fișier nou)

```python
class JSONFormatter(logging.Formatter):
    def format(self, record) -> str:
        # câmpuri standard + orice extra kwargs
        return json.dumps({
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            **{k: v for k, v in record.__dict__.items() if k not in _SKIP_FIELDS},
        })

def setup_logging(fmt: str = "text") -> None:
    # fmt="json" → JSONFormatter pe root + uvicorn loggers
    # fmt="text" (default) → comportament standard, nu schimbă nimic
```

### Activare

Controlat de `LOG_FORMAT` env var:
- `LOG_FORMAT=json` → JSON (producție)
- nesetat / orice altceva → text plain (dev local, nu se schimbă nimic)

### `backend/main.py`

Apel `setup_logging()` la top-level, înainte de crearea app FastAPI.

## Criterii de succes

- [ ] `LOG_FORMAT=json` → fiecare linie de log e JSON valid parsabil cu `jq`
- [ ] `LOG_FORMAT` nesetat → comportament identic cu azi (text plain)
- [ ] uvicorn access logs (`INFO: GET /health 200`) apar și ele în JSON când activ
- [ ] pytest trece
