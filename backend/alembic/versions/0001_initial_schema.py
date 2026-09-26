"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-26

Rendered from app.models (no database was available when Phase 1 was scaffolded).
Verify against a live PostGIS with `alembic upgrade head && alembic check`.
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AUDIT_LOG_APPEND_ONLY = """
CREATE FUNCTION audit_log_block_changes() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only';
END;
$$;
CREATE TRIGGER audit_log_append_only
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_block_changes();
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE TYPE alert_frequency AS ENUM ('off', 'on_data_update', 'weekly')")
    op.execute(
        "CREATE TYPE area_kind AS ENUM ('country', 'county', 'local_authority', 'electoral_division', 'small_area', 'townland', 'settlement', 'routing_key', 'dublin_district')"
    )
    op.execute(
        "CREATE TYPE consent_kind AS ENUM ('terms', 'privacy', 'marketing_email', 'cookies_analytics', 'age_18_plus')"
    )
    op.execute(
        "CREATE TYPE county AS ENUM ('carlow', 'cavan', 'clare', 'cork', 'donegal', 'dublin', 'galway', 'kerry', 'kildare', 'kilkenny', 'laois', 'leitrim', 'limerick', 'longford', 'louth', 'mayo', 'meath', 'monaghan', 'offaly', 'roscommon', 'sligo', 'tipperary', 'waterford', 'westmeath', 'wexford', 'wicklow')"
    )
    op.execute(
        "CREATE TYPE environment_layer_kind AS ENUM ('radon_grid', 'noise_road_lden', 'noise_rail_lden', 'noise_air_lden', 'gzt_zone')"
    )
    op.execute(
        "CREATE TYPE geocode_confidence AS ENUM ('exact', 'street', 'locality', 'routing_key', 'county', 'unmatched')"
    )
    op.execute("CREATE TYPE hex_window AS ENUM ('rolling_12m', 'rolling_36m')")
    op.execute(
        "CREATE TYPE ingest_kind AS ENUM ('ppr', 'gtfs', 'osm', 'census', 'pobal', 'schools', 'boundaries', 'crime', 'planning', 'environment', 'benchmarks')"
    )
    op.execute(
        "CREATE TYPE ingest_status AS ENUM ('running', 'succeeded', 'failed', 'skipped_unchanged')"
    )
    op.execute("CREATE TYPE period_kind AS ENUM ('month', 'quarter', 'year', 'rolling_12m')")
    op.execute(
        "CREATE TYPE planning_match_kind AS ENUM ('same_address', 'same_eircode', 'within_250m', 'large_scheme_1km')"
    )
    op.execute(
        "CREATE TYPE poi_type AS ENUM ('school_primary', 'school_post_primary', 'school_special', 'bus_stop', 'luas_stop', 'rail_station', 'dart_station', 'shop', 'supermarket', 'pharmacy', 'park', 'gym', 'restaurant', 'gp')"
    )
    op.execute("CREATE TYPE property_interest AS ENUM ('new', 'second_hand', 'both')")
    op.execute("CREATE TYPE removal_relationship AS ENUM ('owner', 'occupant', 'other')")
    op.execute(
        "CREATE TYPE removal_request_type AS ENUM ('suppress_display', 'correct_location', 'correct_details')"
    )
    op.execute(
        "CREATE TYPE removal_status AS ENUM ('new', 'in_review', 'approved', 'rejected', 'withdrawn')"
    )
    op.execute("CREATE TYPE segment AS ENUM ('all', 'new', 'second_hand')")
    op.execute("CREATE TYPE size_band AS ENUM ('lt_38', '38_to_125', 'gte_125')")
    op.execute(
        "CREATE TYPE user_type AS ENUM ('first_time_buyer', 'mover', 'investor', 'agent', 'researcher')"
    )
    op.execute("CREATE TYPE wishlist_target_kind AS ENUM ('property', 'area')")
    op.create_table(
        "app_user",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_hash", sa.Text(), nullable=False, comment="argon2id"),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("history_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("marketing_opt_in", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="soft delete; hard purge after 30 days",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_app_user")),
        sa.UniqueConstraint("email", name=op.f("uq_app_user_email")),
    )
    op.create_table(
        "area",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
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
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("name_ga", sa.Text(), nullable=True),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
            comment="generalised, for display",
        ),
        sa.Column(
            "geom_full",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=2157,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
            comment="ungeneralised ITM, for point-in-polygon",
        ),
        sa.Column(
            "is_approximate",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
            comment="derived shapes, e.g. routing keys",
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_version", sa.Text(), nullable=True),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["parent_id"], ["area.id"], name=op.f("fk_area_parent_id_area")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_area")),
        sa.UniqueConstraint("kind", "code", name=op.f("uq_area_kind_code")),
        sa.UniqueConstraint("slug", name=op.f("uq_area_slug")),
    )
    op.create_index(
        "ix_area_geom_full_gist", "area", ["geom_full"], unique=False, postgresql_using="gist"
    )
    op.create_index("ix_area_geom_gist", "area", ["geom"], unique=False, postgresql_using="gist")
    op.create_index(
        "ix_area_name_trgm",
        "area",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_index(op.f("ix_area_parent_id"), "area", ["parent_id"], unique=False)
    op.create_table(
        "benchmark_series",
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("series_key", sa.Text(), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("value", sa.Numeric(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("source", "series_key", "period", name=op.f("pk_benchmark_series")),
    )
    op.create_table(
        "environment_layer",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM(
                "radon_grid",
                "noise_road_lden",
                "noise_rail_lden",
                "noise_air_lden",
                "gzt_zone",
                name="environment_layer_kind",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_num", sa.Numeric(), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("licence", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_environment_layer")),
    )
    op.create_index(
        "ix_environment_layer_geom_gist",
        "environment_layer",
        ["geom"],
        unique=False,
        postgresql_using="gist",
    )
    op.create_index(op.f("ix_environment_layer_kind"), "environment_layer", ["kind"], unique=False)
    op.create_table(
        "permission",
        sa.Column("id", sa.SmallInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_permission")),
        sa.UniqueConstraint("code", name=op.f("uq_permission_code")),
    )
    op.create_table(
        "planning_application",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False, comment="authority+number"),
        sa.Column("planning_authority", sa.Text(), nullable=False),
        sa.Column("application_number", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("dev_address", sa.Text(), nullable=True),
        sa.Column("dev_address_key", sa.Text(), nullable=True),
        sa.Column("eircode", sa.CHAR(length=7), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("application_type", sa.Text(), nullable=True),
        sa.Column("decision", sa.Text(), nullable=True),
        sa.Column("received_date", sa.Date(), nullable=True),
        sa.Column("decision_date", sa.Date(), nullable=True),
        sa.Column("grant_date", sa.Date(), nullable=True),
        sa.Column("withdrawn_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("appeal_ref", sa.Text(), nullable=True),
        sa.Column("appeal_status", sa.Text(), nullable=True),
        sa.Column("appeal_decision", sa.Text(), nullable=True),
        sa.Column("land_use_code", sa.Text(), nullable=True),
        sa.Column("site_area", sa.Numeric(), nullable=True),
        sa.Column("num_residential_units", sa.Integer(), nullable=True),
        sa.Column("one_off_house", sa.Boolean(), nullable=True),
        sa.Column("floor_area", sa.Numeric(), nullable=True),
        sa.Column("link_url", sa.Text(), nullable=True),
        sa.Column("etl_date", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_planning_application")),
        sa.UniqueConstraint("source_ref", name=op.f("uq_planning_application_source_ref")),
    )
    op.create_index(
        op.f("ix_planning_application_dev_address_key"),
        "planning_application",
        ["dev_address_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_planning_application_eircode"), "planning_application", ["eircode"], unique=False
    )
    op.create_index(
        "ix_planning_application_geom_gist",
        "planning_application",
        ["geom"],
        unique=False,
        postgresql_using="gist",
    )
    op.create_index(
        op.f("ix_planning_application_received_date"),
        "planning_application",
        ["received_date"],
        unique=False,
    )
    op.create_table(
        "poi",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "type",
            postgresql.ENUM(
                "school_primary",
                "school_post_primary",
                "school_special",
                "bus_stop",
                "luas_stop",
                "rail_station",
                "dart_station",
                "shop",
                "supermarket",
                "pharmacy",
                "park",
                "gym",
                "restaurant",
                "gp",
                name="poi_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=True),
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
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column(
            "attrs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_poi")),
        sa.UniqueConstraint("source", "source_ref", name=op.f("uq_poi_source_source_ref")),
    )
    op.create_index("ix_poi_geom_gist", "poi", ["geom"], unique=False, postgresql_using="gist")
    op.create_index(op.f("ix_poi_type"), "poi", ["type"], unique=False)
    op.create_table(
        "price_hex",
        sa.Column("h3", sa.BigInteger(), nullable=False),
        sa.Column(
            "window",
            postgresql.ENUM("rolling_12m", "rolling_36m", name="hex_window", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "segment",
            postgresql.ENUM("all", "new", "second_hand", name="segment", create_type=False),
            nullable=False,
        ),
        sa.Column("resolution", sa.SmallInteger(), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("median_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("suppressed", sa.Boolean(), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("h3", "window", "segment", name=op.f("pk_price_hex")),
    )
    op.create_index(
        "ix_price_hex_geom_gist", "price_hex", ["geom"], unique=False, postgresql_using="gist"
    )
    op.create_table(
        "role",
        sa.Column("id", sa.SmallInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_role")),
        sa.UniqueConstraint("name", name=op.f("uq_role_name")),
    )
    op.create_table(
        "api_key",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("prefix", sa.CHAR(length=8), nullable=False),
        sa.Column("key_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.Text(), dimensions=1), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_api_key_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_key")),
        sa.UniqueConstraint("key_hash", name=op.f("uq_api_key_key_hash")),
    )
    op.create_index(op.f("ix_api_key_user_id"), "api_key", ["user_id"], unique=False)
    op.create_table(
        "area_attribute",
        sa.Column("area_id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("value", sa.Numeric(), nullable=True),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("licence", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["area_id"],
            ["area.id"],
            name=op.f("fk_area_attribute_area_id_area"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "area_id", "source", "key", "as_of", name=op.f("pk_area_attribute")
        ),
    )
    op.create_table(
        "area_stats",
        sa.Column("area_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "period_kind",
            postgresql.ENUM(
                "month", "quarter", "year", "rolling_12m", name="period_kind", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column(
            "segment",
            postgresql.ENUM("all", "new", "second_hand", name="segment", create_type=False),
            nullable=False,
        ),
        sa.Column("n_sales", sa.Integer(), nullable=False),
        sa.Column("median_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("p25", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("p75", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("mean_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("provisional", sa.Boolean(), nullable=False),
        sa.Column("suppressed", sa.Boolean(), nullable=False, comment="n < 5"),
        sa.ForeignKeyConstraint(
            ["area_id"], ["area.id"], name=op.f("fk_area_stats_area_id_area"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint(
            "area_id", "period_kind", "period_start", "segment", name=op.f("pk_area_stats")
        ),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_kind", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip_hash", sa.CHAR(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["app_user.id"],
            name=op.f("fk_audit_log_actor_user_id_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(
        "ix_audit_log_actor_user_id_created_at",
        "audit_log",
        ["actor_user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_log_target_kind_target_id",
        "audit_log",
        ["target_kind", "target_id"],
        unique=False,
    )
    op.create_table(
        "consent_record",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM(
                "terms",
                "privacy",
                "marketing_email",
                "cookies_analytics",
                "age_18_plus",
                name="consent_kind",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("document_version", sa.Text(), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ip_hash", sa.CHAR(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_consent_record_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consent_record")),
    )
    op.create_index(op.f("ix_consent_record_user_id"), "consent_record", ["user_id"], unique=False)
    op.create_table(
        "email_verification_token",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_email_verification_token_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_verification_token")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_email_verification_token_token_hash")),
    )
    op.create_index(
        op.f("ix_email_verification_token_user_id"),
        "email_verification_token",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "ingest_run",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM(
                "ppr",
                "gtfs",
                "osm",
                "census",
                "pobal",
                "schools",
                "boundaries",
                "crime",
                "planning",
                "environment",
                "benchmarks",
                name="ingest_kind",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "running",
                "succeeded",
                "failed",
                "skipped_unchanged",
                name="ingest_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_sha256", sa.CHAR(length=64), nullable=True),
        sa.Column("source_bytes", sa.BigInteger(), nullable=True),
        sa.Column("rows_read", sa.Integer(), nullable=False),
        sa.Column("rows_inserted", sa.Integer(), nullable=False),
        sa.Column("rows_withdrawn", sa.Integer(), nullable=False),
        sa.Column("rows_failed", sa.Integer(), nullable=False),
        sa.Column(
            "stats",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("triggered_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["triggered_by"],
            ["app_user.id"],
            name=op.f("fk_ingest_run_triggered_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingest_run")),
    )
    op.create_index(
        "ix_ingest_run_kind_started_at", "ingest_run", ["kind", "started_at"], unique=False
    )
    op.create_table(
        "password_reset_token",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_password_reset_token_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_reset_token")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_password_reset_token_token_hash")),
    )
    op.create_index(
        op.f("ix_password_reset_token_user_id"), "password_reset_token", ["user_id"], unique=False
    )
    op.create_table(
        "property",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("address_display", sa.Text(), nullable=False),
        sa.Column("address_normalised", sa.Text(), nullable=False),
        sa.Column("address_key", sa.Text(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.Column("house_number", sa.Text(), nullable=True),
        sa.Column(
            "county",
            postgresql.ENUM(
                "carlow",
                "cavan",
                "clare",
                "cork",
                "donegal",
                "dublin",
                "galway",
                "kerry",
                "kildare",
                "kilkenny",
                "laois",
                "leitrim",
                "limerick",
                "longford",
                "louth",
                "mayo",
                "meath",
                "monaghan",
                "offaly",
                "roscommon",
                "sligo",
                "tipperary",
                "waterford",
                "westmeath",
                "wexford",
                "wicklow",
                name="county",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("dublin_district", sa.Text(), nullable=True),
        sa.Column("eircode", sa.CHAR(length=7), nullable=True),
        sa.Column("eircode_routing_key", sa.CHAR(length=3), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.Column(
            "geocode_confidence",
            postgresql.ENUM(
                "exact",
                "street",
                "locality",
                "routing_key",
                "county",
                "unmatched",
                name="geocode_confidence",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("geocode_method", sa.Text(), nullable=True),
        sa.Column("geocode_source", sa.Text(), nullable=True),
        sa.Column("geocoded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("geocode_locked", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("small_area_id", sa.BigInteger(), nullable=True),
        sa.Column("ed_id", sa.BigInteger(), nullable=True),
        sa.Column("townland_id", sa.BigInteger(), nullable=True),
        sa.Column("settlement_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "h3_r8",
            sa.BigInteger(),
            nullable=True,
            comment="H3 cell id, computed in the pipeline (D-024)",
        ),
        sa.Column("is_suppressed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["ed_id"], ["area.id"], name=op.f("fk_property_ed_id_area")),
        sa.ForeignKeyConstraint(
            ["settlement_id"], ["area.id"], name=op.f("fk_property_settlement_id_area")
        ),
        sa.ForeignKeyConstraint(
            ["small_area_id"], ["area.id"], name=op.f("fk_property_small_area_id_area")
        ),
        sa.ForeignKeyConstraint(
            ["townland_id"], ["area.id"], name=op.f("fk_property_townland_id_area")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_property")),
        sa.UniqueConstraint("public_id", name=op.f("uq_property_public_id")),
    )
    op.create_index(
        "ix_property_address_normalised_trgm",
        "property",
        ["address_normalised"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"address_normalised": "gin_trgm_ops"},
    )
    op.create_index("ix_property_eircode", "property", ["eircode"], unique=False)
    op.create_index(
        "ix_property_eircode_routing_key", "property", ["eircode_routing_key"], unique=False
    )
    op.create_index(
        "ix_property_geom_gist", "property", ["geom"], unique=False, postgresql_using="gist"
    )
    op.create_index(
        "ix_property_geom_precise_gist",
        "property",
        ["geom"],
        unique=False,
        postgresql_using="gist",
        postgresql_where=sa.text("geocode_confidence IN ('exact', 'street')"),
    )
    op.create_index("ix_property_h3_r8", "property", ["h3_r8"], unique=False)
    op.create_index("ix_property_small_area_id", "property", ["small_area_id"], unique=False)
    op.create_index(
        "uq_property_county_address_key_unit",
        "property",
        ["county", "address_key", sa.literal_column("coalesce(unit, '')")],
        unique=True,
    )
    op.create_table(
        "role_permission",
        sa.Column("role_id", sa.SmallInteger(), nullable=False),
        sa.Column("permission_id", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permission.id"],
            name=op.f("fk_role_permission_permission_id_permission"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["role.id"],
            name=op.f("fk_role_permission_role_id_role"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_id", name=op.f("pk_role_permission")),
    )
    op.create_table(
        "saved_search",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("query", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "alert_frequency",
            postgresql.ENUM(
                "off", "on_data_update", "weekly", name="alert_frequency", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("last_alerted_data_version", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_saved_search_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_search")),
    )
    op.create_index(op.f("ix_saved_search_user_id"), "saved_search", ["user_id"], unique=False)
    op.create_table(
        "search_history",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("query", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "searched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_search_history_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_search_history")),
    )
    op.create_index(
        "ix_search_history_user_id_searched_at",
        "search_history",
        ["user_id", "searched_at"],
        unique=False,
    )
    op.create_table(
        "user_profile",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "user_type",
            postgresql.ENUM(
                "first_time_buyer",
                "mover",
                "investor",
                "agent",
                "researcher",
                name="user_type",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "counties",
            postgresql.ARRAY(
                postgresql.ENUM(
                    "carlow",
                    "cavan",
                    "clare",
                    "cork",
                    "donegal",
                    "dublin",
                    "galway",
                    "kerry",
                    "kildare",
                    "kilkenny",
                    "laois",
                    "leitrim",
                    "limerick",
                    "longford",
                    "louth",
                    "mayo",
                    "meath",
                    "monaghan",
                    "offaly",
                    "roscommon",
                    "sligo",
                    "tipperary",
                    "waterford",
                    "westmeath",
                    "wexford",
                    "wicklow",
                    name="county",
                    create_type=False,
                ),
                dimensions=1,
            ),
            nullable=True,
        ),
        sa.Column("area_ids", postgresql.ARRAY(sa.BigInteger(), dimensions=1), nullable=True),
        sa.Column("budget_min", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("budget_max", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column(
            "property_interest",
            postgresql.ENUM(
                "new", "second_hand", "both", name="property_interest", create_type=False
            ),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_user_profile_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_profile")),
    )
    op.create_table(
        "user_role",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role_id", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"], ["role.id"], name=op.f("fk_user_role_role_id_role"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_user_role_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "role_id", name=op.f("pk_user_role")),
    )
    op.create_table(
        "user_session",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("token_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_hash", sa.CHAR(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_user_session_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_session")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_user_session_token_hash")),
    )
    op.create_index(
        op.f("ix_user_session_expires_at"), "user_session", ["expires_at"], unique=False
    )
    op.create_index(op.f("ix_user_session_user_id"), "user_session", ["user_id"], unique=False)
    op.create_table(
        "alert_delivery",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("saved_search_id", sa.UUID(), nullable=False),
        sa.Column("data_version", sa.Text(), nullable=False),
        sa.Column("n_matches", sa.Integer(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["saved_search_id"],
            ["saved_search.id"],
            name=op.f("fk_alert_delivery_saved_search_id_saved_search"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_delivery")),
        sa.UniqueConstraint(
            "saved_search_id",
            "data_version",
            name=op.f("uq_alert_delivery_saved_search_id_data_version"),
        ),
    )
    op.create_table(
        "geocode_attempt",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("property_id", sa.BigInteger(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=True),
        sa.Column("step", sa.SmallInteger(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column(
            "candidate_geom",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.Column("candidate_type", sa.Text(), nullable=True),
        sa.Column(
            "confidence",
            postgresql.ENUM(
                "exact",
                "street",
                "locality",
                "routing_key",
                "county",
                "unmatched",
                name="geocode_confidence",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column(
            "raw_response",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="dropped after 90 days",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_geocode_attempt_property_id_property"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["ingest_run.id"], name=op.f("fk_geocode_attempt_run_id_ingest_run")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_geocode_attempt")),
    )
    op.create_index(
        "ix_geocode_attempt_candidate_geom_gist",
        "geocode_attempt",
        ["candidate_geom"],
        unique=False,
        postgresql_using="gist",
    )
    op.create_index(
        op.f("ix_geocode_attempt_property_id"), "geocode_attempt", ["property_id"], unique=False
    )
    op.create_table(
        "ingest_row_error",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("ingest_run_id", sa.BigInteger(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("raw_line", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["ingest_run_id"],
            ["ingest_run.id"],
            name=op.f("fk_ingest_row_error_ingest_run_id_ingest_run"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingest_row_error")),
    )
    op.create_index(
        op.f("ix_ingest_row_error_ingest_run_id"),
        "ingest_row_error",
        ["ingest_run_id"],
        unique=False,
    )
    op.create_table(
        "property_enrichment",
        sa.Column("property_id", sa.BigInteger(), nullable=False),
        sa.Column("nearest_stop_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "nearest_stop_type",
            postgresql.ENUM(
                "school_primary",
                "school_post_primary",
                "school_special",
                "bus_stop",
                "luas_stop",
                "rail_station",
                "dart_station",
                "shop",
                "supermarket",
                "pharmacy",
                "park",
                "gym",
                "restaurant",
                "gp",
                name="poi_type",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("nearest_stop_m", sa.Integer(), nullable=True),
        sa.Column("nearest_rail_m", sa.Integer(), nullable=True),
        sa.Column("nearest_primary_school_id", sa.BigInteger(), nullable=True),
        sa.Column("nearest_primary_school_m", sa.Integer(), nullable=True),
        sa.Column("nearest_post_primary_school_id", sa.BigInteger(), nullable=True),
        sa.Column("nearest_post_primary_school_m", sa.Integer(), nullable=True),
        sa.Column("amenities_1km", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("deprivation_band", sa.Text(), nullable=True),
        sa.Column("deprivation_level", sa.Text(), nullable=True, comment="'ed' (D-011)"),
        sa.Column("radon_high_area", sa.Boolean(), nullable=True),
        sa.Column("radon_pct", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("noise_mapped", sa.Boolean(), nullable=True),
        sa.Column("noise_lden_band", sa.Text(), nullable=True),
        sa.Column("gzt_zone", sa.Text(), nullable=True),
        sa.Column("planning_nearby_count_5y", sa.Integer(), nullable=True),
        sa.Column("large_schemes_1km", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "provenance",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["nearest_post_primary_school_id"],
            ["poi.id"],
            name=op.f("fk_property_enrichment_nearest_post_primary_school_id_poi"),
        ),
        sa.ForeignKeyConstraint(
            ["nearest_primary_school_id"],
            ["poi.id"],
            name=op.f("fk_property_enrichment_nearest_primary_school_id_poi"),
        ),
        sa.ForeignKeyConstraint(
            ["nearest_stop_id"], ["poi.id"], name=op.f("fk_property_enrichment_nearest_stop_id_poi")
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_property_enrichment_property_id_property"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("property_id", name=op.f("pk_property_enrichment")),
    )
    op.create_table(
        "property_planning",
        sa.Column("property_id", sa.BigInteger(), nullable=False),
        sa.Column("planning_application_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "match_kind",
            postgresql.ENUM(
                "same_address",
                "same_eircode",
                "within_250m",
                "large_scheme_1km",
                name="planning_match_kind",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("distance_m", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["planning_application_id"],
            ["planning_application.id"],
            name=op.f("fk_property_planning_planning_application_id_planning_application"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_property_planning_property_id_property"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "property_id", "planning_application_id", name=op.f("pk_property_planning")
        ),
    )
    op.create_table(
        "property_summary",
        sa.Column("property_id", sa.BigInteger(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("data_version", sa.Text(), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_property_summary_property_id_property"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("property_id", name=op.f("pk_property_summary")),
    )
    op.create_table(
        "removal_request",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("property_id", sa.BigInteger(), nullable=True),
        sa.Column("submitted_address", sa.Text(), nullable=False),
        sa.Column("requester_email", postgresql.CITEXT(), nullable=True),
        sa.Column(
            "requester_relationship",
            postgresql.ENUM(
                "owner", "occupant", "other", name="removal_relationship", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "request_type",
            postgresql.ENUM(
                "suppress_display",
                "correct_location",
                "correct_details",
                name="removal_request_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "new",
                "in_review",
                "approved",
                "rejected",
                "withdrawn",
                name="removal_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["app_user.id"],
            name=op.f("fk_removal_request_decided_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_removal_request_property_id_property"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_removal_request")),
    )
    op.create_index(
        op.f("ix_removal_request_property_id"), "removal_request", ["property_id"], unique=False
    )
    op.create_index(op.f("ix_removal_request_status"), "removal_request", ["status"], unique=False)
    op.create_table(
        "sale",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("property_id", sa.BigInteger(), nullable=False),
        sa.Column("source_row_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("raw_date", sa.Text(), nullable=False),
        sa.Column("raw_address", sa.Text(), nullable=False),
        sa.Column("raw_county", sa.Text(), nullable=False),
        sa.Column("raw_eircode", sa.Text(), nullable=False),
        sa.Column("raw_price", sa.Text(), nullable=False),
        sa.Column("raw_nfmp", sa.Text(), nullable=False),
        sa.Column("raw_vat", sa.Text(), nullable=False),
        sa.Column("raw_description", sa.Text(), nullable=False),
        sa.Column("raw_size", sa.Text(), nullable=False),
        sa.Column("sale_date", sa.Date(), nullable=False),
        sa.Column("price_eur", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("not_full_market_price", sa.Boolean(), nullable=False),
        sa.Column("vat_exclusive", sa.Boolean(), nullable=False),
        sa.Column("is_new", sa.Boolean(), nullable=False),
        sa.Column(
            "size_band",
            postgresql.ENUM("lt_38", "38_to_125", "gte_125", name="size_band", create_type=False),
            nullable=True,
        ),
        sa.Column("bulk_group_id", sa.BigInteger(), nullable=True),
        sa.Column("bulk_group_size", sa.Integer(), nullable=True),
        sa.Column(
            "is_possible_duplicate", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("first_seen_run_id", sa.BigInteger(), nullable=False),
        sa.Column("last_seen_run_id", sa.BigInteger(), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["first_seen_run_id"],
            ["ingest_run.id"],
            name=op.f("fk_sale_first_seen_run_id_ingest_run"),
        ),
        sa.ForeignKeyConstraint(
            ["last_seen_run_id"],
            ["ingest_run.id"],
            name=op.f("fk_sale_last_seen_run_id_ingest_run"),
        ),
        sa.ForeignKeyConstraint(
            ["property_id"], ["property.id"], name=op.f("fk_sale_property_id_property")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sale")),
        sa.UniqueConstraint("source_row_hash", name=op.f("uq_sale_source_row_hash")),
    )
    op.create_index(
        "ix_sale_market_sale_date",
        "sale",
        ["sale_date"],
        unique=False,
        postgresql_where=sa.text(
            "NOT not_full_market_price AND bulk_group_id IS NULL AND withdrawn_at IS NULL"
        ),
    )
    op.create_index("ix_sale_price_eur", "sale", ["price_eur"], unique=False)
    op.create_index(
        "ix_sale_property_id_sale_date",
        "sale",
        ["property_id", sa.literal_column("sale_date DESC")],
        unique=False,
    )
    op.create_index(
        "ix_sale_sale_date_brin", "sale", ["sale_date"], unique=False, postgresql_using="brin"
    )
    op.create_table(
        "view_history",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("property_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "viewed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_view_history_property_id_property"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_view_history_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_view_history")),
    )
    op.create_index(
        "ix_view_history_user_id_viewed_at", "view_history", ["user_id", "viewed_at"], unique=False
    )
    op.create_table(
        "wishlist_item",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "target_kind",
            postgresql.ENUM("property", "area", name="wishlist_target_kind", create_type=False),
            nullable=False,
        ),
        sa.Column("property_id", sa.BigInteger(), nullable=True),
        sa.Column("area_id", sa.BigInteger(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(target_kind = 'property' AND property_id IS NOT NULL AND area_id IS NULL) OR (target_kind = 'area' AND area_id IS NOT NULL AND property_id IS NULL)",
            name=op.f("ck_wishlist_item_one_target"),
        ),
        sa.CheckConstraint("char_length(note) <= 2000", name=op.f("ck_wishlist_item_note_length")),
        sa.ForeignKeyConstraint(
            ["area_id"], ["area.id"], name=op.f("fk_wishlist_item_area_id_area"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_wishlist_item_property_id_property"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_wishlist_item_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_wishlist_item")),
        sa.UniqueConstraint(
            "user_id",
            "target_kind",
            "property_id",
            "area_id",
            name=op.f("uq_wishlist_item_user_id_target_kind_property_id_area_id"),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.execute(AUDIT_LOG_APPEND_ONLY)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_append_only ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_block_changes()")
    op.drop_table("wishlist_item")
    op.drop_table("view_history")
    op.drop_table("sale")
    op.drop_table("removal_request")
    op.drop_table("property_summary")
    op.drop_table("property_planning")
    op.drop_table("property_enrichment")
    op.drop_table("ingest_row_error")
    op.drop_table("geocode_attempt")
    op.drop_table("alert_delivery")
    op.drop_table("user_session")
    op.drop_table("user_role")
    op.drop_table("user_profile")
    op.drop_table("search_history")
    op.drop_table("saved_search")
    op.drop_table("role_permission")
    op.drop_table("property")
    op.drop_table("password_reset_token")
    op.drop_table("ingest_run")
    op.drop_table("email_verification_token")
    op.drop_table("consent_record")
    op.drop_table("audit_log")
    op.drop_table("area_stats")
    op.drop_table("area_attribute")
    op.drop_table("api_key")
    op.drop_table("role")
    op.drop_table("price_hex")
    op.drop_table("poi")
    op.drop_table("planning_application")
    op.drop_table("permission")
    op.drop_table("environment_layer")
    op.drop_table("benchmark_series")
    op.drop_table("area")
    op.drop_table("app_user")
    op.execute("DROP TYPE IF EXISTS alert_frequency")
    op.execute("DROP TYPE IF EXISTS area_kind")
    op.execute("DROP TYPE IF EXISTS consent_kind")
    op.execute("DROP TYPE IF EXISTS county")
    op.execute("DROP TYPE IF EXISTS environment_layer_kind")
    op.execute("DROP TYPE IF EXISTS geocode_confidence")
    op.execute("DROP TYPE IF EXISTS hex_window")
    op.execute("DROP TYPE IF EXISTS ingest_kind")
    op.execute("DROP TYPE IF EXISTS ingest_status")
    op.execute("DROP TYPE IF EXISTS period_kind")
    op.execute("DROP TYPE IF EXISTS planning_match_kind")
    op.execute("DROP TYPE IF EXISTS poi_type")
    op.execute("DROP TYPE IF EXISTS property_interest")
    op.execute("DROP TYPE IF EXISTS removal_relationship")
    op.execute("DROP TYPE IF EXISTS removal_request_type")
    op.execute("DROP TYPE IF EXISTS removal_status")
    op.execute("DROP TYPE IF EXISTS segment")
    op.execute("DROP TYPE IF EXISTS size_band")
    op.execute("DROP TYPE IF EXISTS user_type")
    op.execute("DROP TYPE IF EXISTS wishlist_target_kind")
    # Extensions (postgis, pg_trgm, citext) are left installed on purpose.
