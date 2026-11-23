"""Structural validation of GeoJSON geometries (RFC 7946 subset).

This checks shape and coordinate ranges only. It does not repair geometries, check
self-intersection, or verify that data is authoritative.
"""

from __future__ import annotations

from typing import Any

from app.gis.bounds import is_valid_lon_lat

GEOMETRY_TYPES = {"Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"}


class GeometryError(ValueError):
    pass


def _check_position(pos: Any) -> None:
    if not isinstance(pos, list | tuple) or len(pos) not in (2, 3):
        raise GeometryError("position must be [lon, lat] or [lon, lat, alt]")
    if not all(isinstance(v, int | float) and not isinstance(v, bool) for v in pos):
        raise GeometryError("position values must be numbers")
    if not is_valid_lon_lat(pos[0], pos[1]):
        raise GeometryError("position out of WGS84 range (expected [lon, lat])")


def _check_line(coords: Any, min_len: int = 2) -> None:
    if not isinstance(coords, list | tuple) or len(coords) < min_len:
        raise GeometryError(f"line needs at least {min_len} positions")
    for pos in coords:
        _check_position(pos)


def _check_ring(ring: Any) -> None:
    _check_line(ring, min_len=4)
    if list(ring[0]) != list(ring[-1]):
        raise GeometryError("polygon ring must be closed")


def validate_geometry(geometry: Any) -> str:
    """Validate a GeoJSON geometry object; return its type or raise GeometryError."""
    if not isinstance(geometry, dict):
        raise GeometryError("geometry must be an object")
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if gtype not in GEOMETRY_TYPES:
        raise GeometryError(f"unsupported geometry type: {gtype!r}")

    if gtype == "Point":
        _check_position(coords)
    elif gtype == "MultiPoint":
        _require_list(coords)
        for pos in coords:
            _check_position(pos)
    elif gtype == "LineString":
        _check_line(coords)
    elif gtype == "MultiLineString":
        _require_list(coords)
        for line in coords:
            _check_line(line)
    elif gtype == "Polygon":
        _require_list(coords)
        for ring in coords:
            _check_ring(ring)
    else:  # MultiPolygon
        _require_list(coords)
        for polygon in coords:
            _require_list(polygon)
            for ring in polygon:
                _check_ring(ring)
    return gtype


def _require_list(coords: Any) -> None:
    if not isinstance(coords, list | tuple) or len(coords) == 0:
        raise GeometryError("coordinates must be a non-empty array")
