# Phase 4 Route Familiarity Benchmark

Command: `make benchmark-route-familiarity` (module entry point
`python -B -m scripts.benchmark_route_familiarity`). Fresh run on 2026-10-08,
with 5 measured samples after 1 warmup per measurement, 30 candidate routes,
H3 Resolution 11, Python 3.14, and local PostgreSQL. Times are milliseconds.

## Production Python paths

| Logical history rows | Evaluator p50 / p95 | Rows fetched (personal / community) | Rows scored (personal / community) | Community drivers fetched |
|---:|---:|---:|---:|---:|
| 150 | 96.916 / 115.395 | 51 / 99 | 50 / 99 | 99 |
| 10,000 | 244.823 / 261.663 | 51 / 606 | 50 / 500 | 101 |
| 100,000 | 366.402 / 457.560 | 51 / 606 | 50 / 500 | 101 |

The evaluator calls the production `RouteFamiliarityService` and weighted
similarity implementation. Both the in-memory and PostgreSQL measurements use
the same deterministic Hanoi route signature: 9 resolution-11 cells and about
304 m of route distance. The 150-row fixture contains 51 personal rows and
99 community rows, one for each community driver. Larger fixtures contain 51
personal rows and distribute the remainder across 101 active community drivers.
Queries fetch one personal sentinel and community sentinels (the 101st driver
and sixth route per driver); scoring still uses at most 50 personal and 500
community rows. Therefore `history_truncated` is true for personal history in
all three cases, and for community history in the larger cases. All synthetic
historical rows use the same signature, deliberately exercising overlap work. This is a local
microbenchmark, not an API latency SLA.

| Production operation | p50 / p95 |
|---|---:|
| `create_route_signature` | 0.112 / 0.134 |
| `weighted_ordered_overlap` | 0.016 / 0.028 |

## PostgreSQL repository queries

The benchmark creates disposable database
`route_familiarity_bench_48205120b8774d49a51b1fef6b5924c8` on the configured
PostgreSQL server, applies the route-history schema, seeds synthetic rows, times
the real asyncpg `personal_routes` and `community_routes` methods, captures
`EXPLAIN (ANALYZE, BUFFERS)`, and drops the database. The configured application
database was not written. Disposable database writes were committed so the
repository queries could read the seed rows; the disposable database was then
dropped. JSON lifecycle flags: `disposable_database_created: true`,
`disposable_database_writes_committed: true`,
`disposable_database_dropped: true`, `cleanup_succeeded: true`, and
`application_database_written: false`; `cleanup_errors` is empty. The
PostgreSQL inventory check confirmed zero leftover UUID benchmark databases.

| Rows in disposable DB | Personal query p50 / p95 | Community query p50 / p95 | Lookup pair p50 / p95 | Rows fetched (personal / community) | Rows scored (personal / community) | Community drivers / max fetched per driver |
|---:|---:|---:|---:|---:|---:|---:|
| 150 | 1.108 / 2.036 | 2.241 / 3.995 | 5.419 / 6.200 | 51 / 99 | 50 / 99 | 99 / 1 |
| 10,000 | 1.970 / 2.221 | 54.809 / 64.686 | 48.148 / 66.211 | 51 / 606 | 50 / 500 | 101 / 6 |
| 100,000 | 1.950 / 2.292 | 655.785 / 1892.086 | 635.231 / 1027.366 | 51 / 606 | 50 / 500 | 101 / 6 |

Personal and community query timings measure the actual repository methods
separately, including the repository acquire wrapper, asyncpg roundtrip, and row
decoding. The wrapper borrows an open connection, so real asyncpg pool checkout
and wait time are excluded. Each stage has
its own one warmup and five measured calls using the same seeded rows,
request `as_of`, seven-day lookback, driver, and route cells. The retained
lookup-pair measurement runs both queries sequentially in a separate sample
series; its percentiles are not the sum of the individual percentiles. These
measurements ran on the local active development environment and do not isolate
concurrent host activity.

Community query plan execution was 1.098 ms, 42.700 ms, and 528.378 ms
respectively (Seq Scan for 150/10,000 rows; parallel scan at 100,000 rows).

The actual personal and community truncation flags were true/false for the
150-row case and true/true for both larger cases. The same disposable database
run measured production evaluation backed by the real repository:

| PostgreSQL history rows | Full evaluation, 30 candidates, p50 / p95 |
|---:|---:|
| 150 | 135.049 / 150.027 ms |
| 10,000 | 491.359 / 578.743 ms |
| 100,000 | 1162.858 / 1385.446 ms |

Full plans, including buffers, row counts, and planning/execution time, are in
[phase4-route-familiarity-benchmark.json](phase4-route-familiarity-benchmark.json).
The community query is the measured scaling cost; this task records the result
without an unmeasured query rewrite.

## Database operation evidence

The additive migration and destructive rollback were verified against local
PostgreSQL. Immediately before rollback, the route table existed with 0 rows.
Rollback removed the table, and the final apply recreated it empty. Fresh
command evidence:

```text
Before rollback: to_regclass('realtime.route_familiarity_routes') = true; row count = 0
python -B -m scripts.migrate_route_familiarity --rollback  exit 0
Immediately after rollback: to_regclass('realtime.route_familiarity_routes') IS NOT NULL = false
python -B -m scripts.migrate_route_familiarity             exit 0
After final apply: to_regclass('realtime.route_familiarity_routes') = true; row count = 0
```

These migration operations are separate from the benchmark, which wrote only
to the disposable database. The benchmark CLI maps the Compose-only `ev_db`
hostname to `127.0.0.1` for this host-run command; an explicit
`--database-url` keeps its supplied hostname.

The benchmark requires PostgreSQL `CREATE DATABASE` permission. An unavailable
server, denied create, or unavailable connection to the new disposable database
returns `status: not_measured` with cleanup state. Errors after the database
connection is established are cleaned up and re-raised so broken measurement
queries cannot be reported as an unavailable optional database. Missing
database timings must not be represented as measured.
