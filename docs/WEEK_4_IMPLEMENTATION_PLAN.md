# Week 4 Ranking and Recommendation Implementation Plan

**Goal:** Rank eligible Week 3 station/service alternatives using persisted,
timestamped snapshots and return an explainable recommendation.
**Execution:** Continuous task execution with test-first checks, relevant
regression, diff review, fixes and retests before each task/phase exit. Use the
executing-plans workflow and bounded independent review where useful. No approval
pause after this plan; the user approved automatic implementation.
**Stack:** Existing FastAPI, PostgreSQL/PostGIS and GraphHopper; asyncpg repository
and Redis KV client. Work stays in `E:/build6week`.

## Phase 0 — Audited baseline (PASS)

- Root `E:/build6week`, initial branch `graphhopper-full-migration-20260921`,
  commit `d8574c0`; clean tree. Migration and Week 3 completion tags both point here.
- Required project, acceptance, data, architecture, decision, routing, Week 1–3,
  migration and Dataset documents inspected together with actual models,
  generators, validator, Compose and tests. Historical engine evidence is not
  current acceptance evidence.
- Baseline executed: `python -m pytest backend/tests -q`: 239 passed.
- Canonical validator through `python -B scripts/validate_frozen_dataset.py`:
  152 PASS / 0 FAIL, 22/22 scenarios. Direct invocation writes Dataset reports,
  so ADR-012's wrapper is required to preserve the immutable tree.
- `python -B scripts/verify_graphhopper.py` passed actual car/fixed-bike/swap/BOTH,
  via-leg, missing-destination and route API checks. DB/API/GraphHopper healthy.
- Hash manifest covers all 63 tracked Dataset files plus six pre-existing ignored
  bytecode files. All 69 unchanged after audit checks.
- Week 3 `CandidateSearchResult` contains composite identities, eligibility,
  operational state, base station/onward/via/direct/detour route metrics. It has
  no candidate-search version or traffic traversal mapping. Optional reduction
  is input-order based; Week 4 orchestration must request the complete set.
- `StationCatalog` loads static CSVs and exact ten-minute operational buckets;
  missing data currently defaults to nominal OPEN/zero queue. Week 4 must inject
  a pinned persisted-state catalog into the existing search, avoiding these
  defaults without changing legacy Week 3 endpoints.
- Dataset: 3,270 station rows, 3,270 queue rows (109 ten-minute timestamps),
  883,597 traffic rows (37 half-hour timestamps). OPEN/OFFLINE state, separate
  charging/swap slots, inventory, service time, queue and estimated wait exist.
  Traffic has `delay_factor`, free-flow/current speed and traffic level.
- Actual ranking: 3,439 rows / 553 groups (75 single, 478 multiple); 848
  recommendation labels (553 positive, 295 empty). Reference pool is nearest
  eight eligible alternatives; runtime will rank all eligible alternatives.
- Reference formula includes both travel legs, queue/service and detour/capacity
  terms. Runtime service-completion objective intentionally differs. Labels are
  opened only after inference in evaluation; no reference features enter runtime.
- Existing DB access uses psycopg2 for PostGIS; `app/db` has no repository or ORM
  setup. asyncpg/SQLAlchemy already declared, Redis installed locally but not
  declared or deployed. Reuse asyncpg, add Redis dependency/Compose service.
- User resolved operational invalidation: HTTP 409 `CANDIDATE_STATE_CHANGED`;
  ranking never filters/re-evaluates; orchestration can retry search once.

Phase 0 exit: correct repository, safe tree, official scope, Dataset semantics,
Week 3 handoff and infrastructure understood; no unrelated conflicts.

## Design and phase ordering

Implement contracts, persistence, resolution, ranking, orchestration/API, then
evaluation and real-backend acceptance. Grouping closely coupled concerns avoids
shipping APIs before their state/consistency behavior exists. All original scope
areas remain covered below; no streaming or future-week feature is added.

```text
Internal snapshot ingestion -> PostgreSQL immutable history
                              -> Redis latest payload (best effort)
Request-time resolver -> DB authoritative snapshot IDs -> Redis / DB payloads
Pinned station context -> existing Week 3 search -> persisted search evidence
Current pinned context + eligible search result -> invalidation check
    -> ranking features -> total completion policy -> recommendation
Synchronous orchestration retries search once on candidate-state conflict
```

Shared rules: aware UTC timestamps; latest valid snapshot <= request time;
append-only history; no future state leakage. Station and queue remain distinct
snapshot kinds because their updates may arrive independently. One snapshot table
holds validated JSON payloads with an entity/time index and source/created_at/ID.
Database ID pinning is one statement for all entities, then immutable payloads
are fetched from cache or DB. Missing station state fails explicitly. Missing
traffic uses base duration; missing queue uses labelled configurable assumption.

## Phase 1 — Domain contracts

### W4-01 — Snapshot and recommendation contracts
- **OBJECTIVE:** Define strict immutable snapshot models, provenance, ranking
  policy/features/results, and structured candidate-state conflict.
- **WHY:** Make units, identity, missing state and explanations explicit.
- **INPUTS:** Audited CSV fields, Week 2/3 models, ADR-013.
- **OUTPUTS:** Snapshot and ranking models plus validation tests.
- **DEPENDENCIES:** Phase 0.
- **FILES EXPECTED TO CHANGE:** `backend/app/services/snapshots/models.py`,
  `backend/app/services/ranking/models.py`, package initializers,
  `backend/tests/test_week4_models.py`.
- **IMPLEMENTATION APPROACH:** Reuse `ServiceType`, `EnergyServiceRequest`,
  `CandidateSearchResult`; validate finite nonnegative values, aware timestamps,
  enum state and payload kinds. Preserve base/adjusted travel, observed/assumed
  queue, service duration, distinct three ETA fields and provenance. Candidate
  evidence includes search ID, time, snapshot IDs and static catalog fingerprint.
- **TEST PLAN:** Reject negative/nonfinite values, naive timestamps, extra fields;
  serialize both service alternatives and conflict payload. Run targeted pytest.
- **SELF-REVIEW CHECKLIST:** No labels, engine HTTP fields or duplicate Week 3
  models; all units explicit; immutable snapshots.
- **EXIT GATE:** Targeted tests and existing model regression pass; diff reviewed.
- **RISKS:** Naive legacy dates; normalize only inside explicit integration adapter.
- **FAILURE / FALLBACK BEHAVIOR:** Malformed API input is 422; no silent coercion
  to nominal station state.

## Phase 2 — Persistence and ingestion

### W4-02 — Immutable PostgreSQL snapshot repository
- **OBJECTIVE:** Persist snapshots/search evidence and resolve historical IDs.
- **WHY:** CSV lookup cannot support concurrent ingestion and authoritative history.
- **INPUTS:** Validated models and existing road-segment/catalog identifiers.
- **OUTPUTS:** Idempotent schema setup and asyncpg repository.
- **DEPENDENCIES:** W4-01.
- **FILES EXPECTED TO CHANGE:** `backend/app/services/snapshots/repository.py`,
  `backend/app/services/snapshots/schema.sql`, `backend/tests/test_week4_database.py`.
- **IMPLEMENTATION APPROACH:** Unique `(kind,entity_id,timestamp)`, UUID snapshot
  identity, JSONB payload, source/schema version/created_at. Existing-key exact
  retry returns original; different content/source conflicts. Parameterized SQL,
  transaction-scoped writes, one indexed descending time lookup per entity.
  Persist server-issued candidate results so clients cannot forge eligibility.
- **TEST PLAN:** Real Postgres tests for duplicate/concurrent retries, conflicting
  retries, older timestamps, historical lookup, unknown entities and query plans.
- **SELF-REVIEW CHECKLIST:** No duplicate ORM layer, unbounded transaction, unsafe
  SQL interpolation or redundant indexes; schema idempotent.
- **EXIT GATE:** Real DB tests and model regression pass; SQL/diff reviewed.
- **RISKS:** Concurrent insert race; use database uniqueness and compare persisted
  row after `ON CONFLICT DO NOTHING`.
- **FAILURE / FALLBACK BEHAVIOR:** DB unavailable => explicit dependency failure;
  conflicting immutable identity => 409; unknown identifier => 422.

### W4-03 — Validated state ingestion and source import
- **OBJECTIVE:** Accept separate traffic/station/queue updates and import source CSVs.
- **WHY:** Demonstrate dynamic state without streaming or Dataset mutation.
- **INPUTS:** Canonical sources only; internal API payloads.
- **OUTPUTS:** Ingestion service and repeatable Dataset loader.
- **DEPENDENCIES:** W4-02.
- **FILES EXPECTED TO CHANGE:** `backend/app/services/snapshots/ingestion.py`,
  `scripts/load_week4_snapshots.py`, ingestion tests.
- **IMPLEMENTATION APPROACH:** Validate station/segment existence, slot bounds,
  supported services, numeric/enum/time constraints. Load source rows in bounded
  batches, preserve timestamps and service semantics; never execute generators.
- **TEST PLAN:** Malformed/unknown/overcapacity rejection; exact retry and changed
  payload conflict; loader count and rerun idempotency against real DB.
- **SELF-REVIEW CHECKLIST:** No labels or writes under Dataset; no fake zero waits;
  queue and station histories independent; source and timestamp retained.
- **EXIT GATE:** Ingestion/DB tests pass; source import exact counts verified.
- **RISKS:** Large traffic table; use bounded batch inserts rather than per-row API.
- **FAILURE / FALLBACK BEHAVIOR:** Reject invalid batch transaction; retain prior
  committed history; no snapshot replacement.

## Phase 3 — Resolution, cache and freshness

### W4-04 — Consistent request-time snapshot provider
- **OBJECTIVE:** Resolve latest <= request time with Redis hit/miss/down support.
- **WHY:** Prevent future-state leakage, stale cache masking and arrival-order bugs.
- **INPUTS:** Entity keys, request time, configurable freshness/TTL.
- **OUTPUTS:** Provider, atomic cache operations, pinned resolved state.
- **DEPENDENCIES:** W4-02, W4-03.
- **FILES EXPECTED TO CHANGE:** `backend/app/services/snapshots/resolver.py`,
  `backend/app/config.py`, `backend/pyproject.toml`, `backend/Dockerfile`,
  `docker-compose.yml`, `backend/tests/test_week4_snapshots.py`.
- **IMPLEMENTATION APPROACH:** Central key namespace; latest cache entry stores
  payload and ID. Pin authoritative DB IDs across entity set, validate cached IDs,
  batch fetch misses, populate through atomic timestamp CAS. Historical resolution
  never moves latest backwards. Freshness uses age, not TTL. Existing asyncpg
  pool and Redis client are owned/closed by application lifespan.
- **TEST PLAN:** Real Redis hit/miss/down/corrupt data, failed write then recovery,
  out-of-order writers, future cached snapshot, DB outage with warm cache,
  simultaneous ingestion/resolution and freshness boundary tests.
- **SELF-REVIEW CHECKLIST:** DB remains authority; one logical context cannot mix
  changing head selections; cache errors cannot roll back committed ingestion.
- **EXIT GATE:** Cache/DB integration and prior phase tests pass; diff reviewed.
- **RISKS:** Cross-store atomicity; DB ID validation deliberately remains on hits.
- **FAILURE / FALLBACK BEHAVIOR:** Redis timeout/error => DB payloads; DB failure
  => 503; missing values => explicit MISSING; stale => visible STALE.

## Phase 4 — Context, ranking and recommendation

### W4-05 — Context builder and candidate-set conflict boundary
- **OBJECTIVE:** Combine eligible search output and pinned operational/traffic state.
- **WHY:** Ranking needs current context while Week 3 retains eligibility ownership.
- **INPUTS:** Stored search evidence, energy request, current snapshot view.
- **OUTPUTS:** Explainable candidate features or structured 409 conflict.
- **DEPENDENCIES:** W4-04.
- **FILES EXPECTED TO CHANGE:** `backend/app/services/ranking/context.py`,
  `backend/tests/test_week4_ranking.py`.
- **IMPLEMENTATION APPROACH:** Inspect all supplied eligible identities before any
  scoring. Detect changed OFFLINE, full capacity, swap inventory and eligibility
  queue limit; static catalog fingerprint changes invalidate evidence. Never call
  the eligibility evaluator or remove invalidated alternatives. Use origin-segment
  delay proxy where available; preserve base duration and provenance. Canonical
  estimated wait is consumed once. Carry energy context without dynamic weights.
- **TEST PLAN:** OPEN queue/traffic changes update features; OFFLINE/FULL/no battery
  fail whole set; rejected candidates never promoted; service/time/identity and
  snapshot provenance tests; no extra GraphHopper calls.
- **SELF-REVIEW CHECKLIST:** No competing eligibility engine, no fabricated routing,
  no label feature, no double queue/detour counting.
- **EXIT GATE:** All conflict/context tests and prior regression pass.
- **RISKS:** Static capabilities have no live ingestion; fingerprint invalidates
  stored sets if canonical catalog changes outside request lifetime.
- **FAILURE / FALLBACK BEHAVIOR:** 409 requires rerun; malformed eligible route
  evidence fails explicitly; missing traffic/queue marked with chosen fallback.

### W4-06 — Deterministic total-completion policy
- **OBJECTIVE:** Rank all eligible alternatives and select zero/one/many correctly.
- **WHY:** Provide a transparent baseline in seconds rather than opaque weights.
- **INPUTS:** CandidateRankingFeatures and RankingPolicy.
- **OUTPUTS:** Ranked candidates, chosen station/service, full breakdown/flags.
- **DEPENDENCIES:** W4-05.
- **FILES EXPECTED TO CHANGE:** `backend/app/services/ranking/service.py`,
  ranking tests.
- **IMPLEMENTATION APPROACH:** `station=base*delay`, `start=station+wait`,
  `complete=start+service`; sort by rounded millisecond completion, start,
  detour (missing last), operational age, descending capacity, station/service.
  Expose policy/version; no generalized cost unless evaluation demonstrates need.
  Top-N limits returned alternatives only after all eligible candidates are ranked.
- **TEST PLAN:** Zero/single/multiple, CHARGING/SWAP/BOTH, nearer-but-slower,
  stable ties/input permutations, missing/stale assumptions, score arithmetic.
- **SELF-REVIEW CHECKLIST:** Exactly one best iff valid eligible set nonempty;
  composite identity preserved; no randomized tie; no hidden penalty.
- **EXIT GATE:** Ranking tests, context tests and Week 3 regression pass.
- **RISKS:** Different objective/pool from Dataset reference; measure disagreement.
- **FAILURE / FALLBACK BEHAVIOR:** Never return partial success on state conflict.

## Phase 5 — API and orchestration

### W4-07 — Snapshot-aware search and synchronous recommendation APIs
- **OBJECTIVE:** Expose internal ingestion, stored candidate search, ranking and
  Week 2 -> Week 3 -> Week 4 synchronous orchestration.
- **WHY:** Connect actual backend state to recommendations without streaming.
- **INPUTS:** Energy request or telemetry/explicit service, snapshot payloads.
- **OUTPUTS:** APIs and one-retry orchestration with lifespan wiring.
- **DEPENDENCIES:** W4-06.
- **FILES EXPECTED TO CHANGE:** `backend/app/services/ranking/orchestration.py`,
  `backend/app/api/v1/ranking.py`, `backend/app/core/lifespan.py`,
  `backend/app/main.py`, `backend/tests/test_week4_api.py`.
- **IMPLEMENTATION APPROACH:** Pin DB station/queue state, inject a static-catalog
  view into unchanged CandidateSearchService, request no pre-ranking truncation,
  persist search result/evidence. `/api/v1/ranking/candidates`, `/api/v1/ranking`,
  `/api/v1/recommend`; internal `/api/v1/internal/snapshots/{traffic,station,queue}`.
  Protect ingestion using configurable internal token (unconfigured => disabled).
  Only orchestration retries search once on the typed conflict. Preserve existing
  routing exception status handling. Record structured timing/count/cache logs.
- **TEST PLAN:** HTTP 200/401/403/404/409/422/503/504; all seven user-approved
  boundary cases, second conflict stops, invalid request/zero candidates,
  real GraphHopper outage, cache outage, pool/client shutdown.
- **SELF-REVIEW CHECKLIST:** No retry in ranking, no forged client candidate set,
  no global service mutation per request, no regression in existing endpoints.
- **EXIT GATE:** API/orchestration and full existing suite pass; diff reviewed.
- **RISKS:** Historical Dataset timestamps differ from current wall clock; requests
  use explicit aware scenario time; stored evidence records both context and creation.
- **FAILURE / FALLBACK BEHAVIOR:** Typed errors, bounded retry, no mock fallback.

## Phase 6 — Evaluation and real backend evidence

### W4-08 — Leakage-free evaluation and baseline comparison
- **OBJECTIVE:** Compare runtime ordering/recommendation with frozen labels.
- **WHY:** Quantify reference-policy differences without tuning expected outputs.
- **INPUTS:** Source telemetry, catalog, snapshots and live GraphHopper; labels
  joined only after predictions are generated.
- **OUTPUTS:** Reproducible script, compact checked-in report, detailed ignored data.
- **DEPENDENCIES:** W4-07.
- **FILES EXPECTED TO CHANGE:** `scripts/evaluate_week4.py`,
  `docs/reports/week4-evaluation.json`, evaluation self-check/test.
- **IMPLEMENTATION APPROACH:** Reconstruct source request contexts; run actual
  demand/search/ranking. Compare nearest eligible, station ETA, total completion;
  report full pool and reference-common pool separately. Report station/service
  top-1, pairwise agreement, zero/single/multiple and concrete mismatch causes.
- **TEST PLAN:** Audit imports/input columns; verify labels opened after prediction;
  evaluation metrics on controlled ranking examples; execute complete evaluation.
- **SELF-REVIEW CHECKLIST:** No truth eligibility/routes/segment identities injected
  into production inference; no claim of exact objective parity.
- **EXIT GATE:** Evaluation completes, metrics/mismatches/limitations documented.
- **RISKS:** Dataset legacy metadata differs from actual source; inspect actual
  generator event sampling and reconcile joins explicitly.
- **FAILURE / FALLBACK BEHAVIOR:** Dependency failure aborts evaluation; no mocks
  and no reported agreement for non-comparable groups.

### W4-09 — Dynamic state, failure and initial performance demonstration
- **OBJECTIVE:** Prove history/cache correctness and state-sensitive recommendations.
- **WHY:** Unit tests alone cannot establish real-backend behavior or latency.
- **INPUTS:** Running DB/Redis/GraphHopper/API and source-based requests.
- **OUTPUTS:** Real demo and latency artifacts with median/P90/P95/max.
- **DEPENDENCIES:** W4-08.
- **FILES EXPECTED TO CHANGE:** `scripts/verify_week4.py`,
  `docs/reports/week4-runtime.json`, focused test as needed.
- **IMPLEMENTATION APPROACH:** Ingest newer queue states swapping best choice;
  verify old request resolves prior history and older arrivals cannot regress cache.
  Measure ingestion, cache hit, miss/DB fallback, ranking-only and end-to-end at
  concurrency 1/5/10; capture actual sample counts/candidate distributions.
- **TEST PLAN:** Run actual services, explicit Redis and DB/engine failure
  injections with restored normal state; record timing samples and provenance.
- **SELF-REVIEW CHECKLIST:** No production-scale claim; distinguish service timing
  from HTTP end-to-end; all evidence writes outside Dataset.
- **EXIT GATE:** Dynamic demo and failures pass; local measurements complete.
- **RISKS:** Shared laptop noise; label INITIAL LOCAL WEEK 4 BACKEND PERFORMANCE
  BASELINE and report sample population.
- **FAILURE / FALLBACK BEHAVIOR:** Real unavailable service blocks verification;
  never substitute mocks.

## Phase 7 — Regression, documentation and freeze

### W4-10 — Final acceptance and independent review
- **OBJECTIVE:** Verify complete scope and preserve prior milestones before freeze.
- **WHY:** Passing new tests cannot certify Dataset integrity or regressions.
- **INPUTS:** All source changes, evidence and original baseline hash manifest.
- **OUTPUTS:** `docs/WEEK_4.md`, current architecture/ADR/README updates,
  final report, focused commits and conditional completion tag.
- **DEPENDENCIES:** W4-09.
- **FILES EXPECTED TO CHANGE:** `docs/WEEK_4.md`, `docs/ARCHITECTURE.md`,
  `docs/ACCEPTANCE_CRITERIA.md`, `docs/DECISIONS.md`, `AGENTS.md`, `README.md`,
  this plan, `.gitignore`, `Makefile` where needed.
- **IMPLEMENTATION APPROACH:** Run full Week 4 tests, protected canonical Dataset
  validator, Weeks 3/2/1 regressions and live smoke; compare all Dataset hashes.
  Review `git diff d8574c0` for frozen subsystem changes, leakage, prohibited
  technologies, artifact hygiene, cache authority and deterministic conflicts.
  Record known limitations and all 29 requested review topics in Week 4 report.
- **TEST PLAN:** `python -m pytest backend/tests -q`; explicit week-file groups;
  `python -B scripts/validate_frozen_dataset.py`; live scripts; integrity comparison;
  `git diff --check`; source leakage/prohibited-runtime searches.
- **SELF-REVIEW CHECKLIST:** Every user gate linked to evidence; no invented passes;
  only intentional paths staged; prior tags untouched; clean tree before tag.
- **EXIT GATE:** All required gates PASS, focused commits, clean working tree;
  only then tag `week4-ranking-recommendation-complete`. Do not start Week 5.
- **RISKS:** Hidden stale cache or label use; independent final spec/code review.
- **FAILURE / FALLBACK BEHAVIOR:** Fix/retest genuine defects; unresolved gate =>
  PARTIAL and no freeze. Production readiness remains NOT READY.

## Plan exit gate (PASS)

The audited plan covers Week 4 only; preserves Weeks 1–3 and Dataset; ranks only
eligible composite identities; includes persistence, idempotency, out-of-order
safety, Redis KV, DB fallback, stale/missing provenance, evaluation and phase
tests. Explicit approved conflict behavior replaces the earlier ambiguity.
No Kafka, Redis Streams, live feed, continuous monitoring, push or ML runtime.

## Execution ledger

| Phase | Tasks | Result / exit gate |
|---|---|---|
| 0 | Audit | PASS: 239 baseline tests, validator 152/22, live routing smoke |
| Plan | Detailed design / ADR-013 | PASS: approved boundary recorded; coverage reviewed |
| 1 | W4-01 | PASS: 9 contract tests; 21 with prior model regression; reviewed/fixed provenance |
| 2 | W4-02, W4-03 | PASS: 7 real DB tests; 890,137 imported, exact retry created 0; independent review |
| 3 | W4-04 | PASS: 7 real cache tests + 7 DB tests; historical/empty-cache fix verified |
| 4 | W4-05, W4-06 | PASS: 25 ranking tests; 105 with model/Week 3 regression; independent review |
| 5 | W4-07 | PASS: 4 API tests including real DB/Redis lifespan shutdown; 30 with ranking/lifecycle; live API rebuilt and healthy |
| 6 | W4-08, W4-09 | PASS: 1,200 real predictions, 848 recommendation/553 ranking groups; dynamic S029-to-S007 demo, real HTTP failure probes and concurrency 1/5/10 baseline; 7 script tests; independent evaluation review |
| 7 | W4-10 | Pending implementation |
