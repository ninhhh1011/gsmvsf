# Frontend optional destination and authoritative station plans

Implemented 2026-10-12 in the approved journey ranking branch.

- A and B start absent. Explicit map A or accepted GPS supplies origin. B can be picked/cleared; after-B is disabled without B.
- Station target and passenger destination remain separate, including changing stations without B.
- Station selection calls `/api/v1/station-plan` using station/service identity and original telemetry; it reuses returned geometry and physical timing. Generation, route revision and energy revision reject late selections.
- After-B recommendations send original A telemetry and B to backend. Frontend does not forecast positive SOC/range or force a station-to-B return.
- Drawer queue uses effective wait, labels assumed queue estimates, blocks unknown/ineligible station actions. Physical completion total and ranking preference score remain separate.
- Cost detail shows backend score components and familiarity evidence. No invented driver motive, demo badge or history picker.
- Client accepts only server-provided fixed sample identity/signature from config and forwards the read signature, never a signing secret.
- Extracted station planning into `ui/station_planning.js`; controller remains DOM-free and below its line ceiling. No dependencies added.

## Verification

Failing reproductions before fix: `node --test tests/frontend/test_optional_destination.mjs` initially 0 PASS / 2 FAIL (forced B and unknown queue shown zero).

Final `node --test tests/frontend/*.mjs`: 223 PASS / 0 FAIL; log `runtime/frontend-scale-tests.txt`.

`git diff --check`: clean.

New tests cover no-B confirmed geometry and changing station, stale telemetry during selection, original zero-energy after-B requests, after-B prefix subtraction, station-arrival wording and scoped read-signature forwarding. Existing navigation fixtures now mock the authoritative station-plan endpoint while retaining asynchronous/race assertions.

## Remaining integration verification

Root must run new desktop/mobile browser and real API plan/config tests. This frontend result does not establish live station eligibility, energy calibration or real-world causes. Synthetic provenance remains internal as approved.

## Review round 1

Closed the five findings in frontend-review.md:

1. Selected reroutes revalidate the same composite pair and plan mode through station-plan; unlocked replies require generation/route/energy revision. Recommendation previews use confirmed constrained geometry instead of independent `/route` legs. Map preview accepts backend coordinate arrays.
2. Drawer preserves each station/service pair, with rank ordering, service filters and exact action identity. Top-5 remains five unique stations; each may expose multiple services.
3. Connected completion recommendation uses total physical journey time and weighted ranking explanation. Unknown queue remains unknown; assumptions are displayed.
4. Active and completed route evidence prefers selected plan's freshly confirmed ranked_candidate; comparison ranking list remains separate.
5. Active visible/accessibility destination wording uses goal_role.

Before fix: added three regressions, 8 PASS / 3 FAIL (`round1-red.txt`).
After fix: full frontend 229 PASS / 0 FAIL (`round1-tests.txt`); `git diff --check` clean. Added selected-evidence, role-wording and stale-reroute tests too.

Remaining live/browser verification belongs to root. AFTER plans need attention if revalidated after already passing B: backend currently accepts mode, not a journey stage. This limitation was sent to root for integrated handling; no production stage-completion claim is made here.

## Journey navigation stage follow-up

Closed the integration gap after already passing intermediate B/station. Backend plan waypoints identify cumulative actual-geometry indices. Frontend confirms passage through monotonic on-route projection; a 100m proximity check no longer unlocks navigation or claims service completion. Off-route projections cannot advance confirmed segment progress.

After B passage, station replanning and drawer requests omit B and use BEFORE_DESTINATION station-only requests while retaining original passenger destination locally. After station passage in a BEFORE plan, rerouting goes directly to passenger B using the last confirmed domain constraints. Reset/new goals clear stages; refreshed plans preserve accepted stage state. Station passage is navigation evidence only, never proof of charging/swap completion.

Failing stage regressions before fix: 14 PASS / 2 FAIL (`stage-red.txt`). Final full frontend: 234 PASS / 0 FAIL (`stage-tests.txt`); diff check clean. Additional checks cover projection proof, new-goal reset and API constraint forwarding.

Real-browser replay and API integration remain root verification responsibilities.

## Review round 2: filtered fallback identity

Reproduced both directions: a mixed station with only charging eligibility regained a charging action under SWAP, and only swap eligibility regained a swap action under FAST_DC. Before fix: 19 PASS / 2 FAIL (`round2-red.txt`).

The card resolves the requested service from the active filter before selecting either ranking or candidate evidence, including the unranked fallback. Filtered-out services cannot restore their action, score or badge. Final full frontend: 236 PASS / 0 FAIL (`round2-tests.txt`); diff check clean.

Browser/API integration remains root verification.

## Live-browser snapshot authority correction

The chooser previously ran a separate candidate endpoint beside recommendation, mixing static catalog OFFLINE evidence with current PostgreSQL OPEN eligibility. Reproduced both before/no-B and AFTER evidence propagation: 21 PASS / 2 FAIL (`snapshot-ui-red.txt`).

Drawer refresh now makes one `/recommend` workflow request and takes `candidate_details` from that same backend result for both modes. Ranked/current pair eligibility controls actions; stale static station flags cannot disable the pair. Operating status is displayed from the ranking feature snapshot, with no invented static fallback. Unknown/unranked cards remain unselectable. Existing generation/route/energy/latest-request guards remain intact.

Final full frontend: 238 PASS / 0 FAIL (`snapshot-ui-tests.txt`). Root still owns real-browser rerun and snapshot/API integration evidence.

## Optional-goal labels and header contrast

The drawer now says A ➔ Trạm with no remaining B, and A ➔ Trạm ➔ B when B is available. The clear-B action is hidden/disabled when no B exists. After B passage, the remaining station-only label is retained and the after-B option is disabled. The existing semantic binding updates these states, with a new failing-before/passing-after DOM binding regression.

Raised `.brand-subtitle` from shared light-surface muted text to existing slate #cbd5e1 on header #0f172a, giving computed contrast 12.02:1. No layout/redesign changes.

Before: focused bindings 10 PASS / 1 FAIL (`intent-label-red.txt`). After: full frontend 239 PASS / 0 FAIL (`intent-label-tests.txt`); diff check clean. Root owns browser confirmation.

## Vehicle-model navigation invalidation (2026-10-13)

Reproduced car-to-swap-only selection persistence, already-passed B persistence, and missing profile replan with three failing focused tests before the change (same-model control passed).

Actual model changes with a trip pause replay and use existing destination reset/revision and custom-route helpers. They invalidate selected station/service, cost evidence, route and matching evidence while retaining current A, SOC percentage and only outstanding passenger B. With B, ordinary A-to-B routing uses the new domain vehicle category; without B, station-only lookup requires a fresh explicit station choice. A pending route keeps its passenger goal so rapid further model changes invalidate the older profile result. Same model preserves committed navigation.

Added five regressions: swap-only compatibility, passed B, station-only lookup, rapid pending-profile changes and same-model preservation. Existing power-only tests now explicitly omit a navigation trip rather than triggering routing through incomplete API fixtures.

Verification: covering tests 38 PASS / 0 FAIL (`vehicle-model-focused-tests.txt`); full frontend 244 PASS / 0 FAIL (`vehicle-model-frontend-tests.txt`); `git diff --check` clean. No backend or canonical Dataset edits. Real-browser model-switch verification remains root work.

## Assignment caller regression correction (2026-10-13)

Independent review identified automatic `assignTrip` model initialization being treated as a manual vehicle switch. A failing regression reproduced historical identity replaced by CUSTOM_TRIP, lost causal start time/trajectory and an extra generation reset (`vehicle-assignment-red.txt`).

Automatic assignment now awaits model initialization with navigation replanning explicitly disabled, then checks its generation. User-triggered switches retain the default reset/replan behavior. The regression checks original historical trip identity, causal time, loaded trajectory, new domain route profile and assigned state.

Final covering tests: 39 PASS / 0 FAIL. Full frontend: 245 PASS / 0 FAIL (`vehicle-model-frontend-tests.txt`); diff check clean. Browser verification remains root work.
