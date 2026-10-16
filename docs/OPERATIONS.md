# Operations Guide

## Local deployment

Run the stack on one Docker host:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f
```

After recreating API containers, wait for their readiness checks and run `docker compose exec frontend nginx -s reload`. The current upstream configuration resolves container addresses when Nginx loads; an existing frontend container can otherwise retain old API addresses. This local rollout does not guarantee uninterrupted requests.

All published ports bind to `127.0.0.1`: PostgreSQL 5432, Redis 6379, GraphHopper 8989, API ports 8000, 8002, 8003 and 8004, and frontend 3000. The four single-worker API containers share one PostgreSQL, Redis, and GraphHopper instance. Only `api_1` runs the operational simulator. Nginx uses all four replicas; the route budget is four per replica, sixteen in aggregate. The data plane is single-node; this setup does not provide host-level failover.

## Checks

```bash
make lint
make test
make validate-data
```

The metrics endpoint is `/metrics`. Readiness is `/readiness`. Runtime dependencies are PostgreSQL, Redis for shared GPS state, and GraphHopper; dependency failures are reported explicitly. Redis caching of PostgreSQL snapshots is optional, but shared GPS must not fall back to replica-local memory.

## Maintenance

Use the repository's migration and dataset validation scripts. Dataset V1 is canonical and read-only. Keep generated reports under `runtime/`, never in `dataset_v1/`.

### Historical route familiarity v2 baseline

The section below describes the original cell-only/30-second baseline and its microbenchmark. Current geometric 80/10/10 ranking is defined by ADR-025/026 and [ARCHITECTURE.md](ARCHITECTURE.md); it uses both personal and community evidence. Historical benchmark outputs are not capacity evidence for the current runtime.

Route history is opt-in and `ENABLE_ROUTE_FAMILIARITY` defaults to `false`. Enabling it requires a `ROUTE_FAMILIARITY_IDENTITY_SECRET` of at least 32 bytes and an authenticated trusted gateway that signs the exact driver ID in `X-Driver-Identity-Signature`. The gateway signature is required on `/recommend`; the trusted producer token protects route ingestion. Do not expose either secret to the browser. The configured producer and identity secrets must be shared by the API containers on this single host.

Apply the additive schema explicitly after reviewing the target database:

```bash
make migrate-route-familiarity
```

Rollback is destructive and drops all route familiarity history:

```bash
make rollback-route-familiarity
```

No schema migration runs at application startup. Route history stores protected driver/trip identifiers, completion time, optional trip start and observed geometry, route distance, ordered H3 Resolution 11 index cells, and per-cell distance weights. There is no history read API. Geometry is private history evidence and shares its retention/erasure policy; disable the feature before a rollback. Personal lookup is capped at 50 recent trips. Community lookup examines at most 100 recently active drivers and five matching trips per driver (500 total); community details are hidden below five distinct supporting drivers. A seven-day event-time lookback is the default. Missing history adds no penalty; familiarity can add at most 30 seconds to final ranking cost and does not change eligibility or physical ETA.

The community caps apply globally to the union of candidate route cells for one recommendation batch. If a cap binds, one candidate's community explanation may depend on other candidates in that batch; this evidence remains explanation-only.

Run the local microbenchmark with `make benchmark-route-familiarity`. It reports warmups, sample count and p50/p95 for signature creation, similarity, and the actual bounded evaluator at 150, 10,000 and 100,000 logical history rows with 30 candidate routes. Both in-memory and database paths use the same deterministic route signature (9 H3 Resolution 11 cells, about 304 m). Repository lookups fetch bounded sentinels (51 personal rows and at most 606 community rows) to distinguish exact-full histories from truncation; scoring still uses at most 50/500 rows. If `DATABASE_URL` points to an available PostgreSQL server with `CREATE DATABASE` permission, the command creates a UUID-named disposable database, installs the route schema, runs actual asyncpg repository queries against 150, 10,000 and 100,000 deterministic synthetic rows, emits per-size `EXPLAIN (ANALYZE, BUFFERS)` plans, then drops that database. It never writes to the configured application database. An unavailable server, denied create, or unavailable connection to the disposable database is reported as `not_measured`; failures after a successful database connection are re-raised after cleanup.
# Offline comparison and geometric weighting migration (2026-10-10)

Apply `python -B scripts/migrate_route_familiarity.py` explicitly before enabling geometric familiarity. It adds nullable `geometry` and `started_at` columns and bounds without dropping existing rows; running it twice is safe. The database configured for the application is changed only by this explicit operator action. Schema changes are not applied during application startup.

Existing cell-only rows are preserved and cannot supply directional geometry evidence. A trusted producer can re-ingest the original polyline with optional aware `started_at`; if the immutable trip signature agrees, only missing evidence is filled. Known geometry/start conflicts remain HTTP 409. Do not use `--rollback` as a migration rollback: it still drops the history table. A nondestructive rollback keeps the additive columns/data and disables the feature.

`ENABLE_ROUTE_FAMILIARITY=false` remains the default. Enabling requires the ingestion token and trusted exact-driver identity signing gateway; never put those secrets in browser JS. All API replicas must use the migrated database and identical identity configuration. The new comparison endpoint accesses protected history only when a driver is requested and authenticated; otherwise it performs geometric comparison only.

The Driver banner evaluates the whole observed trip offline. It does not supply future GPS to realtime recommendation or energy stepping. Energy stepping uses accepted observed timestamps; trip/model/SOC changes invalidate pending updates. HUD power is an estimate, and unsupported physical models display unavailable. Route similarity thresholds and energy coefficients require calibration before claiming real-world accuracy.

## H3 departure statistics (2026-10-14)

Run `python -B -m scripts.migrate_route_familiarity --namespace realtime` (or
`--namespace synthetic`) explicitly against the intended database. This adds
`route_deviation_trips` and its completion index without editing old history.
Startup does not migrate. `--rollback` is destructive and now drops both history
and paired evidence in the selected namespace. Disable the feature for a
nondestructive rollback.

Trusted producers submit paired evidence to
`POST /api/v1/internal/route-deviations/trips` with the existing ingestion token;
never expose that token to the browser. `GET /api/v1/routing/departure-heatmap`
accepts resolution 5–10 and optional aware `as_of_iso`, fixes lookback to seven days,
and returns aggregate evidence only. Missing schema/dependencies/work budget is an
explicit outage. Existing `ENABLE_ROUTE_FAMILIARITY` and server history namespace
control the optional feature; no automatic synthetic fallback or legacy backfill.

`python -B -m scripts.verify_h3_departures` audits actual paired/unpaired history
counts and verifies independent fake cases in a UUID-named disposable database.
Supply the local PostgreSQL URL explicitly when needed. `--seed-demo` additionally
installs 30 paired fake trips solely in `synthetic`, with stable batch identifiers;
it never writes realtime history or Dataset V1. Evaluation truth stays offline.
The separate branch review API is `http://127.0.0.1:8005/demo`; existing production
API containers are left in place.

### Road-based synthetic review batch

`python -B -m scripts.seed_guided_hanoi --as-of 2026-10-14T03:00:00Z`
uses live GraphHopper and writes only synthetic paired evidence. The default
12 corridors / five drivers / six maneuvers create 360 trips. Generated manifest,
offline truth and report are under `runtime/h3-road-journeys-20261014/`; manifest
reuse makes retries stable. Do not delete old history or edit Dataset V1.

The seven-day overlay also displays legacy histories as gray approximate footprints,
without inferred departure percentages. User map pan reuses all-region cells; change
resolution/time or reload to fetch refreshed evidence. Controls passing does not
establish perfect synthetic event-count agreement or real driver behavior.

### Trip evidence and coverage review

Open `/demo/static/journeys.html` from the branch API for synthetic examples,
interval inspection and the fixed offline coverage report. Production/private
namespaces never supply examples.

Run `python -B -m scripts.audit_guided_coverage --as-of 2026-10-14T07:00:00Z` to
write `runtime/h3-coverage/coverage-summary.json` and measured `targets.json`.
Canonical CSV is read-only and PostgreSQL audit tables are temporary. Reports
measure candidate reference proximity, not verified motorcar permissions.
`--exclude-batch d1a492ab9705` reproduces the pre-extension cohort without deleting
stored trips at the same event time.

The gap seed used `python -B -m scripts.seed_guided_hanoi --as-of 2026-10-14T07:00:00Z
--seed 2026101402 --targets runtime/h3-coverage-before/targets.json
--output runtime/h3-gap-journeys-20261014`. Retry with the same seed/time/output;
omit `--targets` to use frozen manifest hubs. Different provided targets fail
rather than mutate the batch. Seed writes remain synthetic only.

`python -B -m scripts.verify_guided_evidence --as-of 2026-10-14T07:00:00Z` runs
held-out geometric/live GraphHopper controls without storing evaluation trips.
`node scripts/verify_guided_browser.mjs` verifies desktop/mobile inspector behavior;
external tiles are intentionally aborted. Tile network availability is separate
from rendering/API success.

### Local road coverage and stress cohorts (2026-10-15)

Review the unmerged branch at `http://127.0.0.1:8005/demo`: enable H3 and select
`Bộ phủ đường` or `Bộ kiểm thử lệch`. The inspector remains at
`/demo/static/journeys.html`. Existing container UI on port 3000 is not this review
process. The local API must use the synthetic namespace and explicit public sample
capability; production history is not exposed. External OSM tile failures remain
independent of H3/API behavior.

Frozen batch `6c688ea447a7` uses event time `2026-10-15T04:30:00Z`. Retry without
rerouting or duplicating IDs:

```powershell
python -B -m scripts.seed_local_guided --targets runtime/h3-local-20261015/seed/source-targets.json --as-of 2026-10-15T04:30:00Z
```

The manifest rejects a different source/seed/time. Do not replace it to force a
retry. New audit targets change after ingestion, so use the frozen source above.
Reproduce baseline without deleting records and compare the same method/time:

```powershell
python -B -m scripts.audit_guided_coverage --as-of 2026-10-15T04:30:00Z --exclude-batch 6c688ea447a7 --output runtime/h3-local-20261015/before
python -B -m scripts.audit_guided_coverage --as-of 2026-10-15T04:30:00Z
```

Seven-day evidence expires normally. This seed is bounded to the current imported
graph, not all Hanoi. See the [measured report](reports/h3-local-coverage-2026-10-15.md).
