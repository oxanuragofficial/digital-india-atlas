"""Declarative base for all ORM models.

The naming convention gives every constraint and index a deterministic name, which keeps Alembic
migrations stable and lets error messages and tests refer to constraints by name. Constraints
that matter (checks, composite keys, partial/expression indexes) are named explicitly in the
models and migrations; this convention is the fallback for the rest.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
