# Architecture

## Runtime shape

GSMVSF is a FastAPI modular monolith with a browser demo. Docker Compose runs two API containers on one host, plus one PostgreSQL/PostGIS instance, one Redis instance, and one GraphHopper 11.0 instance. The API containers share the same data-plane services; this is not a multi-host or high-availability deployment. All published ports bind to `127.0.0.1`.

PostgreSQL is the authority for candidate and snapshot data. Redis is an optional key-value cache. GraphHopper is the only production routing and map-matching engine. Application services are created during lifespan and exposed through `app.state`; routes obtain runtime dependencies from request state. No runtime route may consume evaluation labels.

## Recommendation flow

The request resolves current location, searches eligible station/service pairs, ranks the resulting candidates against the current snapshot, and returns the recommendation. Week 3 owns candidate eligibility. Week 4 returns HTTP 409 `CANDIDATE_STATE_CHANGED` when the candidate snapshot is invalidated; the full workflow may repeat the search once. Week 5 refresh is client/request-driven and does not run a streaming or background refresh service.

The frontend vehicle energy catalog has one source: `GET /api/v1/vehicles/catalog`. Frontend fallback specs are used only when that request fails. Labels remain evaluation-only.

## Route familiarity v2

When explicitly enabled, the combined `/recommend` workflow compares the candidate's recommended GraphHopper geometry against protected completed-route history using ordered, distance-weighted H3 Resolution 11 signatures. PostgreSQL stores route history; no read API exposes it. The route producer is trusted through the existing ingestion token. Because `/recommend` has no end-user authentication, enabling familiarity also requires a trusted authenticated gateway to HMAC-sign the exact driver ID; the API verifies that signature before history access. API replicas on one host share these secrets and the same PostgreSQL data plane, which remains single-node.

The default lookback is seven days. Personal history is capped at 50 trips. Community history considers at most 100 recently active drivers with up to five matching trips each, and community evidence is suppressed below five distinct drivers and never changes ranking. No history produces zero penalty. Personal history can add at most 30 seconds to final ranking cost; it cannot change eligibility, physical ETA, queue/service costs, or snapshot invalidation behavior. See [OPERATIONS.md](OPERATIONS.md) for explicit migration, destructive rollback, privacy, and benchmark operations.

## Routing and matching

Routing constraints, vehicle capabilities, optimization objectives, and dynamic context are project/domain contracts. GraphHopper is the sole production adapter behind them. `EV_CAR` maps to `car`; `EV_MOTORBIKE` maps to `motorcycle` using GraphHopper's `car_access` model. The canonical patched Hanoi map is primary. Matching quality describes geometric proximity, not calibrated probability. Ambiguous directed traversal withholds road segment and direction.

## Deployment limits

The data plane is single-node: one PostgreSQL, Redis, and GraphHopper service. Two API containers on the same Docker host do not provide host failure tolerance. No Kubernetes manifests, multi-AZ setup, numeric production SLA, or zero-downtime guarantee is part of the verified system. See [OPERATIONS.md](OPERATIONS.md) for supported local operations and [DECISIONS.md](DECISIONS.md) for recorded decisions.
