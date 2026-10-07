# Phase 4 Route Familiarity Benchmark

Command: `make benchmark-route-familiarity` (module entry point
`python -B -m scripts.benchmark_route_familiarity`). Fresh run on 2026-10-08,
with 5 measured samples after 1 warmup per measurement, 30 candidate routes,
H3 Resolution 11, Python 3.14, and local PostgreSQL. Times are milliseconds.

## Production Python paths

| Logical history rows | Evaluator p50 / p95 | Rows per candidate (personal / community) | Community drivers |
|---:|---:|---:|---:|
| 150 | 176.366 / 234.860 | 50 / 100 | 100 |
| 10,000 | 639.559 / 788.880 | 50 / 500 | 100 |
| 100,000 | 345.812 / 398.546 | 50 / 500 | 100 |

The evaluator calls the production `RouteFamiliarityService` and weighted
similarity implementation. The 150-row case contains one route for each of 100
community drivers; larger cases contain at least five routes for each. All
fixture routes share one cell, deliberately exercising overlap work. This is a
local microbenchmark, not an API latency SLA.

| Production operation | p50 / p95 |
|---|---:|
| `create_route_signature` | 0.207 / 0.223 |
| `weighted_ordered_overlap` | 0.037 / 0.069 |

## PostgreSQL repository queries

The benchmark creates disposable database
`route_familiarity_bench_558d72ef9c924e9999121184bb776cf2` on the configured
PostgreSQL server, applies the route-history schema, seeds synthetic rows, times
the real asyncpg `personal_routes` and `community_routes` methods, captures
`EXPLAIN (ANALYZE, BUFFERS)`, and drops the database. The configured application
database was not written. Disposable database writes were committed so the
repository queries could read the seed rows; the disposable database was then
dropped. JSON lifecycle flags: `disposable_database_created: true`,
`disposable_database_writes_committed: true`,
`disposable_database_dropped: true`, `cleanup_succeeded: true`, and
`application_database_written: false`; `cleanup_errors` is empty. The
orchestrator independently confirmed zero leftover UUID benchmark databases.

| Rows in disposable DB | Lookup pair p50 / p95 | Community rows returned / drivers | Community plan execution |
|---:|---:|---:|---:|
| 150 | 3.163 / 4.044 | 100 / 100 | 0.701 ms, Seq Scan |
| 10,000 | 35.593 / 38.789 | 500 / 100 | 39.989 ms, Seq Scan |
| 100,000 | 563.218 / 717.936 | 500 / 100 | 181.286 ms, parallel scan; 99,950 joined rows |

Direct per-driver counts show maxima of 1, 5, and 5 respectively across 100
distinct drivers. The same disposable database run measured production
evaluation backed by the real repository:

| PostgreSQL history rows | Full evaluation, 30 candidates, p50 / p95 |
|---:|---:|
| 150 | 50.447 / 89.391 ms |
| 10,000 | 242.334 / 264.078 ms |
| 100,000 | 982.108 / 1288.332 ms |

Full plans, including buffers, row counts, and planning/execution time, are in
[phase4-route-familiarity-benchmark.json](phase4-route-familiarity-benchmark.json).
The community query is the measured scaling cost; this task records the result
without an unmeasured query rewrite.

## Database operation evidence

The additive migration and destructive rollback were verified against local
PostgreSQL. Rollback exited 0; a final apply with `DEBUG=false` also exited 0.
Fresh command evidence:

```text
python -B -m scripts.migrate_route_familiarity --rollback  exit 0
python -B -m scripts.migrate_route_familiarity             exit 0 (DEBUG=false)
SELECT to_regclass('realtime.route_familiarity_routes');  true
SELECT count(*) FROM realtime.route_familiarity_routes;   0
```

These migration operations are separate from the benchmark, which wrote only
to the disposable database. The benchmark CLI maps the Compose-only `ev_db`
hostname to `127.0.0.1` for this host-run command; an explicit
`--database-url` keeps its supplied hostname.

The benchmark requires PostgreSQL `CREATE DATABASE` permission. Failures report
`status: not_measured`, the reason, and whether cleanup/drop succeeded. Missing
database timings must not be represented as measured.
