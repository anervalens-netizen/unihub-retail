# Design: Composite Partial Index — cartela receipt count

**Date:** 2026-04-15
**Branch:** `perf/cartela-index`
**Status:** Approved

## Problema

Query-ul cartela receipt count din `specials_data.py` rulează la ~39.4ms cu 922 buffer hits
și 872 heap block re-checks. Planul curent face BitmapAnd pe doi indecși separați:
- `idx_sales_transactions_month_cartela (import_month) WHERE is_cartela = false` (partial)
- `idx_sales_date (sale_date)` (full)

Aceasta înseamnă că PostgreSQL combină două bitmap-uri, apoi re-verifică heap blocks
pentru a filtra false positives — costisitor mai ales când luna are multe tranzacții.

## Soluție aleasă: Composite partial index (Opțiunea A)

```sql
CREATE INDEX idx_sales_month_date_cartela
  ON sales_transactions (import_month, sale_date)
  WHERE is_cartela = false;
```

**De ce A și nu B (covering cu INCLUDE bon_nr):**
- A elimină BitmapAnd și heap re-checks → estimat 10–15ms
- B (index-only scan) ar da ~2–5ms dar crește semnificativ dimensiunea indexului
- Upgrade la B rămâne opțiune ulterioară dacă query-ul rămâne hot după A

## Query țintă

```sql
SELECT COUNT(DISTINCT st.bon_nr) AS total_receipts
FROM sales_transactions st
JOIN stores s ON s.site_code = st.site_code
WHERE st.import_month = $1
  AND st.sale_date BETWEEN $2 AND $3
  AND st.item_code = ANY($4::TEXT[])
  [... scoped_clauses ...]
```

Sursa: `backend/services/dashboard/specials_data.py` liniile 98–111.

## Plan de implementare

### 1. Baseline measurement
Rulează `EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)` pe query-ul cartela cu luna
de test `2026-03` (fully loaded, 31819 tx). Capturează exec time + buffer hits.

### 2. Migration file
Creează `backend/db/migrations/NNN_add_cartela_composite_index.sql`:
```sql
CREATE INDEX IF NOT EXISTS idx_sales_month_date_cartela
  ON sales_transactions (import_month, sale_date)
  WHERE is_cartela = false;
```
`IF NOT EXISTS` pentru idempotență (migrația poate rula de mai multe ori în staginguri diferite).

Numărul NNN = primul disponibil după ultimul fișier existent.

### 3. Aplică migrația
Prin mecanismul existent (`apply_pending_migrations()` la boot sau manual via script).

### 4. After measurement
Rulează același EXPLAIN ANALYZE și compară:
- Exec time (target: <15ms)
- Buffer hits (target: <100)
- Plan node: trebuie să dispară BitmapAnd, să apară Index Scan pe noul index

### 5. Documentează rezultatele
Update `docs/perf_index_audit_2026-04.md` cu tabel before/after.

### 6. Verificare import path
Rulează un import test (sau verifică planul pentru INSERT în `sales_transactions`)
să confirme că indexul nou nu degradează write-urile.

## Rollback

```sql
DROP INDEX CONCURRENTLY idx_sales_month_date_cartela;
```

Fără risc de data loss — index-ul nu afectează datele, doar query planning.

## Criterii de succes

- [ ] Exec time cartela query < 15ms (de la 39.4ms)
- [ ] Planul nu mai conține `BitmapAnd`
- [ ] Buffer re-checks = 0 sau neglijabile
- [ ] Testele pytest trec
- [ ] Import path neafectat
