# GraphHopper migration research

Verified 2026-09-21 against the maintained GraphHopper repository and its latest
release API. Decision: GraphHopper is already selected; benchmarks diagnose
regressions, not engine choice.

## Pinned baseline

- GraphHopper **11.0**, released 2025-10-14, latest published GitHub release
  returned by `https://api.github.com/repos/graphhopper/graphhopper/releases/latest`.
- Official Maven artifact: [graphhopper-web-11.0.jar](https://repo.maven.apache.org/maven2/com/graphhopper/graphhopper-web/11.0/graphhopper-web-11.0.jar).
- JAR SHA-256: `b59c024afe172ec6ec85b6327006c3138ec58c7d0bcd26253d0e42853f613def`.
- Java requirement **17+**, confirmed in the [11.0 README](https://github.com/graphhopper/graphhopper/blob/11.0/README.md#installation)
  and [11.0 pom](https://github.com/graphhopper/graphhopper/blob/11.0/pom.xml).
  The development branch's Java 25 requirement does not describe release 11.0.
- Runtime strategy: project Docker image `build6week-graphhopper:11.0`, verified
  official JAR on `eclipse-temurin:21.0.8_9-jre-jammy`; immutable base digest is
  recorded in the Dockerfile and execution report. No floating GraphHopper image.
- Import only read-only `dataset_v1/map/raw/hanoi-patched.osm.pbf`. Import occurs
  with `java -jar graphhopper.jar server config.yml`, cached under ignored
  `runtime/graphhopper/graph-cache-11`. Existing snapshot cache is not reused.
- Port 8989; only car and motorcycle profiles. CH for routing; matching uses
  the same profile weighting and disables CH internally.

## API and identity

[RouteResource](https://github.com/graphhopper/graphhopper/blob/11.0/web-bundle/src/main/java/com/graphhopper/resources/RouteResource.java)
accepts GET `/route?point=lat,lon&point=lat,lon&profile=car`. Distances are meters,
times milliseconds. Encoded `paths[0].points` is a string, not an `encoded`
object. Request path details for actual leg distances/times; never split totals
equally. Domain requests and results remain engine-independent.

[Maintained map-matching guide](https://github.com/graphhopper/graphhopper/blob/11.0/map-matching/README.md)
and [MapMatchingResource](https://github.com/graphhopper/graphhopper/blob/11.0/web-bundle/src/main/java/com/graphhopper/resources/MapMatchingResource.java)
confirm POST `/match?profile=car&type=json`, content type `application/gpx+xml`.
The old separate map-matching repository is not the implementation source.
Normal JSON returns matched geometry plus path details, not a one-to-one
`matched_points` array. `extended_json` contains edge-associated snapped states,
but observations can be filtered. Therefore the Python adapter projects each
observation onto the actual returned matched path, with a distance cutoff;
this is explicitly a project reconstruction, not native per-observation posterior.
Request unsimplified geometry and `osm_way_id` path details. GraphHopper internal
edge/node IDs are never represented as Dataset segment or OSM identifiers.

Segment IDs come from the existing PostGIS resolver, constrained by actual
matched OSM way where present and path traversal bearing; unresolved identities
remain null. Matching confidence is a project-defined geometric residual quality
`exp(-0.5 * (distance_m / gps_accuracy_m)^2)`, not the historical engine confidence.
Report the method and parameters; never describe it as a calibrated probability.

## Motorcycle semantics

The maintained [motorcycle custom model](https://github.com/graphhopper/graphhopper/blob/11.0/core/src/main/resources/com/graphhopper/custom_models/motorcycle.json)
uses `car_access` and 90% of `car_average_speed`, with different priorities and
surface penalties. It is a distinct supported motorcycle weighting, not a bicycle
model or an API request using the car profile. The [access parser](https://github.com/graphhopper/graphhopper/blob/11.0/core/src/main/java/com/graphhopper/routing/util/parsers/CarAccessParser.java)
does not provide full independent motorcycle access semantics.

Project baseline extends that supported model: exclude MOTORWAY (including
links, through GraphHopper road_class), penalize TRUNK, retain rough-surface/track
restrictions and cap modeled speed at 60 km/h for this local urban EV baseline.
This cap is a conservative project assumption, not a nationwide legal-speed claim.
No blanket bridge/tunnel penalties are invented. No curvature preference is needed
for service-station routing. Profiles are selected deterministically:
`EV_CAR -> car`, `EV_MOTORBIKE -> motorcycle`, equally for routing and matching.

**Known limitation:** shared `car_access` conservatively excludes motorcar=no
roads, including the patched bridge, even when motorcycles could be allowed;
motorcycle-specific access tags are not fully modeled. This migration does not
claim complete Vietnamese legal access coverage. An independent motorcycle OSM
access parser would require separate validated access rules and graph reimport.
The frozen PBF will not be altered to bypass these restrictions.

## Phase 1 exit gate

- [x] Actual maintained release and JAR pinned.
- [x] Java requirement checked against release, not master.
- [x] Official routing API and matching module confirmed.
- [x] Distinct supported motorcycle model, extensions and limitations documented.
- [x] No archived implementation selected.
