"""Untrusted nonfinite telemetry must not enter state or energy calculations."""
import json

import pytest
from pydantic import ValidationError

from backend.app.api.v1.demand import EnergyStepRequest
from backend.app.api.v1.realtime import LocationIngestionRequest
from backend.app.services.map_matching.models import GPSObservation

@pytest.mark.parametrize('value',[float('inf'),float('nan'),float('-inf')])
@pytest.mark.parametrize('field',['speed_kmh','accuracy_m','heading_deg'])
def test_gps_request_models_reject_nonfinite(field,value):
    common={'timestamp':'2026-01-01T00:00:00Z','latitude':21,'longitude':105,field:value}
    with pytest.raises(ValidationError):
        LocationIngestionRequest(**common)
    with pytest.raises(ValidationError):
        GPSObservation(observation_id='a',trajectory_id='a',trip_id='a',**common)

@pytest.mark.parametrize('value',[float('inf'),float('nan'),float('-inf')])
@pytest.mark.parametrize('field',['distance_km','current_soc_pct','consumption_wh_per_km'])
def test_legacy_energy_rejects_nonfinite(field,value):
    payload={'vehicle_model':'VF_3','distance_km':1,'current_soc_pct':80,field:value}
    with pytest.raises(ValidationError):
        EnergyStepRequest(**payload)

@pytest.mark.asyncio
@pytest.mark.parametrize('token',['1e309','NaN'])
@pytest.mark.parametrize('field',['speed_kmh','accuracy_m'])
async def test_invalid_gps_http_is_422_and_not_accepted(client,app,field,token):
    payload={'timestamp':'2026-01-01T00:00:00Z','latitude':21,'longitude':105}
    raw=json.dumps(payload)[:-1]+f',"{field}":{token}'+'}'
    response=await client.post('/api/v1/drivers/nonfinite-regression/location',content=raw,headers={'Content-Type':'application/json'})
    assert response.status_code==422
    state=await app.state.driver_state_manager.get_or_create('nonfinite-regression')
    assert state.total_observations_received==0

@pytest.mark.asyncio
@pytest.mark.parametrize('token',['1e309','NaN'])
@pytest.mark.parametrize('field',['distance_km','consumption_wh_per_km'])
async def test_invalid_legacy_energy_http_is_422(client,field,token):
    payload={'vehicle_model':'VF_3','distance_km':1,'current_soc_pct':80}
    raw=json.dumps(payload)[:-1]+f',"{field}":{token}'+'}'
    response=await client.post('/api/v1/vehicles/energy-step',content=raw,headers={'Content-Type':'application/json'})
    assert response.status_code==422

@pytest.mark.asyncio
async def test_validation_metadata_does_not_echo_private_payload(client):
    response=await client.post('/api/v1/drivers/nonfinite-regression/location',json={
        'timestamp':'2026-01-01T00:00:00Z','latitude':21,'longitude':105,
        'speed_kmh':'private-telemetry-value'})
    assert response.status_code==422
    error=response.json()['detail'][0]
    assert error['loc']==['body','speed_kmh']
    assert error['type']=='float_parsing'
    assert error['msg']
    assert 'input' not in error and 'ctx' not in error
    assert 'private-telemetry-value' not in response.text

def test_finite_zero_gps_preserves_timestamp():
    stamp='2026-01-01T07:00:00+07:00'
    common={'timestamp':stamp,'latitude':0,'longitude':0,'speed_kmh':0,'accuracy_m':0}
    assert LocationIngestionRequest(**common).timestamp.isoformat()==stamp
    assert GPSObservation(observation_id='a',trajectory_id='a',trip_id='a',**common).timestamp==stamp
