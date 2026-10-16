"""Read-only capture of bounded synthetic history; no Dataset or history writes."""
import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import asyncpg

from backend.app.config import settings
from backend.app.services.route_familiarity.repository import RouteHistoryRepository, coordinates_from_row


async def main():
    as_of = datetime.now(UTC)
    async with asyncpg.create_pool(settings.database_url.replace('postgresql+asyncpg://', 'postgresql://'), min_size=1, max_size=1) as pool:
        repository = RouteHistoryRepository(pool, 'synthetic')
        personal = await repository.personal_routes('synthetic-scale-final-500-0000', as_of, timedelta(days=7))
        community = await repository.community_routes(['fixture'], 'synthetic-scale-final-500-0000', as_of, timedelta(days=7))
    routes, indexes, drivers = [], {}, {}
    def row(value):
        geometry = coordinates_from_row(value)
        if geometry not in indexes:
            indexes[geometry] = len(routes)
            routes.append(geometry)
        driver = value.get('driver_id', 'personal')
        if driver not in drivers:
            drivers[driver] = f'synthetic-fixture-{len(drivers)}'
        return {'route': indexes[geometry], 'driver_id': drivers[driver],
                'started_at': value['started_at'].isoformat(), 'completed_at': value['completed_at'].isoformat(),
                'active_rank': value.get('active_rank', 1), 'driver_rank': value.get('driver_rank', 1)}
    payload = {'provenance': 'Seeded synthetic GraphHopper histories, read-only capture; identities anonymized',
               'as_of': as_of.isoformat(), 'personal': [row(value) for value in personal],
               'community': [row(value) for value in community], 'routes': routes}
    target = Path('backend/tests/fixtures/synthetic-familiarity-217.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload), encoding='utf-8')
    print(json.dumps({'routes': len(routes), 'personal': len(personal), 'community': len(community), 'first_vertices': len(routes[0])}))


asyncio.run(main())
