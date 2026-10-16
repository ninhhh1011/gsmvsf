# History footprints and road-based paired synthetic data

Owner approved both parts in this conversation. Execute inline on
`feat/h3-departure-statistics-7d`; no merge or push.

Spec: [updated H3 contract](../specs/2026-10-14-h3-departure-statistics.md).

1. Test and add bounded legacy-signature footprint aggregation; use seven-day
   completion cohort, distinct trips per cell, minimum production support and
   neutral null departure weights. Merge paired GPS footprints at observation time.
2. Test UI gray-history popup and separate coverage/ratio counts. Preserve selected
   resolution, spatial clipping, cell cap and stale-response guards. No blank grid.
3. Add deterministic paired road-based seed tooling with diverse OD corridors,
   manifests and separate offline truth. Use the existing GraphHopper adapter and
   only synthetic storage. Retain old history and Dataset V1.
4. Verify real DB/API, diverse geometry and geographic footprint, finite synthetic
   detector controls, desktop/mobile browser, backend/frontend suites and Dataset
   integrity. Record results; keep branch unmerged.

No new dependencies, ranking changes, inferred past guidance or production SLAs.
Legacy counts and paired eligibility must not be conflated. Signature/group/SQL
work limits fail explicitly, never return fabricated or partially computed ratios.

Completed on branch. Verification and limits: [report](../../reports/h3-departure-statistics-2026-10-14.md).
742 backend PASS / 12 skips, 269 frontend PASS, nine live isolated DB/API groups,
16/16 browser checks and unchanged 63 canonical hashes. Old histories retained;
360 new paired synthetic road trips seeded separately. No merge or push.
