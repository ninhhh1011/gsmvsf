# Local-road coverage and synthetic departures

Implemented on `feat/h3-departure-statistics-7d`; no merge/push, Dataset V1 edit,
new dependency, routing/ranking change or Week 6 activation.

## Scope and implementation

Live GraphHopper 11 `/info` reports `[105.735296,20.666476,106.049376,21.135483]`
(west,south,east,north). Configured service bounds are `[105.6,20.8,106.1,21.25]`.
New journeys stay within intersection `[105.735296,20.8,106.049376,21.135483]`,
including intermediate route geometry. This is an availability envelope, not a
Hanoi administrative boundary. No PBF import or canonical map expansion occurred.

The audit targets measured gaps on residential/service/living_street/tertiary/
unclassified reference roads, one origin per H3-7 cell, with nearby H3-9 vias.
Short GraphHopper journeys replace repeated major-road hubs for this new batch.
Requested endpoints/vias must snap within 35 m. Real routes have bounded lengths;
no straight-line substitute or mock. Different departure indices, nearby branch
vias, GPS cadence and nonoverlapping per-driver schedules diversify the cases.

120 origins produced 93 route templates; 27 rejected targets remain in preparation
evidence. Rejections are reported rather than forcing remote snaps. Existing trips
are preserved. Source SHA, manifest and inputs support deterministic batch retries.
Analysis never filters a valid deviating case merely because it detects no event.

## Measured results

Fixed seven-day event time: **2026-10-15T04:30:00Z**. Batch: `6c688ea447a7`.

| Measure | Before | After |
|---|---:|---:|
| Paired runtime trips | 810 | 1,195 |
| Distinct continuous GPS paths | 267 | 575 |
| Candidate-reference proximity coverage | 7.86% | 12.32% |
| Covered reference road length | 789.767 km | 1,237.731 km |
| Residential covered length | 69.543 km | 228.362 km |
| Tertiary covered length | 75.031 km | 185.191 km |
| Service covered length | 28.744 km | 69.487 km |

Same 331,228 deduplicated physical reference segments / 10,048.745 km, same bbox,
12 m continuous paired GPS proximity and EPSG:32648 measurement. Before excludes
only this batch; no records were deleted. Available-map reference coverage happens
to equal the overall reference figure for this canonical reference set. It does
not mean all of the configured service area has an imported road graph.

| New runtime cohort | Trips | Drivers | Departing trips | Departing drivers | Detected events |
|---|---:|---:|---:|---:|---:|
| Coverage FOLLOW | 77 | 30 | 0 | 0 | 0 |
| Stress | 308 | 80 | 231 | 60 | 320 |

The 75% stress departing-trip rate is deliberately designed. It is not a real
driver prevalence estimate. Runtime maneuver intentions total 308 departure events;
detector outputs total 320. All 231 intended departing trips were detected, but
event segmentation differs by 12 and must not be described as exact event accuracy.
The UI explicitly labels stress and allows separate cohort inspection. Default
all-source retains old paired data and gray legacy footprints. At this time the
aggregate includes 43,631 legacy-only histories; filtered cohorts include none.

80 held-out journey records (16 templates) are not stored: direct database query
finds zero. FOLLOW: 32/32 without departure; EXIT: 16/16 detected; EXIT_LATE: 16/16;
RETURN_EXIT: 16/16 with 32 detected events. These controls use the same generator
and may share roads with runtime data; they are not geographical or field validation.

## Verification and evidence

Backend: 757 PASS / 12 existing skips plus 3 separate evaluation PASS (760 total).
Frontend tests, Ruff, canonical validator and Dataset hashes are recorded under
`runtime/h3-local-20261015`.
Canonical validation: 152 PASS / 0 FAIL, 22/22 scenarios; 63 file hashes unchanged.
Frontend: 275 PASS. Browser: 22/22 aggregate and 30/30 inspector checks on desktop/
mobile, with remote tiles deliberately aborted. Cohort selection, counts, scope
warning and pan/zoom retention verified against the local real API/database.
Independent review found no remaining blockers after the intermediate-point scope
guard and record-level hold-out wording corrections.

Evidence: `before/coverage-summary.json`, `seed/manifest.json`, `seed/preparation.json`,
`seed/source-targets.json`, `seed/{coverage,stress,held_out}-inputs.json`,
`seed/evaluation_truth.json`, `seed/seed-report.json`, `live-cohorts.json`,
`dataset-integrity.json`; after audit `runtime/h3-coverage/coverage-summary.json`.
Browser results/screenshots: `runtime/h3-departures/browser` and
`runtime/h3-evidence-browser`. These are generated evidence, not canonical data.

## Remaining limits

Coverage is still 12.32% of candidate reference length, not complete city coverage.
Complete motorcar access and district boundaries are absent; eligible-road coverage
stays null. Proximity can count nearby parallel roads. Missing map areas need a
separately approved map expansion. More records alone cannot fix those limits.
External OSM tile network availability was not certified by isolated rendering
checks. Existing seven-day expiry, privacy and backend work limits remain active.
