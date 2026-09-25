# GSMVSF ROUND 02 — independent review of cfbe350

## Verdict and scope

Read `AUDIT_ROUND02_CFBE350_VI.md`, then `SOURCE_EVIDENCE.md` and `results/SUMMARY.json`.

**Verdict: ROUND_02_NOT_COMPLETE**, based on counterexamples in the isolated harness. This is **not** a two-OS-process, live Redis/GraphHopper/PostGIS test. The 385-test local run was not reproduced here.

The supplied `input/` export was read-only. All 39 exported source files match their supplied hashes before and after this audit. The export itself declares no raw live test evidence available.

## Layout

- `input/`: user's new cfbe350 source export, unchanged.
- `harness/audit_support.py`: imports unmodified source modules; explicit import shims and boundary fixtures.
- `harness/test_correctness.py`: 16 prior-counterexample/positive-regression checks adapted to the current source.
- `harness/test_new_protocol.py`: 12 checks focusing on CAS composition, final-write failure, generation, UTC, dedup.
- `harness/test_original_integration_in_harness.py`: runs the six original test bodies with network/Redis fixtures and an intentionally unavailable matching engine. This is assertion-coverage evidence, not live integration.
- `results/`: raw outputs, JUnit XML, individual observations, summaries, integrity and source comparison.

## Environment and boundary

Used Python 3.13.5, FastAPI, HTTPX, Pydantic, pytest, pytest-asyncio, pydantic-settings and installed Linux liblua5.4. Exact package versions are in `results/SUMMARY.json`.

Redis-py/psycopg2 imports and the map-matching provider are shimmed. Production handler/manager/repository/state/trigger source is not replaced with reimplemented business logic. Production Lua strings execute in Lua 5.4 with Python JSON/KV callbacks. Top-level Lua array replies are converted to Python lists. Redis cjson/TTL/network/replication behavior is not fully modeled. No Redis server is present.

For race tests, fixtures only control when a manager read or matching call returns, not the application mutation logic. The manager-stale-payload test also reproduces data loss without overlapping network timing.

The source imports are taken from `input/snapshot`, not an installed gsmvsf package. Do not copy the shims or fake KV client into production.

## Run in a compatible audit environment

From this directory:

```bash
PYTHONDONTWRITEBYTECODE=1 python harness/run_audit.py \
  harness/test_correctness.py harness/test_new_protocol.py \
  -q --tb=short --junitxml=results/rerun_independent.xml
```

Expected on the supplied **unfixed** snapshot: 17 pass / 11 fail. Failures are correctness assertions, deliberately not inverted into green “bug exists” tests. HTTP 200 with a stale/rejected business status does not count as accepted in the lost-update test.

To execute the three original unit test files:

```bash
PYTHONDONTWRITEBYTECODE=1 python harness/run_audit.py \
  input/snapshot/backend/tests/test_driver_state_shared.py \
  input/snapshot/backend/tests/test_driver_state_manager.py \
  input/snapshot/backend/tests/test_driver_state_repository.py \
  -q --tb=short
```

Observed: 26 pass. The runner intentionally uses `--noconftest` because the export does not include the complete application and its dependencies. These are not all repository tests.

Assertion-coverage experiment:

```bash
PYTHONDONTWRITEBYTECODE=1 python harness/run_audit.py \
  harness/test_original_integration_in_harness.py -q --tb=short
```

Observed: all six bodies pass even when matching always raises ENGINE_UNAVAILABLE. Original fixture startup/network checks are intentionally not exercised by this experiment.

## For the implementation agent on Windows

Do not spend time installing Lua 5.4 merely to mirror this sandbox. Port the event schedules/assertions to your existing test tooling and real Redis. Do not modify the bundled snapshot to pretend the original evidence passed. Implement fixes in the actual repository and save fresh evidence in a new run directory.

A valid fix should preserve the newly passing positive cases (CAS primitive, ordinary dedup/reset/persistence and EVAL failure) while closing the end-to-end manager/handler gaps.
