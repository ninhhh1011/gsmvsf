# H3 evidence and coverage extension

Owner approved the five-part proposal: coverage audit, diverse paired synthetic
journeys, two route-similarity denominators, complete deviation paths, and evidence
copy. Continue on feat/h3-departure-statistics-7d; no merge/push, no Week 6 rollout.

Keep departure-origin statistics distinct from continuous observed deviation paths.
Green means no confirmed departure origin in the eligible sample, not proof that
the whole trip followed guidance. Gray means unknown/unpaired; expose supporting
trips and uncertainty. Whole-trip comparison retains its two existing geometric
coverage denominators and frozen-guidance semantics.

Add timestamped per-trip inspection using the active guidance version. Classify
continuous intervals only when both observations are unambiguous, same guidance,
and within the existing continuity limits. Confirm off-route runs before coloring
them red; pending runs, gaps, ambiguous locations and unobserved tails stay unknown.
Report observed distance/time, confirmed off-route distance/time, unknown time,
departure origins, version boundaries, and both frozen-route coverage percentages
separately. Guidance updates never manufacture exits or bridge a gap.

Public examples are explicitly synthetic, gated by enabled synthetic namespace and
existing public_synthetic_sample capability. No arbitrary/private history reader.
User-supplied inspection does not look up history or mutate evidence. Bound payload
and comparison work; run geometry off the event loop. Reuse installed Leaflet and
current geometry helpers; frontend only renders backend evidence.

Audit seven-day completed paired GPS against deduplicated physical canonical road
geometry, report covered reference length and gaps by geographic regions. Canonical
CSV has road_type/access but not complete motorcar permissions or district borders:
candidate road coverage is approximate, eligible-road coverage remains unavailable
until the engine verifies those roads. Never call this authoritative Hanoi coverage.
Exclude nonmotor road classes and explicit restricted access; retain provenance,
projection/tolerance/time semantics. Do not consume any labels. Target uncovered
regions for additional real GraphHopper synthetic routes; report before/after road
coverage and valid-route failures instead of trip/hex count as a coverage metric.

Independent fixture truth is authored before detection; road-based declared maneuvers
are intent, not perfect event ground truth. Keep development/evaluation cases
separate and report disagreements. Preserve Dataset V1 and all existing histories.
