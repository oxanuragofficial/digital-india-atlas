import pytest

from app.gis.geojson import GeometryError, validate_geometry

# Abstract shapes for structure tests only. These are NOT real places or boundaries.
SQUARE = [[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]


def test_valid_point_and_line():
    assert validate_geometry({"type": "Point", "coordinates": [10, 20]}) == "Point"
    line = {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}
    assert validate_geometry(line) == "LineString"


def test_valid_polygon_and_multipolygon():
    assert validate_geometry({"type": "Polygon", "coordinates": [SQUARE]}) == "Polygon"
    assert validate_geometry({"type": "MultiPolygon", "coordinates": [[SQUARE]]}) == "MultiPolygon"


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "Point", "coordinates": [200, 0]},  # lon out of range
        {"type": "Point", "coordinates": [0, 95]},  # lat out of range
        {"type": "Point", "coordinates": [0]},  # too short
        {"type": "Point", "coordinates": ["a", "b"]},  # not numbers
        {"type": "Point", "coordinates": [True, False]},  # bools are not numbers
        {"type": "LineString", "coordinates": [[0, 0]]},  # one position
        {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [0, 0]]]},  # ring has <4 positions
        {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0]]]},  # not closed
        {"type": "Polygon", "coordinates": []},
        {"type": "GeometryCollection", "geometries": []},  # unsupported here
        {"type": "Circle", "coordinates": [0, 0]},
        "not an object",
    ],
)
def test_invalid_geometries_rejected(geometry):
    with pytest.raises(GeometryError):
        validate_geometry(geometry)
