"""Coordinate and bounding-box helpers (WGS84 / EPSG:4326, longitude-first)."""

from __future__ import annotations

from dataclasses import dataclass


def is_valid_lon_lat(lon: float, lat: float) -> bool:
    return -180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0


@dataclass(frozen=True)
class BoundingBox:
    """Axis-aligned box in degrees. Does not support antimeridian-crossing boxes."""

    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    def __post_init__(self) -> None:
        if not (
            is_valid_lon_lat(self.min_lon, self.min_lat)
            and is_valid_lon_lat(self.max_lon, self.max_lat)
        ):
            raise ValueError("bounding box coordinates out of range")
        if self.min_lon >= self.max_lon or self.min_lat >= self.max_lat:
            raise ValueError("bounding box minimums must be smaller than maximums")

    def contains(self, lon: float, lat: float) -> bool:
        return self.min_lon <= lon <= self.max_lon and self.min_lat <= lat <= self.max_lat

    def intersects(self, other: BoundingBox) -> bool:
        return not (
            other.min_lon > self.max_lon
            or other.max_lon < self.min_lon
            or other.min_lat > self.max_lat
            or other.max_lat < self.min_lat
        )

    def as_list(self) -> list[float]:
        """[west, south, east, north] - the order MapLibre and GeoJSON use."""
        return [self.min_lon, self.min_lat, self.max_lon, self.max_lat]


# Approximate framing for the initial map view of India. This is a *viewport convenience only*:
# it is NOT an administrative or legal boundary and must not be used for clipping, area
# calculations, or deciding what is "inside India". Authoritative boundaries will come from
# official sources in a later milestone.
INDIA_VIEWPORT = BoundingBox(min_lon=67.5, min_lat=5.5, max_lon=98.5, max_lat=37.5)
