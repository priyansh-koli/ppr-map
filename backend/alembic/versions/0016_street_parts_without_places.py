"""comparables: a town, county or postal district is not a street (P1 #15)

`address_street_parts` dropped only an address's last part as its town. In "8 annesley park,
ranelagh, dublin 6" or "15 cluain dara, clonard, co wexford" the last part is the district or
county, so the suburb or town before it counted as a street, and every home there was "on
the same street" (44% of a sample of precisely placed homes had such a part).

The function now also drops county parts ("co clare", "county clare") and Dublin postal
districts ("dublin 6", "d6w"), including one at the end of a part ("sandyford dublin 18").
It still cannot tell "ranelagh" from an estate by its text, so the comparables query also
leaves out parts named like a town, suburb or townland nearby (`gazetteer_feature` places,
and settlements and townlands in `area`), unless they carry a street word ("navan road").
The partial index keeps that lookup to the places, not the 400,000 address points.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-04 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STREET_PARTS = r"""
CREATE OR REPLACE FUNCTION address_street_parts(address text) RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT coalesce(array_agg(s) FILTER (
               WHERE s <> '' AND s !~ '^[0-9]'
                 AND s !~ '^(co\.?|county) '
                 AND s !~ '^(dublin|d|bhaile [aá]tha cliath) ?[0-9]{1,2}w?$'), '{}')
    FROM (
        SELECT trim(regexp_replace(
                   regexp_replace(part,
                       '^\s*((apt|apartment|unit|flat|no)\.?\s*)?[0-9][0-9a-z/-]*\s*', ''),
                   '\s+(dublin|bhaile [aá]tha cliath) ?[0-9]{1,2}w?$', '')) AS s
        FROM unnest(string_to_array(address, ',')) WITH ORDINALITY AS t(part, i)
        WHERE i < array_length(string_to_array(address, ','), 1)
    ) parts
$$;
"""

# Migration 0010's version.
PREVIOUS_STREET_PARTS = r"""
CREATE OR REPLACE FUNCTION address_street_parts(address text) RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT coalesce(array_agg(s) FILTER (WHERE s <> '' AND s !~ '^[0-9]'), '{}')
    FROM (
        SELECT trim(regexp_replace(part,
                    '^\s*((apt|apartment|unit|flat|no)\.?\s*)?[0-9][0-9a-z/-]*\s*', '')) AS s
        FROM unnest(string_to_array(address, ',')) WITH ORDINALITY AS t(part, i)
        WHERE i < array_length(string_to_array(address, ','), 1)
    ) parts
$$;
"""


def upgrade() -> None:
    op.execute(STREET_PARTS)
    op.create_index(
        "ix_gazetteer_feature_place_geom",
        "gazetteer_feature",
        ["geom"],
        unique=False,
        postgresql_using="gist",
        postgresql_where=sa.text("kind IN ('place', 'city')"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_gazetteer_feature_place_geom",
        table_name="gazetteer_feature",
        postgresql_using="gist",
        postgresql_where=sa.text("kind IN ('place', 'city')"),
    )
    op.execute(PREVIOUS_STREET_PARTS)
