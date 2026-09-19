"""
Network-Distance Energy Feasibility Evaluator for Week 3.

Evaluates whether a vehicle has sufficient battery charge / remaining range to physically
reach a candidate station on the road network.
Preserves exact canonical formula from Dataset V1.3.1:
  feasible = (route_distance_km + 0.5 <= estimated_remaining_range_km)
"""

from typing import Optional

SOC_REACH_BUFFER_KM: float = 0.5


def check_energy_feasibility_to_station(
    network_distance_m: Optional[float],
    estimated_remaining_range_km: Optional[float],
    buffer_km: float = SOC_REACH_BUFFER_KM,
) -> bool:
    """
    Check if the vehicle can reach the station using current energy state.

    Args:
        network_distance_m: True road network distance to station in meters.
        estimated_remaining_range_km: Vehicle's current estimated remaining range.
        buffer_km: Safety reserve buffer to station (default 0.5 km as frozen in Dataset V1.3.1).

    Returns:
        bool: True if vehicle can reach station with buffer, False otherwise.
    """
    if network_distance_m is None or network_distance_m == float("inf"):
        return False

    if estimated_remaining_range_km is None or estimated_remaining_range_km <= 0:
        return False

    route_km = float(network_distance_m) / 1000.0
    return (route_km + buffer_km) <= float(estimated_remaining_range_km)
