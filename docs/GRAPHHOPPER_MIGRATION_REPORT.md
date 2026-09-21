# GraphHopper-only migration report

Measured 2026-09-21 in `E:/build6week`. The routing and matching migration gates are complete. This is a development baseline, not production approval. Week 4 was not started.

## 1. Repository audit

Git root was verified before implementation. Baseline was `a2f43a3`, with an inherited, incomplete dual-engine draft. Required project, acceptance, data, architecture, decision, routing and Week 1–3 documents were read. The original dependency inventory was recorded before deletion. A concurrent branch/document writer caused an earlier pause; after the user's retry, the stable `graphhopper-full-migration-20260921` branch was continued. Historical freeze tags were preserved. Local agent memory was preserved and ignored.

See [audit](GRAPHHOPPER_MIGRATION_AUDIT.md) and [before/after inventory](GRAPHHOPPER_OSRM_INVENTORY.md).

## 2. Implementation plan

Each task's inputs, outputs, dependencies, files, steps, tests, review, risks and failure behavior are in [the implementation plan](GRAPHHOPPER_FULL_MIGRATION_PLAN.md). Exit evidence:

| Phase / task | Result | Exit gate |
|---|---|---|
| 0 / GH-00 | Repository and engine inventory recorded; baseline tests executed | PASS |
| 1 / GH-01 | Official 11.0 APIs, Java and motorcycle strategy verified | PASS |
| 2 / GH-02 | Complete task plan reviewed, then implemented | PASS |
| 3 / GH-03 | Pinned runtime imported patched Hanoi graph | PASS |
| 4 / GH-04 | Car and motorcycle profiles exercised | PASS |
| 5 / GH-05 | Legacy runtime selection disconnected | PASS |
| 6 / GH-06 | Real routing, unequal leg details and errors verified | PASS |
| 7 / GH-07 | Real GPX matching and actual segment resolution verified | PASS |
| 8 / GH-08 | Shared batch/realtime matching; state/trigger policy preserved | PASS |
| 9 / GH-09 | Full frozen-label quality measured and mismatches inspected | PASS, measurement gate |
| 10 / GH-10 | Car, fixed-bike, swap and BOTH candidate routing verified | PASS |
| 11 / GH-11 | Liveness/readiness and dependency failure verified | PASS |
| 12 / GH-12 | Three-service Compose valid and healthy | PASS |
| 13 / GH-13 | Live deployed API and misconfigured-engine API tested | PASS |
| 14 / GH-14 | Real service/API and concurrency baselines measured | PASS |
| 15 / GH-15 | Dead adapters/tests/profile removed; old instructions archived | PASS |
| 16 / GH-16 | Current architecture, ADRs, procedures and limitations updated | PASS |
| 17 / GH-17 | 239 tests; 152 validator checks and 22 assertions pass | PASS |
| 18 / GH-18 | Review, architecture audit, explicit commits and freeze gate | PASS at tagged commit |

## 3. OSRM removal

Removed both production adapters, their HTTP clients, default construction, API selector branches, settings and environment selectors, readiness probe, Compose service/mounts/dependency, checked-in runtime profile and obsolete adapter tests. Smoke/benchmark commands now use actual GraphHopper and fail on outage. The former production mock adapter resides only in `backend/tests/mock_routing_adapter.py`; the production image copies only `backend/app`.

Removed the old project container after real GraphHopper tests passed. Ignored legacy generated artifacts remain local provenance and are not mounted or started. Four obsolete skill instruction files were renamed `HISTORICAL.md`, so they cannot be discovered as active skills. Remaining mentions are historical/reference documentation, frozen data provenance, negative architecture tests, and ignore rules for historical artifacts. No active application dependency remains.

## 4. GraphHopper runtime

| Item | Verified value |
|---|---|
| Release | GraphHopper 11.0 |
| Image | `build6week-graphhopper:11.0` |
| Local image digest | `sha256:02c3c00088c59deee53732a67a2f869dd278fb4408675904c6ee729ebf2f0e02` |
| Java | Temurin 21.0.8+9 LTS; release requires Java 17+ |
| Pinned base digest | `sha256:db1689535962d757a5adabf57387584ed543d38c0b9d1fe870123ea362ad73b0` |
| Official JAR SHA-256 | `b59c024afe172ec6ec85b6327006c3138ec58c7d0bcd26253d0e42853f613def` |
| Source | `dataset_v1/map/raw/hanoi-patched.osm.pbf`, read-only mount |
| PBF SHA-256 | `0d3a66b2fb03019fd9d7877115c1ed9efbb736a83c5ac6f6e5440d71ddcfff60` |
| Cache | ignored `runtime/graphhopper/gh-cache-11`, 45,137,456 bytes at final inspection |
| Initial startup/import | Approximately 146.8 seconds; recorded JVM startup time, not an isolated import-only timer |
| Port / profiles | 8989 / `car`, `motorcycle` |

The local image digest includes build attestations and can differ on rebuild; the JAR checksum and immutable Java base define the reproducible inputs. Authoritative release references are in [research](GRAPHHOPPER_MIGRATION_RESEARCH.md).

## 5. Car profile

`EV_CAR` deterministically maps to `car` for routing and matching. The supported built-in model uses motorcar access and turn restrictions. Requests with unsupported constraints, objectives, dynamic context or engine profile hints fail explicitly instead of silently ignoring them.

## 6. Motorcycle profile

`EV_MOTORBIKE` maps to the actual `motorcycle` profile and `hanoi_motorcycle.json`. The supported upstream model uses `car_access`, 90% of car average speed and track/surface restrictions; the project model excludes motorway, penalizes trunk roads, and caps modeled speed at 60 km/h. Turn costs use motorcycle/motor-vehicle restriction types.

This is a distinct motorcycle weighting, but **not a complete independent motorcycle access parser**. `motorcar=no` can exclude motorcycles too, including the patched bridge. Motorcycle-specific way-access permissions are not fully modeled. These are conservative modeling limitations, not claims about Vietnamese legal access or speed limits. The PBF was not altered.

## 7. Routing

Real deployed `/api/v1/route`, origin `(21.028, 105.854)`, destination `(21.036, 105.830)`:

| Category | Selected profile | Distance | Duration |
|---|---|---:|---:|
| EV_CAR | car | 3,615.227 m | 289.719 s |
| EV_MOTORBIKE | motorcycle | 3,885.175 m | 349.387 s |

Real via routes also passed. GraphHopper `leg_distance` and `leg_time` details provide unequal actual legs; milliseconds are converted to seconds. No equal-leg fabrication or straight-line routing fallback exists. Infrastructure failures propagate through every leg; genuine no-route remains a business result. Successful via totals survive a missing direct route, with unavailable detours left null.

## 8. Map matching

Real deployed `/api/v1/map-match`, 20 actual Dataset observations per case:

| Case | Profile | Matched | Directed identity emitted | API latency |
|---|---|---:|---:|---:|
| Car T0001 | car | 20/20 | 17 | 91.5 ms |
| Fixed motorcycle T0024 | motorcycle | 20/20 | 11 | 51.9 ms |
| Swap-capable motorcycle T0015 | motorcycle | 20/20 | 10 | 55.5 ms |

Actual GPX enters maintained `/match`; unsimplified path geometry and `osm_way_id` details are parsed. Per-observation coordinates are projected onto the returned path. PostGIS resolves canonical segments from actual way identity and geometry. Revisited-path ambiguity and segment ties withhold directed IDs/direction. Internal GraphHopper edge IDs are never passed off as OSM/Dataset identities.

Encoded geometry prefixes and representative real metrics are in [checked-in evidence](reports/graphhopper-migration-evidence.json). Full response evidence is retained under ignored `runtime/migration/`.

Quality is `max(0, 1 - distance_to_path_m / 100)` per observation, averaged over the request. The 100 m cutoff concerns raw GPS-to-path distance, not true-position evaluation error. This is project geometric quality, not a calibrated probability or historical engine confidence.

## 9. Week 1 quality

150 complete trajectories, 65,847 observations, including all 5,029 selected frozen evaluation points; 93 car and 57 motorcycle requests all succeeded. Labels were joined only after inference.

| Metric | All observations | Selected subset |
|---|---:|---:|
| Match rate | 98.83% | 98.77% |
| Position mean / median | 8.10 / 5.04 m | 8.10 / 5.02 m |
| Position P95 / maximum | 25.75 / 131.50 m | 26.60 / 101.85 m |
| Directed segment accuracy | 26.96% | 27.08% |
| Base segment accuracy | 27.20% | 27.30% |
| OSM-way accuracy | 80.96% | 80.19% |
| Direction accuracy | 34.42% | 34.19% |
| Directed identity coverage | 37.28% | 37.17% |

Identity accuracies include abstentions in the matched-observation denominator. Conditional directed precision is 72.30% over emitted IDs, but does not replace the low coverage figure. There are 40,815 withheld IDs, chiefly 39,000 ambiguous path projections. Different-way and same-way segment errors were inspected and retained in evidence.

Historical OSRM evidence is 247/250 matched, 36.0% directed accuracy, 46.2% direction accuracy, and mean/median/P95/max position error 4.65/3.91/11.84/20.21 m. Unequal populations and trace contexts prevent a controlled improvement/regression claim. Historical base/way figures are unavailable.

The evaluation gate passes because measurements, mismatches and limitations are documented; **no unspecified accuracy threshold or production-quality gate is declared passed**. See [full quality report](GRAPHHOPPER_MATCHING_QUALITY.md), including source reconciliation and a final-source 699-observation replay with identical predictions.

## 10. Week 1 realtime

Batch and realtime use the same matching service. Live streams for all three cases above reached `MATCHED`, and engine failure produced `ENGINE_UNAVAILABLE`. Realtime returns actual matched coordinates. Duplicate observation IDs now select the latest matching result. `DriverStateStore`, `HybridTrigger`, bounded context, warm-up, stationary suppression, gap reset and stale-observation policy files are unchanged from baseline.

## 11. Week 3 candidate search

Live deployed searches returned 30 car alternatives/19 eligible, 30 fixed-bike alternatives/0 eligible, and 60 BOTH alternatives/13 eligible. Zero eligible is an explicit valid business outcome, not an engine outage or fabricated fallback. Existing compatibility, operational and energy rules remain responsible for eligibility.

Twenty distinct canonical trips (five each car, fixed bike, swap and BOTH) generated **1,220 successful road-route calls**, exactly 61 per search. BOTH expands 60 station/service alternatives while reusing the same station's two legs. Direct route is computed once. Actual station/onward/direct/via/detour and ETA arithmetic was checked. Missing destination leaves unavailable metrics null. No ranking, scores or recommendation selection was introduced.

## 12. Failure behavior

A temporary API container used `GRAPHHOPPER_BASE_URL=http://127.0.0.1:1` with real PostGIS and read-only Dataset mounts. Actual HTTP assertions passed:

| Endpoint | Observed outage behavior |
|---|---|
| `/health` | 200, process alive |
| `/readiness` | 503, GraphHopper false / PostGIS true |
| `/api/v1/route` | 503 |
| `/api/v1/map-match` | 503 |
| `/api/v1/candidate-search` | 503 for car/fixed/BOTH |
| Realtime ingestion after warm-up | `ENGINE_UNAVAILABLE` |

The temporary container was stopped and removed. Production services remained available. Legacy and mock implementations are absent from the production image. Separate unit tests verify timeout, malformed response, invalid request, no-route and errors on all route legs.

## 13. Health / readiness

Root and `/api/v1` liveness/readiness aliases exist. Readiness actually routes with both profiles and checks a populated PostGIS segment table. A process-only response is not considered routing readiness. Compose validates and API, GraphHopper and PostGIS are healthy. No legacy engine probe remains.

## 14. Performance

**INITIAL LOCAL GRAPHHOPPER PERFORMANCE BASELINE.** Shared development host, warm imported graph; quality work overlapped part of testing. No high-load capability claim.

Twenty sequential service searches: median 938.1, P90 1295.7, P95 1505.2, maximum 1707.9 ms. This excludes API serialization and initial catalog loading. The production API now shares its HTTP connection pool for its lifespan too.

Twenty deployed API requests at each concurrency, same representative trip set:

| Concurrency | Median | P90 | P95 | Max | Throughput |
|---:|---:|---:|---:|---:|---:|
| 1 | 777.2 ms | 896.5 ms | 955.8 ms | 1354.9 ms | 1.230 searches/s |
| 5 | 2384.8 ms | 2917.6 ms | 2945.5 ms | 2974.9 ms | 2.059 searches/s |
| 10 | 6621.7 ms | 7337.2 ms | 7358.6 ms | 7477.6 ms | 1.457 searches/s |

API P90/P95 use nearest-rank values. Service benchmark and matching reports use interpolated quantiles. Concurrency 10 reduced throughput and increased latency; these measurements are not capacity approval.

Matching full trajectories (50–743 observations): native HTTP median/P90/P95 119.1/482.2/701.1 ms; service including projection/PostGIS 1733.7/4184.9/6047.1 ms. Size buckets are in the quality report. An incidental Docker snapshot during evaluation showed GraphHopper about 100.8% CPU/535.8 MiB, API 82.6 MiB and PostGIS 439.8 MiB; these are observations, not measured peaks.

## 15. Tests

Executed `DEBUG=false python -m pytest backend/tests -q --basetemp=runtime/migration/pytest --junitxml=runtime/migration/tests.xml`: **239 passed**.

| Group | Passing tests |
|---|---:|
| Week 1 matching/realtime/config/health | 37 |
| Week 2 demand/capability/energy/scenarios | 69 |
| Week 3 candidates/routing/contracts | 71 |
| GraphHopper migration/adapter/lifecycle/failure | 62 |

Independent review reproduced and verified fixes for loop-direction fabrication, ambiguous directed IDs, per-route client construction and duplicate-ID realtime selection. Latest focused review: 99 passed. Meaningful new regressions were observed failing before their fixes.

## 16. Dataset regression

The canonical `dataset_v1/validation/validate_dataset.py` executed via `scripts/validate_frozen_dataset.py`: **152 PASS / 0 FAIL; 22/22 scenario assertions**. This corrects stale documentation counts of 163/21; 21 scenario-definition rows are distinct from 22 assertions.

The validator normally writes inside Dataset V1. The wrapper executes its unchanged source using `runpy` while redirecting only its generated reports to `runtime/migration/validation/`. This preserves frozen source bytes rather than claiming the unwrapped command was harmless. SHA-256 comparison confirms all **63 canonical files unchanged**, including both PBFs. The road loader separately verified 701,407 canonical PostGIS segments and inserted zero into the already populated database.

## 17. Final architecture audit

OSM remains the data foundation. GraphHopper is the sole production route/match implementation behind neutral contracts. Car/motorcycle mapping is deterministic. No engine selector, fallback, mock production module, runtime labels, legacy service or future-week implementation remains. Week 2 and realtime state/trigger implementations are unchanged. Generated caches, JARs and full measurement artifacts are ignored. Final source searches and diff checks pass.

## 18. Documentation

Updated README, AGENTS, acceptance counts, data contract, architecture, routing strategy, Week 3 status and ADR-010–012. Historical Week 1/2 reports and old plans retain their evidence with superseded-runtime banners. Added research, implementation plan, inventory, matching evaluator/report, this report and compact checked-in evidence. Reproduction commands are in README and the reports.

## 19. Git

Coherent implementation commits include `8232305` (pinned import), `9e48b41` (sole production runtime), and `adccf17` (deployment, real verification and cleanup), following the audit/plan commits. Final evidence/documentation is committed separately. Explicit paths were staged; no destructive Git or history rewriting was used.

Freeze tags at the final clean commit: `graphhopper-full-migration-complete` and `week3-candidate-routing-complete`. Historical Week 1/2 tags retain their original targets. Tagging is conditional on the actual final clean-tree check, not this prose. Local agent memory and generated runtime evidence remain ignored and preserved.

## 20. Limitations

- Motorcycle way access shares the car parser and is not independent legal-access modeling.
- Full-path observation projection is not an ordered HMM correspondence. Identity coverage and position-error tails require further quality work; confidence is not calibrated.
- In-memory driver state, synchronous segment queries, sequential per-search routing and local concurrency results are development constraints. No production-scale claim is made.
- Non-default routing constraints, objectives and dynamic traffic are explicitly unsupported. No Week 4 ranking was added.
- Historical quality/performance evidence has different populations and methods; no controlled cross-engine performance conclusion is available.

## 21. Bugs remaining

No unresolved blocking engine-wiring defect was identified in final review. Measured wrong-way/segment assignments, incomplete directed coverage and motorcycle access limitations remain material quality deficiencies. This migration does not certify those as solved. The matching adapter's optional custom timeout is not independently applied when a shared client is injected; current production callers use the same 60-second default. Production readiness is **NOT READY**.

```text
OSRM ACTIVE RUNTIME REFERENCES: 0
GRAPHHOPPER ROUTING RUNTIME: VERIFIED
GRAPHHOPPER MAP MATCHING RUNTIME: VERIFIED
CAR PROFILE: VERIFIED
MOTORCYCLE PROFILE: VERIFIED (documented shared-access limitation)
WEEK 1 MIGRATION: PASS (functional migration; quality limitations remain)
WEEK 3 MIGRATION: PASS
REGRESSION: PASS
REAL RUNTIME: VERIFIED
MIGRATION QUALITY: PASS (defined migration gates, not production accuracy)
PRODUCTION READINESS: NOT READY
FINAL DECISION: GRAPHHOPPER-ONLY MIGRATION COMPLETE
```
