---
name: week1-map-matching
description: Use this skill for Week 1 implementation, review, debugging, or evaluation of the Green SM Map Matching scope. It governs the pipeline from Dataset V1 GPS observations through OSRM Match to normalized road-position outputs and evaluation against map-matching labels. Do not use it for Demand Detection, station search, ranking, or later-week features.
---

# Week 1 — Map Matching

## Purpose

Implement and evaluate only the Week 1 Map Matching scope for this repository.

The Week 1 problem is:

```text
Dataset V1 GPS trace
        ↓
Map Matching
        ↓
matched position / matched road context / direction / quality
        ↓
evaluation against Dataset V1 labels
```

Use the existing project foundation. Do not redesign Milestone 0 unless a verified blocker requires it.

## Source of truth

Before changing Week 1 code, read in this order:

1. `AGENTS.md`
2. `docs/PROJECT_SCOPE.md`
3. `docs/ACCEPTANCE_CRITERIA.md`
4. `docs/DATA_CONTRACT.md`
5. `docs/ARCHITECTURE.md`
6. `docs/DECISIONS.md`
7. `docs/WEEK_1.md` if it exists
8. Relevant Dataset V1 documentation

If the documents conflict, do not silently choose a new interpretation. Report the conflict and preserve the higher-authority requirement.

## Fixed project context

- Dataset V1 is the canonical development dataset and is read-only during normal development.
- Primary initial map: `dataset_v1/map/raw/hanoi-baseline.osm.pbf`.
- Initial Map Matching baseline: OSRM Match.
- OSRM is already proven to run with MLD preprocessing.
- Milestone 0 smoke trajectory: T0001 / TRJ0001.
- Do not make `hanoi-patched.osm.pbf` the primary map without explicit human approval.
- Generated runtime artifacts belong outside `dataset_v1/`.

## Runtime input rule

Runtime Map Matching must consume observation data only.

Never use evaluation labels or ground truth as runtime inputs.

Examples of runtime inputs may include, when present in the Dataset V1 contract:

- observation ID
- trajectory/trip ID
- timestamp
- latitude
- longitude
- speed
- heading
- accuracy

The exact request schema must follow the repository data contract and current implementation. Do not invent fields only to make a test pass.

## Ground-truth rule

Ground-truth and label data may be used only for:

- offline evaluation
- test assertions
- error analysis
- benchmark reporting

Never leak:

- true segment ID
- true matched coordinate
- true direction
- expected output

into the runtime matching path.

## Implementation sequence

Use this order unless a documented blocker requires otherwise.

### 1. Confirm baseline health

Before changing algorithmic code:

- confirm Dataset V1 validation remains passing
- confirm OSRM is healthy
- confirm direct OSRM Match still works on the known normal trace
- confirm no source dataset file was modified

Do not debug application code before proving the engine is healthy.

### 2. Define the Week 1 contract

Define a clean project-level input/output contract.

The output should expose only values that can be produced or honestly derived from the engine and project data.

Typical output concepts include:

- trace ID
- observation ID
- raw coordinate
- matched coordinate
- matched/unmatched status
- matched route geometry
- road/segment identity when the chosen representation can provide it correctly
- travel direction when it can be derived correctly
- match quality/confidence when supported or explicitly derived

Do not invent confidence scores.

Do not equate an OSM Way ID with the project's road segment ID unless the data contract explicitly defines that mapping.

### 3. Keep OSRM behind an adapter boundary

Application/domain code must not scatter direct OSRM HTTP calls across controllers and services.

Preferred dependency direction:

```text
API
 ↓
MapMatchingService
 ↓
Routing/MapMatching engine boundary
 ↓
OSRM adapter
```

Keep the abstraction small. Do not build a multi-engine framework unless the baseline produces evidence that another engine is needed.

### 4. Implement normal-case vertical slice

Start with the known normal trace from Dataset V1.

Prove:

```text
Dataset V1 observations
        ↓
FastAPI request
        ↓
MapMatchingService
        ↓
OSRM Match
        ↓
normalized response
```

Only after the normal path works should hard cases be added.

### 5. Build offline evaluation

Compare predicted output with Dataset V1 labels without exposing labels to runtime code.

At minimum report metrics that the available ground truth can support honestly, such as:

- number of observations evaluated
- matched vs unmatched/null observations
- segment correctness when segment mapping is available
- positional error when true positions are available
- direction correctness when direction labels are available
- results broken down by scenario type

Do not invent acceptance thresholds. Use official thresholds if they exist; otherwise report measured values and document that thresholds remain to be agreed.

### 6. Add scenario coverage

Progress from normal data to harder Dataset V1 scenarios.

Prioritize cases represented by the dataset, including as applicable:

- normal GPS
- normal noise
- high noise
- GPS drift
- missing points
- low sampling frequency
- heading noise
- intersections
- parallel roads
- service roads
- bridges
- U-turns

Do not claim a scenario is supported unless it has actually been exercised.

### 7. Perform error analysis

For each meaningful failure class, record:

- scenario
- input characteristics
- OSRM response
- project-normalized result
- expected label
- observed failure mode
- suspected cause
- whether the problem is data, engine configuration, integration, or algorithmic limitation

Fix integration/configuration problems before changing algorithms.

## Baseline-first rule

OSRM Match is the Week 1 baseline.

Do not begin by training a custom model or implementing HMM from scratch.

Only propose another approach after producing concrete evidence that the OSRM baseline does not satisfy a Week 1 requirement or repeatedly fails an important Dataset V1 scenario.

Possible later investigations may include:

- OSRM parameter tuning
- additional trajectory/context handling
- Valhalla Meili
- custom HMM/candidate scoring

But they require an explicit, documented failure case and a reason the change addresses it.

## Testing requirements

Tests should be layered:

### Unit tests
- request validation
- response normalization
- error mapping
- adapter behavior with controlled responses

### Integration tests
- FastAPI → service → real OSRM
- normal Dataset V1 trace
- selected non-normal traces

### Evaluation tests/scripts
- runtime prediction against offline labels
- metrics by scenario

Mocks are acceptable for unit tests.

They are not a substitute for at least one real OSRM integration path.

## Error handling

Handle engine and data failures explicitly.

Examples:

- empty trace
- too few points for the chosen operation
- invalid coordinates
- non-monotonic/invalid timestamps when timestamps are used
- OSRM timeout
- OSRM unavailable
- OSRM `NoMatch`
- null/unmatched tracepoints
- malformed engine response

Do not convert failures into fabricated matched positions.

## Documentation discipline

During Week 1:

- create/update `docs/WEEK_1.md`
- keep `docs/ARCHITECTURE.md` aligned with actual implementation
- update `docs/DECISIONS.md` only for real architectural decisions
- document evaluation methodology and measured results
- document known limitations rather than hiding them

## Scope boundary

Do not implement Week 2–6 business features while this skill is active.

Out of scope:

- Charging Demand Detection
- Battery Swap Demand Detection
- station candidate search
- station recommendation routing workflow
- queue prediction
- traffic prediction
- station ranking
- Learning-to-Rank
- recommendation API
- realtime recommendation orchestration
- fleet optimization
- LLM agent or multi-agent runtime

Routing calls may be used only when they are necessary to support or debug Week 1 Map Matching.

## Definition of Week 1 completion

Do not declare Week 1 complete only because the endpoint returns HTTP 200.

Completion requires evidence that the implemented Map Matching path:

1. consumes Dataset V1 GPS data without label leakage
2. calls the real baseline engine
3. normalizes engine output through the project service boundary
4. handles unmatched/error cases
5. is covered by automated tests
6. is evaluated against Dataset V1 labels
7. reports results by important scenario type
8. documents known failure modes and limitations
9. satisfies the official Week 1 deliverable/criteria in `docs/ACCEPTANCE_CRITERIA.md`

If official acceptance criteria and this checklist differ, the official criteria win.
