# Complete replenishment and measured capacity

Customer authorized continuation and autonomous sub-agent implementation on 2026-10-13. With B, charge only enough for onward road travel plus reserve; without B or after B, target 80% without reducing existing charge. Swap receives 90% of effective usable installed capacity. Ranking stays 80/10/10 and physical ETA stays separate.

Charging powers are absent from canonical catalogs. Use explicit configurable application assumptions with provenance, never motor power or evaluation labels. Charging time replaces the historical flat service duration; swap retains current snapshot service time. Predicted replenishment does not mutate accepted live SOC or prove charging happened. Preserve Dataset V1 and GraphHopper as sole production engine.

- [x] Load worker: expose sanitized dependency error class/duration, reproduce real load, identify and fix measured Redis/GraphHopper bottlenecks; no arbitrary timeout-only workaround.
- [x] Energy worker: shared arrival/replenishment/onward model, candidate eligibility, ranking/confirmation duration and evidence; after-B prefix consumed exactly once; boundary and regression tests.
- [x] Root: frontend energy explanation, ADR/data contract/architecture, independent reviews and actual low-SOC station plans in browser/API.
- [ ] Repeat real 100/500/1000 GPS cadence with recommendations measured separately, then longer observation for queues/memory. Record resource configuration, errors, availability and latency; explicit failure is not capacity success.
- [ ] Full suites, lint, validator/integrity, regression review and authorized local integration. Do not close merely because errors were measured.

Functional gates on the four-replica deployment: 15 API contracts, four live replenishment cases and 34 desktop/mobile browser checks passed. Independent source review found no remaining blocker within this scope. The final finite and sustained capacity gates remain pending; earlier failed soak results are retained.
