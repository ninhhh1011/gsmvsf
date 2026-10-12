# Ranking and authoritative station plans

Implemented Task 2 on 2026-10-12. Full journey physical time includes station travel, effective queue, service, and optional onward travel. Policy is `FULL_JOURNEY_FAMILIARITY_80_10_10_V2`; score components and time reference are exposed, and preference seconds never modify physical ETA. Personal coverage is averaged over comparable trips; community averages comparable coverage by driver, including non-supporters, while preserving the five-supporter privacy threshold and bounded causal history.

`POST /api/v1/station-plan` extends the recommendation request with station/service identity. Both endpoints accept `plan_mode` before or after destination. After-destination uses original A plus B, checks A-to-B energy, and searches B-to-station with no return leg. The selection endpoint confirms eligibility, uses persisted constraints, checks geometry/timing consistency and rechecks snapshot invalidation. It returns actual longitude/latitude geometry, cost/score breakdown, goal role and projected station range. Rejected selection includes the eligibility reason.

Traffic avoidance now selects each segment's latest snapshot at or before request time before applying congestion threshold and deterministic limiting. Direct and station paths use the same constraints. Candidate and recommendation origins resolve through shared driver state.

## Evidence

- Before implementation, two new ranking regressions failed: onward travel ignored, and familiarity could not change rank.
- Focused suite 96 PASS before the additional candidate-outage variant; journey additions cover three goal modes, impossible B, unknown pair, no unproven replenishment, frequency denominators, route constraints and missing shared state. Both candidate and recommendation outage paths return HTTP 503 through the root-owned shared exception handler.
- Full backend run at this worker's checkpoint: 594 PASS / 12 SKIP (`runtime/journey-ranking-backend-tests.txt`). Root performs final integrated verification after concurrent changes.
- Ruff passes for owned source and new tests.
- Live cross-replica, actual congestion SQL, GraphHopper and browser verification remain root-owned gates.

## Owned files

`api/v1/candidate.py`, `api/v1/ranking.py`; candidate models/service; ranking models/context/orchestration/service; route-familiarity service; snapshot repository; new `test_journey_ranking.py`; updated familiarity service/ranking/privacy/workflow tests. No Dataset, configuration, lifespan, main, history repository or frontend changes by this worker.

## Limits

Round 1 review fixes: selection confirmation reads snapshots at server wall time, catches a station that goes offline during geometry generation, and refreshes cost while retaining the earlier bounded causal familiarity evidence. After-destination preserves origin-segment traffic on A-to-B exactly once, with adjusted prefix duration and snapshot provenance; it does not apply A traffic again to B-to-station. Reproductions failed before fixes; covering suite 46 PASS. Comparable time-window filtering still follows bounded repository cohort selection, so availability can be reduced when the bounded cohort contains other windows; truncation is exposed and root records this limitation.

Integration waypoint metadata: station plans expose each leg endpoint's role, cumulative geometry index and snapped geometry coordinate. Frontend uses monotonic route progress to keep reroutes from revisiting an already passed passenger destination/station. No client-controlled eligibility-bypass or service-completion flag is introduced; ordinary constrained direct routing remains a separate domain operation. Three goal-mode metadata regressions failed before implementation and pass afterward.

Live congestion-query optimization: the original latest-per-entity query sorted traffic payload history and took 2.361 / 3.038 / 4.458 seconds against the current real database. The replacement enumerates traffic entity keys, then uses the existing entity/time unique index for each latest-as-of payload before delay threshold, road geometry, deterministic ordering and limit. Same read-only DAO probe afterward took 1.778 / 0.557 / 0.591 seconds, five polygons each time. Timing varies with cache/load; this is not a production SLA. No timeout increase, history deletion, new index or Dataset mutation. Regression red before replacement; 22 covering tests PASS afterward, including real isolated PostgreSQL cleared/future congestion semantics, and Ruff PASS. Evidence: `congestion-query-before.json`, `congestion-query-after.json`, `db-probe-ranking-query.py` beside this report.

Existing service duration is not proof of added energy. Onward routing conservatively requires current remaining range to cover both legs plus reserve, otherwise `ONWARD_ENERGY_UNVERIFIED`. This can reject useful charging plans until an explicit replenishment model exists. Historical `max_penalty_s` settings remain backward-compatible internal fields; ranking and public explanation use actual weighted-score seconds, not the old 30-second cap. The bounded comparable cohort uses causal time-window coverage, not demonstrated real-world driver intent. No live load or exhaustive correctness claim is made here.
