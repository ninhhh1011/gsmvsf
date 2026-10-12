"""Verify real cross-replica state and journey contracts without mocks."""
import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import uuid4

import httpx


async def main():
    results = []
    async with httpx.AsyncClient(timeout=120) as client:
        config = (await client.get('http://127.0.0.1:8000/api/v1/config')).json()
        identity = config['route_familiarity_identity']
        assert identity and len(identity['signature']) == 64
        driver = 'journey-check-' + uuid4().hex
        timestamp = datetime.now(UTC).isoformat()
        gps = {'vehicle_id': 'V0001', 'timestamp': timestamp, 'observation_id': 'first',
               'latitude': 20.9849, 'longitude': 105.7935, 'speed_kmh': 20}
        response = await client.post(f'http://127.0.0.1:8000/api/v1/drivers/{driver}/location', json=gps)
        assert response.status_code == 200, response.text
        body = {'vehicle_id': 'V0001', 'current_soc_pct': 84}
        response = await client.post(f'http://127.0.0.1:8002/api/v1/drivers/{driver}/demand/evaluate', json=body)
        assert response.status_code == 200, response.text
        assert response.json()['latitude'] == gps['latitude']
        results.append({'check': 'shared accepted GPS visible on replica2', 'pass': True})
        response = await client.delete(f'http://127.0.0.1:8000/api/v1/drivers/{driver}/location')
        assert response.status_code == 200, response.text
        response = await client.post(f'http://127.0.0.1:8002/api/v1/drivers/{driver}/demand/evaluate', json=body)
        assert response.status_code == 200 and response.json()['latitude'] is None, response.text
        results.append({'check': 'reset visible on replica2', 'pass': True})
        headers = {'x-driver-identity-signature': identity['signature']}
        for mode, destination in [('STATION_ONLY', {}), ('BEFORE_DESTINATION', {
                'destination_latitude': 21.0315, 'destination_longitude': 105.7830}),
                ('AFTER_DESTINATION', {'destination_latitude': 21.0315,
                                       'destination_longitude': 105.7830})]:
            payload = {'context': {'vehicle_id': 'V0001', 'driver_id': identity['driver_id'],
                'timestamp': datetime.now(UTC).isoformat(), 'current_soc_pct': 84,
                'raw_latitude': 20.9849, 'raw_longitude': 105.7935},
                'requested_service': 'ANY', **destination}
            if mode == 'AFTER_DESTINATION':
                payload['plan_mode'] = mode
            response = await client.post('http://127.0.0.1:8002/api/v1/recommend', json=payload, headers=headers)
            assert response.status_code == 200, response.text
            rec = response.json()
            assert rec['ranked_candidates'], rec
            best = rec['ranked_candidates'][0]
            assert abs(best['ranking_score'] - sum(best['score_components'].values())) < 1e-8
            feature = best['features']
            assert abs(best['total_completion_time_s'] - best['eta_to_service_complete_s'] -
                       (feature['duration_station_to_dest_s'] or 0)) < 1e-6
            invalidations = 0
            for attempt in range(3):
                response = await client.post('http://127.0.0.1:8002/api/v1/station-plan',
                    json={**payload, 'station_id': best['station_id'], 'service_type': best['service_type']},
                    headers=headers)
                if response.status_code != 409 or attempt == 2:
                    break
                invalidations += 1
                payload['context']['timestamp'] = datetime.now(UTC).isoformat()
                refreshed = await client.post('http://127.0.0.1:8002/api/v1/recommend', json=payload, headers=headers)
                assert refreshed.status_code == 200, refreshed.text
                best = refreshed.json()['ranked_candidates'][0]
            assert response.status_code == 200, response.text
            plan = response.json()
            assert len(plan['route']['geometry']) >= 2
            results.append({'check': mode, 'pass': True, 'station': best['station_id'],
                'total_completion_time_s': best['total_completion_time_s'],
                'ranking_score': best['ranking_score'], 'familiarity': best['familiarity'],
                'geometry_vertices': len(plan['route']['geometry']),
                'explicit_reselections_after_invalidation': invalidations})
        response = await client.post('http://127.0.0.1:8002/api/v1/recommend',
            json={**payload, 'context': {**payload['context'], 'driver_id': 'arbitrary-real-driver'}}, headers=headers)
        assert response.status_code == 403, response.text
        results.append({'check': 'sample signature cannot read arbitrary identity', 'pass': True})
    output = Path('runtime/journey-scale/live-contract.json')
    output.write_text(json.dumps(results, indent=2), encoding='utf8')
    print(json.dumps({'passed': len(results), 'report': str(output)}))


if __name__ == '__main__':
    asyncio.run(main())
