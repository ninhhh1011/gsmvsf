from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.config import Settings, settings
from backend.app.services.route_familiarity.repository import RouteHistoryRepository


def test_public_sample_requires_isolated_enabled_history():
    with pytest.raises(ValueError):
        Settings(_env_file=None, public_synthetic_sample=True)
    with pytest.raises(ValueError):
        RouteHistoryRepository(None, namespace='public; DROP SCHEMA realtime')


async def test_only_synthetic_mode_exposes_fixed_read_signature(client, monkeypatch):
    monkeypatch.setattr(settings, 'enable_route_familiarity', True)
    monkeypatch.setattr(settings, 'route_familiarity_identity_secret', 'x' * 32)
    monkeypatch.setattr(settings, 'route_history_namespace', 'synthetic')
    monkeypatch.setattr(settings, 'public_synthetic_sample', True)
    result = (await client.get('/api/v1/config')).json()
    identity = result['route_familiarity_identity']
    from backend.app.api.v1.ranking import verify_driver_identity
    assert identity['driver_id'] == 'synthetic_sample_driver'
    assert verify_driver_identity(identity['driver_id'], identity['signature'], 'x' * 32)
    assert not verify_driver_identity('real_driver', identity['signature'], 'x' * 32)
    assert 'x' * 32 not in str(result)
    monkeypatch.setattr(settings, 'route_history_namespace', 'realtime')
    assert (await client.get('/api/v1/config')).json()['route_familiarity_identity'] is None


async def test_queries_and_migration_stay_inside_selected_namespace():
    conn = AsyncMock()
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    repo = RouteHistoryRepository(pool, namespace='synthetic')
    await repo.ensure_schema()
    assert 'realtime.' not in conn.execute.call_args.args[0]
    assert 'synthetic.route_familiarity_routes' in conn.execute.call_args.args[0]
    from datetime import UTC, datetime, timedelta
    await repo.personal_routes('d', datetime.now(UTC), timedelta(days=7))
    await repo.community_routes(['cell'], 'd', datetime.now(UTC), timedelta(days=7))
    for call in conn.fetch.call_args_list:
        assert 'synthetic.route_familiarity_routes' in call.args[0]
        assert 'realtime.' not in call.args[0]
