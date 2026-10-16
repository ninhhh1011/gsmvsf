# Replenishment and measured capacity continuation

Customer-authorized continuation of ADR-025/026; this report supersedes the earlier extension's replenishment limitation only for the implemented model. Final sustained capacity verification and local integration are pending at this draft's creation.

## Delivered behavior

Ranking retains 80% complete journey time, 10% personal familiarity and 10% community familiarity. Complete time includes represented road legs, queue and modeled charging or swap service. Physical ETA is displayed separately from preference score.

The shared backend model predicts energy on arrival at the selected station, energy added, departure SOC, onward reserve and service duration. With B, charge only enough for onward network travel plus reserve. Without B, or at a station after completing B, charge to 80% without reducing an already higher charge. Swap receives 90% of effective installed usable capacity. Canonical capacity and installed modules are authoritative; explicit valid remaining kWh takes precedence over rounded SOC. AFTER_DESTINATION consumes the A-to-B prefix once in the planning context and preserves live A energy in the response.

Charging time replaces the historical fixed charging service time; it does not add that fixed time again. Swap retains the operational snapshot's service duration. A projected station visit never mutates accepted live SOC or proves charging occurred. Changing SOC invalidates selected estimates immediately, then refreshes the selected station/service pair with stale-response guards. Assigned historical trips can use their planning origin before the first replay GPS.

Published examples and assumptions are in [charging references](../CHARGING_POWER_REFERENCES.md): representative car station 60 kW, VF 3 acceptance bound 24 kW, generic other-car acceptance 30 kW, motorcycle charging 0.4 kW. Efficiency, setup and high-SOC taper are configurable project assumptions. Motor power is not charging power.

## Capacity changes and evidence boundaries

The measured bottleneck was CPU work starving API event loops and shared-state sockets, compounded by route fanout. Removed redundant Redis health pings, offloaded signature preparation and familiarity CPU work, admitted one actual CPU worker per service, and drained canceled CPU tasks before releasing admission. Query preparation deduplicates exact centers. Per-route query metadata and per-comparison candidate memoization preserve heading, projection, monotonic ordering and comparison budgets. Real-network profile comparisons retained all 96 full comparison results and reduced selected CPU medians by approximately 21–34%. Failed station searches now cancel and drain unfinished sibling routing tasks instead of continuing abandoned fanout; regressions cover failure and caller cancellation.

The final deployment uses four single-worker API replicas on the existing eight-CPU local Docker host. Each adapter admits four routing calls, keeping the aggregate maximum at 16, the same as the previous two-replica configuration. Only API 1 runs the existing simulator. Nginx balances all four; Redis remains authoritative shared GPS state, with no replica-local fallback. Redis socket timeout remains 0.2 seconds and routing timeout remains 10 seconds. Default rate limiting is 100/minute per replica; the private load-client configuration is explicitly 6,000/minute. No new technology or production SLA is introduced.

Earlier failed measurements remain under `runtime/journey-scale/`: the initial 500/1,000 stages had explicit Redis 503 and routing timeout failures; the first sustained two-replica run built a backlog and timed out recommendations. Candidate caching improved but did not eliminate overload in a second sustained run. A fresh transport per measurement stage fixes the load client's canceled-pool contamination; this is distinct from server capacity. Those runs are not relabelled as successful.

The first four-replica finite run also failed capacity: all 4,800 scheduled GPS requests and the separate 100-request burst succeeded, but the 1,000-driver stage completed only 10/25 recommendations, with five routing HTTP 504 responses and ten client timeouts. Four replicas alone are therefore not an established solution. Subsequent diagnosis separates route admission wait, route HTTP duration, matching HTTP duration and comparison work counts; timing logs contain no identities or geometry. The workload uses CH routing without congestion custom models. Moving GPS updates trigger one match each after warmup. JVM and Docker agree on eight effective CPUs, so no processor-count override is justified.

A further real cadence defect was reproduced: the old 30-second matching context excluded a previous sample when scheduling jitter exceeded 30 seconds, so a clean 500-driver diagnostic had only 200 actual matches among 1,500 accepted GPS requests. Its 13/13 successful recommendations and 2.3-second P95 do not establish full matching capacity. The following sustained run also failed (9,951/10,000 GPS and 55/140 recommendations; peak pending 3,638). The default context is now 60 seconds, aligned with the existing session gap, with unchanged three-point warmup/50-point cap and no matching across a gap greater than 60 seconds. State and endpoint regressions prove adapter invocation at 30.001 seconds and warmup after a session break.

Independent source review then removed unused signature arrays from history query projections and deduplicated identical serialized geometry decoding per assessment. This preserves complete assessment values, causal cohorts, 550 history comparisons/100 community drivers in the regression, sentinel/truncation and per-trip point limits. The expected performance benefit still requires measurement; it is not inferred from fewer lines.

Final workload uses isolated synthetic histories outside Dataset V1, real GraphHopper geometry, PostgreSQL, Redis and HTTP APIs. GPS cadence is 30 real seconds, with 100 → 500 → 1,000 drivers. Recommendations are measured separately: explicit charging intent for every fortieth driver, following demand evaluation. The longer 1,000-driver run repeats demand sampling every interval, giving 25 recommendations per 30 seconds over ten intervals. Concurrency is 32, request timeout 60 seconds and drain deadline 90 seconds. Synthetic intent explains generated choices; it does not prove real driver motivation.

The final seed is `synthetic-scale-cadence-evening-20261013`, batch `57b58540dc871c58`, eight real-network templates and 8,005 histories across 1,601 identities. All histories belong to EVENING_PEAK and completed on October 8–12, strictly before the October 13 measurement. The manifest's 11:00Z horizon chooses historical time-of-day; it does not introduce future completed trips. Earlier off-peak seeds remain intact, outside Dataset V1.

## Final finite measurement

Actual HTTP measurement: 2026-10-13 10:24:11.398799Z–10:28:46.704240Z. Four API replicas, real services and the final cadence/hydration code. Each clean driver has exactly two initial warmup updates followed by one actual match. All successful recommendations have AVAILABLE familiarity.

| Drivers | GPS 200/sent | Warmup / actual matched | Recommendation 200/sent | Elapsed seconds | Peak pending |
|---|---:|---:|---:|---:|---:|
| 100 | 300/300 | 200 / 100 | 3/3 | 90.00 | 2 |
| 500 | 1,500/1,500 | 1,000 / 500 | 13/13 | 90.54 | 2 |
| 1,000 | 3,000/3,000 | 2,000 / 1,000 | 25/25 | 91.86 | 11 |
| Separate cold burst | 100/100 | 100 / 0 | Not requested | See artifact | See artifact |

No HTTP/transport errors or deadline cancellations. Server GPS counts across the replicas are 1,296 / 1,221 / 1,217 / 1,166, totaling 4,900 including the burst; bounded logs contain zero HTTP 503 and zero Redis CAS failures. Mean comparison CPU/wall time is 1,307/1,374 ms across 41 assessments. The cold burst verifies ingestion, not map-matching burst capacity. Full evidence: `runtime/journey-scale/load-cadence-finite.json` and corresponding API/Nginx/timing/resource artifacts.

The following full-matching soak **failed**, 10:30:10.820720Z–10:36:43.076353Z: 9,996/10,000 GPS (four Redis GET 503), 7,991 actual matches/2,005 warmup responses; 188 recommendations sent, 122 HTTP 200 with AVAILABLE familiarity, 12 gateway 504, 22 client timeouts and unfinished/canceled events. Peak pending 2,849; elapsed 390.03 seconds including the maximum drain. GraphHopper matching HTTP mean/P95 was 221/790 ms and routing mean/P95 970/3,507 ms; no successful-count interpretation erases the failures. Four-replica request counts show all replicas working; momentary CPU imbalance is not evidence of persistent load-balancer skew. Evidence: `load-cadence-soak.json` and bounded attribution artifacts.

The controlled Landmark experiment was **rejected**. Same-server interleaved LM/Dijkstra matching outputs agreed for original and sampled actual-workload traces; all 1,398 canonical observations retained resolution, including 390 AMBIGUOUS cases with road IDs/direction withheld, and route/restriction/congestion geometry remained unchanged. LM mean matching times were worse: 54.62 versus 12.37 ms on 288 original samples per mode, and 23.07 versus 17.28 ms on 900 sampled workload traces per mode. Restore baseline graph/configuration and congestion solver; retain the isolated preparation and evidence. One route request and a tool sleep experienced a roughly 44-minute environment pause, so that route's latency and overall probe duration are not valid capacity measurements. Paired matching work had completed before the pause. Evidence: `landmark-probe-comparison.json` and raw bounded inputs/results.

## Verification

- Four-replica live API: 15/15, including cross-replica GPS visibility/reset and identity/validation boundaries.
- Live replenishment plans: 4/4, including low-SOC A → station → B, station-only 80%, after-B planning and swap 90%.
- Real desktop/mobile browser: 34/34, including selected-plan refresh after SOC changes and absence of stale charging estimates.
- Independent connected-source reviews found no remaining blocker within this scope; capacity remains dependent on the final measurements.
- Fresh whole suites after cadence/hydration corrections: 712 backend passed / 12 skipped; 256 frontend passed; scoped Ruff and JavaScript syntax checks passed.
- Final shared signature/query/comparison admission: 718 backend passed / 12 skipped in the idle full run. An earlier full run had one actual snapshot-database 503; unchanged isolated real-resource test and the subsequent full run passed. Its original exception class was not available, so its cause is not invented. Earlier failed evidence is retained.
- Canonical validator: 152 passed / 0 failed and 22/22 scenarios; 63 canonical file hashes unchanged.
- Sustained-load completion and local integration: pending.

Local evidence lives under `runtime/journey-scale/`; private environment values and secrets are not delivery artifacts.

## Limits

The charging model uses representative powers and a simplified curve, not calibrated session predictions. The workload uses a limited set of real-network templates and virtual vehicle copies on one host. A five-minute observation cannot establish a production SLA, citywide diversity, long-term memory stability or real-world causal explanations. Existing motorcycle access limitations and protected production identity requirements remain.
