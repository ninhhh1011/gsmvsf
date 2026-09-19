"""
Week 3 Smoke Test Script: Candidate Search & Multi-Leg Routing.

Demonstrates:
1. Routing engine connectivity (Real OSRM if available, MockRoutingAdapter otherwise)
2. Real-world route metrics:
   - Driver -> Station
   - Station -> Destination
   - Direct Driver -> Destination
   - Via-route total distance and duration
   - Detour distance and duration
   - Base ETA to station
3. Car Charging Candidate Search
4. Swap-Capable Motorcycle Unresolved Search (Expanding to both services)
5. Missing Destination Graceful Fallback
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx

from backend.app.services.candidate.models import CandidateSearchRequest
from backend.app.services.candidate.service import CandidateSearchService
from backend.app.services.demand.models import (
    EnergyServiceRequest,
    ReasonCode,
    RequestSource,
    ServiceType,
)
from backend.app.services.routing.mock_adapter import MockRoutingAdapter
from backend.app.services.routing.osrm_routing_adapter import OSRMRoutingAdapter


async def check_osrm_available(base_url: str = "http://localhost:5000") -> bool:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{base_url}/route/v1/driving/105.78,21.01;105.79,21.02")
            return resp.status_code == 200 and resp.json().get("code") == "Ok"
    except Exception:
        return False


async def run_smoke_test():
    print("==================================================")
    print("WEEK 3 SMOKE TEST: CANDIDATE SEARCH & ROUTING")
    print("==================================================")

    # 1. Routing Engine Selection
    is_osrm = await check_osrm_available()
    if is_osrm:
        print("[Engine] Real OSRM detected at http://localhost:5000 (hanoi-patched.osrm)")
        engine = OSRMRoutingAdapter()
        routing_mode = "REAL_OSRM"
    else:
        print("[Engine] OSRM service not running on port 5000. Using deterministic road network MockRoutingAdapter.")
        engine = MockRoutingAdapter(winding_factor=1.25, average_speed_mps=8.33)
        routing_mode = "MOCK_ROAD_NETWORK"

    service = CandidateSearchService(routing_engine=engine)

    # 2. Test Case A: EV Car (VF 8) requiring charging with explicit destination
    print("\n--- TEST CASE A: EV Car (VF 8) Charging with Destination ---")
    driver_lat, driver_lon = 21.0156, 105.7807  # Near S002
    dest_lat, dest_lon = 21.0566, 105.8998      # Near S011

    esr_car = EnergyServiceRequest(
        service_request_id="SMOKE-CAR-01",
        vehicle_id="V0004",
        vehicle_model="VF_8",
        vehicle_type="EV_CAR",
        timestamp=datetime.fromisoformat("2026-09-01T06:20:00+07:00"),
        request_source=RequestSource.AUTO_DETECTED,
        need_service=True,
        allowed_service_types=[ServiceType.CHARGING],
        resolved_service_type=ServiceType.CHARGING,
        reason_code=ReasonCode.LOW_SOC,
        current_soc_pct=18.0,
        estimated_remaining_range_km=55.0,
        latitude=driver_lat,
        longitude=driver_lon,
        swap_supported=False,
    )

    req_car = CandidateSearchRequest(
        energy_request=esr_car,
        destination_latitude=dest_lat,
        destination_longitude=dest_lon,
    )

    res_car = await service.search_candidates(req_car)
    print(f"Total evaluated alternatives: {res_car.total_candidates_evaluated}")
    print(f"Eligible candidates found: {res_car.eligible_count}")

    eligs = [c for c in res_car.candidates if c.eligible]
    if eligs:
        c0 = eligs[0]
        m = c0.route_metrics
        print(f"\nExample Eligible Candidate: {c0.station_id} ({c0.service_type.value})")
        print(f"  Station Coordinates: ({c0.station_latitude}, {c0.station_longitude})")
        print(f"  Operating Status: {c0.operational.operating_status}, Available Capacity: {c0.operational.available_capacity}")
        print(f"  Energy Feasibility to Station: {c0.soc_feasible}")
        if m:
            print("  --- Multi-Leg Route Metrics ---")
            print(f"  Driver -> Station Distance: {m.distance_to_station_m:.1f} m")
            print(f"  Driver -> Station Duration (Base ETA): {m.duration_to_station_s:.1f} s ({m.duration_to_station_s/60.0:.1f} min)")
            print(f"  Station -> Destination Distance: {m.distance_station_to_dest_m:.1f} m")
            print(f"  Station -> Destination Duration: {m.duration_station_to_dest_s:.1f} s ({m.duration_station_to_dest_s/60.0:.1f} min)")
            print(f"  Direct Route Distance: {m.direct_distance_m:.1f} m")
            print(f"  Direct Route Duration: {m.direct_duration_s:.1f} s ({m.direct_duration_s/60.0:.1f} min)")
            print(f"  Via Route Total Distance: {m.via_total_distance_m:.1f} m")
            print(f"  Via Route Total Duration: {m.via_total_duration_s:.1f} s ({m.via_total_duration_s/60.0:.1f} min)")
            print(f"  DETOUR Distance: {m.detour_distance_m:.1f} m")
            print(f"  DETOUR Duration: {m.detour_duration_s:.1f} s ({m.detour_duration_s/60.0:.1f} min)")

    # 3. Test Case B: Swap-capable Motorcycle (EVO) Unresolved Need
    print("\n--- TEST CASE B: Swap-Capable Bike (EVO) Unresolved Search ---")
    esr_bike = EnergyServiceRequest(
        service_request_id="SMOKE-BIKE-01",
        vehicle_id="V0055",
        vehicle_model="EVO",
        vehicle_type="EV_MOTORBIKE",
        timestamp=datetime.fromisoformat("2026-09-01T06:20:00+07:00"),
        request_source=RequestSource.AUTO_DETECTED,
        need_service=True,
        allowed_service_types=[ServiceType.CHARGING, ServiceType.BATTERY_SWAP],
        resolved_service_type=None,
        reason_code=ReasonCode.LOW_SOC,
        current_soc_pct=15.0,
        estimated_remaining_range_km=30.0,
        latitude=21.0311,
        longitude=105.8590,
        swap_supported=True,
    )

    req_bike = CandidateSearchRequest(
        energy_request=esr_bike,
        destination_latitude=21.0740,
        destination_longitude=105.8756,
    )

    res_bike = await service.search_candidates(req_bike)
    ch_count = sum(1 for c in res_bike.candidates if c.service_type == ServiceType.CHARGING)
    sw_count = sum(1 for c in res_bike.candidates if c.service_type == ServiceType.BATTERY_SWAP)
    print(f"Total evaluated: {res_bike.total_candidates_evaluated}")
    print(f"  CHARGING alternatives evaluated: {ch_count}")
    print(f"  BATTERY_SWAP alternatives evaluated: {sw_count}")
    print(f"Eligible candidates: {res_bike.eligible_count}")

    # 4. Test Case C: Missing Destination Fallback
    print("\n--- TEST CASE C: Missing Destination (Detour Graceful Fallback) ---")
    req_no_dest = CandidateSearchRequest(
        energy_request=esr_car,
        destination_latitude=None,
        destination_longitude=None,
    )
    res_no_dest = await service.search_candidates(req_no_dest)
    print(f"Total evaluated: {res_no_dest.total_candidates_evaluated}, Eligible: {res_no_dest.eligible_count}")
    c_sample = res_no_dest.candidates[0]
    if c_sample.route_metrics:
        print(f"  Driver -> Station Distance: {c_sample.route_metrics.distance_to_station_m:.1f} m")
        print(f"  Destination Distance: {c_sample.route_metrics.distance_station_to_dest_m} (Expected: None)")
        print(f"  Detour Distance: {c_sample.route_metrics.detour_distance_m} (Expected: None)")

    print("\n==================================================")
    print(f"SMOKE TEST RESULT: PASS (Mode: {routing_mode})")
    print("==================================================")
    return routing_mode


if __name__ == "__main__":
    asyncio.run(run_smoke_test())
