"""Shared-state replicas must retain identical identity and one simulator producer."""
from pathlib import Path

import yaml


def test_four_api_replicas_share_contract_and_gateway_with_one_simulator():
    services = yaml.safe_load(Path('docker-compose.yml').read_text('utf-8'))['services']
    replicas = [services[f'api_{index}'] for index in range(1, 5)]
    environments = [dict(entry.split('=', 1) for entry in replica['environment']) for replica in replicas]
    for name in ('DATABASE_URL', 'REDIS_URL', 'ROUTE_FAMILIARITY_IDENTITY_SECRET',
                 'SNAPSHOT_INGESTION_TOKEN', 'ROUTE_HISTORY_NAMESPACE', 'ENABLE_ROUTE_FAMILIARITY'):
        assert len({environment[name] for environment in environments}) == 1
    assert environments[0]['ENABLE_REALTIME_SIMULATOR'] == '${ENABLE_REALTIME_SIMULATOR:-true}'
    assert all(environment['ENABLE_REALTIME_SIMULATOR'] == 'false' for environment in environments[1:])
    assert all(environment['MAX_CONCURRENT_ROUTES'] == '${MAX_CONCURRENT_ROUTES:-4}' for environment in environments)
    assert all(replica['volumes'] == ['./dataset_v1:/app/dataset_v1:ro'] for replica in replicas)
    assert [replica['ports'] for replica in replicas] == [[f'127.0.0.1:{port}:8000'] for port in (8000, 8002, 8003, 8004)]
    gateway = Path('frontend/nginx.conf').read_text('utf-8')
    for index in range(1, 5):
        assert f'server api_{index}:8000 ' in gateway
        assert services['frontend']['depends_on'][f'api_{index}']['condition'] == 'service_healthy'
