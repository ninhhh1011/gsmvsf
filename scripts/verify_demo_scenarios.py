"""
End-to-end live demonstration and verification script for Week 5.5 Demo Scenarios.
Executes against live running backend services (FastAPI, GraphHopper, PostGIS, Redis).
"""

import json
import sys
import httpx
from datetime import datetime, timezone

BASE_URL = "http://127.0.0.1:8000"

def run_all_scenarios():
    client = httpx.Client(base_url=BASE_URL, timeout=15.0)

    results = {}
    print("==================================================")
    print("RUNNING LIVE WEEK 5.5 DEMO SCENARIOS VERIFICATION")
    print("==================================================")

    # Health check
    ready = client.get("/ready").json()
    print(f"Backend Readiness: {ready}")
    assert ready.get("status") == "ready", "Backend dependencies not ready"

    # SCENARIO 1: Driver trip safe
    print("\n--- SCENARIO 1: Driver trip safe ---")
    s1_resp = client.post("/api/v1/recommend", json={
        "context": {
            "vehicle_id": "V0001",
            "timestamp": "2026-09-01T06:06:00Z",
            "current_soc_pct": 85.0,
            "estimated_remaining_range_km": 100.0,
            "remaining_trip_distance_km": 3.5,
            "safety_reserve_km": 1.0,
            "raw_latitude": 21.0182,
            "raw_longitude": 105.8152
        },
        "destination_latitude": 21.0365,
        "destination_longitude": 105.8341
    }).json()

    print("Reason:", s1_resp.get("reason"))
    print("Need service:", s1_resp["energy_context"]["need_service"])
    print("Reason code:", s1_resp["energy_context"]["reason_code"])
    print("Has rec:", s1_resp.get("has_recommendation"))
    assert s1_resp["energy_context"]["need_service"] is False
    assert s1_resp["energy_context"]["reason_code"] == "SUFFICIENT_SOC_RANGE"
    results["scenario_1"] = {
        "status": "PASS",
        "need_service": s1_resp["energy_context"]["need_service"],
        "reason_code": s1_resp["energy_context"]["reason_code"],
        "level": "SAFE"
    }

    # SCENARIO 2: Destination reachable but reserve insufficient (Advisory)
    print("\n--- SCENARIO 2: Destination reachable but reserve insufficient ---")
    s2_resp = client.post("/api/v1/recommend", json={
        "context": {
            "vehicle_id": "V0004",
            "timestamp": "2026-09-01T06:40:00Z",
            "current_soc_pct": 22.0,
            "estimated_remaining_range_km": 12.0,
            "remaining_trip_distance_km": 10.0,
            "safety_reserve_km": 5.0,
            "raw_latitude": 21.0285,
            "raw_longitude": 105.8542
        },
        "destination_latitude": 20.9850,
        "destination_longitude": 105.8120
    }).json()

    print("Reason code:", s2_resp["energy_context"]["reason_code"])
    print("Margin km:", s2_resp["energy_context"]["energy_margin_km"])
    assert s2_resp["energy_context"]["need_service"] is True
    assert s2_resp["energy_context"]["reason_code"] == "INSUFFICIENT_POST_DESTINATION_RESERVE"
    results["scenario_2"] = {
        "status": "PASS",
        "reason_code": s2_resp["energy_context"]["reason_code"],
        "margin_km": s2_resp["energy_context"]["energy_margin_km"],
        "level": "ADVISORY"
    }

    # SCENARIO 3: Destination not reachable (Critical)
    print("\n--- SCENARIO 3: Destination not reachable ---")
    s3_resp = client.post("/api/v1/recommend", json={
        "context": {
            "vehicle_id": "V0004",
            "timestamp": "2026-09-01T06:40:00Z",
            "current_soc_pct": 25.0,
            "estimated_remaining_range_km": 30.0,
            "remaining_trip_distance_km": 45.0,
            "safety_reserve_km": 5.0,
            "raw_latitude": 21.0285,
            "raw_longitude": 105.8542
        },
        "destination_latitude": 20.9850,
        "destination_longitude": 105.8120
    }).json()

    print("Reason code:", s3_resp["energy_context"]["reason_code"])
    print("Range vs Trip:", s3_resp["energy_context"]["estimated_remaining_range_km"], "<", s3_resp["energy_context"]["remaining_trip_distance_km"])
    assert s3_resp["energy_context"]["need_service"] is True
    assert s3_resp["energy_context"]["reason_code"] == "DESTINATION_NOT_REACHABLE"
    results["scenario_3"] = {
        "status": "PASS",
        "reason_code": s3_resp["energy_context"]["reason_code"],
        "level": "CRITICAL"
    }

    # SCENARIO 4: Charge recommendation
    print("\n--- SCENARIO 4: Charge recommendation ---")
    s4_resp = client.post("/api/v1/recommend", json={
        "context": {
            "vehicle_id": "V0004",
            "timestamp": "2026-09-01T06:24:00Z",
            "current_soc_pct": 12.0,
            "estimated_remaining_range_km": 25.0,
            "remaining_trip_distance_km": 4.1,
            "safety_reserve_km": 2.0,
            "raw_latitude": 21.0285,
            "raw_longitude": 105.8542
        },
        "requested_service": "CHARGING",
        "destination_latitude": 21.0450,
        "destination_longitude": 105.8350
    }).json()

    rec_st = s4_resp.get("recommended_station_id")
    rec_srv = s4_resp.get("recommended_service_type")
    top_cost = s4_resp["ranked_candidates"][0]["final_cost_s"]
    print(f"Recommended: {rec_st} ({rec_srv}), Cost: {top_cost:.1f}s")
    assert s4_resp.get("has_recommendation") is True
    assert rec_srv == "CHARGING"
    assert len(s4_resp.get("ranked_candidates", [])) > 0
    results["scenario_4"] = {
        "status": "PASS",
        "station_id": rec_st,
        "service_type": rec_srv,
        "cost_s": top_cost,
        "ranked_count": len(s4_resp["ranked_candidates"])
    }

    # SCENARIO 5: Swap recommendation
    print("\n--- SCENARIO 5: Swap recommendation ---")
    s5_resp = client.post("/api/v1/recommend", json={
        "context": {
            "vehicle_id": "V0003",
            "timestamp": "2026-09-01T00:40:00Z",
            "current_soc_pct": 10.0,
            "estimated_remaining_range_km": 15.0,
            "remaining_trip_distance_km": 4.0,
            "safety_reserve_km": 2.0,
            "raw_latitude": 21.0310,
            "raw_longitude": 105.8550
        },
        "requested_service": "BATTERY_SWAP",
        "destination_latitude": 21.0500,
        "destination_longitude": 105.8200
    }).json()

    rec_st = s5_resp.get("recommended_station_id")
    rec_srv = s5_resp.get("recommended_service_type")
    top_cost = s5_resp["ranked_candidates"][0]["final_cost_s"]
    print(f"Recommended: {rec_st} ({rec_srv}), Cost: {top_cost:.1f}s")
    assert s5_resp.get("has_recommendation") is True
    assert rec_srv == "BATTERY_SWAP"
    results["scenario_5"] = {
        "status": "PASS",
        "station_id": rec_st,
        "service_type": rec_srv,
        "cost_s": top_cost
    }

    # SCENARIO 6: Queue snapshot changes recommendation
    print("\n--- SCENARIO 6: Queue snapshot changes recommendation ---")
    payload_t1 = {
        "context": {
            "vehicle_id": "V0017",
            "timestamp": "2026-09-01T00:42:00Z",
            "current_soc_pct": 12.0,
            "estimated_remaining_range_km": 25.0,
            "remaining_trip_distance_km": 7.1,
            "safety_reserve_km": 2.0,
            "raw_latitude": 20.9729508,
            "raw_longitude": 105.8750792
        },
        "destination_latitude": 20.9717137,
        "destination_longitude": 105.8749075
    }
    payload_t2 = {
        "context": {
            "vehicle_id": "V0017",
            "timestamp": "2026-09-01T00:52:00Z",
            "current_soc_pct": 12.0,
            "estimated_remaining_range_km": 25.0,
            "remaining_trip_distance_km": 7.1,
            "safety_reserve_km": 2.0,
            "raw_latitude": 20.9729508,
            "raw_longitude": 105.8750792
        },
        "destination_latitude": 20.9717137,
        "destination_longitude": 105.8749075
    }
    r6_t1 = client.post("/api/v1/recommend", json=payload_t1).json()
    r6_t2 = client.post("/api/v1/recommend", json=payload_t2).json()

    st_t1 = r6_t1.get("recommended_station_id")
    st_t2 = r6_t2.get("recommended_service_type")
    st2_id = r6_t2.get("recommended_station_id")
    print(f"At T1 (07:42): Recommended {st_t1}")
    print(f"At T2 (07:52): Recommended {st2_id}")
    assert st_t1 == "S022", f"Expected S022 at T1, got {st_t1}"
    assert st2_id == "S016", f"Expected S016 at T2, got {st2_id}"
    results["scenario_6"] = {
        "status": "PASS",
        "t1_station": st_t1,
        "t2_station": st2_id,
        "switch_verified": True
    }

    # SCENARIO 7: Station OFFLINE causes candidate ineligibility
    print("\n--- SCENARIO 7: Station OFFLINE causes candidate ineligibility ---")
    s7_cand = client.post("/api/v1/candidate-search/evaluate", json={
        "vehicle_id": "V0001",
        "timestamp": "2026-09-01T08:00:00+07:00", # 08:00 VN when S001 is OFFLINE
        "current_soc_pct": 15.0,
        "estimated_remaining_range_km": 25.0,
        "remaining_trip_distance_km": 6.0,
        "raw_latitude": 21.0900,
        "raw_longitude": 105.7570,
        "eligible_only": False
    }).json()

    s001_cand = next((c for c in s7_cand.get("candidates", []) if c["station_id"] == "S001"), None)
    print(f"S001 at 08:00 VN: eligible={s001_cand.get('eligible')}, reason={s001_cand.get('reason')}")
    assert s001_cand is not None
    assert s001_cand["eligible"] is False
    assert s001_cand["reason"] == "OFFLINE"
    results["scenario_7"] = {
        "status": "PASS",
        "station_id": "S001",
        "eligible": False,
        "reason": "OFFLINE"
    }

    # SCENARIO 8: Simulation A -> B
    print("\n--- SCENARIO 8: Simulation A -> B ---")
    s8_route = client.post("/api/v1/route", json={
        "origin": {"latitude": 21.0285, "longitude": 105.8542},
        "destination": {"latitude": 21.0150, "longitude": 105.7800},
        "profile": {"vehicle_category": "EV_CAR"}
    }).json()

    print(f"Route status: {s8_route.get('status')}, Distance: {s8_route.get('distance_m')}m, Duration: {s8_route.get('duration_s')}s")
    assert s8_route.get("status") == "SUCCESS"
    assert s8_route.get("geometry") is not None
    results["scenario_8"] = {
        "status": "PASS",
        "distance_m": s8_route.get("distance_m"),
        "duration_s": s8_route.get("duration_s"),
        "has_geometry": bool(s8_route.get("geometry"))
    }

    print("\n==================================================")
    print("ALL 8 DEMO SCENARIOS VERIFIED SUCCESSFULLY!")
    print("==================================================")
    return results

if __name__ == "__main__":
    res = run_all_scenarios()
    print(json.dumps(res, indent=2))
