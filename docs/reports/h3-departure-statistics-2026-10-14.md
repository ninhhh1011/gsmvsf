# H3 departure statistics branch report

## Current journey-only coverage and source expansion

The owner approved gray legacy footprints and a separate road-based paired batch.
The browser renders only journey-supported cells at the chosen resolution, clips
locally on pan and caps visible polygons at 500. There is no geographic background
grid or automatic resolution reduction. Hexagons cover areas: a road-backed cell
can overlap buildings/water; it does not claim those areas were driven through.

At `2026-10-14T03:00:00Z`, all 48,535 old synthetic journeys in the window contribute
approximate gray footprints from eight repeated resolution-11 signature arrays.
Legacy completion time selects the cohort; no point times or guidance are invented.
The new batch `ab4aa5d760c9` adds 360 paired trips on 12 real GraphHopper corridors,
108 distinct observed geometries, alongside the earlier 30 small controls. Combined
resolution-9 evidence: 649 cells, 505 with known departure ratios and six red cells.
Only paired guided exposure enters ratios; legacy visits cannot inflate denominators.

FOLLOW/REROUTE/NOISE/GAP controls produce zero departures. EXIT detects 70 events
and RETURN_EXIT detects 130, versus declared maneuvers of 60/120. These paths can
cross the guidance corridor multiple times; the counts do not establish perfect
truth agreement or field accuracy. Offline declarations never enter runtime.

Latest verification: 742 backend PASS / 12 existing skips, 269 frontend PASS,
Ruff PASS, canonical validator 152/0 and 22/22, 63 unchanged SHA-256 files,
nine real engine/isolated DB/API groups and 16/16 desktop/mobile browser checks.
Independent review found no remaining material issue after the replay anti-join fix.

Branch: `feat/h3-departure-statistics-7d`, forked from
`feat/h3-deviation-heatmap` at `e8b1ede7797711288d60f4b181b72d784d5daacb`.
Owner requires separate merge permission. No merge or remote push performed.

## Behavior

The default H3 mode renders journey-supported cells at the selected resolution,
clipping locally on map pan with an explicit 500-visible-cell cap. Gray means missing
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
completed paths, without paired guidance. They remain intact; their gray footprints are retained without departure weights.
There is no attempt to turn visit counts into exits or reconstruct old guidance
using present-day routing. The new paired table is separate. The original local review
database contained 30 deliberately synthetic paired cases in its synthetic namespace
only, stable batch `f959ddf3771d`, ending at `2026-10-14T03:00:00Z`.

Independent fake cases cover noise, one long exit, repeated exit after return,
guidance changes, observation gaps and starting away from guidance. Offline truth
is written before detection and never read by runtime. Additional regressions cover
upstream return, unobserved tails, stale responses and cancellation during replay.
One genuine 7,200.63 m GraphHopper path supplies an identity-route control; fake
maneuvers in the earlier 30-control batch are simple geometric fixtures, not claimed
road-valid trips. The new 360-trip batch uses the recorded GraphHopper road geometry.

## Verification

| Check | Result | Evidence |
|---|---|---|
| Backend main batch, excluding only separately run evaluation file | 739 PASS / 12 existing skips | `runtime/h3-departures/backend-history-complete.txt` |
| Complete Week 5 evaluation file, separate process | 3 PASS | `runtime/h3-departures/backend-history-evaluation.txt` |
| Total backend | 742 PASS / 12 existing skips | Both batches above cover all backend test files |
| Frontend complete suite | 269 PASS | `runtime/h3-departures/frontend-history-release.txt` |
| Ruff, backend and changed Python scripts | PASS | Executed on current source |
| Canonical validator | 152 PASS / 0 FAIL, 22/22 scenario assertions | `runtime/h3-departures/validator-history.txt` |
| Dataset SHA-256 comparison with pre-migration manifest | 63 identical files | `runtime/h3-departures/dataset-integrity.json` |
| Independent cases, real GraphHopper and isolated PostgreSQL/API | 9 groups PASS | `runtime/h3-departures/history-verification/verification.json` |
| Live desktop/mobile branch browser | 16/16 PASS, no page errors | `runtime/h3-departures/browser/results.json` |
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
Screenshots: `runtime/h3-departures/browser/desktop-journey-footprint.png`,
`mobile-journey-footprint.png`, `desktop-departure-popup.png`, `mobile-departure-popup.png`.

## Expanded source verification and query budget

The disposable DB regression also verifies that a future same-ID paired completion
does not erase a legacy footprint at an earlier replay time, and that adding legacy
footprints does not change the guided numerator/denominator. Python deduplicates
legacy driver IDs for privacy; paired observations may remain gray when guidance
comparison is unknown.

The first expanded browser run exposed a real five-second statement timeout.
EXPLAIN showed 5.11 seconds sorting toasted legacy arrays. Removing unnecessary
SQL ordering/DISTINCT avoids that sort; per-cell time predicates are materialized
once to avoid repeated evaluation during aggregation. No timeout increase or mock
fallback. Local post-change timings: metadata 0.164 s, paired cells 0.614 s, legacy
footprints 2.571 s (`runtime/h3-departures/query-timing.json`). This is a local sample,
not a load-capacity claim. Work caps also bound legacy trips/groups/group cells at
100,000/2,000/100,000; overflow remains 503, never partial ratios.

New source report: `runtime/h3-road-journeys-20261014/seed-report.json`.
Manifest and offline declarations are kept beside it. Canonical Dataset and old
history rows remain untouched. The new batch only writes paired synthetic evidence;
it does not populate ranking history or change production containers.
