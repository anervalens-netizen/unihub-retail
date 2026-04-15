---
type: "query"
date: "2026-04-15T05:42:49.833688+00:00"
question: "Why does get_pool() connect so many communities?"
contributor: "graphify"
source_nodes: ["get_pool", "init_db_pool", "ensure_schema_current"]
---

# Q: Why does get_pool() connect so many communities?

## Answer

get_pool() is the asyncpg connection pool singleton at backend/db/connection.py:L74. It has 3 EXTRACTED edges (direct callers init_db_pool and ensure_schema_current) and 76 INFERRED edges spanning 10 of 69 communities. The breadth is not accidental coupling — it is infrastructure: every endpoint, test, and script that touches PostgreSQL goes through the shared pool via 'async with get_pool().acquire() as conn'. Betweenness 0.189 reflects that any path between a feature module and database state passes through it. One suspect INFERRED edge: login() in src/api/auth.ts cannot directly call the Python get_pool(); the model confused HTTP chain with direct function call — should be AMBIGUOUS.

## Source Nodes

- get_pool
- init_db_pool
- ensure_schema_current