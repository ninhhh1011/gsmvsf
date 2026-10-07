from dataclasses import dataclass


@dataclass(frozen=True)
class RouteSignature:
    cells: tuple[str, ...]
    cell_distances_m: tuple[float, ...]
    distance_m: float
    resolution: int


@dataclass(frozen=True)
class SimilarityResult:
    shared_route_distance_m: float
    adherence: float
