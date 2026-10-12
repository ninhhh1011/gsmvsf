"""Bounded before/after assessment of captured real-network synthetic histories."""
import asyncio
import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from time import perf_counter

from backend.app.services.route_familiarity import service
from backend.app.services.route_familiarity.signature import create_route_signature
from backend.app.services.route_familiarity.similarity import ComparisonBudget
from backend.tests.test_route_familiarity_domain import polyline


async def main():
    data = json.loads(Path('backend/tests/fixtures/synthetic-familiarity-217.json').read_text('utf-8'))
    def rows(items):
        return [dict(value, geometry=data['routes'][value['route']],
                     started_at=datetime.fromisoformat(value['started_at']),
                     completed_at=datetime.fromisoformat(value['completed_at'])) for value in items]
    class Repository:
        async def personal_routes(self, *_):
            return rows(data['personal'])
        async def community_routes(self, *_):
            return rows(data['community'])
    signatures = {f'station-{index}': create_route_signature([polyline(route)]) for index, route in enumerate(data['routes'][:3])}
    original_prepare, original_consume = service.prepare_route, ComparisonBudget.consume
    report = []
    try:
        for optimized in (False, True):
            budgets, limit = {}, []
            def consume(self, count):
                if self.used_pairs + count > self.max_pairs:
                    limit.append({'used': self.used_pairs, 'attempted': count, 'maximum': self.max_pairs})
                original_consume(self, count)
                budgets[id(self)] = {'maximum': self.max_pairs, 'used': self.used_pairs}
            ComparisonBudget.consume = consume
            service.prepare_route = original_prepare if optimized else lambda *args, **kwargs: replace(original_prepare(*args, **kwargs), spatial_positions=None)
            started = perf_counter()
            result = await service.RouteFamiliarityService(Repository()).assess_many('fixture', signatures, datetime.fromisoformat(data['as_of']))
            report.append({'optimized': optimized, 'duration_s': round(perf_counter() - started, 4),
                           'budgets': list(budgets.values()), 'limits': limit,
                           'assessments': {key: {'status': value.status, 'reason': value.degraded_reason,
                                                 'personal_trips': value.personal_history_trip_count,
                                                 'community_drivers': value.community_driver_count} for key, value in result.items()}})
    finally:
        service.prepare_route, ComparisonBudget.consume = original_prepare, original_consume
    print(json.dumps(report, indent=2))


asyncio.run(main())
