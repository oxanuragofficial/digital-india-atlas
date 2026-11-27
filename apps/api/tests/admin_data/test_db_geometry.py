"""Geometry columns: type, CRS, validity and publication rules.

The shapes below are ABSTRACT unit squares near the origin, used only to exercise constraints.
They are not, and do not resemble, any real administrative boundary.
"""

from __future__ import annotations

import pytest
from geoalchemy2.elements import WKTElement
from helpers import (
    expect_rejected,
    force_status,
    make_chain,
    make_unit,
    make_version,
    requires_db,
)
from sqlalchemy import text

from app.admin_data.models import AdminUnitGeometry
from app.admin_data.status import PublicationStatus

pytestmark = requires_db
S = PublicationStatus

SQUARE = "MULTIPOLYGON(((0 0,0 1,1 1,1 0,0 0)))"
POINT = "POINT(0.5 0.5)"


def multipolygon(wkt: str = SQUARE, srid: int = 4326) -> WKTElement:
    return WKTElement(wkt, srid=srid)


def add_geometry(session, unit, boundary=None, point=None):
    row = AdminUnitGeometry(unit_id=unit.id, boundary=boundary, representative_point=point)
    session.add(row)
    session.flush()
    return row


@pytest.fixture
def unit(session):
    return make_unit(session, make_version(session), "state_ut", "01")


# ---- what is stored, and in which CRS --------------------------------------------------------


def test_documented_geometry_types_and_crs_match_the_database(session):
    rows = session.execute(
        text(
            "SELECT f_geometry_column, type, srid FROM geometry_columns "
            "WHERE f_table_name = 'admin_unit_geometry' ORDER BY f_geometry_column"
        )
    ).all()
    assert rows == [
        ("boundary", "MULTIPOLYGON", 4326),
        ("representative_point", "POINT", 4326),
    ]


def test_a_boundary_can_be_stored_and_read_back_in_epsg_4326(session, unit):
    add_geometry(session, unit, boundary=multipolygon())
    result = session.execute(
        text(
            "SELECT ST_SRID(boundary), ST_GeometryType(boundary), ST_Area(boundary) "
            "FROM admin_unit_geometry WHERE unit_id = :u"
        ),
        {"u": unit.id},
    ).one()
    assert result == (4326, "ST_MultiPolygon", 1.0)


def test_a_representative_point_can_be_stored_without_a_boundary(session, unit):
    add_geometry(session, unit, point=WKTElement(POINT, srid=4326))


def test_both_geometries_can_be_stored_together(session, unit):
    add_geometry(session, unit, boundary=multipolygon(), point=WKTElement(POINT, srid=4326))


def test_axis_order_is_longitude_then_latitude(session, unit):
    add_geometry(session, unit, point=WKTElement("POINT(77.0 28.0)", srid=4326))
    x, y = session.execute(
        text(
            "SELECT ST_X(representative_point), ST_Y(representative_point) "
            "FROM admin_unit_geometry WHERE unit_id = :u"
        ),
        {"u": unit.id},
    ).one()
    assert (x, y) == (77.0, 28.0)  # x = longitude, y = latitude


def test_a_unit_can_have_at_most_one_geometry_row(session, unit):
    add_geometry(session, unit, boundary=multipolygon())
    with expect_rejected(session, constraint="pk_admin_unit_geometry"):
        add_geometry(session, unit, boundary=multipolygon())


# ---- what is refused ------------------------------------------------------------------------


def test_a_geometry_row_must_contain_something(session, unit):
    with expect_rejected(session, constraint="ck_admin_unit_geometry_not_empty"):
        add_geometry(session, unit)


def test_boundaries_in_another_crs_are_refused(session, unit):
    with expect_rejected(session, message="SRID"):
        add_geometry(session, unit, boundary=multipolygon(srid=3857))


def test_points_in_another_crs_are_refused(session, unit):
    with expect_rejected(session, message="SRID"):
        add_geometry(session, unit, point=WKTElement(POINT, srid=3857))


def test_a_plain_polygon_is_promoted_so_stored_boundaries_are_always_multipolygons(session, unit):
    """PostGIS promotes a single Polygon to a MultiPolygon on insert into a MULTIPOLYGON column.
    The stored type is therefore always MultiPolygon, whatever the loader sent."""
    add_geometry(session, unit, boundary=WKTElement("POLYGON((0 0,0 1,1 1,1 0,0 0))", srid=4326))
    stored = session.scalar(
        text("SELECT ST_GeometryType(boundary) FROM admin_unit_geometry WHERE unit_id = :u"),
        {"u": unit.id},
    )
    assert stored == "ST_MultiPolygon"


def test_a_point_cannot_go_in_the_boundary_column(session, unit):
    with expect_rejected(session, message="does not match column type"):
        add_geometry(session, unit, boundary=WKTElement(POINT, srid=4326))


def test_a_polygon_cannot_go_in_the_point_column(session, unit):
    with expect_rejected(session, message="does not match column type"):
        add_geometry(session, unit, point=multipolygon())


@pytest.mark.parametrize(
    "wkt",
    [
        "MULTIPOLYGON(((0 0,1 1,1 0,0 1,0 0)))",  # self-intersecting "bow-tie"
        "MULTIPOLYGON EMPTY",
    ],
    ids=["self_intersecting", "empty"],
)
def test_invalid_or_empty_boundaries_are_refused(session, unit, wkt):
    with expect_rejected(session, constraint="ck_admin_unit_geometry_boundary_valid"):
        add_geometry(session, unit, boundary=multipolygon(wkt))


@pytest.mark.parametrize(
    "wkt",
    [
        "MULTIPOLYGON(((179 0,181 0,181 1,179 1,179 0)))",  # longitude > 180
        "MULTIPOLYGON(((0 89,1 89,1 91,0 91,0 89)))",  # latitude > 90
        "MULTIPOLYGON(((-181 0,-179 0,-179 1,-181 1,-181 0)))",  # longitude < -180
    ],
)
def test_boundaries_outside_lon_lat_range_are_refused(session, unit, wkt):
    with expect_rejected(session, constraint="ck_admin_unit_geometry_boundary_valid"):
        add_geometry(session, unit, boundary=multipolygon(wkt))


@pytest.mark.parametrize("wkt", ["POINT(181 0)", "POINT(0 91)", "POINT(-181 0)", "POINT EMPTY"])
def test_points_outside_lon_lat_range_or_empty_are_refused(session, unit, wkt):
    with expect_rejected(session, constraint="ck_admin_unit_geometry_point_valid"):
        add_geometry(session, unit, point=WKTElement(wkt, srid=4326))


def test_geometry_cannot_exist_without_a_unit(session):
    with expect_rejected(session, constraint="fk_admin_unit_geometry_unit"):
        session.add(AdminUnitGeometry(unit_id=987654321, boundary=multipolygon()))


# ---- indexing ---------------------------------------------------------------------------------


def test_spatial_columns_have_gist_indexes(session):
    defs = dict(
        session.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'admin_unit_geometry'"
            )
        ).all()
    )
    assert "USING gist (boundary)" in defs["gix_admin_unit_geometry_boundary"]
    assert "USING gist (representative_point)" in defs["gix_admin_unit_geometry_point"]


def test_spatial_queries_find_units_by_location(session):
    v = make_version(session)
    inside = make_unit(session, v, "state_ut", "01")
    outside = make_unit(session, v, "state_ut", "02")
    add_geometry(session, inside, boundary=multipolygon())
    add_geometry(
        session, outside, boundary=multipolygon("MULTIPOLYGON(((10 10,10 11,11 11,11 10,10 10)))")
    )
    found = session.scalars(
        text(
            "SELECT u.code FROM admin_unit_geometry g JOIN admin_unit u ON u.id = g.unit_id "
            "WHERE ST_Intersects(g.boundary, ST_SetSRID(ST_MakePoint(0.5, 0.5), 4326))"
        )
    ).all()
    assert found == ["01"]


# ---- geometry follows its unit through the publication workflow -----------------------------


def test_geometry_is_deleted_with_its_unit_while_editable(session, unit):
    add_geometry(session, unit, boundary=multipolygon())
    session.execute(text("DELETE FROM admin_unit WHERE id = :u"), {"u": unit.id})
    assert session.scalar(text("SELECT count(*) FROM admin_unit_geometry")) == 0


@pytest.mark.parametrize("status", [S.UNDER_REVIEW, S.APPROVED, S.PUBLISHED, S.SUPERSEDED])
def test_geometry_is_frozen_from_review_onward(session, status):
    v = make_version(session)
    chain = make_chain(session, v)
    row = add_geometry(session, chain["state"], boundary=multipolygon())
    force_status(session, v, status)
    with expect_rejected(session, message="is frozen"):
        add_geometry(session, chain["district"], boundary=multipolygon())
    with expect_rejected(session, message="is frozen"):
        row.boundary = multipolygon("MULTIPOLYGON(((0 0,0 2,2 2,2 0,0 0)))")
    with expect_rejected(session, message="cannot be deleted"):
        session.execute(
            text("DELETE FROM admin_unit_geometry WHERE unit_id = :u"), {"u": row.unit_id}
        )


def test_geometry_can_still_be_changed_while_validated(session):
    v = make_version(session)
    chain = make_chain(session, v)
    row = add_geometry(session, chain["state"], boundary=multipolygon())
    force_status(session, v, S.VALIDATED)
    row.boundary = multipolygon("MULTIPOLYGON(((0 0,0 2,2 2,2 0,0 0)))")
    session.flush()


def test_only_published_geometry_is_visible_in_the_published_view(session):
    hidden = make_version(session)
    shown = make_version(session, dataset_name="Another Synthetic Dataset")
    for version in (hidden, shown):
        chain = make_chain(session, version)
        add_geometry(session, chain["state"], boundary=multipolygon())
    force_status(session, hidden, S.APPROVED)
    force_status(session, shown, S.PUBLISHED)
    visible = session.scalars(text("SELECT unit_id FROM published_admin_unit_geometry")).all()
    assert len(visible) == 1
    owner = session.scalar(
        text("SELECT dataset_version_id FROM admin_unit WHERE id = :u"), {"u": visible[0]}
    )
    assert owner == shown.id
