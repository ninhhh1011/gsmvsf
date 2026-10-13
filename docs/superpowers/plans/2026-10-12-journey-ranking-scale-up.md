# Journey ranking and synthetic scale-up implementation plan

> For agentic workers: use subagent-driven-development, failing reproductions before fixes, scoped review and final branch review. Customer approved the written spec and autonomous implementation on 2026-10-12; no repeated plan-approval checkpoint is required.

Goal: close the eight recorded correctness findings and deliver optional-B, full-completion 80/10/10 ranking, internally traceable synthetic familiarity/explanations and measured 100/500/1,000-driver operation.

Architecture: keep the modular monolith, existing PostgreSQL/Redis/GraphHopper and existing HTTP/client ownership. Reuse domain contracts; no new engine, infrastructure or model API. Protected real history stays behind the existing HMAC boundary. Public synthetic examples are isolated in a validated synthetic namespace and use a server-controlled scoped read identity.

Spec: `docs/superpowers/specs/2026-10-12-journey-ranking-scale-up.md`.

## Global constraints and rulings

- Dataset V1 and both PBFs are immutable; labels/evaluation reasons never runtime prediction inputs.
- GraphHopper is the only production routing/matching engine. Synthetic inputs are acceptable; mock success/latency/ranking outputs are not live verification.
- Time includes every applicable leg, queue and service once. Preference score does not alter physical ETA or eligibility.
- Weights: 0.8 time, 0.1 personal mismatch, 0.1 community mismatch. Confidence attenuates missing/weak evidence; absent evidence is neutral, not reported as known zero familiarity.
- `Tref=max(1 second, fastest eligible total completion time)`; record reference and all components in output. The 1-second floor only avoids a zero denominator; physical zero remains zero.
- Personal compares meaningful corridor usage across comparable trips; community denominator includes comparable non-supporting drivers. Preserve minimum five supporting drivers, bounded causal history and geometric work limits.
- No fake/demo UI badges. Internal records retain synthetic batch/seed/provenance and limitations; no real-world causal claim from synthetic data.
- Ruling: service duration remains the existing snapshot estimate, not a new charging-curve model. A single-stop plan must reject an onward leg that cannot be completed under its represented replenishment capability. No durable booking/billing/real charger control is introduced.
- Ruling: default UI synthetic profile is a fixed public sample, not a new historical-trip selector. Its read signature is restricted to synthetic history; signing/ingestion secrets never go to frontend. Production identity checks remain intact.
- Recommendation workload follows backend demand and a finite client refresh policy. GPS cadence is 30 real seconds, staggered; test burst separately. No invented production SLA or fabricated stage success.
- Worker file ownership is exclusive. Root owns docs, config/lifespan/main wiring, synthetic scripts/data and integrated verification. Workers do not revert others or mutate Dataset/unrelated artifacts.

## Review focus

1. Reset/ingest/match races cannot resurrect or erase accepted state; read payload/version/generation together.
2. Optional destination and zero coordinates/zero travel are not replaced with defaults; station navigation target is not passenger B.
3. Snapshot/energy invalidation before selection denies a stale or impossible plan; only the full workflow repeats search once.
4. Fake read capabilities cannot select arbitrary identities or reach real history; missing seed/caps/failures stay explicit.
5. Current physical warnings and preference rankings survive manual updates, concurrent replies and missing evidence without false certainty.

## Task 1 — Shared state correctness (worker state)

Ownership: `backend/app/services/realtime/driver_state_manager.py`, `driver_state_repository.py`, `driver_trace.py`, `location.py`, `backend/app/api/v1/realtime.py`, `backend/app/services/map_matching/service.py/models.py`; corresponding backend tests. Do not edit ranking/candidate/demand API files or lifespan/main; send root the shared-location integration contract.

- [x] Reproduce lost B update and reset resurrection; implement CAS against the snapshot read, retry mutations on fresh state, withhold stale match commits.
- [x] Add an async shared-state location resolver, preserving explicit-coordinate priority and the common freshness policy; no Redis-outage memory fallback.
- [x] Normalize/sort batch timestamps by instants, preserve valid external representation, validate malformed timestamps; update invalid legacy fixtures deliberately.
- [x] Run focused state/map-matching tests; reproduce interleavings and report API call-site changes root must apply.
- [x] Root/reviewer checks invariants before task acceptance.

## Task 2 — Full journey ranking and authoritative station plans (worker ranking)

Ownership: `backend/app/services/ranking/{models,service,context,orchestration}.py`, `backend/app/services/candidate/{models,service}.py`, `backend/app/services/route_familiarity/service.py`, `backend/app/services/snapshots/repository.py`, `backend/app/api/v1/{ranking,candidate}.py`; new focused planning module/API if needed; corresponding tests. Do not edit config/lifespan/main, route history repository or frontend. Coordinate shared-location helper with root/state worker.

- [x] Regression: earlier service completion loses when onward travel makes full journey later; no-B uses service completion alone; after-B has no return leg.
- [x] Implement versioned policy and 80/10/10 score with contribution/reference metadata, physical ETA separate. Replace fixed 30-second ranking semantics; keep history bounds/privacy.
- [x] Personal and community each change ranking; sparse/legacy/partial evidence is explicit and neutral. Community frequency counts its comparable cohort, not only supporting drivers.
- [x] Fix latest-as-of traffic before threshold/limit, and direct/via constraint consistency.
- [x] Provide authoritative selection/plan confirmation: consumes current telemetry, station/service identity, optional passenger B and intent; validates feasibility and current eligibility, returns actual geometry/durations and reason/invalidation. Reuse eligibility/workflow rather than clone business rules.
- [x] Block impossible after-B arrival without positive SOC/range floors; reject impossible onward single-stop legs. Do not fabricate replenishment proof.
- [x] Send frontend/root precise request/response and score contracts early. Run focused tests including snapshot changes.

## Task 3 — Optional-B frontend and trustworthy display (worker frontend)

Ownership: `backend/app/static/demo/index.html`, all affected demo JS, frontend tests. CSS remains root-owned until cleanup commit, then worker may add necessary narrowly scoped rules with notice. No backend/source-data changes.

- [x] No default B; map choose/clear B. Find from accepted/current or explicitly chosen A without assigning a fake trip B.
- [x] Keep passenger goal separate from station navigation target, including changing station in station-only mode. Hide/disable after-B without B.
- [x] Consume backend authoritative selected plans; reject ineligible/unknown cards and stale replies, preserve station/service identity, reuse actual constrained geometry.
- [x] All cost displays use total physical completion and separate weighted score; queue null uses effective wait/provenance, not zero. No hardcoded fallback distances/ETAs.
- [x] Show derived personal/community evidence and feature-supported explanations; no new demo badge or historical-trip picker. Receive server-controlled synthetic sample identity/signature; never signing secrets.
- [x] Maintain mobile map/actions, native disclosures, all energy states, H3 and current vehicle values. Controller stays DOM-free; split by responsibility if necessary, not by arbitrary line padding.
- [x] Focused tests first, full frontend suite and later root browser matrix.

## Task 4 — Synthetic provenance, protected sample and finite load (root)

Ownership: config/lifespan/main routing and shared-location call-site wiring, route history repository namespace support, new synthetic generation/load scripts, docs. Respect worker-owned files through coordination; no duplicated patches.

- [x] Add validated isolated synthetic history namespace with explicit additive setup; no writes/deletes to real history or Dataset. Production defaults/privacy unchanged.
- [x] Controlled public UI sample read capability uses existing HMAC verifier and fixed synthetic identity only; no arbitrary-ID signer. Config emits only scoped signature, never secrets. Wire frontend identity and signature contract.
- [x] Generate deterministic real-network histories and scenario context, with behavioral inputs/seed/batch metadata. Actual overlap/ranking/explanations are computed, not stored expected outputs. Keep evaluation truth separate.
- [x] Generate virtual-driver GPS on real geometries with bounded noise/model templates, unique driver namespaces and monotone timestamps; no fake matching success.
- [x] Finite workload: 100, 500, 1,000 virtual drivers with staggered 30-second GPS; demand/recommendation tracked independently. Run at least three observed intervals per stage, extend where sample counts are inadequate; record duration, warmup, rates, errors/backlog, distributions, family availability and resource/cap failures. No pass claim for an overloaded stage.
- [x] Test synthetic/real namespace isolation, bad signature/arbitrary ID, missing seed, immutable retry and causal history boundaries before local activation.

## Task 5 — Integration, cleanup and completion (root + reviewer)

- [x] Inspect CSS producers/callers and driver-only decisions; remove dead technical/simulation rules and consolidate overwritten cost styles. Preserve hidden-but-connected and unresolved intended styles.
- [x] Close each of eight findings with reproduction, fix, regression and appropriate live evidence.
- [x] Full backend/frontend suites, Ruff, validator and 63-file integrity; cross-replica/concurrency/traffic and real routing tests.
- [x] Browser both goal modes and after-B, changes during requests, selected route/score consistency, SAFE/ADVISORY/CRITICAL (UNAVAILABLE via API/unit), map picker, drawer, cost modal and H3 at desktop/mobile.
- [x] Preflight/each task scoped review, whole-branch independent review, fix verified findings and update ledger; no blanket bug-free claim.
- [ ] Update ADR/architecture/data contract/tracker/report with new policy and remaining limitations. Commit owned files only; integrate authorized local branch; no unrequested remote push.

## Execution ledger

- Customer approved the design and autonomous sub-agent implementation on 2026-10-12.
- Tasks 1–3 implemented and reviewed; Task 4 namespace/sample/seed/finite-runner implementation complete. Final finite load measured: clean 100-driver stage; explicit dependency failures at 500/1,000, not a capacity pass.
- Eight original findings have regression fixes; additional integration findings are recorded in the final report.
- Current suites: backend 666 PASS / 12 skipped; frontend 247 PASS; Ruff PASS. Canonical validation 152 PASS / 0 FAIL, 22/22 scenarios and 63 unchanged hashes.
- Live API eight checks passed; final load counts and overload are recorded. Expanded browser 32/32 passed; final scoped reviews found no blocker. Documentation reconciled; local integration remains pending. See [current report](../../reports/journey-ranking-scale-up-2026-10-13.md).
