# Trip evidence and spatial coverage — branch report

Owner approved the five-part extension on `feat/h3-departure-statistics-7d`.
No merge/push, ranking change, new dependency or Week 6 activation.

## Behavior

Aggregate green means no confirmed departure origin in the eligible sample,
not full-trip adherence; popup explains 0/5 and uncertainty. Gray legacy footprints
do not enter departure denominators. Canvas remains uncapped and retains all
aggregate cells through pan/zoom.

The new [inspector](http://127.0.0.1:8005/demo/static/journeys.html) shows curated
synthetic paired evidence. It renders initial/current guidance, confirmed red
deviation paths, verified on-corridor intervals, unknown intervals and approximate
H3-origin markers. Backend returns duration/distance and both existing initial-route
coverage denominators. Active guidance drives interval states; a guidance change
is not a departure. No line joins missing GPS or a version boundary.

Unobserved head/tail time is explicit UNKNOWN with no connector. Missing continuity,
zero movement and comparison work limits withhold whole-route percentages. A long
valid observed path exceeding the 100 km whole-route comparison budget still returns
its valid interval inspection, with the reason displayed. Unknown distance across
a missing segment is not invented. The UI renders backend evidence and rejects
stale responses; unknown lists over 100 explicitly disclose the displayed subset.

Public examples require enabled familiarity, public_synthetic_sample and a synthetic
repository. Selection is restricted to generated h3-road driver-zero cases, bounded
to 12 and stripped of original identities. Caller inspection is stateless and
bounded to 2 MB / existing point/comparison budgets. No arbitrary realtime/private
history reader. Coverage API serves only the fixed validated synthetic report.

## Measured spatial gap and targeted source expansion

Same event time: `2026-10-14T07:00:00Z`, preceding seven days.
Reference bbox: latitude 20.8–21.25, longitude 105.6–106.1, from existing configuration.
Deduplicated physical candidate roads: 331,228; reference length 10,048.745 km.

| Measurement | Before | After |
|---|---:|---:|
| Paired completed journeys | 390 | 810 |
| Distinct continuous GPS paths | 127 | 267 |
| Candidate reference length near GPS | 371.944 km | 789.767 km |
| Candidate proximity coverage | 3.70% | 7.86% |

Coverage uses 12 m buffered continuous paired GPS, EPSG:32648 lengths, physical
road deduplication and canonical road_type/access filtering; explicit restrictions,
nonmotor classes and patched way 881947000 are excluded. No labels or legacy H3
centres supply this measurement. Entire roads are assigned to approximate geodesic
midpoint H3-5 buckets; target coordinates use that same midpoint. These are not
clipped areas or administrative districts. Region buttons locate the bucket.

Candidate permissions remain incomplete because the CSV lacks full motorcar access.
`eligible_road_coverage_pct` is deliberately null. Nearby parallel roads and bucket
boundary attribution limit interpretation. This is not authoritative drivable-road
coverage or all Hanoi coverage; it identifies reproducible evidence gaps.

Batch `d1a492ab9705` added 420 paired synthetic trips over 14 real GraphHopper
corridors through measured gap targets, with 126 distinct observed geometries.
All existing journeys were retained. Source manifest/truth/report:
`runtime/h3-gap-journeys-20261014/`. FOLLOW/REROUTE/GAP/NOISE controls record zero
departure events. EXIT records 85 versus 70 declared maneuvers; RETURN_EXIT records
170 versus 140 declarations. Repeated corridor crossings and geometric assumptions
mean these declarations are not perfect event ground truth; do not claim accuracy.
The new batch writes only paired synthetic evidence, not ranking history.

Before/after reports: `runtime/h3-coverage-before/coverage-summary.json` and
`runtime/h3-coverage/coverage-summary.json`. Before can be reproduced by excluding
the new source batch without deleting data. The initial audit's whole-union
intersection was slow; subdivision/spatial indexing of temporary geometry replaced
it. The interrupted query wrote only temporary audit tables. No application
timeout was increased or unavailable dependency replaced with a mock.

## Verification

| Check | Evidence |
|---|---|
| Backend main suite 748 PASS / 12 existing skips | `runtime/h3-departures/backend-evidence-final-complete.txt` |
| Complete Week 5 evaluation, separate process, 3 PASS | `runtime/h3-departures/backend-evidence-evaluation.txt` |
| Frontend complete suite 274 PASS | `runtime/h3-departures/frontend-evidence-final.txt` |
| Ruff PASS | Changed Python source/scripts/tests |
| Canonical validator 152 PASS / 0 FAIL, 22/22 | `runtime/h3-departures/validator-evidence.txt` |
| 63 canonical SHA-256 values identical | `runtime/h3-departures/dataset-integrity.json` |
| Held-out evaluation 16 PASS; no runtime trips written | `runtime/h3-evidence-evaluation/verification.json` |
| Inspector desktop/mobile 18/18 PASS | `runtime/h3-evidence-browser/results.json` |
| Aggregate desktop/mobile 18/18 PASS | `runtime/h3-departures/browser/results.json` |
| Independent review clear within scope | 33 targeted tests independently rerun; midpoint/boundary issues fixed |

Held-out evaluation has 12 independent synthetic maneuver/distance/continuity
fixtures and four separate live GraphHopper identity-route controls. Offline truth
is written before detection and never enters runtime. It does not calibrate field
accuracy. Browser rendering tests explicitly abort external tile requests; gray
tile failures remain an independent network/DNS limitation.

## Remaining limits

Data still covers only 7.86% of the candidate reference length by this proximity
metric. More road-valid paired observations are needed before making citywide
behavior claims. Real driver motivations and full access eligibility remain
unknown. Corridor thresholds require field calibration; long whole-route comparison
and unknown GPS remain explicit rather than false zeros. No production capacity
or numeric performance guarantee is introduced.
