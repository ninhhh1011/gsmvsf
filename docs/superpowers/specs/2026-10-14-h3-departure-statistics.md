# Seven-day H3 departure statistics

Authorized in this conversation on 2026-10-14. Work only on
`feat/h3-departure-statistics-7d`; do not merge without the owner's permission.

## Product contract

Owner's screenshot correction: coverage means cells supported by driver journeys,
not a geographic grid across the viewport. Show those cells without selecting a route. Aggregate all
guided trips in the seven days ending at the selected event time. Red indicates
where trips begin leaving the guidance effective immediately before departure,
not traffic frequency, familiarity, or the entirety of a divergent path. Count
every confirmed departure, rearming only after a confirmed return. A trip counts
once per cell in the denominator and numerator; departure event counts may be
larger. Denominator means guidance passed through the cell and the observed trip
reached that guided corridor. Missing evidence is unknown, never zero departures.
Guidance updates reset comparison state without manufacturing a departure.

Persist immutable paired guidance versions and timestamped observations through
trusted ingestion. Keep old unpaired histories intact and report their exclusion.
Do not manufacture past guidance by routing old endpoints today. Completed trips
only; neither unfinished trips nor future completion evidence enters a replay.
Filter individual exposure/departure times to the seven-day window too.

## Implementation assumptions and limits

Reuse the existing geometric corridor (45 m lateral, 60 degree heading tolerance),
H3 and asyncpg. Confirm departure/return with at least three sequential observations
and 30 m of travel. Gaps over 60 seconds, jumps over 200 m, implausible movement,
ambiguous projection and insufficient confirmation break evidence continuity;
do not bridge them. These are transparent project assumptions, not calibrated
real-driver behavior. Mark the last unambiguous guided location before confirmed
departure as an approximate departure origin, not an exact road-junction ID.

Keep the user's selected H3 resolution; do not coarsen based on empty viewport area.
Render only cells returned from journey evidence, clipped to the viewport, with
an explicit 500-visible-cell cap. No evidence means no invented grid cells. Never
add child-cell percentages. Whether to add gray footprints from unpaired legacy
journeys remains an explicit source-selection question; their departure weights
must stay unavailable, not reconstructed or inferred from visits.
Keep whole-trip offline comparison as a separately selected mode. Production
aggregate cells require at least five contributing drivers; synthetic statistics
are explicitly identified. No raw third-party routes/identities in public output.
Bound geometry/ingestion and query work; expose outages and missing schema.

Synthetic verification uses independently authored scenarios with separate offline
truth. It verifies counting, not Hanoi behavior or motivations. Existing repeated
route templates are not departure evidence. No new dependencies, ranking changes,
Dataset V1 changes, or Week 6 infrastructure.

## Acceptance

Paired evidence ingestion is validated and idempotent; conflicting retries fail.
Noise produces no departure; one long divergence produces one; return then departure
produces two; guidance changes and gaps produce no invented departure. Window bounds,
distinct-trip aggregation and privacy are tested. Only journey-supported cells
are rendered, with backend percentages at the selected resolution.
An audit records actual PostgreSQL data gaps; deterministic synthetic evaluation
and real PostgreSQL/API/browser verification supply reviewable branch evidence.
