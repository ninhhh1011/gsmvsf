"""Test the deployed API, including real profiles or an explicitly unavailable engine."""
import argparse
import asyncio
import csv
import gzip
import statistics
import time
import httpx
from verify_graphhopper import dataset_cases, save_evidence


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--expect-unavailable", action="store_true")
    parser.add_argument("--benchmark", action="store_true")
    args = parser.parse_args()
    down = args.expect_unavailable
    cases = dataset_cases()
    evidence = {"api_base": args.api_base, "expect_unavailable": down, "checks": {}}
    with gzip.open("dataset_v1/gps/gps_observations.csv.gz", "rt", encoding="utf-8") as handle:
        gps = list(csv.DictReader(handle))
    async with httpx.AsyncClient(base_url=args.api_base, timeout=120) as client:
        for endpoint, code in [("/health", 200), ("/readiness", 503 if down else 200)]:
            response = await client.get(endpoint)
            assert response.status_code == code, response.text
            evidence["checks"][endpoint] = {"http": code, "body": response.json()}
        for group in ("car", "fixed_bike", "both"):
            request = next(request for name, request in cases if name == group)
            response = await client.post("/api/v1/candidate-search", json=request.model_dump(mode="json"))
            assert response.status_code == (503 if down else 200), response.text
            evidence["checks"]["candidate_" + group] = {"http": response.status_code, "body": response.json()}
            route = {"origin": {"latitude": 21.028, "longitude": 105.854},
                     "destination": {"latitude": 21.036, "longitude": 105.830},
                     "profile": {"vehicle_category": "EV_CAR" if group == "car" else "EV_MOTORBIKE"}}
            response = await client.post("/api/v1/route", json=route)
            assert response.status_code == (503 if down else 200), response.text
            evidence["checks"]["route_" + group] = {"http": response.status_code, "body": response.json()}
            rows = [row for row in gps if row["trip_id"] == request.energy_request.trip_id][:20]
            match = {"trip_id": request.energy_request.trip_id, "trajectory_id": rows[0]["trajectory_id"], "observations": rows}
            started = time.perf_counter()
            response = await client.post("/api/v1/map-match", json=match)
            assert response.status_code == (503 if down else 200), response.text
            evidence["checks"]["match_" + group] = {"http": response.status_code, "latency_ms": 1000 * (time.perf_counter() - started), "body": response.json()}
            driver = "smoke_" + group
            await client.delete("/api/v1/drivers/" + driver + "/location")
            statuses = []
            for row in rows:
                body = {key: row[key] for key in ("timestamp", "observation_id", "latitude", "longitude", "speed_kmh", "heading_deg")}
                body["vehicle_id"] = request.energy_request.vehicle_id
                response = await client.post("/api/v1/drivers/" + driver + "/location", json=body)
                assert response.status_code == 200, response.text
                statuses.append(response.json())
            assert any(row["status"] == ("ENGINE_UNAVAILABLE" if down else "MATCHED") for row in statuses), statuses
            evidence["checks"]["realtime_" + group] = statuses
        if args.benchmark and not down:
            evidence["benchmark"] = {"label": "INITIAL LOCAL GRAPHHOPPER PERFORMANCE BASELINE", "measurement": "deployed HTTP API including serialization and station search"}
            for concurrency in (1, 5, 10):
                semaphore = asyncio.Semaphore(concurrency)

                async def run_case(case):
                    async with semaphore:
                        start = time.perf_counter()
                        response = await client.post("/api/v1/candidate-search", json=case[1].model_dump(mode="json"))
                        assert response.status_code == 200, response.text
                        return 1000 * (time.perf_counter() - start)

                start = time.perf_counter()
                timings = sorted(await asyncio.gather(*(run_case(case) for case in cases)))
                wall = time.perf_counter() - start
                evidence["benchmark"][str(concurrency)] = {"requests": len(timings), "median_ms": statistics.median(timings), "p90_ms": timings[17], "p95_ms": timings[18], "max_ms": max(timings), "throughput_per_s": len(timings) / wall, "wall_s": wall}
                print(concurrency, evidence["benchmark"][str(concurrency)], flush=True)
    evidence["status"] = "PASS"
    save_evidence("api-outage.json" if down else "api-smoke.json", evidence)
    print("PASS: deployed API " + ("explicit outage" if down else "real profiles, matching, realtime, candidates"))


if __name__ == "__main__":
    asyncio.run(main())
