# Phase 4 Route Familiarity Benchmark

Command: `make benchmark-route-familiarity` (module entry point
`python -B -m scripts.benchmark_route_familiarity`). Fresh run on 2026-10-07,
with 5 measured samples after 1 warmup per measurement, 30 candidate routes,
Python 3.14, and local PostgreSQL. Times are milliseconds.

## Production Python paths

| Logical history rows | Evaluator p50 / p95 | Rows per candidate (personal / community) | Community drivers |
|---:|---:|---:|---:|
| 150 | 81.088 / 117.831 | 50 / 100 | 100 |
| 10,000 | 291.178 / 545.178 | 50 / 500 | 100 |
| 100,000 | 470.908 / 693.367 | 50 / 500 | 100 |

The evaluator calls the production `RouteFamiliarityService` and weighted
similarity implementation. Fixtures contain exactly 50 personal rows. The
150-row case contains one route for each of 100 community drivers; larger cases
contain at least five routes for each. Thus the large cases reach the 500-row
and 100-driver repository caps. All fixture routes share one cell, deliberately
exercising overlap work. This is a local microbenchmark, not an API latency SLA.

| Production operation | p50 / p95 |
|---|---:|
| `create_route_signature` | 0.102 / 0.138 |
| `weighted_ordered_overlap` | 0.018 / 0.032 |

## PostgreSQL repository queries

The benchmark creates a random `route_familiarity_bench_<uuid>` database on the
configured PostgreSQL server, applies the route-history schema, seeds synthetic
rows, times the real asyncpg `personal_routes` and `community_routes` methods,
captures `EXPLAIN (ANALYZE, BUFFERS)`, and drops the database. The configured
application database is not written. This run reports
`application_database_written: false`,
`disposable_database_writes_committed: true`, and
`disposable_database_dropped: true`. Synthetic seed rows are committed inside
the disposable benchmark database so the repository queries can read them;
that database is dropped after capture. Actual query
results contained 50 personal plus 100 community rows for 150 total, then 50
personal plus 500 community rows for the larger cases. Direct per-driver counts
show maxima of 1, 5, and 5 respectively across 100 distinct drivers.

| Rows in disposable DB | Lookup pair p50 / p95 | Community rows returned / drivers | Community plan execution |
|---:|---:|---:|---:|
| 150 | 3.086 / 4.072 | 100 / 100 | 0.585 ms, Seq Scan |
| 10,000 | 35.296 / 39.892 | 500 / 100 | 52.976 ms, Seq Scan |
| 100,000 | 439.661 / 486.754 | 500 / 100 | 202.988 ms, parallel scan with 99,950 rows examined |

The same disposable database run measured production evaluation backed by the
real repository:

| PostgreSQL history rows | Full evaluation, 30 candidates, p50 / p95 |
|---:|---:|
| 150 | 50.423 / 55.977 ms |
| 10,000 | 278.557 / 313.942 ms |
| 100,000 | 612.488 / 620.534 ms |

Full plans, including buffers, row counts, and planning/execution time, are in
[phase4-route-familiarity-benchmark.json](phase4-route-familiarity-benchmark.json).
The community query is the measured scaling cost; this task records the result
without an unmeasured query rewrite.

## Database operation evidence

The additive migration and destructive rollback commands were run against the
local PostgreSQL service and exited successfully:

```text
python -B -m scripts.migrate_route_familiarity          exit 0
python -B -m scripts.migrate_route_familiarity --rollback  exit 0
```

The local application database retains the empty familiarity table from the
explicit migration. Benchmark measurements used disposable databases only;
the UUID database was dropped after capture.

The CLI maps the application's Compose-only `ev_db` hostname to `127.0.0.1`
for this host-run benchmark; an explicit `--database-url` keeps its given host.
The benchmark requires PostgreSQL `CREATE DATABASE` permission. Failures report
`status: not_measured`, the reason, and whether cleanup/drop succeeded. Missing
database timings must not be represented as measured.
