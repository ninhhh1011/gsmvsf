"""
Realtime Map Matching Benchmark Harness

Replays Dataset V1 trajectories with configurable:
- GPS sampling rate
- Context window size
- Trigger policy (time/distance/hybrid)
- Stationary suppression

Metrics:
- Match rate, accuracy, latency
- Calls per driver per minute
- Update interval distribution
"""

import asyncio
import csv
import gzip
import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import httpx

# Configuration
DATASET_PATH = Path("dataset_v1")
GPS_FILE = DATASET_PATH / "gps" / "gps_observations.csv.gz"
OSRM_URL = "http://localhost:5000"
TIMEOUT_SEC = 30.0


@dataclass
class GPSObservation:
    """Single GPS observation."""
    observation_id: str
    trajectory_id: str
    trip_id: str
    timestamp: datetime
    latitude: float
    longitude: float
    speed_kmh: Optional[float] = None
    heading_deg: Optional[float] = None
    accuracy_m: Optional[float] = None


class TriggerPolicy:
    """Base trigger policy."""
    name: str

    def should_trigger(
        self,
        obs: GPSObservation,
        state: "DriverTraceState",
    ) -> tuple[bool, str]:
        """Returns (should_trigger, reason)."""
        raise NotImplementedError


class TimeTrigger(TriggerPolicy):
    """Trigger after elapsed time."""
    def __init__(self, elapsed_seconds: float = 10.0):
        self.name = f"TimeTrigger({elapsed_seconds}s)"
        self.elapsed_seconds = elapsed_seconds

    def should_trigger(
        self,
        obs: GPSObservation,
        state: "DriverTraceState",
    ) -> tuple[bool, str]:
        if state.last_match_time is None:
            return True, "INITIAL"
        elapsed = (obs.timestamp - state.last_match_time).total_seconds()
        if elapsed >= self.elapsed_seconds:
            return True, f"TIME({elapsed:.1f}s>={self.elapsed_seconds}s)"
        return False, f"NOT_TIME({elapsed:.1f}s<{self.elapsed_seconds}s)"


class DistanceTrigger(TriggerPolicy):
    """Trigger after distance traveled."""
    def __init__(self, distance_meters: float = 50.0):
        self.name = f"DistanceTrigger({distance_meters}m)"
        self.distance_meters = distance_meters

    def should_trigger(
        self,
        obs: GPSObservation,
        state: "DriverTraceState",
    ) -> tuple[bool, str]:
        if state.movement_since_match < self.distance_meters:
            return False, f"NOT_DIST({state.movement_since_match:.0f}m<{self.distance_meters}m)"
        return True, f"DIST({state.movement_since_match:.0f}m>={self.distance_meters}m)"


class HybridTrigger(TriggerPolicy):
    """Trigger on time OR distance."""
    def __init__(self, elapsed_seconds: float = 10.0, distance_meters: float = 50.0):
        self.name = f"HybridTrigger({elapsed_seconds}s/{distance_meters}m)"
        self.elapsed_seconds = elapsed_seconds
        self.distance_meters = distance_meters

    def should_trigger(
        self,
        obs: GPSObservation,
        state: "DriverTraceState",
    ) -> tuple[bool, str]:
        # Check time
        elapsed = 0.0
        if state.last_match_time is not None:
            elapsed = (obs.timestamp - state.last_match_time).total_seconds()
            if elapsed >= self.elapsed_seconds:
                return True, f"TIME({elapsed:.1f}s>={self.elapsed_seconds}s)"

        # Check distance
        if state.movement_since_match >= self.distance_meters:
            return True, f"DIST({state.movement_since_match:.0f}m>={self.distance_meters}m)"

        return False, f"NO_TRIGGER(elapsed={elapsed if state.last_match_time else 0:.1f}s, dist={state.movement_since_match:.0f}m)"


@dataclass
class DriverTraceState:
    """Per-driver trace state."""
    driver_id: str
    observations: list[GPSObservation] = field(default_factory=list)
    last_match_time: Optional[datetime] = None
    last_matched_state: Optional[dict] = None
    movement_since_match: float = 0.0
    last_observation_timestamp: Optional[datetime] = None
    observations_since_match: int = 0
    consecutive_stationary: int = 0

    def add_observation(self, obs: GPSObservation):
        """Add observation and update movement."""
        if self.observations:
            prev = self.observations[-1]
            dist = haversine(
                prev.latitude, prev.longitude,
                obs.latitude, obs.longitude
            )
            self.movement_since_match += dist

            # Check for stationary (GPS jitter < 5m)
            if dist < 5.0:
                self.consecutive_stationary += 1
            else:
                self.consecutive_stationary = 0

        self.observations.append(obs)
        self.last_observation_timestamp = obs.timestamp
        self.observations_since_match += 1

    def get_recent_context(
        self,
        window_seconds: float = 30.0,
        max_points: int = 50,
    ) -> list[GPSObservation]:
        """Get recent observations within window."""
        if not self.observations:
            return []

        # Time-based filter
        if self.last_observation_timestamp:
            cutoff = self.last_observation_timestamp - timedelta(seconds=window_seconds)
            recent = [o for o in self.observations if o.timestamp >= cutoff]
        else:
            recent = list(self.observations)

        # Point limit
        return recent[-max_points:]

    def reset_after_match(self):
        """Reset after successful match."""
        self.last_match_time = self.last_observation_timestamp
        self.movement_since_match = 0.0
        self.observations_since_match = 0

    def reset_session(self, gap_seconds: float = 60.0):
        """Reset if gap detected."""
        if (self.last_observation_timestamp and
            self.last_observation_timestamp and
            self.observations):
            # Already handled in add_observation
            pass


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in meters."""
    import math
    R = 6371000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


@dataclass
class BenchmarkResult:
    """Results from benchmark run."""
    policy_name: str
    trajectory_id: str
    total_observations: int
    match_calls: int
    matched_count: int
    unmatched_count: int
    trigger_reasons: dict = field(default_factory=dict)
    match_latencies: list[float] = field(default_factory=list)
    update_intervals: list[float] = field(default_factory=list)
    stationary_suppressions: int = 0
    gap_resets: int = 0


async def call_osrm_match(
    client: httpx.AsyncClient,
    coordinates: list[tuple[float, float]],
) -> tuple[Optional[dict], float]:
    """Call OSRM match and return (result, latency_sec)."""
    if len(coordinates) < 2:
        return None, 0.0

    coords_str = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in coordinates)
    url = f"{OSRM_URL}/match/v1/driving/{coords_str}"

    start = time.time()
    try:
        response = await client.get(
            url,
            params={"overview": "simplified"},
            timeout=TIMEOUT_SEC,
        )
        latency = time.time() - start

        if response.status_code == 200:
            data = response.json()
            if data.get("code") == "Ok":
                return data, latency
        return None, latency
    except Exception as e:
        return None, time.time() - start


def load_trajectory(gps_file: Path, trajectory_id: str) -> list[GPSObservation]:
    """Load observations for a single trajectory."""
    observations = []
    with gzip.open(gps_file, 'rt', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['trajectory_id'] != trajectory_id:
                continue
            try:
                obs = GPSObservation(
                    observation_id=row['observation_id'],
                    trajectory_id=row['trajectory_id'],
                    trip_id=row['trip_id'],
                    timestamp=datetime.fromisoformat(row['timestamp']),
                    latitude=float(row['latitude']),
                    longitude=float(row['longitude']),
                    speed_kmh=float(row['speed_kmh']) if row.get('speed_kmh') else None,
                    heading_deg=float(row['heading_deg']) if row.get('heading_deg') else None,
                    accuracy_m=float(row['accuracy_m']) if row.get('accuracy_m') else None,
                )
                observations.append(obs)
            except Exception:
                continue
    return sorted(observations, key=lambda x: x.timestamp)


def sample_observations(
    observations: list[GPSObservation],
    sample_interval: float = None,
) -> list[GPSObservation]:
    """Downsample observations by interval (None = native)."""
    if sample_interval is None:
        return observations

    sampled = []
    last_ts = None
    for obs in observations:
        if last_ts is None or (obs.timestamp - last_ts).total_seconds() >= sample_interval:
            sampled.append(obs)
            last_ts = obs.timestamp
    return sampled


async def run_benchmark(
    trajectory_id: str,
    policy: TriggerPolicy,
    context_window_seconds: float = 30.0,
    max_context_points: int = 50,
    sample_interval: float = None,
    suppress_stationary: bool = True,
    stationary_threshold: int = 3,
) -> BenchmarkResult:
    """Run benchmark for one trajectory."""
    # Load trajectory
    observations = load_trajectory(GPS_FILE, trajectory_id)
    if not observations:
        return BenchmarkResult(
            policy_name=policy.name,
            trajectory_id=trajectory_id,
            total_observations=0,
            match_calls=0,
            matched_count=0,
            unmatched_count=0,
        )

    # Sample if needed
    if sample_interval:
        observations = sample_observations(observations, sample_interval)

    result = BenchmarkResult(
        policy_name=policy.name,
        trajectory_id=trajectory_id,
        total_observations=len(observations),
        match_calls=0,
        matched_count=0,
        unmatched_count=0,
    )

    # Initialize state
    state = DriverTraceState(driver_id=trajectory_id)

    async with httpx.AsyncClient() as client:
        prev_match_time = None
        observations_since_last_match = 0

        for obs in observations:
            # Check for gap (session reset)
            if (state.last_observation_timestamp and
                (obs.timestamp - state.last_observation_timestamp).total_seconds() > 60.0):
                state = DriverTraceState(driver_id=trajectory_id)
                result.gap_resets += 1

            # Add observation
            state.add_observation(obs)

            # Stationary suppression
            if (suppress_stationary and
                state.consecutive_stationary >= stationary_threshold and
                policy.name != "INITIAL"):
                result.stationary_suppressions += 1
                continue

            # Check trigger
            should_trigger, reason = policy.should_trigger(obs, state)

            # Track trigger reasons
            result.trigger_reasons[reason] = result.trigger_reasons.get(reason, 0) + 1

            if should_trigger:
                # Get context
                context = state.get_recent_context(
                    window_seconds=context_window_seconds,
                    max_points=max_context_points,
                )

                if len(context) >= 2:
                    coords = [(o.longitude, o.latitude) for o in context]
                    data, latency = await call_osrm_match(client, coords)

                    result.match_calls += 1
                    result.match_latencies.append(latency)

                    if prev_match_time:
                        interval = (obs.timestamp - prev_match_time).total_seconds()
                        result.update_intervals.append(interval)
                    prev_match_time = obs.timestamp

                    if data:
                        tracepoints = data.get("matchings", [{}])[0]
                        matched = tracepoints.get("matchings_index", 0) >= 0
                        result.matched_count += len(context)
                    else:
                        result.unmatched_count += len(context)

                    state.reset_after_match()

    return result


async def run_multi_trajectory_benchmark(
    trajectory_ids: list[str],
    policy: TriggerPolicy,
    context_window_seconds: float = 30.0,
    max_context_points: int = 50,
    sample_interval: float = None,
    suppress_stationary: bool = True,
) -> dict:
    """Run benchmark across multiple trajectories."""
    tasks = [
        run_benchmark(
            trajectory_id=tid,
            policy=policy,
            context_window_seconds=context_window_seconds,
            max_context_points=max_context_points,
            sample_interval=sample_interval,
            suppress_stationary=suppress_stationary,
        )
        for tid in trajectory_ids
    ]
    results = await asyncio.gather(*tasks)
    return results


def aggregate_results(results: list[BenchmarkResult]) -> dict:
    """Aggregate results across trajectories."""
    total_obs = sum(r.total_observations for r in results)
    total_calls = sum(r.match_calls for r in results)
    total_matched = sum(r.matched_count for r in results)
    total_unmatched = sum(r.unmatched_count for r in results)
    all_latencies = [l for r in results for l in r.match_latencies]
    all_intervals = [i for r in results for i in r.update_intervals]

    # Aggregate trigger reasons
    all_triggers = defaultdict(int)
    for r in results:
        for reason, count in r.trigger_reasons.items():
            all_triggers[reason] += count

    return {
        "total_trajectories": len(results),
        "total_observations": total_obs,
        "total_match_calls": total_calls,
        "match_rate": total_matched / total_obs if total_obs > 0 else 0,
        "unmatched_rate": total_unmatched / total_obs if total_obs > 0 else 0,
        "calls_per_trajectory": total_calls / len(results) if results else 0,
        "observations_per_call": total_obs / total_calls if total_calls > 0 else 0,
        "stationary_suppressions": sum(r.stationary_suppressions for r in results),
        "gap_resets": sum(r.gap_resets for r in results),
        "latency_mean": sum(all_latencies) / len(all_latencies) if all_latencies else 0,
        "latency_p50": sorted(all_latencies)[len(all_latencies)//2] if all_latencies else 0,
        "latency_p95": sorted(all_latencies)[int(len(all_latencies)*0.95)] if all_latencies else 0,
        "update_interval_mean": sum(all_intervals) / len(all_intervals) if all_intervals else 0,
        "trigger_reasons": dict(all_triggers),
    }


async def main():
    """Run benchmark suite."""
    # Load sample trajectories (first 10)
    trajectories = []
    with gzip.open(GPS_FILE, 'rt', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        seen = set()
        for row in reader:
            tid = row['trajectory_id']
            if tid not in seen:
                seen.add(tid)
                trajectories.append(tid)
                if len(trajectories) >= 10:
                    break

    print(f"Benchmarking with {len(trajectories)} trajectories: {trajectories}")
    print()

    # Test policies
    policies = [
        TimeTrigger(elapsed_seconds=5.0),
        TimeTrigger(elapsed_seconds=10.0),
        TimeTrigger(elapsed_seconds=15.0),
        DistanceTrigger(distance_meters=20.0),
        DistanceTrigger(distance_meters=50.0),
        DistanceTrigger(distance_meters=100.0),
        HybridTrigger(elapsed_seconds=5.0, distance_meters=30.0),
        HybridTrigger(elapsed_seconds=10.0, distance_meters=50.0),
        HybridTrigger(elapsed_seconds=15.0, distance_meters=100.0),
    ]

    all_results = {}

    for policy in policies:
        print(f"Running {policy.name}...")
        results = await run_multi_trajectory_benchmark(
            trajectory_ids=trajectories,
            policy=policy,
            context_window_seconds=30.0,
            max_context_points=50,
        )
        agg = aggregate_results(results)
        all_results[policy.name] = agg

        print(f"  Calls: {agg['total_match_calls']}")
        print(f"  Calls/traj: {agg['calls_per_trajectory']:.1f}")
        print(f"  Obs/call: {agg['observations_per_call']:.1f}")
        print(f"  Latency mean: {agg['latency_mean']*1000:.1f}ms")
        print(f"  Latency p95: {agg['latency_p95']*1000:.1f}ms")
        print()

    # Save results
    output_file = Path("runtime/benchmark_results.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f"Results saved to {output_file}")

    return all_results


if __name__ == "__main__":
    asyncio.run(main())
