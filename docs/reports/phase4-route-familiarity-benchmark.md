# Phase 4 Route Familiarity Benchmark

Command: `make benchmark-route-familiarity` (module entry point
`python -B -m scripts.benchmark_route_familiarity`). The captured run used
5 measured samples after 1 warmup per measurement, 30 candidate routes, Python
3.14, and PostgreSQL from the local Compose environment. Times are milliseconds.

## Production Python paths

| Logical history rows | Bounded evaluator p50 / p95 | Rows compared per candidate (personal / community) |
|---:|---:|---:|
| 150 | 101.109 / 121.364 | 50 / 150 |
| 10,000 | 246.319 / 254.211 | 50 / 500 |
| 100,000 | 379.331 / 533.214 | 50 / 500 |

The evaluator calls the production `RouteFamiliarityService` and weighted
similarity implementation. Its in-memory repository harness returns the same
50-personal / 500-community row limits as production. All fixture routes share
one cell, deliberately exercising overlap work. This is a local microbenchmark,
not an API latency SLA.

| Production operation | p50 / p95 |
|---|---:|
| `create_route_signature` | 0.086 / 0.095 |
| `weighted_ordered_overlap` | 0.014 / 0.025 |

## PostgreSQL repository queries

The benchmark creates a random `route_familiarity_bench_<uuid>` database on the
configured PostgreSQL server, applies the route-history schema there, seeds
synthetic rows, times the real asyncpg `personal_routes` and
`community_routes` methods together, captures `EXPLAIN (ANALYZE, BUFFERS)`, and
drops the database. The configured application database is not written. The
captured run reported `disposable_database_dropped: true`.

| Rows in disposable DB | Repository lookup pair p50 / p95 | Personal plan | Community plan execution |
|---:|---:|---|---:|
| 150 | 4.659 / 6.063 | Seq Scan | 0.278 ms, Seq Scan |
| 10,000 | 10.887 / 13.310 | B-tree index scan | 7.771 ms, Seq Scan |
| 100,000 | 55.147 / 122.079 | B-tree index scan | 45.263 ms, Seq Scan of 50,000 matching-window rows |

The same disposable database run measured the production evaluator backed by
the real repository and database rows, with 30 one-cell candidate signatures:

| PostgreSQL history rows | Database-backed full evaluation p50 / p95 |
|---:|---:|
| 150 | 36.557 / 62.185 ms |
| 10,000 | 49.180 / 56.543 ms |
| 100,000 | 205.921 / 222.731 ms |

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

The benchmark requires PostgreSQL `CREATE DATABASE` permission. If server
connection, database creation, or cleanup fails, it reports
`status: not_measured` and includes the reason. Never report missing DB timings
as measured.
