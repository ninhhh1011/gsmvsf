# Coverage-driven paired road benchmark

Implemented on `feat/route-weight-calibration`; runtime ranking remains **80/10/10**.
No merge, remote push, application-image rebuild or production-capacity certification.

## Data and measured coverage

At fixed event time **2026-10-15T09:00:00Z**, the audit selected 240 uncovered local
reference-road targets at H3-8. Real GraphHopper produced 189 valid templates and
51 rejected targets; their reasons remain in `preparation.json`. Greedy additional
sampled H3-11 footprint selected 120 templates across 83 H3-7 origin groups. This is
a bounded selection proxy, not an optimal road-length or junction-cover solver.

| Same-time measurement | Before | After |
|---|---:|---:|
| Paired runtime trips | 1,195 | 1,657 |
| Distinct continuous observed paths | 575 | 1,037 |
| Candidate-reference proximity coverage | 12.32% | 15.81% |
| Covered reference road length | 1,237.731 km | 1,589.041 km |

Additional coverage is **351.310 km**, approximately **3.49 percentage points**.
Both audits use the same 331,228 deduplicated physical reference segments,
10,048.745 km denominator, event time, seven-day window, bbox, 12 m buffer and
EPSG:32648 lengths. This is approximate GPS proximity, with potential nearby-road
overcounting. Verified directed-access, junction-maneuver and all-Hanoi coverage
are not established. Generation stays inside the configured/imported map intersection.

## Frozen evidence and evaluation

Each template has FOLLOW, EXIT, EXIT_LATE, RETURN_EXIT, REROUTE, GAP and NOISE.
Initial guidance and revisions remain paired with observed coordinates/times.
Origin-group hashes assign every template variant to one split before detection;
driver identities and event-time ranges are disjoint. Paths can cross groups.

| Split | Templates | Trips | Stored in runtime |
|---|---:|---:|---:|
| Train | 66 | 462 | 462 |
| Validation | 34 | 238 | 0 |
| Test | 20 | 140 | 0 |

Direct database checks confirm train identity equality and zero validation/test
records for batch **`1037fa5ae229`**. Generated records and offline declarations
reproduce exactly from its frozen manifest. No maneuver labels enter runtime
analysis or ranking; this workflow does not populate familiarity ranking histories.

On test, 60 declared departing trips were detected, and none of the 80 designed
non-departure controls produced a departure. These are same-generator synthetic
trip-level results, not field accuracy. **85 events were detected against 80 declared**,
with absolute event-count error 5. Unknown evidence remains visible: the test group
contains 84 uncertain intervals, including 64 from guidance-update controls. A
zero false-positive trip count does not establish fully understood route intervals.
All split/scenario counts are in the companion JSON.

Real generation exposed a short-route GAP defect: removing 20 observations could
remove the tail rather than create an interior gap. A failing regression reproduced
it. Benchmark generator revision 2 preserves both sides with a 70-second gap;
all 120 generated GAP controls were checked. Legacy generation is preserved.
The initial defective batch `425cb09b121e` was retired in one transaction only
after its complete 462-key set matched its saved input backup. The same frozen
road geometry/splits were reused for revision 2; historical batches were untouched.
The detector and scenarios were not tuned to improve measured detection outcomes.

## Verification and status corrections

- Backend: **765 passed, 12 skipped**; focused generation/coverage/detector tests: **32 passed**.
- Ruff passed. No diff in runtime ranking code; 80/10/10 remains fixed.
- All **63 canonical files** match tracked Git blob hashes.
- Four existing APIs returned readiness **200**. Docker had stopped between turns;
  existing containers were restarted without rebuilding images.
- Independent read-only review of implementation commit `4af55ed` found no important
  defects, reran 32 focused tests and checked split/gap artifacts. Final summary
  values were separately checked against generated JSON and direct database proof.

AGENTS/README now distinguish historical Week 6 completion (`be5a9c2`, tag
`week6-productionization-complete`) from current single-host deployment readiness.
Public deployment, failover and a production load target remain unverified here.
The earlier standalone weight experiment now explicitly states that its generator
changed after held-out inspection, so its gain is exploratory.

## Artifacts and reproduction

The [machine-readable report](guided-data-quality-2026-10-16.json) is committed.
Detailed local artifacts live under `runtime/guided-quality-20261015/`:
`before/`, `seed-v2/`, `after-v2/`, `verification.json`, `canonical-integrity.json`,
`retired-batch.json`, `backend-final.log` and `verification-run.log`. The initial
`seed/` directory is retained solely as the defective batch's backup.

Reproduce this existing batch from this worktree with an accessible `DATABASE_URL`
and `DATASET_PATH`. Keep the existing frozen `before/local-targets.json` intact:

```powershell
python -m scripts.audit_guided_coverage --as-of 2026-10-15T09:00:00Z --exclude-batch 1037fa5ae229 --output runtime/guided-quality-20261015/baseline-reproduced --target-count 240 --target-resolution 8
python -m scripts.seed_local_guided --targets runtime/guided-quality-20261015/before/local-targets.json --as-of 2026-10-15T09:00:00Z --seed 20261015 --benchmark --max-templates 120 --output runtime/guided-quality-20261015/seed-v2
python -m scripts.audit_guided_coverage --as-of 2026-10-15T09:00:00Z --output runtime/guided-quality-20261015/after-v2 --target-count 240 --target-resolution 8
```

The first command excludes this batch to reconstruct its baseline without deleting
records. For a new experiment, run a fresh pre-audit before ingestion and use a new
output directory. Do not overwrite the frozen target file used by the seed
manifest: its content hash is checked. Existing seed retries reuse frozen
geometry and immutable trip identities. Changed seed/time/source/options require
a new output directory. These data and results do not establish a ranking lift or
real-driver behavioral preferences. No data replication was added merely to satisfy
public H3 privacy thresholds; some sparse cells can remain withheld.
