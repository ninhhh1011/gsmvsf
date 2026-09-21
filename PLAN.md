# GraphHopper migration plan entry point

The earlier dual-engine integration draft is superseded by
[GRAPHHOPPER_FULL_MIGRATION_PLAN](docs/GRAPHHOPPER_FULL_MIGRATION_PLAN.md) and
[ADR-010](docs/DECISIONS.md#adr-010-graphhopper-as-the-sole-routing-and-matching-runtime).
Use that execution plan for phase/task gates, checks, findings and completion.

Functional migration verification is PASS: 239 tests, live normal/outage API
checks, and unchanged hashes for all 63 Dataset files. The deployed HTTP endpoint
benchmark now records 20 requests at each concurrency level 1, 5 and 10 in
`runtime/migration/api-smoke.json`. Formal reporting and the freeze gate remain
pending completion in the authoritative execution plan.

GraphHopper 11.0 is the sole production routing and map-matching runtime.
`EV_CAR -> car` and `EV_MOTORBIKE -> motorcycle` apply consistently. OSM remains
canonical and the approved patched PBF remains immutable. Domain interfaces
remain engine-independent. No selectors, mock fallback, alternate runtime,
Week 4 ranking, or unrequested technology are authorized by this plan.

The historical draft's JDK 25 requirement, floating third-party image, nested
encoded-route points, JSON matching request, fabricated per-observation matching
schema, and default motorcycle profile are incorrect for the selected release.
The verified contracts are recorded in
[GRAPHHOPPER_MIGRATION_RESEARCH](docs/GRAPHHOPPER_MIGRATION_RESEARCH.md): Java 17+,
pinned official JAR on Java 21, encoded route points string, GPX matching, and
explicit project reconstruction of observation locations from the matched path.

Runtime files, caches, verification reports and generated validator reports stay
within the repository and outside `dataset_v1/`. This plan requires no external
backup location. Historical engine decisions and quality reports are preserved
as superseded evidence; final migration acceptance and freeze require the
current execution gates to pass and are not asserted here.
