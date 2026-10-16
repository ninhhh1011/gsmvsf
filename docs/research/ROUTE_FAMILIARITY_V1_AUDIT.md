# Route Familiarity v1 Forensic Audit

**Audit baseline:** `feature/route-familiarity-v2` at `c80a2b4`  
**Method:** read-only inspection of the pre-removal tree (`7313cde^`) and the ADR-020 removal commit. No deleted code was restored.

## Old capabilities

The deleted subsystem intended to ingest matched routes, build ordered H3 signatures, find personal and community route candidates, compare routes, assign route families, calculate familiarity, and persist/query history. The package overview described this flow in `backend/app/services/route_history/__init__.py` at `7313cde^`.

## Old data model

`backend/app/services/route_history/schema.sql` at `7313cde^` defined `historical_routes`, `historical_route_segments`, `historical_route_h3`, `route_families`, and `route_family_members`. It stored driver/trip/time/distance, ordered segment and H3 records, family representatives, support counts, time/recency weights, and indexes for driver, timestamp, endpoint, segment, and H3 lookup. The old repository also kept separate synchronous and asynchronous database URLs (`backend/app/config.py` at `7313cde^`).

## Old algorithms

- H3 signatures used resolution 11 by default, retained ordered cells, and collapsed consecutive duplicate cells (`signature.py`).
- Candidate lookup used both an in-memory cell-to-route inverted index and a PostgreSQL cell-overlap query (`index.py`, `repository.py`).
- Route similarity code considered road-segment similarity and H3 overlap/sequential overlap (`similarity.py`).
- Route-family assignment compared route representatives with a default threshold of 0.6 and time/recency weights (`families.py`).
- A configurable bounded penalty and Bayesian confidence were described and unit-tested (`familiarity.py`, `test_bayesian_familiarity.py`).

The production integration did not deliver those calculations end to end: `integration.py` assigned `avg_similarity = 0.7`, set `dominant_family = None`, and returned route-count-derived support. Its penalty helper was not called by `ranking/service.py`; recommendation called `rank_features(features)` directly. Thus the isolated algorithms/tests did not prove production familiarity affected ranking.

## Old APIs

`backend/app/api/v1/route_history.py` at `7313cde^` exposed status, family, driver-history, similarity, route comparison, and H3 lookup endpoints. The route comparison endpoint used empty `RouteSegments`, estimated shared distance as shared segment count times a fixed 100 m, and only checked the first segment for divergence. The driver endpoint queried route-family context without consistently restricting it to the requested driver's own families.

## Old tests

Deleted tests covered signatures, overlap, inverted indexes, filters and time weighting, road-level similarity, familiarity penalties, confidence, families, persistence, and end-to-end behavior. Relevant paths include `backend/tests/services/test_route_history.py`, `test_route_history_e2e.py`, `test_route_families.py`, `test_familiarity.py`, `test_bayesian_familiarity.py`, and `test_h3_integration.py` at `7313cde^`. They covered many pure helpers but did not prove that computed production history was used in ranking.

## Old performance risks

- Synchronous database connections ran beneath asynchronous recommendation code.
- Personal and population reads were separate work per recommendation, and candidate fanout could multiply them.
- The in-memory inverted index introduced a second lifecycle/indexing mechanism alongside PostgreSQL H3 lookup.
- One H3 row per route cell and a trigram index on cell text added storage and index maintenance.
- Family representative comparisons and refresh cost were not established by the tests or a reproducible benchmark.

## Old architecture problems

ADR-020 records removal of the dead route-history system, async/sync database mixing, and lazy module-global service construction. The old ranking module created `_history_service` lazily. The integration hardcoded similarity and did not apply its advertised penalty. API outputs included approximate/synthetic distance and incomplete similarity behavior. Road-segment, H3, and route-family concepts duplicated one another without a single proven truth path.

## Useful components

- Preserve ordered traversal and direction in route representations.
- Keep retrieval evidence distinct from ranking policy.
- Keep the familiarity adjustment neutral without personal history and strictly bounded.
- Retain focused tests for reversed routes, no history, and penalty bounds.

## Components that must not return

- The old package/schema/API/import-script bundle.
- Synchronous database connections in async request paths.
- Lazy global service construction.
- Hardcoded `avg_similarity = 0.7`, synthetic shared-distance estimates, or unused penalty helpers.
- Parallel route-family truth or mixed H3 resolutions.
- Claims that the old production integration applied familiarity; the inspected path did not.

