from collections import Counter, defaultdict

from backend.app.services.route_familiarity.models import RouteSignature, SimilarityResult

MAX_MATCHING_CELL_PAIRS = 250_000


class SimilarityWorkLimitExceeded(Exception):
    pass


class ComparisonBudget:
    def __init__(self, max_pairs=MAX_MATCHING_CELL_PAIRS):
        self.max_pairs = max_pairs
        self.used_pairs = 0

    def consume(self, pairs):
        if self.used_pairs + pairs > self.max_pairs:
            raise SimilarityWorkLimitExceeded
        self.used_pairs += pairs


def index_route_signature(signature: RouteSignature):
    positions = defaultdict(list)
    for index, cell in enumerate(signature.cells):
        positions[cell].append(index)
    return {cell: tuple(indexes) for cell, indexes in positions.items()}


def weighted_ordered_overlap(
    recommended: RouteSignature,
    historical: RouteSignature,
    *,
    budget: ComparisonBudget | None = None,
    historical_positions=None,
) -> SimilarityResult:
    if recommended.resolution != historical.resolution:
        raise ValueError("route signatures must use the same resolution")
    if (len(recommended.cells) != len(recommended.cell_distances_m) or
            len(historical.cells) != len(historical.cell_distances_m)):
        raise ValueError("route signature cells and weights must align")

    positions = historical_positions or index_route_signature(historical)
    counts = Counter(recommended.cells)
    shared_cells = counts.keys() & positions.keys()
    if not shared_cells:
        return SimilarityResult(0.0, 0.0)
    pair_count = sum(counts[cell] * len(positions[cell]) for cell in shared_cells)
    if budget is not None:
        budget.consume(pair_count)

    # Fenwick tree stores the best ordered match ending at or before each prefix.
    tree = [0.0] * (len(historical.cells) + 1)

    def query(count):
        best = 0.0
        while count:
            best = max(best, tree[count])
            count -= count & -count
        return best

    def update(index, value):
        while index < len(tree):
            tree[index] = max(tree[index], value)
            index += index & -index

    for cell, distance in zip(recommended.cells, recommended.cell_distances_m):
        # Descending positions prevent this recommended cell from matching itself twice.
        for index in reversed(positions.get(cell, ())):
            update(index + 1, query(index) + min(distance, historical.cell_distances_m[index]))

    shared = min(recommended.distance_m, max(0.0, query(len(historical.cells))))
    adherence = min(1.0, max(0.0, shared / recommended.distance_m)) if recommended.distance_m > 0 else 0.0
    return SimilarityResult(shared, adherence)
