import pytest
from backend.app.services.energy.replenishment import estimate_replenishment
from backend.app.services.demand.models import VehicleCapability, VehicleCategory, ServiceType
from types import SimpleNamespace

CAP = VehicleCapability(vehicle_model='test', vehicle_category=VehicleCategory.EV_CAR, usable_capacity_kwh=20, estimated_consumption_wh_per_km=200)
def energy(soc=20, **kw):
    return SimpleNamespace(current_soc_pct=soc, remaining_energy_kwh=None, estimated_remaining_range_km=soc, usable_capacity_kwh=20, battery_capacity_kwh=20, installed_battery_modules=None, safety_reserve_km=5, **kw)

def test_low_soc_can_charge_for_onward():
    p = estimate_replenishment(energy(), CAP, ServiceType.CHARGING, 5000, 40000, 20)
    assert p.status == 'AVAILABLE'
    assert p.arrival_energy_kwh == pytest.approx(3)
    assert p.departure_energy_kwh == pytest.approx(9)
    assert p.destination_energy_kwh == pytest.approx(1)
    assert p.added_energy_kwh == pytest.approx(6)
    assert p.service_duration_s == pytest.approx(860)

def test_capacity_limit_and_swap_limit():
    assert estimate_replenishment(energy(), CAP, ServiceType.CHARGING, 5000, 100000, 20).status == 'INFEASIBLE'
    assert estimate_replenishment(energy(), CAP, ServiceType.BATTERY_SWAP, 5000, 90000, 3).status == 'INFEASIBLE'

def test_no_b_target_and_high_soc_zero_duration():
    p = estimate_replenishment(energy(), CAP, ServiceType.CHARGING, 5000, None, 20)
    assert p.target_soc_pct == 80
    assert p.added_energy_kwh == 13
    assert estimate_replenishment(energy(95), CAP, ServiceType.CHARGING, 1000, None, 20).service_duration_s == 0

def test_invalid_energy_is_not_free_service():
    for value in [None, float('nan'), -1, 101]:
        assert estimate_replenishment(energy(value), CAP, ServiceType.CHARGING, 1000, None, 20).status == 'UNAVAILABLE'

def test_installed_modules_and_explicit_energy_are_preserved():
    from backend.app.services.demand.service import create_demand_service
    from backend.app.services.demand.models import DemandContext, RequestedServiceType
    svc = create_demand_service()
    context = DemandContext(vehicle_id='V0006', current_soc_pct=50)
    result = svc.process_driver_request(context, RequestedServiceType.ANY)
    assert result.usable_capacity_kwh == pytest.approx(1.38)
    assert result.remaining_energy_kwh == pytest.approx(.69)
    cap = svc._resolver.resolve_by_vehicle_id('V0006')
    p = estimate_replenishment(result, cap, ServiceType.BATTERY_SWAP, 1000, None, 3)
    assert p.effective_capacity_kwh == pytest.approx(1.38)
    explicit = context.model_copy(update={'remaining_energy_kwh': .5, 'estimated_remaining_range_km': 10})
    result = svc.process_driver_request(explicit, RequestedServiceType.ANY)
    p = estimate_replenishment(result, cap, ServiceType.BATTERY_SWAP, 1000, None, 3)
    assert p.consumption_kwh_per_km == pytest.approx(.05)
    assert p.arrival_energy_kwh == pytest.approx(.45)

def test_swap_refresh_keeps_energy_and_counts_queue_once():
    from backend.app.services.ranking.context import build_features
    from backend.app.services.ranking.models import RankingPolicy
    from backend.app.services.ranking.service import rank_features
    from backend.app.services.candidate.station_catalog import station_catalog
    from backend.tests.test_week4_ranking import candidate, evidence, view, station, queue, NOW
    plan = estimate_replenishment(energy(), CAP, ServiceType.BATTERY_SWAP, 1000, None, 3)
    row = candidate(service=ServiceType.BATTERY_SWAP, replenishment=plan)
    f, = build_features(evidence([row]), view(station(swap_service_time_min=7), queue()), NOW, RankingPolicy(), station_catalog)
    assert f.replenishment.departure_soc_pct == 90
    assert f.service_duration_s == 420
    assert f.effective_queue_wait_s == 60
    ranked, = rank_features([f])
    assert ranked.total_completion_time_s == 100 + 60 + 420


@pytest.mark.asyncio
async def test_after_b_consumes_prefix_once_without_mutating_live_energy(client, app, monkeypatch):
    from backend.tests.test_route_familiarity_workflow import workflow, body
    from backend.app.config import settings
    monkeypatch.setattr(settings, 'enable_route_familiarity', False)
    app.state.recommendation_workflow = workflow()
    payload = body() | {'plan_mode': 'AFTER_DESTINATION'}
    response = await client.post('/api/v1/recommend', json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['energy_context']['current_soc_pct'] == 60
    assert result['energy_context']['estimated_remaining_range_km'] == 200
    saved = await app.state.recommendation_workflow.repository.get_search(result['candidate_search_id'])
    initial_energy = result['energy_context']['remaining_energy_kwh']
    consumption = initial_energy / 200
    assert saved.energy_request.remaining_energy_kwh == pytest.approx(initial_energy - consumption)
    p = result['ranked_candidates'][0]['features']['replenishment']
    assert p['arrival_energy_kwh'] == pytest.approx(initial_energy - 2 * consumption)
    assert p['target_soc_pct'] == pytest.approx(80)


def test_vf3_official_peak_limits_configured_charging_power():
    cap = CAP.model_copy(update={'vehicle_model': 'VF_3'})
    p = estimate_replenishment(energy(), cap, ServiceType.CHARGING, 5000, 40000, 20)
    assert p.effective_charge_power_kw == 24
    assert p.service_duration_s == pytest.approx(1060)


def test_config_rejects_nonfinite_or_invalid_assumptions():
    from backend.app.config import Settings
    for field, value in [('charge_car_station_kw', float('inf')), ('charge_efficiency', 0), ('charge_efficiency', 1.1), ('swap_departure_soc_pct', 101)]:
        with pytest.raises(ValueError):
            Settings(_env_file=None, **{field: value})

@pytest.mark.asyncio
async def test_route_signature_cpu_work_does_not_hold_event_loop(app, monkeypatch):
    import asyncio
    import threading
    import time
    from backend.app.services.route_familiarity import signature
    from backend.tests.test_route_familiarity_workflow import workflow, search_request
    started, finished = threading.Event(), threading.Event()
    original = signature.create_route_signature
    def slow_signature(lines):
        started.set()
        time.sleep(.1)
        result = original(lines)
        finished.set()
        return result
    monkeypatch.setattr(signature, 'create_route_signature', slow_signature)
    async def other_driver():
        while not started.is_set():
            await asyncio.sleep(.001)
        return not finished.is_set()
    combined = workflow()
    concurrent = asyncio.create_task(other_driver())
    await combined._search(search_request(app), collect_signatures=True)
    assert await concurrent

def test_capacity_metadata_cannot_override_canonical_vehicle():
    request = energy()
    request.usable_capacity_kwh = 200
    assert estimate_replenishment(request, CAP, ServiceType.CHARGING, 1000, None, 20).status == 'UNAVAILABLE'


def test_missing_reserve_uses_existing_domain_policy():
    request = energy()
    request.safety_reserve_km = None
    p = estimate_replenishment(request, CAP, ServiceType.CHARGING, 5000, 40000, 20)
    assert p.safety_reserve_km == 6
    assert p.destination_energy_kwh == pytest.approx(1.2)

def test_explicit_energy_drives_derived_range_in_demand_and_replenishment():
    from backend.app.services.demand.service import create_demand_service
    from backend.app.services.demand.models import DemandContext, RequestedServiceType
    svc = create_demand_service()
    result = svc.process_driver_request(DemandContext(vehicle_id='V0001', current_soc_pct=60, remaining_energy_kwh=1, remaining_trip_distance_km=5), RequestedServiceType.CHARGING)
    cap = svc._resolver.resolve_by_vehicle_id('V0001')
    assert result.estimated_remaining_range_km == pytest.approx(1000 / cap.get_effective_consumption_wh_per_km(), abs=.001)
    assert result.current_soc_pct == 60
    assert result.energy_assessment.warning_level == 'ADVISORY'
    p = estimate_replenishment(result, cap, ServiceType.CHARGING, 1000, None, 20)
    assert p.energy_source == 'EXPLICIT_REMAINING_ENERGY'
    assert p.range_source == 'ENERGY_AND_CATALOG_CONSUMPTION'


@pytest.mark.parametrize('remaining', [-1, 10000])
def test_invalid_explicit_energy_withholds_physical_assessment(remaining):
    from backend.app.services.demand.service import create_demand_service
    from backend.app.services.demand.models import DemandContext, RequestedServiceType
    result = create_demand_service().process_driver_request(DemandContext(vehicle_id='V0001', current_soc_pct=60, remaining_energy_kwh=remaining, remaining_trip_distance_km=5), RequestedServiceType.CHARGING)
    assert result.energy_assessment.warning_level == 'UNAVAILABLE'
