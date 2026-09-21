"""Validate operational facts against the canonical catalog before committing."""
import logging

from backend.app.services.candidate.station_catalog import station_catalog
from backend.app.services.snapshots.models import Snapshot, StateError
from backend.app.services.snapshots.repository import SnapshotRepository

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(self, repository: SnapshotRepository, catalog=station_catalog, cache=None):
        self.repository = repository
        self.catalog = catalog
        self.cache = cache

    def _validate(self, snapshot: Snapshot) -> None:
        def reject(message):
            raise StateError(message, 'INVALID_SNAPSHOT', 422)

        if snapshot.kind == 'traffic':
            # Dataset speeds round to .01 km/h; delay factors round to .001.
            tolerance = snapshot.delay_factor * .005 + snapshot.current_speed_kmh * .0005 + .001
            if abs(snapshot.free_flow_speed_kmh - snapshot.delay_factor * snapshot.current_speed_kmh) > tolerance:
                reject('Traffic delay_factor disagrees with free-flow/current speeds')
            return
        station = self.catalog.get_station(snapshot.entity_id)
        if station is None:
            reject(f'Unknown station: {snapshot.entity_id}')
        values = snapshot.model_dump()
        for service, capacity in [('charging', station.charging_slots), ('swap', station.swap_slots)]:
            fields = [value for key, value in values.items() if service in key]
            if not capacity and any(fields):
                reject(f'{service} is not supported at {snapshot.entity_id}')
            if capacity and values[f'{service}_service_time_min'] <= 0:
                reject(f'{service} service time must be positive')
            used = (values[f'available_{service}_slots'] + values[f'occupied_{service}_slots']
                    if snapshot.kind == 'station' else values[f'{service}_active_service_count'])
            if used > capacity:
                reject(f'{service} slots exceed canonical capacity at {snapshot.entity_id}')

    async def _validate_many(self, snapshots: list[Snapshot]) -> None:
        for snapshot in snapshots:
            self._validate(snapshot)
        segments = {snapshot.entity_id for snapshot in snapshots if snapshot.kind == 'traffic'}
        if segments:
            unknown = segments - await self.repository.existing_segments(sorted(segments))
            if unknown:
                raise StateError(f'Unknown road segment: {min(unknown)}', 'INVALID_SNAPSHOT', 422)

    async def _cache(self, snapshots: list[Snapshot]) -> None:
        if self.cache is None:
            return
        for snapshot in snapshots:
            try:
                await self.cache.put(snapshot)
            except Exception:
                # The committed DB version remains authoritative after cache failure.
                logger.warning('Snapshot cache write failed: %s', snapshot.key, exc_info=True)

    async def ingest(self, snapshot: Snapshot) -> tuple[Snapshot, bool]:
        await self._validate_many([snapshot])
        result = await self.repository.ingest(snapshot)
        await self._cache([result[0]])
        return result

    async def ingest_many(self, snapshots: list[Snapshot]) -> int:
        await self._validate_many(snapshots)
        created = await self.repository.ingest_many(snapshots)
        await self._cache(snapshots)
        return created
