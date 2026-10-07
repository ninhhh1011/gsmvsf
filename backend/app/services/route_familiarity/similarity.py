from backend.app.services.route_familiarity.models import RouteSignature, SimilarityResult


def weighted_ordered_overlap(
    recommended: RouteSignature, historical: RouteSignature
) -> SimilarityResult:
    if recommended.resolution != historical.resolution:
        raise ValueError("route signatures must use the same resolution")
    if len(recommended.cells) != len(recommended.cell_distances_m) or len(historical.cells) != len(
        historical.cell_distances_m
    ):
        raise ValueError("route signature cells and weights must align")

    previous = [0.0] * (len(historical.cells) + 1)
    for cell, distance in zip(recommended.cells, recommended.cell_distances_m):
        current = [0.0]
        for index, other_cell in enumerate(historical.cells, 1):
            if cell == other_cell:
                current.append(
                    max(
                        previous[index],
                        current[-1],
                        previous[index - 1] + min(distance, historical.cell_distances_m[index - 1]),
                    )
                )
            else:
                current.append(max(previous[index], current[-1]))
        previous = current

    shared = min(recommended.distance_m, max(0.0, previous[-1]))
    adherence = min(1.0, max(0.0, shared / recommended.distance_m)) if recommended.distance_m > 0 else 0.0
    return SimilarityResult(shared, adherence)
