"""gazetteer_feature: streets, estates, address points and places for local geocoding (D-046)

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-29 12:00:00.000000
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COUNTIES = (
    "carlow", "cavan", "clare", "cork", "donegal", "dublin", "galway", "kerry", "kildare",
    "kilkenny", "laois", "leitrim", "limerick", "longford", "louth", "mayo", "meath",
    "monaghan", "offaly", "roscommon", "sligo", "tipperary", "waterford", "westmeath",
    "wexford", "wicklow",
)  # fmt: skip


def upgrade() -> None:
    op.create_table(
        "gazetteer_feature",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("house_number", sa.Text(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "county",
            postgresql.ENUM(*COUNTIES, name="county", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.Column("radius_m", sa.Integer(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gazetteer_feature")),
    )
    op.create_index(
        "ix_gazetteer_feature_county_kind", "gazetteer_feature", ["county", "kind"], unique=False
    )
    op.create_index(
        "ix_gazetteer_feature_geom_gist",
        "gazetteer_feature",
        ["geom"],
        unique=False,
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index("ix_gazetteer_feature_geom_gist", table_name="gazetteer_feature")
    op.drop_index("ix_gazetteer_feature_county_kind", table_name="gazetteer_feature")
    op.drop_table("gazetteer_feature")
