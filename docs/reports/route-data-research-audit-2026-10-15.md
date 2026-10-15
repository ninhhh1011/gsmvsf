# Route data and research audit — 2026-10-15

## Verified state

- Main inspected: `3a38205`. This audit does not regenerate data or deploy code.
- `week6-productionization-complete` resolves to `be5a9c2` (2026-09-23) and is an ancestor of main. Its historical report records concurrency, Redis shared state, metrics and readiness, but explicitly lists remaining production gaps. Current AGENTS/README statements treating all Week 6 work as future are stale.
- Live Docker Compose has four healthy API replicas, PostgreSQL, Redis, GraphHopper and frontend. All four direct API `/readiness` endpoints returned HTTP 200 during this audit. This does not verify application behavior, public deployment, endurance or failure recovery.
- The current architecture is one host with a single-node data plane. Historical load evidence in `journey-ranking-scale-up-2026-10-13.md` includes 503/504 failures at larger loads; it is not a present-day capacity measurement.

## Data findings

The 2026-10-15 coverage report records 1,195 paired runtime trips, 575 distinct continuous GPS paths and 12.32% candidate-reference proximity coverage (1,237.731 / 10,048.745 km). These are historical fixed-time measurements, not fresh database counts or authoritative drivable-road coverage. The earlier 48,535 legacy histories had eight repeated footprint patterns. More repeated trips do not repair spatial coverage.

The latest local cohort contains 77 FOLLOW controls and 308 stress trips; 231 stress trips depart, with 320 detected events versus 308 declared events. Its deliberately selected 75% departure rate cannot estimate field prevalence. The 80 withheld records use the same generator and may overlap geographically, so they do not establish geographical generalization.

`seed_local_guided.py` and `seed_guided_hanoi.py` already construct real GraphHopper guidance and paired observed road paths. Reuse these producers; a new random feature-only training generator cannot substitute for road evidence.

## Algorithm and evaluation gap

`backend/app/services/ranking/service.py` still uses 80/10/10 time and familiarity scoring. Paired departure detection supports inspection and H3 statistics separately. There is no demonstrated measured improvement from feeding departure experience into ranking. Familiarity is not equivalent to compliance, and an alternative candidate not chosen is not necessarily an abandoned route.

The calibration experiment on this branch is an optimizer demonstration only. Generator latent weights were changed after inspecting held-out outcomes, so its reported 2.5 percentage-point improvement is exploratory and cannot be presented as independent validation. Retire that result as evidence for production weights. Future evaluation must freeze generation assumptions and split assignments before tuning, and retain an untouched final test set.

## Proposed next implementation

1. Agree on the target road envelope. Measure eligible directed road length, junction maneuvers, road classes and geographical strata; distinguish unavailable map from unsampled roads. Where access eligibility is unknown, report the candidate-reference denominator explicitly.
2. Select a compact route library by marginal additional road/junction coverage, not raw trip count. Freeze each initial guidance path, guidance revisions and timestamps. A planned route is a reference, not proof of an optimal route.
3. Pair each selected corridor with FOLLOW, alternate branch, late exit, return-and-exit, legitimate guidance update, GPS gap and parallel-road/noise controls. Allocate cases by coverage deficits and maneuver strata, with counts reported separately. An intentionally balanced stress suite must remain separate from behavioral prevalence estimates.
4. Freeze independent truth from the road construction/maneuver schedule before running the detector. Split by corridor/template and driver, with a later-time evaluation; prevent variants of the same template leaking across splits. Maintain separate in-distribution and unseen-corridor evaluations.
5. Evaluate detection first: trip/event precision and recall, exit localization distance, confirmation delay, false alarms and unknown fraction. Then compare identical candidate sets under time-only, fixed 80/10/10, personal-only, community-only and the proposed learned approach. Report actual decision outcomes, normalized time/energy cost and uncertainty over independent trips/corridors. Do not equate a ranking mismatch with measured abandonment.
6. Connect departure evidence to ranking only after the independent evaluation shows value; preserve EV eligibility and physical constraints. Data shortages and non-identifiability must remain visible.
7. Reconcile historical Week 6 completion with current deployment gates: reproducible build/release, required identity boundary, monitoring/alerts, recovery checks and a measured load target. A historical tag is not current production certification.

## Positioning

EV charging-aware planning and learning driving preferences already exist: Iternio/ABRP (https://api.iternio.com/swagger-ui/) and Google Research's route-choice learning (https://research.google/blog/world-scale-inverse-reinforcement-learning-in-google-maps/). Do not claim these categories as new inventions.

The defensible project question is whether causal, paired guidance/departure evidence improves EV candidate ranking under limited local history while bounding additional journey time and preserving energy feasibility. This is a research question to test, not a superiority claim already established by the repository.

## Limits

No dataset rebuild, current coverage recomputation, full regression suite, new load test or field study was performed in this audit. Target geography remains a user decision. Existing canonical data and deployed services were not mutated.
