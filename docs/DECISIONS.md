# DECISIONS

## ADR-001: Modular Monolith Initially

**Decision**: Use Modular Monolith architecture for the initial implementation.

**Reason**: The six-week scope requires rapid iteration across multiple modules. A modular monolith allows sharing code and data structures between Map Matching, Demand Detection, Candidate Search, and Ranking without distributed system overhead. Each module is a clearly separated Python package within the FastAPI application.

**Trade-off**: If the system scales beyond Week 6 to multi-team or multi-region deployment, extraction will require refactoring. Microservice patterns should not be introduced preemptively.

**Revisit condition**: When deployment requires independent scaling of individual modules or when team size exceeds 10.

---

## ADR-002: OSRM as Initial Map Matching / Routing Engine

**Decision**: Use OSRM (Open Source Routing Machine) as the routing and map-matching engine.

**Reason**: OSRM is production-proven, provides a clean HTTP API, supports MLD (Multi-Level Dijkstra) for fast queries, and has a map-matching endpoint. Dataset V1 provides OSM-derived road data that aligns with OSRM's requirements. No custom routing algorithm is needed for the initial implementation.

**Trade-off**: OSRM requires preprocessing the OSM PBF into OSRM artifacts (extract → partition → customize). The MLD profile is optimized for car routing.

**Revisit condition**: When custom turn-by-turn routing, real-time traffic-reactive routing, or multi-modal routing is required.

---

## ADR-003: PostgreSQL + PostGIS as Geospatial Application DB

**Decision**: Use PostgreSQL 16 with PostGIS 3 as the application database.

**Reason**: PostGIS provides robust geospatial indexing (GiST), spatial queries, and routing graph storage. FastAPI backend can store runtime state, evaluation results, and processed trajectories. PostgreSQL's JSONB support handles semi-structured data from OSRM responses and replay events.

**Trade-off**: PostgreSQL/PostGIS is not purpose-built for real-time routing. For high-volume production routing, a dedicated routing engine like OSRM alone may suffice.

**Revisit condition**: When read-heavy geospatial queries exceed PostgreSQL performance targets.

---

## ADR-004: Dataset V1 as Canonical Project Development Data

**Decision**: Use Dataset V1 (./dataset_v1/) as the authoritative, immutable development dataset for the full six-week project.

**Reason**: Dataset V1 provides a complete, validated, and self-consistent operational dataset covering all six weeks of requirements. It includes ground truth, labels, training data, evaluation data, and replay events. The 163 validation checks and 21 scenario assertions provide confidence in its integrity.

**Trade-off**: Dataset V1 is a synthetic dataset with fixed capacity and station configurations. Real-world deployment will require live station APIs, real GPS streams, and dynamic traffic data.

**Revisit condition**: When a production deployment requires integration with live data sources.

---

## ADR-005: Dataset V1 is Immutable During Normal Development

**Decision**: Dataset V1 is treated as READ-ONLY during the six-week implementation.

**Reason**: Modifying Dataset V1 invalidates the evaluation framework and breaks the validation contract (163 checks, 21 scenarios). Any data derived for application use is placed outside dataset_v1/.

**Trade-off**: If a bug is found in Dataset V1, it cannot be fixed inline. Issues must be reported and resolved through a formal patch process.

**Revisit condition**: When Dataset V1 maintainers provide an official patch mechanism.

---

## ADR-006: hanoi-patched.osm.pbf is Primary Routing Map (Supersedes v1)

**Decision**: Use `hanoi-patched.osm.pbf` as the primary OSRM routing map.

**Reason**: The patched PBF has been approved for production use. It contains motorcar=no for OSM way 881947000 (Cầu Thanh Trì bridge), which is the intended project behavior.

**Trade-off**: The baseline PBF remains available as a reference for historical comparison.

**Revisit condition**: When a new approved PBF patch is provided.

---

## ADR-007: hanoi-baseline.osm.pbf is Reference Map (Supersedes v1)

**Decision**: `hanoi-baseline.osm.pbf` is kept as a reference map only.

**Reason**: The baseline PBF served as the initial OSRM map. With the approval of hanoi-patched.osm.pbf, the baseline is retained for historical reference and comparison purposes.

**Trade-off**: The baseline should not be used for production routing. Both PBFs remain byte-for-byte intact.

**Revisit condition**: When comparing routing behavior between baseline and patched maps is needed.
