"""area_part subdivided polygons

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-26 22:33:38.467445
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "area_part",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("area_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM(
                "country",
                "county",
                "local_authority",
                "electoral_division",
                "small_area",
                "townland",
                "settlement",
                "routing_key",
                "dublin_district",
                name="area_kind",
                create_type=False,  # created in 0001
            ),
            nullable=False,
        ),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=2157,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["area_id"], ["area.id"], name=op.f("fk_area_part_area_id_area"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_area_part")),
    )
    op.create_index(op.f("ix_area_part_area_id"), "area_part", ["area_id"], unique=False)
    op.create_index(
        "ix_area_part_geom_gist", "area_part", ["geom"], unique=False, postgresql_using="gist"
    )
    op.create_index("ix_area_part_kind", "area_part", ["kind"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_area_part_kind", table_name="area_part")
    op.drop_index("ix_area_part_geom_gist", table_name="area_part", postgresql_using="gist")
    op.drop_index(op.f("ix_area_part_area_id"), table_name="area_part")
    op.drop_table("area_part")
