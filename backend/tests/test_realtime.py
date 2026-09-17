"""Tests for realtime map matching."""

import pytest
from datetime import datetime, timedelta, timedelta
from backend.app.services.realtime.state import (
    DriverTraceState,
    DriverStateStore,
    GPSObservation,
    MatchedState,
    haversine_distance,
    DEFAULT_GAP_THRESHOLD_SECONDS,
    DEFAULT_STATIONARY_THRESHOLD,
    DEFAULT_STATIONARY_DISTANCE_M,
)
from backend.app.services.realtime.trigger import (
    TimeTrigger,
    DistanceTrigger,
    HybridTrigger,
    get_default_policy,
)


class TestGPSObservation:
    """Test GPSObservation model."""

    def test_from_dict(self):
        """Test creating observation from dict."""
        data = {
            "observation_id": "O001",
            "driver_id": "D001",
            "timestamp": "2026-09-01T06:00:00+07:00",
            "latitude": 21.103793,
            "longitude": 106.002398,
            "speed_kmh": 25.5,
            "heading_deg": 90.0,
        }
        obs = GPSObservation.from_dict(data)
        assert obs.observation_id == "O001"
        assert obs.driver_id == "D001"
        assert obs.latitude == 21.103793
        assert obs.longitude == 106.002398
        assert obs.speed_kmh == 25.5
        assert obs.heading_deg == 90.0


class TestHaversine:
    """Test haversine distance calculation."""

    def test_same_point(self):
        """Same point should be 0 distance."""
        d = haversine_distance(21.103793, 106.002398, 21.103793, 106.002398)
        assert d == 0.0

    def test_known_distance(self):
        """Test with known distance."""
        # Hanoi to ~1km away
        lat1, lon1 = 21.0285, 105.8542
        lat2, lon2 = 21.0348, 105.8534
        d = haversine_distance(lat1, lon1, lat2, lon2)
        assert 500 < d < 1500  # ~700m


class TestDriverTraceState:
    """Test driver trace state."""

    def test_initial_state(self):
        """Test initial state."""
        state = DriverTraceState(driver_id="D001")
        assert state.driver_id == "D001"
        assert state.total_observations_received == 0
        assert state.total_match_calls == 0
        assert state.is_warming_up()
        assert len(state.observations) == 0

    def test_add_observation(self):
        """Test adding observations."""
        state = DriverTraceState(driver_id="D001")
        obs = GPSObservation(
            observation_id="O001",
            driver_id="D001",
            timestamp=datetime(2026, 9, 1, 6, 0, 0),
            latitude=21.103793,
            longitude=106.002398,
        )
        gap_reset, reason = state.add_observation(obs)
        assert not gap_reset
        assert state.total_observations_received == 1
        assert len(state.observations) == 1
        assert state.is_warming_up()  # 1 obs < 3, still warming up

    def test_warming_up(self):
        """Test warm-up threshold."""
        state = DriverTraceState(driver_id="D001")
        for i in range(3):
            obs = GPSObservation(
                observation_id=f"O{i:03d}",
                driver_id="D001",
                timestamp=datetime(2026, 9, 1, 6, 0, i),
                latitude=21.103793 + i * 0.001,
                longitude=106.002398 + i * 0.001,
            )
            state.add_observation(obs)

        # 3 obs should exit warm-up
        assert not state.is_warming_up()

    def test_gap_reset(self):
        """Test gap detection and reset."""
        state = DriverTraceState(driver_id="D001")

        # Add observations with small gaps
        for i in range(3):
            obs = GPSObservation(
                observation_id=f"O{i:03d}",
                driver_id="D001",
                timestamp=datetime(2026, 9, 1, 6, 0, i),
                latitude=21.103793,
                longitude=106.002398,
            )
            state.add_observation(obs)

        # Add observation with large gap
        gap_obs = GPSObservation(
            observation_id="O100",
            driver_id="D001",
            timestamp=datetime(2026, 9, 1, 6, 2, 0),  # 2 min gap
            latitude=21.103793,
            longitude=106.002398,
        )
        gap_reset, reason = state.add_observation(gap_obs)

        assert gap_reset
        assert "gap" in reason
        assert len(state.observations) == 1  # Reset
        assert state.total_observations_received == 4

    def test_stationary_detection(self):
        """Test stationary detection."""
        state = DriverTraceState(driver_id="D001")

        # Add same location observations
        for i in range(5):
            obs = GPSObservation(
                observation_id=f"O{i:03d}",
                driver_id="D001",
                timestamp=datetime(2026, 9, 1, 6, 0, i),
                latitude=21.103793,
                longitude=106.002398,
            )
            state.add_observation(obs)

        # Should be stationary after 3+ consecutive small movements
        assert state.consecutive_stationary >= DEFAULT_STATIONARY_THRESHOLD
        assert state.is_stationary()

    def test_movement_tracking(self):
        """Test movement tracking."""
        state = DriverTraceState(driver_id="D001")

        # Add moving observations (~100m apart)
        base_lat, base_lon = 21.103793, 106.002398
        for i in range(3):
            obs = GPSObservation(
                observation_id=f"O{i:03d}",
                driver_id="D001",
                timestamp=datetime(2026, 9, 1, 6, 0, i),
                latitude=base_lat + i * 0.001,  # ~100m apart
                longitude=base_lon + i * 0.001,
            )
            state.add_observation(obs)

        assert state.movement_since_match > 100  # Should have moved >100m

    def test_context_window(self):
        """Test context window filtering."""
        state = DriverTraceState(driver_id="D001")

        # Add 10 observations over 60 seconds
        for i in range(10):
            obs = GPSObservation(
                observation_id=f"O{i:03d}",
                driver_id="D001",
                timestamp=datetime(2026, 9, 1, 6, 0, i * 6),  # 6 sec apart
                latitude=21.103793,
                longitude=106.002398,
            )
            state.add_observation(obs)

        # Context with 30s window should return ~5-6 obs
        context = state.get_context(window_seconds=30.0, max_points=50)
        assert 4 <= len(context) <= 6

    def test_context_max_points(self):
        """Test context max points limit."""
        state = DriverTraceState(driver_id="D001")

        # Add 100 observations with increasing timestamps
        base_time = datetime(2026, 9, 1, 6, 0, 0)
        for i in range(100):
            obs = GPSObservation(
                observation_id=f"O{i:03d}",
                driver_id="D001",
                timestamp=base_time + timedelta(seconds=i),
                latitude=21.103793,
                longitude=106.002398,
            )
            state.add_observation(obs)

        # Context with max_points=10 should return 10
        context = state.get_context(window_seconds=1000.0, max_points=10)
        assert len(context) == 10

    def test_reset_after_match(self):
        """Test reset after match."""
        state = DriverTraceState(driver_id="D001")

        # Add observations
        for i in range(5):
            obs = GPSObservation(
                observation_id=f"O{i:03d}",
                driver_id="D001",
                timestamp=datetime(2026, 9, 1, 6, 0, i),
                latitude=21.103793,
                longitude=106.002398,
            )
            state.add_observation(obs)

        # Reset after match
        matched = MatchedState(
            matched_latitude=21.103800,
            matched_longitude=106.002400,
            confidence=0.95,
        )
        state.reset_after_match(matched)

        assert state.movement_since_match == 0.0
        assert state.observations_since_match == 0
        assert state.last_matched_state is not None
        assert state.total_match_calls == 1
        assert state.last_match_time == state.last_observation_timestamp


class TestDriverStateStore:
    """Test driver state store."""

    def test_get_or_create(self):
        """Test get or create."""
        store = DriverStateStore(max_drivers=10)

        # Create new
        state1 = store.get_or_create("D001")
        assert state1.driver_id == "D001"

        # Get existing
        state2 = store.get_or_create("D001")
        assert state2 is state1

        # New driver
        state3 = store.get_or_create("D002")
        assert state3.driver_id == "D002"

    def test_max_drivers_lru(self):
        """Test LRU eviction."""
        store = DriverStateStore(max_drivers=3)

        # Fill up
        store.get_or_create("D001")
        store.get_or_create("D002")
        store.get_or_create("D003")

        # Add one more (should evict oldest)
        store.get_or_create("D004")

        assert store.get("D001") is None
        assert store.get("D002") is not None
        assert store.get("D003") is not None
        assert store.get("D004") is not None

    def test_remove(self):
        """Test remove driver."""
        store = DriverStateStore()
        store.get_or_create("D001")
        assert store.remove("D001")
        assert store.get("D001") is None


class TestTriggers:
    """Test trigger policies."""

    def test_time_trigger_initial(self):
        """Test time trigger on initial state."""
        trigger = TimeTrigger(elapsed_seconds=10.0)
        state = DriverTraceState(driver_id="D001")
        obs_ts = datetime(2026, 9, 1, 6, 0, 0)

        should, reason = trigger.should_trigger(obs_ts, state)
        assert should
        assert reason == "INITIAL"

    def test_time_trigger_not_ready(self):
        """Test time trigger when time not elapsed."""
        trigger = TimeTrigger(elapsed_seconds=10.0)
        state = DriverTraceState(driver_id="D001")

        # Set last match time 5 seconds ago
        state.last_match_time = datetime(2026, 9, 1, 6, 0, 0)
        obs_ts = datetime(2026, 9, 1, 6, 0, 5)

        should, reason = trigger.should_trigger(obs_ts, state)
        assert not should
        assert "NOT_TIME" in reason

    def test_time_trigger_ready(self):
        """Test time trigger when time elapsed."""
        trigger = TimeTrigger(elapsed_seconds=10.0)
        state = DriverTraceState(driver_id="D001")

        # Set last match time 15 seconds ago
        state.last_match_time = datetime(2026, 9, 1, 6, 0, 0)
        obs_ts = datetime(2026, 9, 1, 6, 0, 15)

        should, reason = trigger.should_trigger(obs_ts, state)
        assert should
        assert "TIME" in reason

    def test_distance_trigger_not_ready(self):
        """Test distance trigger when not enough movement."""
        trigger = DistanceTrigger(distance_meters=50.0)
        state = DriverTraceState(driver_id="D001")
        state.movement_since_match = 30.0

        should, reason = trigger.should_trigger(datetime.utcnow(), state)
        assert not should
        assert "NOT_DIST" in reason

    def test_distance_trigger_ready(self):
        """Test distance trigger when enough movement."""
        trigger = DistanceTrigger(distance_meters=50.0)
        state = DriverTraceState(driver_id="D001")
        state.movement_since_match = 75.0

        should, reason = trigger.should_trigger(datetime.utcnow(), state)
        assert should
        assert "DIST" in reason

    def test_hybrid_trigger_time_first(self):
        """Test hybrid trigger fires on time."""
        trigger = HybridTrigger(elapsed_seconds=10.0, distance_meters=50.0)
        state = DriverTraceState(driver_id="D001")

        # Time elapsed but not enough distance
        state.last_match_time = datetime(2026, 9, 1, 6, 0, 0)
        state.movement_since_match = 20.0
        obs_ts = datetime(2026, 9, 1, 6, 0, 15)

        should, reason = trigger.should_trigger(obs_ts, state)
        assert should
        assert "TIME" in reason

    def test_hybrid_trigger_distance_first(self):
        """Test hybrid trigger fires on distance."""
        trigger = HybridTrigger(elapsed_seconds=10.0, distance_meters=50.0)
        state = DriverTraceState(driver_id="D001")

        # Enough distance but not enough time
        state.last_match_time = datetime(2026, 9, 1, 6, 0, 0)
        state.movement_since_match = 75.0
        obs_ts = datetime(2026, 9, 1, 6, 0, 5)

        should, reason = trigger.should_trigger(obs_ts, state)
        assert should
        assert "DIST" in reason

    def test_hybrid_trigger_neither(self):
        """Test hybrid trigger doesn't fire."""
        trigger = HybridTrigger(elapsed_seconds=10.0, distance_meters=50.0)
        state = DriverTraceState(driver_id="D001")

        # Neither condition met
        state.last_match_time = datetime(2026, 9, 1, 6, 0, 0)
        state.movement_since_match = 25.0
        obs_ts = datetime(2026, 9, 1, 6, 0, 5)

        should, reason = trigger.should_trigger(obs_ts, state)
        assert not should
        assert "NO_TRIGGER" in reason

    def test_default_policy(self):
        """Test default policy is hybrid."""
        policy = get_default_policy()
        assert isinstance(policy, HybridTrigger)
        assert policy.elapsed_seconds == 10.0
        assert policy.distance_meters == 50.0
