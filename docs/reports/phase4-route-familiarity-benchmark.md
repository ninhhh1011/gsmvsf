# Phase 4 Route Familiarity Benchmark

Command: `make benchmark-route-familiarity` (module entry point
`python -B -m scripts.benchmark_route_familiarity`). The captured run used
5 measured samples after 1 warmup per measurement, 30 candidate routes, Python
3.14, and PostgreSQL from the local Compose environment. Times are milliseconds.

## Production Python paths

| Logical history rows | Bounded evaluator p50 / p95 | Rows compared per candidate (personal / community) |
|---:|---:|---:|
| 150 | 115.108 / 143.056 | 50 / 150 (30 drivers) |
| 10,000 | 616.800 / 765.718 | 50 / 500 (100 drivers) |
| 100,000 | 316.955 / 476.788 | 50 / 500 (100 drivers) |

The evaluator calls the production `RouteFamiliarityService` and weighted
similarity implementation. Its in-memory repository harness returns up to 50
personal routes and up to five routes for each of 100 distinct community
drivers. The 150-row case has 30 drivers and is not truncated; the larger cases
reach the 500-row / 100-driver cap and are marked truncated. All fixture routes
share one cell, deliberately exercising overlap work. This is a local
microbenchmark, not an API latency SLA.

| Production operation | p50 / p95 |
|---|---:|
| `create_route_signature` | 0.095 / 0.106 |
| `weighted_ordered_overlap` | 0.016 / 0.028 |

## PostgreSQL repository queries

The benchmark creates a random `route_familiarity_bench_<uuid>` database on the
configured PostgreSQL server, applies the route-history schema there, seeds
synthetic rows, times the real asyncpg `personal_routes` and
`community_routes` methods together, captures `EXPLAIN (ANALYZE, BUFFERS)`, and
drops the database. The configured application database is not written. The
captured run reported `disposable_database_dropped: true`.

| Rows in disposable DB | Repository lookup pair p50 / p95 | Personal plan | Community plan execution |
|---:|---:|---|---:|
| 150 | 2.643 / 3.582 | Seq Scan | 0.226 ms, Seq Scan |
| 10,000 | 15.670 / 15.971 | B-tree index scan | 17.189 ms, Seq Scan |
| 100,000 | 339.842 / 360.689 | B-tree index scan | 52.597 ms, Seq Scan of 50,000 matching-window rows |

The same disposable database run measured the production evaluator backed by
the real repository and database rows, with 30 one-cell candidate signatures:

| PostgreSQL history rows | Database-backed full evaluation p50 / p95 |
|---:|---:|
| 150 | 36.196 / 58.552 ms |
| 10,000 | 174.466 / 204.294 ms |
| 100,000 | 403.362 / 516.160 ms |

Plans include buffer counts, row counts, planning time, and execution time in
the committed JSON artifact [phase4-route-familiarity-benchmark.json](phase4-route-familiarity-benchmark.json).
The community query is the measured scaling cost; this task
records the result and does not introduce an unmeasured query rewrite.

## Database operation evidence

The additive migration and destructive rollback commands were both run against
the local PostgreSQL service and exited successfully:

```text
python -B -m scripts.migrate_route_familiarity        exit 0
python -B -m scripts.migrate_route_familiarity --rollback  exit 0
```

The local application database currently has the empty familiarity table from
the explicit migration; the parent workflow verified zero rows and zero
benchmark-prefixed records. The benchmark measurements used only disposable
databases and dropped each UUID database after capture.

The CLI maps the application's Compose-only `ev_db` hostname to
`127.0.0.1` for this host-run benchmark; an explicit `--database-url` keeps its
given host. The benchmark requires PostgreSQL `CREATE DATABASE` permission. If server
connection, database creation, or cleanup fails, it reports
`status: not_measured` and includes the reason. Never report missing DB timings
as measured.
