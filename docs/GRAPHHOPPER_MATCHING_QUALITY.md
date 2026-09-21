# GraphHopper matching quality evaluation

Measured 2026-09-21 using the running GraphHopper 11.0 service and PostGIS road table. This is a quality measurement, not a new acceptance threshold or a production-capacity claim.

## Reproduction and scope

From the repository root:

```powershell
python -B scripts/evaluate_graphhopper_matching.py --self-check
python -B scripts/evaluate_graphhopper_matching.py
```

The script sets `DEBUG=false`, defaults to GraphHopper at `http://127.0.0.1:8989`, and uses the local `ev_recommendation` PostGIS database. It starts no services and writes only `runtime/migration/matching-quality*.json`. `--max-trajectories N` selects an evenly spread deterministic pilot; omit it for the complete replay.

The complete run uses every frozen GPS observation, grouped into complete trajectories and sorted by timestamp. Requests enter the current `MapMatchingService`, which selects car or motorcycle from canonical trip/vehicle runtime metadata. The service calls GraphHopper GPX matching and resolves segment identities against the real PostGIS table. There are no mock or alternate engine predictions.

Only after all inference has finished does the evaluator open `map_matching_labels.csv.gz`. Selected-point membership is then obtained from observation IDs in `map_matching_candidates.csv.gz`; its labels/features never enter inference. Base segment and OSM way identity come from the frozen road-segment table. Dataset files are read only.

Evidence contains per-observation predictions, per-request latency/status/profile, actual `/info`, and SHA-256 fingerprints of the evaluator and relevant runtime sources. The pilot evidence is `runtime/migration/matching-quality-pilot.json`; the full evidence is `runtime/migration/matching-quality.json`. `matching-quality-pre-fix.json` preserves the earlier full replay before ambiguous direction was withheld; its `source_unchanged_during_run` flag is `false` because source changed while the already imported Python modules finished executing. It is not the final-source result.

## Metric definitions

- Match rate: matched observations divided by all labeled observations in the replay scope. A point is matched when the current adapter projects it within 100 m of GraphHopper's returned path.
- Resolution rate: observations with an actual Dataset segment identity divided by matched observations. Ambiguous direction retains a matched position but withholds directed segment ID and direction. Such points remain in accuracy denominators and reduce resolution coverage.
- Directed segment accuracy: exact segment-ID equality. Base accuracy compares `base_segment_id`, ignoring direction. Way accuracy compares OSM way IDs. Direction accuracy compares the service's predicted `FORWARD`/`REVERSE` against the label.
- Identity accuracies use all matched observations as denominator, including unresolved predictions. Evidence also reports accuracy over every labeled observation, counting unmatched observations as incorrect.
- Position error is Haversine distance from the predicted coordinate to labeled true position, among matched observations. Quantiles use linear interpolation; earth radius is 6,371,000 m.
- HTTP latency spans a native GraphHopper request through receipt of its complete response body. Service latency additionally includes category resolution, GPX serialization, observation projection, PostGIS resolution, and response construction. These are individual-request samples, including no-match outcomes; no averages of trajectory means are substituted for raw request quantiles.

## Results

Full replay completed: **150/150 successful native requests**, 93 car and 57 motorcycle. All 65,847 observations and all 5,029 selected evaluation observations were scored. There were no dependency failures or whole-request no-match responses.

| Metric | All observations | Selected observations |
|---|---:|---:|
| Matched / labeled | 65,078 / 65,847 (98.83%) | 4,967 / 5,029 (98.77%) |
| Directed identity resolved / matched | 24,263 / 65,078 (37.28%) | 1,846 / 4,967 (37.17%) |
| Directed segment accuracy, among matched | 26.96% | 27.08% |
| Base segment accuracy, among matched | 27.20% | 27.30% |
| OSM way accuracy, among matched | 80.96% | 80.19% |
| Direction accuracy, among matched | 34.42% | 34.19% |
| Mean position error | 8.10 m | 8.10 m |
| Median position error | 5.04 m | 5.02 m |
| P95 position error | 25.75 m | 26.60 m |
| Maximum position error | 131.50 m | 101.85 m |

Among the 24,263 observations where a directed identity is actually emitted, exact segment precision is 72.30% and direction precision is 92.32%. These conditional figures must be read with the **37.28% resolution coverage**; they do not replace accuracy over all matched points.

### Request latency

| Observations per request | Requests | HTTP median / P90 / P95 (ms) | Service median / P90 / P95 (ms) |
|---|---:|---:|---:|
| All | 150 | 119.1 / 482.2 / 701.1 | 1733.7 / 4184.9 / 6047.1 |
| 2-250 | 22 | 46.9 / 173.9 / 217.8 | 546.1 / 993.1 / 1337.5 |
| 251-500 | 68 | 117.3 / 312.3 / 600.5 | 1456.9 / 2871.1 / 3493.5 |
| 501+ | 60 | 166.2 / 604.7 / 745.9 | 2569.7 / 5977.0 / 7183.5 |

### Mismatch inspection

Of matched observations, **40,815 withhold directed identity**: 39,000 are marked `ambiguous_path_projection`, and 1,815 are ambiguous resolver ties. This explains most of the coverage reduction; it is not evidence that PostGIS is unavailable. Full-trajectory revisits expose direction ambiguity in projection onto the complete path. The remaining exact-segment mismatches comprise 3,755 different-way predictions, 2,805 different segments on the same way, and 160 wrong-direction predictions on the correct base segment.

| Observation | True segment | Predicted segment / way | Position error | Inspection |
|---|---|---|---:|---|
| O00051151 | 973038844_0_R | null / 896452399 | 131.50 m | AMBIGUOUS; directed identity withheld |
| O00051300 | 973038851_0_R | null / 973038845 | 129.87 m | AMBIGUOUS; directed identity withheld |
| O00051215 | 973038851_0_R | null / null | 124.12 m | AMBIGUOUS; directed identity withheld |

For O00051151 the chosen path way (896452399) differs from labeled way 973038844, with 131.50 m position error. O00051300 also has a different way. O00051215 withholds both way and directed identity. These examples establish path/identity uncertainty; they do not isolate whether access restrictions, path selection, GPS noise, or map segmentation caused it. Position error can exceed the 100 m matching cutoff because that cutoff measures distance from **raw GPS to matched path**, whereas evaluation measures distance from **true position to prediction**.

### Source reconciliation

The full run includes the conservative projection/resolver ambiguity fix. Its `source_unchanged_during_run` flag remains `false` because a shared HTTP-client constructor change landed while its already imported modules were running. Exact prior-source SHA-256 reconstruction verifies that the only subsequent changes to the adapter and profile module were the shared-client additions and line-ending formatting. The evaluator explicitly injects its client, so that constructor branch is unchanged for this run. Evidence: `matching-quality-source-reconciliation.json`.

A final-source replay of TRJ0001 (car) and TRJ0150 (motorcycle) produced **699 identical per-observation predictions**, with unchanged source fingerprints. Its independent evidence is `matching-quality-final-smoke.json`. The earlier pre-fix full run is retained solely for audit; its more numerous directed identities include the ambiguity that was subsequently suppressed.

**Assessment:** full frozen-label coverage and engine operation are demonstrated. Directed identity coverage remains limited, and position tails remain material. No undocumented quality threshold is declared passed.

## Interpretation limits

The adapter reconstructs each observation by nearest projection anywhere along the returned path; it does not receive a native per-observation posterior or enforce monotonic traversal during that projection. On loops, revisited roads, and nearby path portions, a low spatial residual can coexist with an incorrect segment or direction. The current confidence is geometric proximity quality, not a calibrated probability of identity correctness.

This evaluation sends complete trajectories sequentially on a shared development host with an already imported graph, whereas realtime matching uses the existing short context window. These batch results do not establish realtime quality, request throughput, or concurrent-driver capacity. Latency is not a controlled comparison against the earlier run or OSRM. The shared `car_access` motorcycle limitation remains as documented in [migration research](GRAPHHOPPER_MIGRATION_RESEARCH.md).

Historical [Week 1](WEEK_1.md) reports OSRM results on 250 observations, with 247 matched: directed accuracy 36.0%, direction accuracy 46.2%, and position mean/median/P95/max 4.65/3.91/11.84/20.21 m. Its population and trace context differ from this full replay, and historical base/way accuracy is absent. These values are context only; neither improvement nor regression can be established by subtracting these unequal-scope aggregates. The [technical audit](WEEK_1_TECHNICAL_AUDIT.md) also explains historical direction attribution and request-latency aggregation limitations.
