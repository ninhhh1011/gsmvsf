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

8. **Update DECISIONS.md** when architecture decisions change — every new technology, pattern, or approach must have an ADR entry.

9. **Week boundaries are strict** — implement only the current week's scope. Do not implement future weeks' features.

---

## Current Milestone

**Milestone 0**: Project Foundation — COMPLETE
**Week 1**: Map Matching — NOT STARTED

---

## Dataset V1 Map Warning

`hanoi-patched.osm.pbf` changes OSM way `881947000` (Cầu Thanh Trì) from `motorcar=designated` to `motorcar=no`. Human confirmation required before use as primary routing map. Both PBFs remain untouched.

---

## Dataset V1 Validation

Dataset V1 has 163 validation checks (163 PASS / 0 FAIL) and 21 scenario assertions (21/21 PASS).

To re-validate:
```bash
make validate-data
```
