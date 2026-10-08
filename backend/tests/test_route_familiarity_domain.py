import pytest
import h3

from backend.app.services.route_familiarity.constants import H3_ROUTE_RESOLUTION
from backend.app.services.route_familiarity.signature import (
    create_route_signature,
    decode_polyline,
)
from backend.app.services.route_familiarity.similarity import weighted_ordered_overlap
from backend.app.services.route_familiarity.models import RouteSignature


def polyline(points):
    lat = lon = 0
    result = []
    for point in points:
        for axis, value in enumerate(point):
            current = round(value * 1e5)
            delta = current - (lat if axis == 0 else lon)
            if axis == 0:
                lat = current
            else:
                lon = current
            encoded = ~(delta << 1) if delta < 0 else delta << 1
            while encoded >= 0x20:
                result.append(chr((0x20 | (encoded & 0x1f)) + 63))
                encoded >>= 5
            result.append(chr(encoded + 63))
    return "".join(result)


def test_decode_polyline_validates_truncation_and_coordinates():
    assert decode_polyline(polyline([(21.0, 105.0), (21.001, 105.002)])) == [
        (21.0, 105.0),
        (21.001, 105.002),
    ]
    with pytest.raises(ValueError):
        decode_polyline("_")
    with pytest.raises(ValueError):
        decode_polyline("\x00")
    with pytest.raises(ValueError):
        decode_polyline(polyline([(91.0, 0.0)]))


def test_signature_is_resolution_11_weighted_and_collapses_only_consecutive_cells():
    points = [(21.0, 105.0), (21.0001, 105.0001), (21.001, 105.001)]
    signature = create_route_signature([polyline(points)])
    assert signature.resolution == H3_ROUTE_RESOLUTION == 11
    assert len(signature.cells) == len(signature.cell_distances_m)
    assert sum(signature.cell_distances_m) == pytest.approx(signature.distance_m, abs=0.001)
    assert signature.cells
    with pytest.raises(ValueError):
        create_route_signature([polyline([(21.0, 105.0), (21.0, 105.0)])])


def test_signature_preserves_revisits_and_rejects_oversized_routes():
    points = [(21.0, 105.0), (21.002, 105.0), (21.0, 105.0)]
    signature = create_route_signature([polyline(points)])
    assert signature.cells[0] == signature.cells[-1]
    assert len(signature.cells) >= 3
    with pytest.raises(ValueError):
        create_route_signature(["?" * 100_001])
    with pytest.raises(ValueError):
        create_route_signature(["?" * 50_001, "?" * 50_000])
    with pytest.raises(ValueError):
        create_route_signature([polyline([(0.0, 0.0), (0.0, 1.0)])])
    with pytest.raises(ValueError, match="vertices"):
        create_route_signature([polyline([(21.0, 105.0)] * 20_001)])


def test_short_nonzero_route_can_stay_in_one_cell():
    signature = create_route_signature([polyline([(21.0, 105.0), (21.00001, 105.00001)])])
    assert len(signature.cells) == 1
    assert signature.distance_m > 0


def test_densified_samples_in_same_cell_collapse_and_sum_their_weights():
    cell = h3.latlng_to_cell(21.0, 105.0, H3_ROUTE_RESOLUTION)
    latitude, longitude = h3.cell_to_latlng(cell)
    route = polyline([(latitude - 0.00008, longitude), (latitude + 0.00008, longitude)])

    signature = create_route_signature([route])

    assert signature.cells == (cell,)
    assert signature.cell_distances_m == pytest.approx((signature.distance_m,), abs=0.001)


def test_weighted_ordered_overlap_is_directional_and_bounded():
    forward = create_route_signature([polyline([(21.0, 105.0), (21.002, 105.0)])])
    reverse = create_route_signature([polyline([(21.002, 105.0), (21.0, 105.0)])])
    same = weighted_ordered_overlap(forward, forward)
    backwards = weighted_ordered_overlap(forward, reverse)
    assert same.shared_route_distance_m == pytest.approx(forward.distance_m)
    assert same.adherence == pytest.approx(1.0)
    assert 0 <= backwards.adherence < 1
    assert 0 <= backwards.shared_route_distance_m <= forward.distance_m


def test_weighted_ordered_overlap_is_zero_without_common_cells():
    a = create_route_signature([polyline([(21.0, 105.0), (21.001, 105.0)])])
    b = create_route_signature([polyline([(22.0, 106.0), (22.001, 106.0)])])
    result = weighted_ordered_overlap(a, b)
    assert result.shared_route_distance_m == 0
    assert result.adherence == 0


def test_weighted_ordered_overlap_uses_optimal_ordered_alignment():
    recommended = RouteSignature(("a", "a"), (10.0, 2.0), 12.0, H3_ROUTE_RESOLUTION)
    historical = RouteSignature(("a",), (2.0,), 2.0, H3_ROUTE_RESOLUTION)
    result = weighted_ordered_overlap(recommended, historical)
    assert result.shared_route_distance_m == 2.0
    assert result.adherence == pytest.approx(1 / 6)


def test_weighted_ordered_overlap_measures_partial_ordered_match():
    recommended = RouteSignature(("a", "b", "c"), (10.0, 20.0, 30.0), 60.0, H3_ROUTE_RESOLUTION)
    historical = RouteSignature(("x", "b", "c", "y"), (5.0, 15.0, 40.0, 8.0), 68.0, H3_ROUTE_RESOLUTION)

    result = weighted_ordered_overlap(recommended, historical)

    assert result.shared_route_distance_m == pytest.approx(45.0)
    assert result.adherence == pytest.approx(0.75)
