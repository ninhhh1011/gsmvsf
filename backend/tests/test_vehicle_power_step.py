import math
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.app.api.v1.vehicles import router
from backend.app.services.energy.powertrain_catalog import get_powertrain_spec
from backend.app.services.energy.physics_model import calculate_instantaneous_power

app = FastAPI()
app.include_router(router, prefix='/api/v1')
client = TestClient(app)

def step(**kwargs):
    return client.post('/api/v1/vehicles/power-step', json={
        'vehicle_model': 'VF_3', 'speed_kmh': 0, 'dt_seconds': 60,
        'current_soc_pct': 80, **kwargs})

def test_parked_hvac_depletes_soc_from_same_power():
    response = step()
    assert response.status_code == 200
    result = response.json()
    assert result['instantaneous_power_kw'] == 1.5
    assert result['energy_delta_kwh'] == pytest.approx(1.5 / 60)
    assert result['current_soc_pct'] == pytest.approx(80 - 100 * result['energy_delta_kwh'] / 17.15)
    assert result['estimated_range_km'] == pytest.approx(17.15 * result['current_soc_pct'] / 100 / .095)
    assert result['power_status'] == 'MODEL_ESTIMATE'

def test_regen_interval_restores_soc():
    result = step(speed_kmh=40, previous_speed_kmh=60, dt_seconds=5).json()
    assert result['instantaneous_power_kw'] < 0
    assert result['energy_delta_kwh'] < 0
    assert result['current_soc_pct'] > 80


def test_stopping_interval_recovers_energy_even_with_zero_endpoint_speed():
    result = step(speed_kmh=0, previous_speed_kmh=50, dt_seconds=10).json()
    assert result['instantaneous_power_kw'] == 1.5
    assert result['energy_delta_kwh'] < 0
    assert result['current_soc_pct'] > 80


def test_battery_power_is_not_capped_at_mechanical_motor_limit():
    from dataclasses import replace
    spec = replace(get_powertrain_spec('VF_3'), max_motor_power_kw=1.0)
    result = calculate_instantaneous_power(spec, speed_kmh=30)
    assert result.total_power_kw > spec.max_motor_power_kw
    assert result.power_status == 'KINEMATICS_EXCEED_CAPABILITY'

def test_zero_interval_has_power_without_energy_or_soc_change():
    result = step(dt_seconds=0, speed_kmh=40, previous_speed_kmh=0).json()
    assert result['instantaneous_power_kw'] > 0
    assert result['energy_delta_kwh'] == 0
    assert result['current_soc_pct'] == 80

def test_infeasible_kinematics_are_explicit_and_not_clipped():
    result = step(speed_kmh=80, previous_speed_kmh=0, dt_seconds=1).json()
    assert result['power_status'] == 'KINEMATICS_EXCEED_CAPABILITY'
    assert result['instantaneous_power_kw'] > result['max_motor_power_kw']

@pytest.mark.parametrize('field,value', [('dt_seconds',-1), ('dt_seconds',3601), ('speed_kmh',-1), ('previous_speed_kmh',-1), ('current_soc_pct',101)])
def test_invalid_step_rejected(field,value):
    assert step(**{field:value}).status_code == 422

@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Infinity'])
def test_nonfinite_step_rejected(value):
    assert step(speed_kmh=value).status_code == 422

def test_unsupported_model_has_no_invented_power():
    result = step(vehicle_model='BYD_ATTO_3').json()
    assert result['power_status'] == 'UNSUPPORTED_MODEL'
    assert result['instantaneous_power_kw'] is None
    assert result['energy_delta_kwh'] is None
    assert result['current_soc_pct'] == 80
    assert step(vehicle_model='NO_SUCH_CAR').status_code == 422
    with pytest.raises(ValueError, match='Unsupported'):
        get_powertrain_spec('NO_SUCH_CAR')

def test_catalog_preserves_physical_metadata_with_field_provenance():
    catalog = {row['id']: row for row in client.get('/api/v1/vehicles/catalog').json()}
    vf3 = catalog['VF_3']
    assert vf3['max_motor_power_kw'] == 30
    assert vf3['parameters_status'] != 'OFFICIAL_VERIFIED'
    assert vf3['parameter_provenance']['max_motor_power_kw']['status'] == 'OFFICIAL_VERIFIED'
    assert vf3['parameter_provenance']['drag_coefficient']['status'] == 'PROJECT_ASSUMPTION'
    assert catalog['BYD_ATTO_3']['max_motor_power_kw'] is None
    assert catalog['BYD_ATTO_3']['parameters_status'] == 'UNSUPPORTED_MODEL'
    assert catalog['BYD_ATTO_3']['parameter_provenance']['drag_coefficient']['status'] == 'UNAVAILABLE'
    assert vf3['parameter_provenance']['efficiency_kwh_per_km']['status'] == 'PROJECT_ESTIMATE'


def test_overflowing_acceleration_is_rejected_at_api_boundary():
    assert step(speed_kmh=1000, previous_speed_kmh=0, dt_seconds=1e-310).status_code == 422

@pytest.mark.parametrize('kwargs', [{'speed_kmh':-1}, {'speed_kmh':math.nan}, {'speed_kmh':1, 'acceleration_ms2':math.inf}])
def test_physics_trust_boundary_rejects_invalid_inputs(kwargs):
    with pytest.raises(ValueError):
        calculate_instantaneous_power(get_powertrain_spec('VF_3'), **kwargs)
