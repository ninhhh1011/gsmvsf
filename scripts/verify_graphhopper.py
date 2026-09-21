"""Live GraphHopper verification using only canonical runtime Dataset inputs.

Run with DEBUG=false. Any engine outage or invalid response fails the process;
there is no synthetic routing fallback. Evidence stays in runtime/migration.
"""
from __future__ import annotations

import asyncio
import csv
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx

from backend.app.config import settings
from backend.app.services.candidate.models import CandidateSearchRequest
from backend.app.services.candidate.service import CandidateSearchService
from backend.app.services.demand.capability import get_capability_resolver
from backend.app.services.demand.models import DemandContext, RequestedServiceType
from backend.app.services.demand.service import get_demand_service
from backend.app.services.routing.engine import raise_for_routing_failure
from backend.app.services.routing.graphhopper_routing_adapter import GraphHopperRoutingAdapter
from backend.app.services.routing.models import Position, RouteRequest, RouteStatus, VehicleRoutingProfile

INPUTS = ["vehicles/vehicles.csv", "trips/trips.csv", "map/processed/road_nodes.csv.gz",
          "battery/soc_history.csv.gz"]
GROUPS = ("car", "fixed_bike", "swap", "both")


def rows(relative):
    path = settings.dataset_path / relative
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle)


def dataset_cases():
    """Twenty distinct trip starts, five for each requested service/category case."""
    resolver = get_capability_resolver()
    vehicles = {row["vehicle_id"]: row for row in rows(INPUTS[0])}
    pools = {"car": [], "fixed_bike": [], "swap": []}
    for trip in rows(INPUTS[1]):
        vehicle = vehicles[trip["vehicle_id"]]
        cap = resolver.resolve_by_model(vehicle["vehicle_model"])
        group = "car" if cap.vehicle_category == "EV_CAR" else "swap" if cap.swap_supported else "fixed_bike"
        pools[group].append(trip)
    selected = [(group, trip) for group in GROUPS for trip in
                (pools["swap"][5:10] if group == "both" else pools[group][:5])]
    assert len(selected) == 20 and len({trip["trip_id"] for _, trip in selected}) == 20
    node_ids = {trip[key] for _, trip in selected for key in ("origin_node_id", "destination_node_id")}
    nodes = {row["node_id"]: row for row in rows(INPUTS[2]) if row["node_id"] in node_ids}
    trip_ids = {trip["trip_id"] for _, trip in selected}
    telemetry = {}
    for row in rows(INPUTS[3]):
        if row["trip_id"] in trip_ids:
            previous = telemetry.get(row["trip_id"])
            if previous is None or row["timestamp"] < previous["timestamp"]:
                telemetry[row["trip_id"]] = row
    cases = []
    demand = get_demand_service()
    for group, trip in selected:
        origin, destination = nodes[trip["origin_node_id"]], nodes[trip["destination_node_id"]]
        soc = telemetry[trip["trip_id"]]
        assert float(soc["distance_travelled_km"]) == 0, "Fixture must use actual trip-start telemetry"
        context = DemandContext(vehicle_id=trip["vehicle_id"], driver_id=trip["driver_id"], trip_id=trip["trip_id"],
            timestamp=datetime.fromisoformat(soc["timestamp"]), current_soc_pct=float(soc["soc_pct"]),
            estimated_remaining_range_km=float(soc["estimated_remaining_range_km"]),
            planned_trip_distance_km=float(trip["planned_network_distance_m"]) / 1000,
            remaining_trip_distance_km=float(trip["planned_network_distance_m"]) / 1000,
            raw_latitude=float(origin["latitude"]), raw_longitude=float(origin["longitude"]))
        intent = RequestedServiceType.ANY if group == "both" else RequestedServiceType.BATTERY_SWAP if group == "swap" else RequestedServiceType.CHARGING
        energy = demand.process_driver_request(context, intent, service_request_id=f"GH-{group}-{trip['trip_id']}")
        assert energy.request_valid and energy.need_service
        request = CandidateSearchRequest(energy_request=energy,
            destination_latitude=float(destination["latitude"]), destination_longitude=float(destination["longitude"]),
            destination_node_id=trip["destination_node_id"])
        cases.append((group, request))
    return cases


class CountingRoutingEngine:
    """Forward every call to the actual adapter; count outcomes without replacing them."""
    def __init__(self, adapter):
        self.adapter = adapter
        self.reset_metrics()

    def reset_metrics(self):
        self.calls = 0
        self.routing_ms = 0.0
        self.statuses = {}

    async def route(self, request):
        self.calls += 1
        started = time.perf_counter()
        result = await self.adapter.route(request)
        self.routing_ms += (time.perf_counter() - started) * 1000
        self.statuses[result.status.value] = self.statuses.get(result.status.value, 0) + 1
        assert result.engine_name == "graphhopper"
        return result

    async def is_healthy(self):
        return await self.adapter.is_healthy()


async def search_case(service, engine, group, request):
    engine.reset_metrics()
    started = time.perf_counter()
    result = await service.search_candidates(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert result.search_status == "SUCCESS"
    stations = {candidate.station_id for candidate in result.candidates}
    reached = {candidate.station_id for candidate in result.candidates if candidate.route_metrics is not None}
    has_destination = request.destination_latitude is not None
    assert result.total_candidates_evaluated == len(stations) * (2 if group == "both" else 1)
    expected_calls = len(stations) + (1 + len(reached) if has_destination else 0)
    assert engine.calls == expected_calls, (group, engine.calls, expected_calls)
    for candidate in result.candidates:
        metrics = candidate.route_metrics
        if not metrics:
            assert candidate.reason == "UNREACHABLE"
            continue
        assert metrics.distance_to_station_m >= 0 and metrics.duration_to_station_s >= 0
        assert metrics.eta_to_station_s == metrics.duration_to_station_s
        if not has_destination:
            assert metrics.distance_station_to_dest_m is None and metrics.detour_distance_m is None
        if metrics.via_total_distance_m is not None:
            assert abs(metrics.via_total_distance_m - metrics.distance_to_station_m - metrics.distance_station_to_dest_m) <= 0.11
            assert abs(metrics.via_total_duration_s - metrics.duration_to_station_s - metrics.duration_station_to_dest_s) <= 0.11
        if metrics.detour_distance_m is not None:
            assert abs(metrics.detour_distance_m - max(0, metrics.via_total_distance_m - metrics.direct_distance_m)) <= 0.11
            assert abs(metrics.detour_duration_s - max(0, metrics.via_total_duration_s - metrics.direct_duration_s)) <= 0.11
    return {
        "case": group, "trip_id": request.energy_request.trip_id,
        "request": request.model_dump(mode="json"), "latency_ms": round(elapsed_ms, 3),
        "routing_ms": round(engine.routing_ms, 3), "route_calls": engine.calls,
        "route_statuses": dict(engine.statuses), "stations": len(stations),
        "reachable_stations": len(reached), "alternatives": result.total_candidates_evaluated,
        "eligible": result.eligible_count, "candidates": [c.model_dump(mode="json") for c in result.candidates],
    }


def save_evidence(filename, report):
    directory = ROOT / "runtime" / "migration"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Evidence: {path}", flush=True)
    return path


def evidence_metadata():
    return {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "engine": "graphhopper",
            "base_url": settings.graphhopper_base_url, "runtime_inputs": INPUTS,
            "labels_consumed": False, "transport": "real HTTP with shared request client",
            "fixture_method": "Canonical trip origins/destinations and earliest SOC; explicit driver requests"}


async def verify_graphhopper():
    cases = dataset_cases()
    samples = [next(case for case in cases if case[0] == group) for group in GROUPS]
    report = evidence_metadata()
    async with httpx.AsyncClient(timeout=10) as client:
        adapter = GraphHopperRoutingAdapter(client=client)
        assert await adapter.is_healthy(), "GraphHopper must route both vehicle profiles"
        engine = CountingRoutingEngine(adapter)
        service = CandidateSearchService(routing_engine=engine)
        report["searches"] = []
        for group, request in samples:
            row = await search_case(service, engine, group, request)
            report["searches"].append(row)
            print(group, row["trip_id"], row["alternatives"], row["route_calls"], flush=True)
        group, request = samples[0]
        no_destination = request.model_copy(update={"destination_latitude": None, "destination_longitude": None,
                                                    "destination_node_id": None})
        report["missing_destination"] = await search_case(service, engine, group, no_destination)
        report["routes"] = []
        for group, request in (samples[0], samples[1]):
            energy = request.energy_request
            station = service.catalog.get_all_stations()[0]
            route_request = RouteRequest(origin=Position(latitude=energy.latitude, longitude=energy.longitude),
                destination=Position(latitude=request.destination_latitude, longitude=request.destination_longitude),
                via=[Position(latitude=station.latitude, longitude=station.longitude)],
                profile=VehicleRoutingProfile(vehicle_category=energy.vehicle_type))
            result = await adapter.route(route_request)
            raise_for_routing_failure(result)
            assert result.status == RouteStatus.SUCCESS and len(result.legs) == 2 and result.geometry
            report["routes"].append({"case": group, "request": route_request.model_dump(mode="json"),
                                      "result": result.model_dump(mode="json")})
        # Exercise the existing application router against the actual GraphHopper adapter.
        from backend.app.api.v1.candidate import set_candidate_service
        from backend.app.main import app
        set_candidate_service(service)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://application") as api:
                response = await api.post("/api/v1/route", json=route_request.model_dump(mode="json"))
                assert response.status_code == 200, response.text
                assert response.json()["engine_name"] == "graphhopper"
                report["route_api"] = {"status_code": response.status_code, "result": response.json()}
        finally:
            set_candidate_service(None)
    assert any(row["case"] == "both" and row["route_calls"] == 61 for row in report["searches"])
    report["status"] = "PASS"
    save_evidence("graphhopper-routing-smoke.json", report)
    print("PASS: real GraphHopper profiles, via legs, candidates, BOTH cache, missing destination, route API")
    return report


if __name__ == "__main__":
    asyncio.run(verify_graphhopper())
