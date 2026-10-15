# Local road coverage and deviation-rich synthetic cohorts

Owner requested planning and implementing the seven agreed tasks. Work remains on
feat/h3-departure-statistics-7d; no merge/push, Dataset edits or production map change.

Record GraphHopper /info bounds and configured service bbox. Seed only their
intersection; bounds are availability envelopes, not administrative borders or
proof that every contained road is routable. Report missing map area explicitly.
The current imported map cannot support a claim of all Hanoi coverage. Expansion
of the canonical primary map is outside this authorization.

Use uncovered residential/service/living_street/tertiary reference roads in H3-7
cells, with many distinct local origins and nearby destinations. Verify real
GraphHopper routes, bounded length and endpoint/via snap distances. Failed targets
remain reported, never silently snapped far away or replaced with straight lines.
Reuse existing paired-trip generation with configurable per-template departure
indices. Vary local vias and departure positions instead of fixed thirds.

Create separate COVERAGE and STRESS cohorts plus held-out evaluation evidence.
Coverage uses short following journeys; stress intentionally contains more exit
and repeated-exit journeys plus following controls. Driver identities and behavior
vary, with deterministic seeds and manifests. Declare maneuver intentions before
detection. Never discard valid deviation cases merely because detection reports zero.
No claim that the designed stress rate represents real driver behavior.

Allow aggregate cohort selection; the default all-source behavior stays compatible.
Legacy unclassified histories appear only in all-source mode. Privacy, seven-day
event time, unknown evidence and work guards remain unchanged. Reports distinguish
trip count, unique drivers, detected departing trips/events and road-length gain.
Offline coverage metrics retain the same method/bbox for before/after comparison;
complete motorcar eligibility remains unknown. No labels enter prediction.
