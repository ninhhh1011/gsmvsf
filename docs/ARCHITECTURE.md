# Architecture

## Runtime shape

GSMVSF is a FastAPI modular monolith with a browser demo. Docker Compose runs two API containers on one host, plus one PostgreSQL/PostGIS instance, one Redis instance, and one GraphHopper 11.0 instance. The API containers share the same data-plane services; this is not a multi-host or high-availability deployment. All published ports bind to `127.0.0.1`.

PostgreSQL is the authority for candidate and snapshot data. Redis is an optional key-value cache. GraphHopper is the only production routing and map-matching engine. Application services are created during lifespan and exposed through `app.state`; routes obtain runtime dependencies from request state. No runtime route may consume evaluation labels.

## Recommendation flow

The request resolves current location, searches eligible station/service pairs, ranks the resulting candidates against the current snapshot, and returns the recommendation. Week 3 owns candidate eligibility. Week 4 returns HTTP 409 `CANDIDATE_STATE_CHANGED` when the candidate snapshot is invalidated; the full workflow may repeat the search once. Week 5 refresh is client/request-driven and does not run a streaming or background refresh service.

The frontend vehicle energy catalog has one source: `GET /api/v1/vehicles/catalog`. Frontend fallback specs are used only when that request fails. Labels remain evaluation-only.

## Routing and matching

Routing constraints, vehicle capabilities, optimization objectives, and dynamic context are project/domain contracts. GraphHopper is the sole production adapter behind them. `EV_CAR` maps to `car`; `EV_MOTORBIKE` maps to `motorcycle` using GraphHopper's `car_access` model. The canonical patched Hanoi map is primary. Matching quality describes geometric proximity, not calibrated probability. Ambiguous directed traversal withholds road segment and direction.

## Deployment limits

The data plane is single-node: one PostgreSQL, Redis, and GraphHopper service. Two API containers on the same Docker host do not provide host failure tolerance. No Kubernetes manifests, multi-AZ setup, numeric production SLA, or zero-downtime guarantee is part of the verified system. See [OPERATIONS.md](OPERATIONS.md) for supported local operations and [DECISIONS.md](DECISIONS.md) for recorded decisions.
