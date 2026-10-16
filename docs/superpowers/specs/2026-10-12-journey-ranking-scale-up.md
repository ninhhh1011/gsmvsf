# Journey ranking, optional destination and synthetic scale-up

Date: 2026-10-12. Business choices confirmed by the customer in the current conversation. Implementation details below are a concrete design for review, not claims of completed functionality.

## Customer requirements

- With B: minimize the weighted score based on the complete A → station → B journey, including travel, queue and charging/swap duration.
- Without B: a driver at A can find and choose a station. B is optional; no hidden default B or forced return to the selected station as a passenger destination.
- Ranking uses 80% time and 20% familiarity. Familiarity includes both personal and community history. It must actually change ranking, not remain a 30-second tie-breaker.
- Synthetic GPS/history/traffic/queue data are acceptable. The customer will tell the mentor. Do not add demo/fake badges to the product UI; preserve provenance in technical records and generated data.
- Measure 100 → 500 → 1,000 virtual drivers, each submitting GPS every 30 seconds. Measure recommendation separately, triggered by demand rather than every GPS message.
- Delete proven obsolete CSS/code. Check producers/callers and intended disconnected features before deletion.

## Ranking definition

With B, `T = travel(A,station) + queue + service + travel(station,B)`.
Without B, `T = travel(A,station) + queue + service`.
For an explicitly chosen after-B plan, `T = travel(A,B) + travel(B,station) + queue + service`; there is no unintended station → B return leg.

Use the same request-time routing constraints and eligible station/service pairs throughout. Missing required onward metrics are unavailable evidence, not zero. Time includes the applicable backend traffic adjustment exactly once. Service/queue values come from the existing snapshot contracts; this does not introduce a calibrated charge-curve model.

Proposed engineering default inside the confirmed 20% familiarity share: equal personal/community shares, i.e. 80/10/10 overall. Let `Tref=max(1 second, fastest eligible T)` and let personal/community mismatch terms be bounded to [0,1] and reduced by their evidence confidence. Score is `0.8*T/Tref + 0.1*personal_mismatch + 0.1*community_mismatch`. Time-equivalent ranking cost is the score converted back to seconds; physical ETA remains the original T and must never include the preference penalty.

Define personal familiarity from comparable historical corridor coverage/frequency, not just whether a route was ever used once. Community combines coverage with supporting-driver frequency in the comparable cohort, including non-supporting drivers in its denominator. Preserve the five-supporting-driver publication threshold, causal start/completion times, bounded lookback/query/comparison work, and explicit missing/truncated evidence. Missing evidence is neutral and is not falsely reported as 0% familiarity. Publish score contributions and evidence counts so the 80/20 effect is inspectable.

## Optional B and station planning

Keep passenger destination separate from the station navigation target. UI starts without a forced B, supports selecting/clearing B, and disables the after-B option when B is absent. A comes from an accepted position or an explicit map choice; a camera center must not be represented as a measured position.

Backend owns station/service eligibility and plan feasibility. Selecting a card requires current backend confirmation, not merely a successful `/route`. Preserve composite station/service identity and the existing single workflow retry on snapshot invalidation. A plan response provides the actual selected route geometry, constraints/provenance, physical durations and goal role; frontend does not recompute a different unrestricted route.

After-B planning first checks that A → B can be reached, then evaluates the remaining energy at B without positive floors. An impossible projected arrival is rejected. A single-stop plan must also respect the vehicle's ability to complete the onward leg; do not invent a second charging stop or full battery.

## Synthetic data and explanations

Keep generated inputs outside `dataset_v1/`, deterministic through recorded seeds, and isolated from real/protected history. Prefer a controlled synthetic namespace and a server-controlled sample driver for the UI. Keep the production HMAC/trusted-producer boundaries; no signing secret or ingestion token goes to the browser. Prefer reusing the existing HMAC verifier: a server-issued read capability for a fixed public synthetic sample profile, backed only by an isolated synthetic history namespace. It must never mint signatures for arbitrary client-supplied IDs or grant real driver/history access; no signing secret is exposed. Production identity verification remains unchanged. Enabling this path needs explicit bounded namespace/session tests before local activation.

Generate real-network route geometries through GraphHopper, observed GPS with controlled noise, personal habits and community cohorts, plus correlated traffic/queue context. Runtime explanations use calculated features, overlaps and counterfactual cost differences. Generation policy and evaluation ground truth are recorded separately; never use expected reason/rank labels as runtime prediction input. Do not claim the simulator proves real-world driver motives.

The current 30-second simulator updates station/queue/traffic snapshots, not a fleet of virtual drivers. A separate finite producer/load runner submits GPS to the real API, with staggered 30-second schedules and a separate burst case. Vehicle metadata may use canonical model templates for virtual copies; report virtual identities/model-template use in the technical run record.

## Prerequisite correctness

Close the eight open findings in `docs/reports/energy-warning-and-project-review-2026-10-12.md`: atomic GPS/reset updates, shared replica location authority, invalid-station selection, impossible after-B projections, latest-as-of congestion, consistent route constraints, instant-based timestamp sorting, and honest unknown queue display.

## Completion gates

- Every fixed bug has a failing reproduction before the fix and a regression afterward.
- With-B, without-B and after-B plans work end to end; no unrelated default point/return leg, no invalid station selection.
- A regression demonstrates a station that finishes service earlier but completes the journey later loses under the new objective.
- Personal and community evidence each affect ranking; physical ETA stays unchanged when preference changes. Missing/partial evidence and zero durations are covered.
- Real PostgreSQL/Redis/GraphHopper/API tests include both replicas, concurrent GPS/reset/matching and snapshot changes.
- Desktop/mobile browser coverage includes goal changes during pending requests, all energy states, map picking, drawers, cost details and H3.
- Load reports show actual achieved event/recommendation rates, errors, latency distributions, backlog and familiarity availability. No mock engine or fabricated success counts. No numeric production SLA is invented; an overloaded stage is reported honestly.
- Canonical validator and 63-file integrity check remain clean; final independent review and the open-finding ledger are reconciled.
- No new infrastructure/framework, production auth rollout, model-training claim or Week 6 productionization is implied.
