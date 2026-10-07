# Operations Guide

## Local deployment

Run the stack on one Docker host:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f
```

All published ports bind to `127.0.0.1`: PostgreSQL 5432, Redis 6379, GraphHopper 8989, API ports 8000 and 8002, and frontend 3000. The two API containers share one PostgreSQL, Redis, and GraphHopper instance. The data plane is single-node; this setup does not provide host-level failover.

## Checks

```bash
make lint
make test
make validate-data
```

The metrics endpoint is `/metrics`. Readiness is `/readiness`. Runtime dependencies are PostgreSQL, optional Redis cache, and GraphHopper; dependency failures are reported explicitly.

## Maintenance

Use the repository's migration and dataset validation scripts. Dataset V1 is canonical and read-only. Keep generated reports under `runtime/`, never in `dataset_v1/`.

### Route familiarity v2

Route history is opt-in and `ENABLE_ROUTE_FAMILIARITY` defaults to `false`. Enabling it requires a `ROUTE_FAMILIARITY_IDENTITY_SECRET` of at least 32 bytes and an authenticated trusted gateway that signs the exact driver ID in `X-Driver-Identity-Signature`. The gateway signature is required on `/recommend`; the trusted producer token protects route ingestion. Do not expose either secret to the browser. The configured producer and identity secrets must be shared by the API containers on this single host.

Apply the additive schema explicitly after reviewing the target database:

```bash
make migrate-route-familiarity
```

Rollback is destructive and drops all route familiarity history:

```bash
make rollback-route-familiarity
```

No schema migration runs at application startup. Route history stores only protected driver/trip identifiers, completion time, route distance, ordered H3 Resolution 11 cells, and per-cell distance weights. There is no history read API. Retention/erasure is an operational responsibility; disable the feature before a rollback. Personal lookup is capped at 50 recent trips. Community lookup examines at most 100 recently active drivers and five matching trips per driver (500 total); community details are hidden below five distinct supporting drivers. A seven-day event-time lookback is the default. Missing history adds no penalty; familiarity can add at most 30 seconds to final ranking cost and does not change eligibility or physical ETA.

The community caps apply globally to the union of candidate route cells for one recommendation batch. If a cap binds, one candidate's community explanation may depend on other candidates in that batch; this evidence remains explanation-only.

Run the local microbenchmark with `make benchmark-route-familiarity`. It reports warmups, sample count and p50/p95 for signature creation, similarity, and the actual bounded evaluator at 150, 10,000 and 100,000 logical history rows with 30 candidate routes. Both in-memory and database paths use the same deterministic route signature (9 H3 Resolution 11 cells, about 304 m). Repository lookups fetch bounded sentinels (51 personal rows and at most 606 community rows) to distinguish exact-full histories from truncation; scoring still uses at most 50/500 rows. If `DATABASE_URL` points to an available PostgreSQL server with `CREATE DATABASE` permission, the command creates a UUID-named disposable database, installs the route schema, runs actual asyncpg repository queries against 150, 10,000 and 100,000 deterministic synthetic rows, emits per-size `EXPLAIN (ANALYZE, BUFFERS)` plans, then drops that database. It never writes to the configured application database. An unavailable server, denied create, or unavailable connection to the disposable database is reported as `not_measured`; failures after a successful database connection are re-raised after cleanup.
