"""Verify new code against real GraphHopper and a disposable PostgreSQL database."""
import asyncio
import hashlib
import hmac
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import asyncpg
import httpx

from backend.app.config import settings
from backend.app.main import create_app
from backend.app.services.route_familiarity.repository import RouteHistoryRepository
from backend.app.services.route_familiarity.service import RouteFamiliarityService
from backend.app.services.route_familiarity.signature import create_route_signature, decode_polyline
from backend.app.services.routing.graphhopper_routing_adapter import GraphHopperRoutingAdapter
from backend.app.services.routing.models import Position, RouteRequest, VehicleRoutingProfile
from backend.app.services.snapshots.models import StateError
from scripts.benchmark_route_familiarity import host_accessible_database_url


async def main():
    report = {}
    async with httpx.AsyncClient(timeout=30) as client:
        adapter = GraphHopperRoutingAdapter(base_url="http://127.0.0.1:8989", client=client)
        result = await adapter.route(RouteRequest(
            origin=Position(latitude=21.0015, longitude=105.8200),
            destination=Position(latitude=20.9985, longitude=105.8350),
            profile=VehicleRoutingProfile(vehicle_category="EV_CAR")))
        assert result.status.value == "SUCCESS", result.status
        signature = create_route_signature([result.geometry])
        report["graphhopper"] = {"status": result.status.value, "engine": result.engine_name,
                                 "distance_m": result.distance_m, "geometry_vertices": len(signature.coordinates)}

    dsn = host_accessible_database_url(settings.database_url).replace("postgresql+asyncpg://", "postgresql://")
    parts = urlsplit(dsn)
    admin_url = urlunsplit(parts._replace(path="/postgres"))
    database_name = "offline_route_verify_" + uuid4().hex
    test_url = urlunsplit(parts._replace(path="/" + database_name))
    admin = await asyncpg.connect(admin_url, timeout=10)
    pool = None
    created = False
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        created = True
        pool = await asyncpg.create_pool(test_url, min_size=1, max_size=2, timeout=10)
        repo = RouteHistoryRepository(pool)
        await repo.ensure_schema()
        await repo.ensure_schema()
        now = datetime(2026, 10, 10, 6, 30, tzinfo=UTC)
        start, end = now - timedelta(minutes=10), now - timedelta(minutes=1)
        # Simulate existing cell-only history, then fill only missing trusted evidence.
        async with pool.acquire() as conn:
            await conn.execute("""INSERT INTO realtime.route_familiarity_routes
                (driver_id,trip_id,completed_at,distance_m,resolution,cells,cell_distances_m)
                VALUES ($1,$2,$3,$4,$5,$6,$7)""", "driver", "legacy", end,
                signature.distance_m, signature.resolution, list(signature.cells), list(signature.cell_distances_m))
        _, inserted = await repo.upsert_route("driver", "legacy", end, signature, start)
        assert not inserted
        _, inserted = await repo.upsert_route("driver", "legacy", end, signature, start)
        assert not inserted
        try:
            await repo.upsert_route("driver", "legacy", end,
                                   replace(signature, coordinates=tuple(reversed(signature.coordinates))), start)
        except StateError as exc:
            assert exc.status == 409
        else:
            raise AssertionError("known geometry was replaced")
        await repo.upsert_route("driver", "equal-time", now, signature, start)
        for index in range(5):
            await repo.upsert_route(f"community-{index}", f"trip-{index}", end, signature, start)
        personal = await repo.personal_routes("driver", now, timedelta(days=7))
        assert [row["trip_id"] for row in personal] == ["legacy"]
        assessment = (await RouteFamiliarityService(repo).assess_many(
            "driver", {("station", "CHARGING"): signature}, now))["station", "CHARGING"]
        assert assessment.status == "AVAILABLE"
        assert assessment.personal_adherence > .99
        assert assessment.community_driver_count == 5
        report["postgresql"] = {"additive_migration_twice": "PASS", "legacy_upgrade": "PASS",
            "idempotency": "PASS", "conflicting_geometry": "409", "completion_equal_as_of_excluded": True,
            "personal_adherence": assessment.personal_adherence, "community_drivers": assessment.community_driver_count}

        settings.enable_route_familiarity = True
        settings.route_familiarity_identity_secret = "isolated-verification-secret-32bytes"
        app = create_app()
        app.state.route_history_repository = repo
        signed = hmac.new(settings.route_familiarity_identity_secret.encode(), b"driver", hashlib.sha256).hexdigest()
        payload = dict(proposed_coordinates=decode_polyline(result.geometry),
                       actual_coordinates=decode_polyline(result.geometry), driver_id="driver", as_of_iso=now.isoformat())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://verification") as client:
            rejected = await client.post("/api/v1/routing/compare-routes", json=payload)
            assert rejected.status_code == 401
            response = await client.post("/api/v1/routing/compare-routes", json=payload,
                                         headers={"X-Driver-Identity-Signature": signed})
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["shared_pct_on_proposed"] > 99
            assert body["history_stats"]["status"] == "AVAILABLE"
            assert body["history_stats"]["community_supporting_driver_count"] == 5
            power = await client.post("/api/v1/vehicles/power-step", json=dict(
                vehicle_model="VF_3", speed_kmh=0, previous_speed_kmh=0, dt_seconds=60, current_soc_pct=80))
            assert power.status_code == 200
            assert power.json()["current_soc_pct"] < 80
            report["new_api"] = {"unauthenticated_history": rejected.status_code,
                "authenticated_comparison": response.status_code,
                "offline_shared_pct": body["shared_pct_on_proposed"],
                "stationary_energy_kwh": power.json()["energy_delta_kwh"]}
    finally:
        if pool is not None:
            await pool.close()
        if created:
            await admin.execute(f'DROP DATABASE "{database_name}"')
        await admin.close()
    report["disposable_database_removed"] = True
    Path("runtime/offline-route-fixes/live-verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


asyncio.run(main())
