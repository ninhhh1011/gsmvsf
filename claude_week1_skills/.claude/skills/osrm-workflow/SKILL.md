---
name: osrm-workflow
description: Use this skill whenever working with, debugging, testing, configuring, or integrating OSRM in this Green SM repository, especially OSRM preprocessing, MLD runtime, nearest/route/match calls, Dataset V1 traces, Docker networking, or FastAPI-to-OSRM integration.
---

# OSRM Workflow — Green SM Project

## Purpose

Provide a deterministic troubleshooting and integration workflow for OSRM.

The main rule is:

```text
prove the engine directly
before debugging the application integration
```

Do not "fix" an OSRM problem by fabricating application output.

## Project invariants

- Primary initial PBF: `dataset_v1/map/raw/hanoi-baseline.osm.pbf`
- Dataset V1 is read-only.
- Generated OSRM artifacts live outside Dataset V1, under the repository runtime area.
- Algorithm: MLD unless a documented decision changes it.
- Existing project commands are preferred over raw ad-hoc commands.
- Known environment: Windows + Docker Desktop may not reliably expose container ports to the host; Docker internal networking and `docker exec` have already been proven as valid verification paths.

Before running commands, inspect the current repository `Makefile`, `make.bat`, `docker-compose.yml`, `.env.example`, and README. Use the repository's actual commands rather than assuming names.

## Preprocessing workflow

The expected MLD preprocessing chain is:

```text
hanoi-baseline.osm.pbf
        ↓
osrm-extract
        ↓
osrm-partition
        ↓
osrm-customize
        ↓
runtime OSRM artifacts
        ↓
osrm-routed --algorithm mld
```

Never write generated `.osrm*` artifacts back into `dataset_v1/`.

Never modify the source PBF as part of preprocessing.

## Debugging order

Always investigate in this order.

### Layer 1 — Inputs

Verify:

- the baseline PBF exists
- the selected trajectory exists in Dataset V1
- coordinates are within the map extent
- GPS points are ordered correctly
- timestamps, when used, are valid and monotonic
- the trace has enough points for the intended request

Do not silently replace the user's trace with an easier one during debugging. If a different trace is needed for diagnosis, state that explicitly.

### Layer 2 — OSRM artifacts

Verify preprocessing completed successfully.

Check that the expected MLD artifacts exist and are not empty.

If artifacts are missing or stale, rebuild through the repository's documented prepare-map command.

### Layer 3 — OSRM process

Verify:

- container/process is running
- MLD is active
- expected data file is loaded
- service is reachable from the network path the caller actually uses

On this Windows Docker setup, distinguish:

- host → published container port
- container → container service name
- `docker exec` inside an existing container
- one-off Docker network test container

A host networking problem is not automatically an OSRM problem.

### Layer 4 — Direct OSRM API

Before inspecting FastAPI, call OSRM directly.

Use the smallest request that proves each layer:

1. `nearest`
2. `route`
3. `match`

If `nearest` fails, do not debug Map Matching logic yet.

If `route` fails, inspect map/profile/connectivity before application code.

If `match` alone fails, inspect the trace and Match-specific inputs.

### Layer 5 — Application integration

Only after direct OSRM requests work:

- inspect adapter request construction
- inspect timeout/retry configuration
- inspect coordinate ordering
- inspect URL encoding/query parameters
- inspect response parsing/normalization
- inspect application error mapping

## Coordinate-order rule

OSRM HTTP coordinate lists use:

```text
longitude,latitude
```

Project/domain objects may store:

```text
latitude, longitude
```

Never rely on positional memory.

Use explicit field names and cover coordinate conversion with tests.

Swapped coordinates can produce plausible-looking but wrong failures.

## Match request discipline

Build Match requests from the actual Dataset V1 observation sequence.

When using timestamps:

- preserve chronological order
- use the engine-supported timestamp representation
- do not manufacture timestamps merely to satisfy a request

When using GPS accuracy/radius parameters:

- use real available observation accuracy and documented OSRM semantics
- do not insert arbitrary radii to force a successful match
- record any parameter changes used during evaluation

Do not drop difficult points without reporting that preprocessing decision.

## Match response discipline

Inspect at least:

- top-level OSRM `code`
- `tracepoints`
- null tracepoints
- `matchings`
- matching confidence when returned by OSRM
- route geometry/distance/duration when relevant

`tracepoints` may contain null entries.

Do not assume:

```text
number of input points == number of successfully matched points
```

unless verified.

Do not fabricate a matched coordinate for a null tracepoint.

## NoMatch behavior

Treat `NoMatch` as a valid engine outcome that the application must handle, not as an exception to hide.

For a `NoMatch`:

1. preserve enough diagnostic context
2. record trajectory/scenario
3. confirm engine health using a known-good trace
4. inspect data/parameters
5. classify the failure
6. only then consider tuning or algorithm changes

## Dataset V1 smoke trace

The known Milestone 0 normal trace is:

- trajectory: `TRJ0001`
- source trajectory family: T0001
- Dataset V1 contains the canonical source observations

Milestone 0 proved direct OSRM Match can succeed on a subset of this trace.

Do not interpret that smoke result as Week 1 accuracy evidence.

Week 1 evaluation must use broader Dataset V1 coverage and labels.

## Evidence to capture during debugging

When reporting an OSRM issue, include:

- exact map source used
- preprocessing status
- OSRM version
- algorithm
- trajectory ID
- number of input observations
- request type
- response code
- matched count
- unmatched/null count
- confidence if returned
- distance/duration if relevant
- network path used to call OSRM
- relevant container/service logs

Avoid reports such as "OSRM doesn't work" without this evidence.

## Repository commands first

Prefer repository commands such as the current equivalents of:

```text
prepare-map
up
down
logs
smoke
test
```

over undocumented raw commands.

If a raw command is needed for diagnosis:

- use it temporarily
- explain why
- do not replace the documented project workflow unless the existing workflow is actually wrong

## Configuration changes

Do not tune OSRM blindly.

Any change to Match behavior or engine configuration should state:

- current behavior
- failing scenario
- proposed parameter/config change
- expected effect
- measured result after change

Keep before/after evidence.

## Engine-switch gate

Do not switch from OSRM to Valhalla, GraphHopper, or custom map matching because one request failed.

An engine change requires:

1. reproducible Dataset V1 failures
2. confirmation that the issue is not integration/config/data
3. a Week 1 requirement affected by those failures
4. a documented comparison criterion
5. an ADR or explicit human approval if the architecture changes

## Safety against scope drift

While using this skill, OSRM work is infrastructure or Week 1 Map Matching support.

Do not use an OSRM task as an excuse to implement:

- station candidate search
- charging recommendation routing
- ranking
- later-week features

unless the active week explicitly requires them.

## Completion rule

An OSRM-related task is not complete when code merely compiles.

It is complete only when the relevant direct engine call has been executed successfully or the failure has been reproduced, classified, and documented with evidence.
