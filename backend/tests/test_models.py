"""Schema conventions from CLAUDE.md and docs/data-model.md, enforced."""

import re

import sqlalchemy as sa
from geoalchemy2 import Geometry

from app.models import Base
from tests.conftest import REPO_ROOT

TABLES = Base.metadata.sorted_tables
# Euro amounts. raw_price is verbatim PPR text (D-002); not_full_market_price is a flag.
MONEY_COLUMN = re.compile(r"^(price_eur|median_price|mean_price|p25|p75|budget_min|budget_max)$")


def test_every_geometry_column_has_a_gist_index() -> None:
    missing = []
    for table in TABLES:
        gist_columns = {
            col.name
            for ix in table.indexes
            if ix.dialect_options["postgresql"]["using"] == "gist"
            and ix.dialect_options["postgresql"]["where"] is None
            for col in ix.columns
        }
        for col in table.columns:
            if isinstance(col.type, Geometry) and col.name not in gist_columns:
                missing.append(f"{table.name}.{col.name}")
    assert not missing, f"geometry columns without a full GIST index: {missing}"


def test_money_is_numeric_never_float() -> None:
    for table in TABLES:
        for col in table.columns:
            if MONEY_COLUMN.search(col.name):
                assert isinstance(col.type, sa.Numeric), f"{table.name}.{col.name}"
                assert not isinstance(col.type, sa.Float), f"{table.name}.{col.name}"


def test_planning_application_never_models_applicant_fields() -> None:
    """D-017: applicant name/address columns exist upstream and must never be stored."""
    columns = {c.name.lower() for c in Base.metadata.tables["planning_application"].columns}
    assert not {c for c in columns if "applicant" in c}


def test_no_table_stores_owner_names() -> None:
    suspicious = re.compile(r"owner|surname|forename|vendor|purchaser")
    for table in TABLES:
        for col in table.columns:
            assert not suspicious.search(col.name), f"{table.name}.{col.name}"


def test_every_table_is_documented_in_data_model() -> None:
    doc = (REPO_ROOT / "docs" / "data-model.md").read_text()
    undocumented = [t.name for t in TABLES if f"`{t.name}`" not in doc]
    assert not undocumented, f"add these tables to docs/data-model.md: {undocumented}"
