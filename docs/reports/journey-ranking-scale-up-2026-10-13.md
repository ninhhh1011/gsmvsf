# Journey ranking and scale-up — 2026-10-13

Status: implementation and verification complete; authorized local integration pending. Approved scope: [design](../superpowers/specs/2026-10-12-journey-ranking-scale-up.md), [plan](../superpowers/plans/2026-10-12-journey-ranking-scale-up.md), ADR-025.

## Delivered behavior

Ranking minimizes `0.8 × T/Tref + 0.1 × personal_mismatch × confidence + 0.1 × community_mismatch × confidence`, where `Tref=max(1 second, fastest eligible T)`. T includes all travel, queue and service. With B: A→station→B. Without B: A→station. After-B: A→B→station, without a return to B. Preference changes ranking, never physical ETA or eligibility. Personal and community evidence independently contribute; unavailable evidence is neutral. Community frequency includes nonsupporting comparable drivers, preserves the five-supporting-driver publication threshold, causal time and bounded work.

B is optional. Station/service selection requires current backend confirmation and uses returned constrained geometry. Navigation preserves waypoint progress; vehicle changes clear incompatible selection and retain only outstanding B. Automatic historical assignment preserves original trip identity, causal time and replay geometry. The station drawer contains Top-5; mobile uses compact/expanded controls. Proven dead/superseded CSS was removed (654 lines).

## Eight original findings reconciled

The [original audit](energy-warning-and-project-review-2026-10-12.md) remains historical evidence of the pre-change defects.

| Finding | Closure and regression evidence |
|---|---|
| Lost GPS / reset resurrection | Payload, version and generation read together; CAS retries apply mutations to fresh state and reject stale match commits. `test_state_race_regressions.py`, shared-state tests. |
| Replica-local location | Async shared manager resolution; explicit coordinates retain priority; outage is explicit. Shared-state integration and cross-replica runtime verifier. |
| Ineligible station navigation | Composite station/service identity, strict card eligibility, current selected-pair confirmation; no successful-route shortcut. Journey backend and complete-journey frontend tests. |
| Impossible after-B energy | Backend verifies arrival at B without positive floors and rejects impossible plans. Journey ranking/planning regressions. |
| Old/future congestion | Latest-as-of selection precedes threshold; existing freshness window excludes stale traffic. Snapshot regressions and query-plan evidence. |
| Constraint mismatch | Direct and via calculations share domain constraints; frontend consumes authoritative selected geometry. Candidate/planning regressions. |
| Lexicographic timestamps | Validate timezone-bearing instants and sort by actual time. Map-matching/shared-state regressions. |
| Unknown queue shown as zero | Display effective wait and provenance; null remains unknown. Frontend cost/queue regressions. |

## Additional verified corrections

- Recommendation card details and both public candidate endpoints use the same pinned PostgreSQL operational source; stale canonical status no longer disables a valid ranked card.
- Confirmation refreshes the chosen pair without rejecting it because an unchosen alternative changed; original preference reference and causal evidence remain inspectable.
- Spatial candidate indexing and cached decoding prevent ordinary long corridor comparisons from exhausting the unchanged work cap; exact geometry, direction and order checks remain. Hard cases still expose unavailable evidence. Live requests during seeding returned `HISTORY_LOOKUP_FAILED` / `SIMILARITY_WORK_LIMIT`; do not infer universal familiarity availability from suite passes.
- Fresh traffic enumeration uses an additive `(kind,timestamp DESC,entity_id)` index. Recorded local query-plan execution fell from 93.11 ms to 1.537 ms; this is a query measurement, not an API SLA.
- Numeric trust boundaries reject NaN/Infinity/overflow, including raw JSON inputs. Validation responses omit unserializable input/context rather than turning an intended 422 into 500; rejected input cannot enter GPS state.
- Vehicle-switch regressions cover swap-only compatibility, passed B, station-only goals, pending-profile races and same-model preservation; assignment initialization avoids a manual-navigation reset.

- Real mobile interaction exposed a station drawer intercepting map clicks after clearing B. Shared origin/destination picker entry points now close the drawer before map selection; eight scoped regressions and independent review verified the fix (`25424fa`).

## Verification ledger

| Gate | Current evidence |
|---|---|
| Backend suite | 666 passed, 12 skipped; skips are not passes |
| Frontend suite | 247 passed, 0 skipped |
| Ruff | Passed |
| Canonical validation / integrity | 152 PASS / 0 FAIL, 22/22 scenarios; 63 canonical hashes unchanged |
| Real API / both replicas / three goal modes | 8 checks PASS, including reset visibility, selected plans, public candidate evaluation and nonfinite HTTP 422 |
| Desktop/mobile browser | 32/32 PASS; desktop/mobile three goal modes, native map picking, drawer/cost modal, SOC 85/12/5, H3, clearing B and motorcycle model change with outstanding B; no JavaScript page exceptions |
| 100→500→1,000 drivers and separate burst | Measurement complete; 100 clean, 500/1,000 overloaded. See measured counts below; no reliable 1,000-driver capacity claim. |
| Independent review | Whole-branch and subsequent scoped changes reviewed; no remaining blocker within reviewed scope. Mobile picker correction independently checked with eight tests. |
| Local main merge | Pending; no remote push requested |

Browser SAFE/ADVISORY/CRITICAL use actual backend evidence. UNAVAILABLE is covered by API/unit tests because the normal widget cannot supply missing energy; it is not claimed as a live browser interaction. Earlier timeout, invalid route-fixture and legitimate changing-snapshot HTTP 409 logs are retained. The harness uses native visible map clicks after Leaflet animation/size settles, with bounded explicit fresh-drawer reselection on 409; it does not mock responses. External OSM tile delivery is not certified.

Detailed local artifacts remain under `runtime/journey-scale/`; source verification scripts are `scripts/verify_journey_runtime.py`, `scripts/verify_journey_browser.mjs` and `scripts/measure_virtual_driver_scale.py`. Private local environment/secrets are not delivery artifacts.

## Synthetic data and measured-load interpretation

Generated inputs live outside Dataset V1 and protected realtime history. Seeds/manifests record batch, time, real GraphHopper route templates, virtual identities and noise. Separate `evaluation_truth.json` is never runtime prediction input. The public sample read signature is fixed-ID and synthetic-only; production HMAC/trusted-producer boundaries remain. No fake/demo UI badge is added at the customer's request.

The finite runner sends GPS every 30 real seconds with staggered schedules; recommendations are independently sampled after demand evaluation or explicit service intent. The report must distinguish achieved rates, error/status counts, latency, queue delay, backlog and familiarity availability. The local rate limit is explicitly 6,000/minute for the single load client; default production configuration remains 100/minute. Earlier overloaded runs remain evidence and are not relabelled as successful final capacity tests.

## Final finite load

Real PostgreSQL/Redis/GraphHopper/API, no mocks: 2026-10-13 03:42:57Z–03:48:58Z. `MEASURED`/process exit 0 means the measurement completed, not every request succeeded. Seed batch `0f3b637bd47b6ad3`, isolated driver namespace `synthetic-scale-complete-20261013`, 8,005 completed routes over eight real-network templates; virtual canonical V0001 model copies.

| Drivers | GPS 200 / sent | Demand 200 / sent | Recommendation 200 / sent | Errors / successful familiarity |
|---|---:|---:|---:|---|
| 100 | 300/300 | 5/5 | 3/3 | No errors; AVAILABLE 3 |
| 500 | 1,448/1,500 | 24/24 | 13/13 | 52 GPS HTTP 503 shared-state failures; AVAILABLE 13 |
| 1,000 | 2,964/3,000 | 48/48 | 11/24 | 36 GPS HTTP 503 shared-state failures; 13 recommendation HTTP 504 GraphHopper timeouts; AVAILABLE 11 |
| Separate burst 100 | 100/100 | Not requested | Not requested | No errors |

| Drivers | Elapsed s | GPS P50/P95/P99 ms | Recommendation P50/P95/P99 ms | Achieved GPS/s | Peak pending events |
|---|---:|---|---|---:|---:|
| 100 | 90.006 | 11.9/83.4/243.1 | 4,300.3/4,333.3/4,333.3 | 3.333 | 3 |
| 500 | 141.862 | 10.5/3,953.3/8,079.8 | 36,257.1/43,514.1/43,514.1 | 10.207 | 120 |
| 1,000 | 123.456 | 12.8/2,034.9/4,519.1 | 12,529.1/23,899.5/24,049.0 | 24.009 | 452 |
| Burst 100 | 4.108 | 1,144.7/2,445.2/2,533.4 | Not requested | 24.346 | 99 |

Three real 30-second intervals per stage; concurrency 32, 60-second request deadline, 90-second drain. Achieved rates include drain time; scheduled targets were 3.33/16.67/33.33 GPS/s. Latency includes errors and warmup. Demand is sampled every twentieth driver in the last interval, with explicit charging intent every fortieth driver; failed GPS chains may omit a demand sample. Zero transport errors and cancellations. Successful recommendation familiarity was AVAILABLE; that does not erase earlier seed-time unavailable evidence or failed requests.

Shared-state 503 responses remained explicit without replica-local fallback. Error bodies establish dependency symptoms; the exact Redis readiness failure cause was not independently proven because that health check suppresses its underlying exception. No new infrastructure or raised dependency timeouts were used to relabel overload as success. Reliable 500/1,000-driver operation is not established. CPU/memory peaks, multi-host load and a long soak were not measured. Full local evidence: `runtime/journey-scale/load-complete-20261013.json` and `load-complete-report.md`.

## Limits

`ONWARD_ENERGY_UNVERIFIED` is deliberately conservative: service duration does not prove battery replenishment, so existing range must cover represented travel plus reserve. Useful low-battery charging journeys can be rejected until a replenishment contract/model exists. A station waypoint is not charging completion.

Synthetic history can explain generated choices, not prove why real drivers choose a road. Traffic is an origin-segment proxy and energy remains an uncalibrated catalog/physics estimate. The workload uses a limited set of real-network templates and virtual model copies; it does not establish heterogeneous citywide capacity or a production SLA. Single-host services, motorcycle `car_access`, protected production identity requirements and bounded-history truncation remain. No new infrastructure, durable charging lifecycle or Week 6 productionization is claimed. This is not an exhaustive guarantee that the repository has no bugs.
