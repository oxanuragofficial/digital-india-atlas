import pytest

from app.gis.bounds import INDIA_VIEWPORT, BoundingBox, is_valid_lon_lat


@pytest.mark.parametrize(
    ("lon", "lat", "expected"),
    [(0, 0, True), (180, 90, True), (-180, -90, True), (181, 0, False), (0, 91, False)],
)
def test_is_valid_lon_lat(lon, lat, expected):
    assert is_valid_lon_lat(lon, lat) is expected


def test_bbox_rejects_inverted_or_out_of_range():
    with pytest.raises(ValueError):
        BoundingBox(10, 10, 5, 20)
    with pytest.raises(ValueError):
        BoundingBox(0, 0, 200, 10)


def test_bbox_contains_and_intersects():
    box = BoundingBox(0, 0, 10, 10)
    assert box.contains(5, 5)
    assert box.contains(0, 10)  # edges inclusive
    assert not box.contains(11, 5)
    assert box.intersects(BoundingBox(9, 9, 20, 20))
    assert not box.intersects(BoundingBox(11, 11, 20, 20))


def test_bbox_as_list_is_west_south_east_north():
    assert BoundingBox(1, 2, 3, 4).as_list() == [1, 2, 3, 4]


def test_india_viewport_is_a_valid_box_in_expected_hemisphere():
    # Sanity check only: the viewport is a framing convenience, not a boundary.
    assert INDIA_VIEWPORT.min_lon < INDIA_VIEWPORT.max_lon
    assert 0 < INDIA_VIEWPORT.min_lat < INDIA_VIEWPORT.max_lat < 90
    assert 60 < INDIA_VIEWPORT.min_lon and INDIA_VIEWPORT.max_lon < 105
