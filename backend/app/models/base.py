import enum
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from geoalchemy2 import Geometry
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


class TimestampMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    )


def pg_enum(enum_cls: type[enum.Enum], name: str) -> sa.Enum:
    """Postgres enum stored by value (lowercase strings), not by Python member name."""
    return sa.Enum(
        enum_cls,
        name=name,
        values_callable=lambda members: [m.value for m in members],
        validate_strings=True,
    )


def point_4326() -> Any:
    # GIST indexes are declared explicitly in __table_args__ (see gist()), so geoalchemy2's
    # implicit index creation is turned off to keep migrations explicit.
    return Geometry(geometry_type="POINT", srid=4326, spatial_index=False)


def multipolygon(srid: int = 4326) -> Any:
    return Geometry(geometry_type="MULTIPOLYGON", srid=srid, spatial_index=False)


def gist(table: str, column: str) -> sa.Index:
    return sa.Index(f"ix_{table}_{column}_gist", column, postgresql_using="gist")


def trgm(table: str, column: str) -> sa.Index:
    return sa.Index(
        f"ix_{table}_{column}_trgm",
        column,
        postgresql_using="gin",
        postgresql_ops={column: "gin_trgm_ops"},
    )
