# H3 departure statistics branch report

## Owner screenshot correction — current UI behavior

The owner clarified that coverage must originate from driver journeys, not a blank
geographic grid. The current UI therefore removes baseline grid generation and
viewport-driven resolution reduction. It displays only journey evidence at the
selected resolution. Empty history/outage produces no invented polygons. The 30
synthetic cases still occupy a small physical area; a few evidence cells do not
establish citywide behavioral coverage. Adding unpaired history as gray, unweighted
footprints remains a source-selection question, not assumed departure evidence.

Correction checks: 268 complete frontend tests PASS; six backend/API cross-language
contract tests PASS. The full backend/data verification recorded below applies to
the unchanged backend. Historical viewport-grid screenshots below are superseded
by `runtime/h3-departures/browser/desktop-journey-footprint.png` and
`mobile-journey-footprint.png` from the correction browser check.

Branch: `feat/h3-departure-statistics-7d`, forked from
`feat/h3-deviation-heatmap` at `e8b1ede7797711288d60f4b181b72d784d5daacb`.
Owner requires separate merge permission. No merge or remote push performed.

## Behavior

The default H3 mode renders a complete viewport grid, coarsening detail as needed
instead of limiting coverage to the static 425 visit cells. Gray means missing
comparison evidence. Red reflects the percentage of distinct guided trips that
begin departing in a cell during the preceding seven days. Every confirmed exit
counts separately; a trip counts once per cell in each ratio denominator/numerator.
Popups show the percentage, departing/reached trip counts and total exit events.
Whole-trip two-route comparison remains a separate selected mode.

Guidance effective at observation time is compared against timestamped observations.
Guidance changes reset state, return followed by another exit rearms, including a
return to an earlier portion of the route. Gaps, ambiguity, unconfirmed exits and
unobserved completion tails do not establish zero-departure contributions. Replay
refreshes at current observation time and rejects stale time/mode/toggle/trip work.
Ranking and Dataset V1 are unchanged.

## Actual data audit

Real PostgreSQL inspection found 15,001 realtime and 48,535 synthetic legacy
completed paths, without paired guidance. They remain intact and are excluded.
There is no attempt to turn visit counts into exits or reconstruct old guidance
using present-day routing. The new paired table is separate. The local review
database contains 30 deliberately synthetic paired cases in its synthetic namespace
only, stable batch `f959ddf3771d`, ending at `2026-10-14T03:00:00Z`.

Independent fake cases cover noise, one long exit, repeated exit after return,
guidance changes, observation gaps and starting away from guidance. Offline truth
is written before detection and never read by runtime. Additional regressions cover
upstream return, unobserved tails, stale responses and cancellation during replay.
One genuine 7,200.63 m GraphHopper path supplies an identity-route control; fake
maneuvers themselves are simple geometric fixtures, not claimed road-valid trips.

## Verification

| Check | Result | Evidence |
|---|---|---|
| Backend main batch, excluding only separately run evaluation file | 734 PASS / 12 existing skips | `runtime/h3-departures/backend-release.txt` |
| Complete Week 5 evaluation file, separate process | 3 PASS | `runtime/h3-departures/backend-evaluation-release.txt` |
| Total backend | 737 PASS / 12 existing skips | Both batches above cover all backend test files |
| Frontend complete suite | 267 PASS | `runtime/h3-departures/frontend-release.txt` |
| Ruff, backend and changed Python scripts | PASS | Executed on current source |
| Canonical validator | 152 PASS / 0 FAIL, 22/22 scenario assertions | `runtime/h3-departures/validator.txt` |
| Dataset SHA-256 comparison with pre-migration manifest | 63 identical files | `runtime/h3-departures/dataset-integrity.json` |
| Independent cases, real GraphHopper and isolated PostgreSQL/API | 8 groups PASS | `runtime/h3-departures/verification.json` |
| Live desktop/mobile branch browser | 14/14 PASS, no page errors | `runtime/h3-departures/browser/results.json` |
| Independent final code review | No remaining material blocker within scope | Reviewer independently reran detector/API and frontend regressions |

The initial single-process broad run encountered a transient snapshot dependency
failure; the next broad run encountered pandas C-parser out-of-memory on a canonical
CSV. Those cases passed on isolated rerun. Final coverage uses two fresh processes
without omitting either test. No application timeout was increased and no runtime
failure was converted into a mock or synthetic fallback.

Disposable-database checks exercised real trusted HTTP ingestion, idempotent retries,
distinct-trip/event aggregation, seven-day time bounds and production cohort privacy.
At the coarse origin cell, 20 comparable trips, 10 departing trips and 15 events
were verified; uncertain gap contributions were excluded. SQL aggregates at the
requested effective resolution, avoiding duplicated trips from adding child counts.

## Review and limits

Review reproduced and fixed uncertain-zero denominators, earlier-progress return,
stale mode-switch responses, replay time refresh, cancelled replay mutation and
unobserved trip tails. Raw paired evidence is immutable; matching retries recompute
derived analysis. Operators must use a consistent detector version across producers.

The 45 m / 60 degree corridor, three-observation / 30 m confirmation, 60-second gap
and 200 m jump limits are project assumptions, not field calibration. Exit origins
are last unambiguous guided positions, not verified road junctions. Aggregation is
limited to completed trips and sampled guided exposure; uncertain outcomes are
excluded and are not proof of adherence. Fake cases validate machinery, not Hanoi
driver behavior, motivations or citywide behavioral coverage. Production small
cohorts are suppressed; work over 10,000 paired trips returns explicit 503.

The paired collector is a trusted-producer HTTP contract. Old histories and ordinary
anonymous route requests are not silently converted to paired trips. Producers
must supply the original active guidance and time-ordered observations. No new
dependency, production-capacity claim, ranking change or Week 6 rollout is included.

Review UI: [local branch demo](http://127.0.0.1:8005/demo). The existing API containers
were not rebuilt or restarted. Separate local review process uses synthetic history.
Screenshots: `runtime/h3-departures/browser/desktop-city-grid.png`,
`mobile-city-grid.png`, `desktop-departure-popup.png`, `mobile-departure-popup.png`.
