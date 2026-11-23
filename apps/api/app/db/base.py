"""Declarative base for all ORM models.

No models are defined yet. Spatial models (e.g. via GeoAlchemy2) will be added together with
their authoritative data sources in a later milestone.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
