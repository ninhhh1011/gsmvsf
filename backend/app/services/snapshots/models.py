"""Dataset-shaped snapshot values; timestamps and freshness are domain evidence."""
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

Count = Annotated[int, Field(ge=0, strict=True)]
Nonnegative = Annotated[float, Field(ge=0)]
Positive = Annotated[float, Field(gt=0)]


def aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('An explicit timezone is required')
    return value.astimezone(timezone.utc)


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid', allow_inf_nan=False)


class SnapshotBase(FrozenModel):
    entity_id: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_.:-]+$')
    timestamp: datetime
    source: str = Field(min_length=1, max_length=100)
    schema_version: Literal[1] = 1

    _timestamp = field_validator('timestamp')(aware_utc)

    @field_validator('*')
    @classmethod
    def normalize_signed_zero(cls, value):
        # PostgreSQL JSONB normalizes -0.0; content identity must survive storage.
        return 0.0 if isinstance(value, float) and value == 0 else value

    @property
    def snapshot_id(self) -> str:
        # Bind cache identity to validated content as well as logical row identity.
        return str(uuid5(NAMESPACE_URL, self.model_dump_json()))

    @property
    def key(self) -> str:
        return f'{self.kind}:{self.entity_id}'


class TrafficSnapshot(SnapshotBase):
    kind: Literal['traffic'] = 'traffic'
    traffic_level: Literal['FREE_FLOW', 'MODERATE', 'HEAVY', 'INCIDENT']
    free_flow_speed_kmh: Positive
    current_speed_kmh: Positive
    delay_factor: Positive


class StationStateSnapshot(SnapshotBase):
    kind: Literal['station'] = 'station'
    operating_status: Literal['OPEN', 'OFFLINE']
    available_charging_slots: Count
    occupied_charging_slots: Count
    available_swap_slots: Count
    occupied_swap_slots: Count
    available_swap_batteries: Count
    charging_service_time_min: Nonnegative
    swap_service_time_min: Nonnegative


class QueueSnapshot(SnapshotBase):
    kind: Literal['queue'] = 'queue'
    charging_queue_length: Count
    charging_active_service_count: Count
    charging_service_time_min: Nonnegative
    charging_estimated_wait_min: Nonnegative
    swap_queue_length: Count
    swap_active_service_count: Count
    swap_service_time_min: Nonnegative
    swap_estimated_wait_min: Nonnegative


Snapshot = Annotated[TrafficSnapshot | StationStateSnapshot | QueueSnapshot,
                     Field(discriminator='kind')]
snapshot_adapter = TypeAdapter(Snapshot)


class ResolvedSnapshot(FrozenModel):
    snapshot: Snapshot | None
    snapshot_id: str | None
    source: str | None
    snapshot_timestamp: datetime | None
    snapshot_age_s: Nonnegative | None
    freshness: Literal['FRESH', 'STALE', 'MISSING']

    @field_validator('snapshot_timestamp')
    @classmethod
    def normalize_optional_time(cls, value):
        return aware_utc(value) if value is not None else None

    @model_validator(mode='after')
    def consistent_provenance(self):
        if self.snapshot is None:
            if self.freshness != 'MISSING' or any(v is not None for v in (
                self.snapshot_id, self.source, self.snapshot_timestamp, self.snapshot_age_s
            )):
                raise ValueError('Missing state must have null provenance')
        elif (self.freshness == 'MISSING' or self.snapshot_age_s is None
              or self.snapshot_id != self.snapshot.snapshot_id
              or self.source != self.snapshot.source
              or self.snapshot_timestamp is None
              or aware_utc(self.snapshot_timestamp) != self.snapshot.timestamp):
            raise ValueError('Provenance must identify the contained snapshot')
        return self

    @classmethod
    def resolve(cls, snapshot: Snapshot | None, request_time: datetime,
                fresh_seconds: float) -> 'ResolvedSnapshot':
        request_time = aware_utc(request_time)
        age = (request_time - snapshot.timestamp).total_seconds() if snapshot else None
        if age is not None and age < 0:
            raise ValueError('Future snapshots cannot enter request context')
        return cls(snapshot=snapshot, snapshot_id=snapshot.snapshot_id if snapshot else None,
                   source=snapshot.source if snapshot else None,
                   snapshot_timestamp=snapshot.timestamp if snapshot else None,
                   snapshot_age_s=age, freshness=('MISSING' if age is None else
                   'FRESH' if age <= fresh_seconds else 'STALE'))


class StateError(Exception):
    def __init__(self, message: str, code: str = 'SNAPSHOT_UNAVAILABLE', status: int = 503):
        super().__init__(message)
        self.status = status
        self.detail = {'error_code': code, 'message': message}
