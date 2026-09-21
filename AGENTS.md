# AGENTS.md

## For Future Coding Agents

Before beginning any implementation work, read these documents in order:

1. **[docs/PROJECT_SCOPE.md](./docs/PROJECT_SCOPE.md)** — Project problem, deliverables, six-week progression
2. **[docs/ACCEPTANCE_CRITERIA.md](./docs/ACCEPTANCE_CRITERIA.md)** — Completion criteria, evaluation rules
3. **[docs/DATA_CONTRACT.md](./docs/DATA_CONTRACT.md)** — Dataset structure, relationships, runtime vs evaluation data
4. **[docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)** — Current system, planned architecture, stack
5. **[docs/DECISIONS.md](./docs/DECISIONS.md)** — Architecture decisions and their rationale

Also read the active-week documentation when it exists (e.g., `docs/WEEK_1.md`).

---

## Hard Rules

1. **Repository is source of truth** — conversation history is NOT source of truth. All requirements and decisions must come from repository documentation.

2. **Do not modify Dataset V1** — `dataset_v1/` is read-only canonical data. Do not regenerate, patch, move, or alter files inside it unless explicitly requested.

3. **Do not silently change requirements** — if you encounter ambiguity or a conflict, state it and wait for clarification.

4. **Labels are evaluation-only** — `demand_labels.csv`, `candidate_labels.csv`, `recommendation_labels.csv`, `ranking_reference.csv`, and `map_matching_labels.csv.gz` must NEVER be consumed as runtime prediction input.

5. **Do not hardcode expected outputs** — use Dataset V1 ground truth for validation, not expected hardcoded values.

6. **Do not over-engineer** — implement only what the current week's acceptance criteria require. Do not build Week 3 features in Week 1.

7. **Do not add technology without demonstrated need** — Kafka, Redis, microservices, vector DBs, LLM agents require explicit approval and documented ADR.

8. **Update DECISIONS.md when architecture decisions change** — every new technology, pattern, or approach must have an ADR entry.

9. **Week boundaries are strict** — implement only the current week's scope. Do not implement future weeks' features.

10. **Routing engine abstraction** — routing business logic must not depend directly on a specific routing engine. Route constraints, optimization objectives, vehicle capabilities, and dynamic context must be represented at the project/domain level. GraphHopper is the sole production routing and matching adapter behind these contracts; mocks are test-only. Do not restore engine selectors or fallback runtimes. Prefer configurable and measurable flexibility over hardcoded ease of implementation.

---

## Current Milestone

**Milestone 0**: Project Foundation — COMPLETE
**Weeks 1–3**: Implemented; historical completion/freeze records describe the prior runtime.
**Current work**: Sole-GraphHopper migration functional verification PASS: 239 tests, live API/outage checks, 63 Dataset file hashes unchanged. Migration gates and evidence are recorded in `docs/GRAPHHOPPER_MIGRATION_REPORT.md`; freeze tags identify the final clean commit. Do not infer acceptance from historical engine reports.

---

## Dataset V1 Map Status

**APPROVED**: OSM is canonical map data; `hanoi-patched.osm.pbf` is the primary GraphHopper map.
- Contains motorcar=no for Cầu Thanh Trì way 881947000
- `hanoi-baseline.osm.pbf` retained as reference
- Both PBFs remain untouched.

---

## Dataset V1 Validation

The current canonical validator, executed on 2026-09-21, reports **152 PASS / 0 FAIL** and **22/22 scenario assertions**. The earlier 163/21 totals are historical and superseded for the current validator source.

`make validate-data` invokes `scripts/validate_frozen_dataset.py`, which runs the frozen canonical validator and redirects generated reports to `runtime/migration/validation`; no Dataset files may be written.

To re-validate:
```bash
make validate-data
```

## GraphHopper Runtime Rules

- GraphHopper 11.0 is the sole production engine for routing and map matching.
- Map `EV_CAR -> car` and `EV_MOTORBIKE -> motorcycle`; reject missing/unsupported categories or conflicting canonical metadata. No global default profile or overriding hint.
- The motorcycle model uses `car_access`; `motorcar=no` also excludes motorcycles, including patched way 881947000. Do not claim independent motorcycle access coverage.
- Matching projects observations onto actual returned geometry and resolves directed Dataset segments through PostGIS; unresolved IDs remain null. Never substitute raw GPS or engine-internal IDs as successful Dataset matches.
- Ambiguous projected traversal or directed-segment identity must withhold road segment and direction; expose `AMBIGUOUS` even when the geometric location is matched.
- Production adapters share the application-lifespan HTTP client; keep its shutdown ownership in the lifespan.
- Matching quality is geometric proximity, not a calibrated probability or native engine confidence. Current quality semantics and limitations are in `docs/ARCHITECTURE.md`.
- Dependency failures must remain explicit; live verification and benchmark scripts must not fall back to mocks.
- Keep generated graphs, logs, evidence and validator reports inside this repository and outside `dataset_v1/`.
