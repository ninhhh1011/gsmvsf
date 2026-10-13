# Architecture

## Runtime shape

GSMVSF is a FastAPI modular monolith with a browser demo. Docker Compose runs two API containers on one host, plus one PostgreSQL/PostGIS instance, one Redis instance, and one GraphHopper 11.0 instance. The API containers share the same data-plane services; this is not a multi-host or high-availability deployment. All published ports bind to `127.0.0.1`.

PostgreSQL is the authority for candidate and snapshot data. Redis is an optional snapshot cache and the shared authority for accepted GPS state across API replicas; GPS state must not fall back to replica-local memory during an outage. GraphHopper is the only production routing and map-matching engine. Application services are created during lifespan and exposed through `app.state`; routes obtain runtime dependencies from request state. No runtime route may consume evaluation labels.

## Recommendation flow

The request resolves current location, searches eligible station/service pairs, ranks the resulting candidates against the current snapshot, and returns the recommendation. Week 3 owns candidate eligibility. Week 4 returns HTTP 409 `CANDIDATE_STATE_CHANGED` when the candidate snapshot is invalidated; the full workflow may repeat the search once. Week 5 refresh is client/request-driven and does not run a streaming or background refresh service.

The frontend vehicle energy catalog has one source: `GET /api/v1/vehicles/catalog`. Frontend fallback specs are used only when that request fails. Labels remain evaluation-only.

An explicit station request and a physical battery warning have separate semantics. `EnergyServiceRequest.need_service/reason_code` retain service-intent semantics; optional `energy_assessment` carries the backend detector's `SAFE`, `ADVISORY`, `CRITICAL` or `UNAVAILABLE` warning level and physical reason. The UI never interprets `VALID_REQUEST` as low energy or missing data as a safe battery. During selected-station navigation, client-driven refresh uses the existing demand evaluation endpoint for energy only; it preserves the selected station and does not rerank. SOC/model/power and drawer revisions reject stale responses. See ADR-024 and the current review report.

## Route familiarity v2

When explicitly enabled, the combined `/recommend` workflow compares candidate GraphHopper geometry against protected completed-route geometry using directed, ordered corridor overlap at H3 Resolution 9. Resolution 11 signatures remain the persisted spatial index; neighboring index cells retrieve possible matches. PostgreSQL stores optional geometry/start time alongside existing history; missing evidence is unavailable and preserved rather than reconstructed. The route producer is trusted through the existing ingestion token. Because `/recommend` has no end-user authentication, enabling familiarity also requires a trusted authenticated gateway to HMAC-sign the exact driver ID; the API verifies that signature before history access. API replicas on one host share these secrets and the same PostgreSQL data plane, which remains single-node.

The default lookback is seven days. Personal history is capped at 50 trips; community considers at most 100 drivers with up to five trips each. Comparable completed history is causal and bounded, with explicit unavailable/truncated evidence. Personal familiarity uses mean corridor coverage; community includes non-supporting comparable drivers and withholds public support below five drivers. Both affect ranking under ADR-025: 80% normalized complete journey time, 10% confidence-adjusted personal mismatch and 10% confidence-adjusted community mismatch. Missing evidence is neutral. Physical ETA and eligibility exclude preference cost. The prior personal-only 30-second penalty is superseded. See [OPERATIONS.md](OPERATIONS.md) for migration and privacy operations.

Total time includes all travel legs, queue and service. Without B there is no onward leg; an after-B goal visits B then the station once. Backend station-plan confirmation validates the selected station/service pair and returns constrained geometry and waypoint roles. Changes to unchosen alternatives alone do not invalidate the selected pair. Recommendation candidate details and standalone candidate endpoints share PostgreSQL snapshot authority. Manual vehicle changes invalidate the previous selection and preserve only outstanding passenger goals.

Traffic avoidance selects the latest snapshot per segment at or before the request, then filters freshness and congestion before result limits. The additive `(kind,timestamp DESC,entity_id)` index bounds fresh-window enumeration. Corridor matching uses cached geometry and a spatial candidate index while preserving geometric verification and existing work caps.

Service duration does not prove added energy. Current onward feasibility requires existing range for represented legs plus reserve; `ONWARD_ENERGY_UNVERIFIED` can exclude a physically useful charging trip. Passing a station waypoint does not prove charging or swapping completed.

Opt-in synthetic history uses a validated separate schema and fixed public sample read capability. Production defaults remain protected realtime history with familiarity disabled. Separate behavioral evaluation truth never enters runtime predictions. Synthetic choices establish simulator behavior, not real driver motivations.

Whole-trip offline Driver comparison uses frozen initial proposed geometry and the full observed GPS route, independently of replay progress. `/routing/compare-routes` returns both coverage denominators, verified shared geometry and the exact cells used for rendering. Anonymous comparison does no history lookup; optional driver history requires the same identity boundary. Comparison is a bounded 10 m chord approximation, with 45 m lateral / 60 degree heading project thresholds. Nearby parallel streets and noisy raw GPS remain evaluation limitations.

`/vehicles/catalog` supplies physical metadata and per-field provenance. `/vehicles/power-step` estimates observed-interval battery energy and updated SOC, including stationary auxiliary load and regenerative braking. Frontend does not duplicate power physics. Unknown physics is explicit; remaining range is still a labelled catalog consumption estimate rather than a calibrated route-energy forecast.

## Routing and matching

Routing constraints, vehicle capabilities, optimization objectives, and dynamic context are project/domain contracts. GraphHopper is the sole production adapter behind them. `EV_CAR` maps to `car`; `EV_MOTORBIKE` maps to `motorcycle` using GraphHopper's `car_access` model. The canonical patched Hanoi map is primary. Matching quality describes geometric proximity, not calibrated probability. Ambiguous directed traversal withholds road segment and direction.

## Deployment limits

The data plane is single-node: one PostgreSQL, Redis, and GraphHopper service. Two API containers on the same Docker host do not provide host failure tolerance. No Kubernetes manifests, multi-AZ setup, numeric production SLA, or zero-downtime guarantee is part of the verified system. See [OPERATIONS.md](OPERATIONS.md) for supported local operations and [DECISIONS.md](DECISIONS.md) for recorded decisions.
