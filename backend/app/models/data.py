"""Property-data tables: PPR sales, properties, geocoding, areas and enrichment.

See docs/data-model.md. Every geometry column has an explicit GIST index
(enforced by tests/test_models.py).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    Base,
    CreatedAtMixin,
    TimestampMixin,
    gist,
    multipolygon,
    pg_enum,
    point_4326,
    trgm,
)
from app.models.enums import (
    AreaKind,
    County,
    EnvironmentLayerKind,
    GeocodeConfidence,
    HexWindow,
    IngestKind,
    IngestStatus,
    PeriodKind,
    PlanningMatchKind,
    PoiType,
    Segment,
    SizeBand,
)

MONEY = sa.Numeric(12, 2)
COUNTY = pg_enum(County, "county")
CONFIDENCE = pg_enum(GeocodeConfidence, "geocode_confidence")
SEGMENT = pg_enum(Segment, "segment")
POI_TYPE = pg_enum(PoiType, "poi_type")


class IngestRun(Base):
    __tablename__ = "ingest_run"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    kind: Mapped[IngestKind] = mapped_column(pg_enum(IngestKind, "ingest_kind"))
    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    status: Mapped[IngestStatus] = mapped_column(
        pg_enum(IngestStatus, "ingest_status"), default=IngestStatus.RUNNING
    )
    source_url: Mapped[str | None] = mapped_column(sa.Text)
    source_sha256: Mapped[str | None] = mapped_column(sa.CHAR(64))
    source_bytes: Mapped[int | None] = mapped_column(sa.BigInteger)
    rows_read: Mapped[int] = mapped_column(sa.Integer, default=0)
    rows_inserted: Mapped[int] = mapped_column(sa.Integer, default=0)
    rows_withdrawn: Mapped[int] = mapped_column(sa.Integer, default=0)
    rows_failed: Mapped[int] = mapped_column(sa.Integer, default=0)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=sa.text("'{}'::jsonb"))
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("app_user.id", ondelete="SET NULL")
    )

    __table_args__ = (sa.Index("ix_ingest_run_kind_started_at", "kind", "started_at"),)


class IngestRowError(Base):
    __tablename__ = "ingest_row_error"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    ingest_run_id: Mapped[int] = mapped_column(
        sa.ForeignKey("ingest_run.id", ondelete="CASCADE"), index=True
    )
    line_no: Mapped[int] = mapped_column(sa.Integer)
    raw_line: Mapped[str] = mapped_column(sa.Text)
    error: Mapped[str] = mapped_column(sa.Text)


class Area(Base, CreatedAtMixin):
    __tablename__ = "area"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    kind: Mapped[AreaKind] = mapped_column(pg_enum(AreaKind, "area_kind"))
    code: Mapped[str] = mapped_column(sa.Text)
    name: Mapped[str] = mapped_column(sa.Text)
    name_ga: Mapped[str | None] = mapped_column(sa.Text)
    parent_id: Mapped[int | None] = mapped_column(sa.ForeignKey("area.id"), index=True)
    geom: Mapped[Any] = mapped_column(multipolygon(4326), comment="generalised, for display")
    geom_full: Mapped[Any | None] = mapped_column(
        multipolygon(2157), comment="ungeneralised ITM, for point-in-polygon"
    )
    is_approximate: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.false(), comment="derived shapes, e.g. routing keys"
    )
    source: Mapped[str] = mapped_column(sa.Text)
    source_version: Mapped[str | None] = mapped_column(sa.Text)
    slug: Mapped[str] = mapped_column(sa.Text, unique=True)

    __table_args__ = (
        sa.UniqueConstraint("kind", "code"),
        gist("area", "geom"),
        gist("area", "geom_full"),
        trgm("area", "name"),
    )


class Property(Base, TimestampMixin):
    __tablename__ = "property"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    public_id: Mapped[str] = mapped_column(sa.Text, unique=True)
    address_display: Mapped[str] = mapped_column(sa.Text)
    address_normalised: Mapped[str] = mapped_column(sa.Text)
    address_key: Mapped[str] = mapped_column(sa.Text)
    unit: Mapped[str | None] = mapped_column(sa.Text)
    house_number: Mapped[str | None] = mapped_column(sa.Text)
    county: Mapped[County] = mapped_column(COUNTY)
    dublin_district: Mapped[str | None] = mapped_column(sa.Text)
    eircode: Mapped[str | None] = mapped_column(sa.CHAR(7))
    eircode_routing_key: Mapped[str | None] = mapped_column(sa.CHAR(3))
    geom: Mapped[Any | None] = mapped_column(point_4326())
    geocode_confidence: Mapped[GeocodeConfidence] = mapped_column(
        CONFIDENCE, default=GeocodeConfidence.UNMATCHED
    )
    geocode_method: Mapped[str | None] = mapped_column(sa.Text)
    geocode_source: Mapped[str | None] = mapped_column(sa.Text)
    geocoded_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    geocode_locked: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.false())
    small_area_id: Mapped[int | None] = mapped_column(sa.ForeignKey("area.id"))
    ed_id: Mapped[int | None] = mapped_column(sa.ForeignKey("area.id"))
    townland_id: Mapped[int | None] = mapped_column(sa.ForeignKey("area.id"))
    settlement_id: Mapped[int | None] = mapped_column(sa.ForeignKey("area.id"))
    h3_r8: Mapped[int | None] = mapped_column(
        sa.BigInteger, comment="H3 cell id, computed in the pipeline (D-024)"
    )
    is_suppressed: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.false())

    __table_args__ = (
        sa.Index(
            "uq_property_county_address_key_unit",
            "county",
            "address_key",
            sa.text("coalesce(unit, '')"),
            unique=True,
        ),
        gist("property", "geom"),
        trgm("property", "address_normalised"),
        sa.Index("ix_property_eircode", "eircode"),
        sa.Index("ix_property_eircode_routing_key", "eircode_routing_key"),
        sa.Index("ix_property_small_area_id", "small_area_id"),
        sa.Index("ix_property_h3_r8", "h3_r8"),
        sa.Index(
            "ix_property_geom_precise_gist",
            "geom",
            postgresql_using="gist",
            postgresql_where=sa.text("geocode_confidence IN ('exact', 'street')"),
        ),
    )


class Sale(Base, CreatedAtMixin):
    __tablename__ = "sale"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    property_id: Mapped[int] = mapped_column(sa.ForeignKey("property.id"))
    source_row_hash: Mapped[str] = mapped_column(sa.CHAR(64), unique=True)
    # Verbatim PPR fields (cp1252-decoded), kept for re-parsing (D-002).
    raw_date: Mapped[str] = mapped_column(sa.Text)
    raw_address: Mapped[str] = mapped_column(sa.Text)
    raw_county: Mapped[str] = mapped_column(sa.Text)
    raw_eircode: Mapped[str] = mapped_column(sa.Text)
    raw_price: Mapped[str] = mapped_column(sa.Text)
    raw_nfmp: Mapped[str] = mapped_column(sa.Text)
    raw_vat: Mapped[str] = mapped_column(sa.Text)
    raw_description: Mapped[str] = mapped_column(sa.Text)
    raw_size: Mapped[str] = mapped_column(sa.Text)
    # Parsed values.
    sale_date: Mapped[date] = mapped_column(sa.Date)
    price_eur: Mapped[Decimal] = mapped_column(MONEY)
    not_full_market_price: Mapped[bool] = mapped_column(sa.Boolean)
    vat_exclusive: Mapped[bool] = mapped_column(sa.Boolean)
    is_new: Mapped[bool] = mapped_column(sa.Boolean)
    size_band: Mapped[SizeBand | None] = mapped_column(pg_enum(SizeBand, "size_band"))
    bulk_group_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    bulk_group_size: Mapped[int | None] = mapped_column(sa.Integer)
    is_possible_duplicate: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.false())
    first_seen_run_id: Mapped[int] = mapped_column(sa.ForeignKey("ingest_run.id"))
    last_seen_run_id: Mapped[int] = mapped_column(sa.ForeignKey("ingest_run.id"))
    withdrawn_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    __table_args__ = (
        sa.Index("ix_sale_property_id_sale_date", "property_id", sa.text("sale_date DESC")),
        sa.Index("ix_sale_sale_date_brin", "sale_date", postgresql_using="brin"),
        sa.Index("ix_sale_price_eur", "price_eur"),
        sa.Index(
            "ix_sale_market_sale_date",
            "sale_date",
            postgresql_where=sa.text(
                "NOT not_full_market_price AND bulk_group_id IS NULL AND withdrawn_at IS NULL"
            ),
        ),
    )


class GeocodeAttempt(Base, CreatedAtMixin):
    __tablename__ = "geocode_attempt"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    property_id: Mapped[int] = mapped_column(
        sa.ForeignKey("property.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[int | None] = mapped_column(sa.ForeignKey("ingest_run.id"))
    step: Mapped[int] = mapped_column(sa.SmallInteger)
    method: Mapped[str] = mapped_column(sa.Text)
    query: Mapped[str] = mapped_column(sa.Text)
    candidate_geom: Mapped[Any | None] = mapped_column(point_4326())
    candidate_type: Mapped[str | None] = mapped_column(sa.Text)
    confidence: Mapped[GeocodeConfidence] = mapped_column(CONFIDENCE)
    score: Mapped[float | None] = mapped_column(sa.Float)
    accepted: Mapped[bool] = mapped_column(sa.Boolean)
    reject_reason: Mapped[str | None] = mapped_column(sa.Text)
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, comment="dropped after 90 days"
    )

    __table_args__ = (gist("geocode_attempt", "candidate_geom"),)


class AreaStats(Base):
    __tablename__ = "area_stats"

    area_id: Mapped[int] = mapped_column(
        sa.ForeignKey("area.id", ondelete="CASCADE"), primary_key=True
    )
    period_kind: Mapped[PeriodKind] = mapped_column(
        pg_enum(PeriodKind, "period_kind"), primary_key=True
    )
    period_start: Mapped[date] = mapped_column(sa.Date, primary_key=True)
    segment: Mapped[Segment] = mapped_column(SEGMENT, primary_key=True)
    n_sales: Mapped[int] = mapped_column(sa.Integer)
    median_price: Mapped[Decimal | None] = mapped_column(MONEY)
    p25: Mapped[Decimal | None] = mapped_column(MONEY)
    p75: Mapped[Decimal | None] = mapped_column(MONEY)
    mean_price: Mapped[Decimal | None] = mapped_column(MONEY)
    provisional: Mapped[bool] = mapped_column(sa.Boolean)
    suppressed: Mapped[bool] = mapped_column(sa.Boolean, comment="n < 5")


class AreaAttribute(Base):
    """Census, deprivation and crime values per area, in long format."""

    __tablename__ = "area_attribute"

    area_id: Mapped[int] = mapped_column(
        sa.ForeignKey("area.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    key: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    as_of: Mapped[date] = mapped_column(sa.Date, primary_key=True)
    value: Mapped[Decimal | None] = mapped_column(sa.Numeric)
    value_text: Mapped[str | None] = mapped_column(sa.Text)
    licence: Mapped[str] = mapped_column(sa.Text)


class Poi(Base):
    __tablename__ = "poi"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    type: Mapped[PoiType] = mapped_column(POI_TYPE, index=True)
    name: Mapped[str | None] = mapped_column(sa.Text)
    geom: Mapped[Any] = mapped_column(point_4326())
    source: Mapped[str] = mapped_column(sa.Text)
    source_ref: Mapped[str] = mapped_column(sa.Text)
    attrs: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=sa.text("'{}'::jsonb"))
    as_of: Mapped[date] = mapped_column(sa.Date)

    __table_args__ = (sa.UniqueConstraint("source", "source_ref"), gist("poi", "geom"))


class PropertyEnrichment(Base):
    """Precomputed vicinity values, one row per property. Provenance per value group."""

    __tablename__ = "property_enrichment"

    property_id: Mapped[int] = mapped_column(
        sa.ForeignKey("property.id", ondelete="CASCADE"), primary_key=True
    )
    nearest_stop_id: Mapped[int | None] = mapped_column(sa.ForeignKey("poi.id"))
    nearest_stop_type: Mapped[PoiType | None] = mapped_column(POI_TYPE)
    nearest_stop_m: Mapped[int | None] = mapped_column(sa.Integer)
    nearest_rail_m: Mapped[int | None] = mapped_column(sa.Integer)
    nearest_primary_school_id: Mapped[int | None] = mapped_column(sa.ForeignKey("poi.id"))
    nearest_primary_school_m: Mapped[int | None] = mapped_column(sa.Integer)
    nearest_post_primary_school_id: Mapped[int | None] = mapped_column(sa.ForeignKey("poi.id"))
    nearest_post_primary_school_m: Mapped[int | None] = mapped_column(sa.Integer)
    amenities_1km: Mapped[dict[str, int] | None] = mapped_column(JSONB)
    deprivation_band: Mapped[str | None] = mapped_column(sa.Text)
    deprivation_level: Mapped[str | None] = mapped_column(sa.Text, comment="'ed' (D-011)")
    radon_high_area: Mapped[bool | None] = mapped_column(sa.Boolean)
    radon_pct: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 2))
    noise_mapped: Mapped[bool | None] = mapped_column(sa.Boolean)
    noise_lden_band: Mapped[str | None] = mapped_column(sa.Text)
    gzt_zone: Mapped[str | None] = mapped_column(sa.Text)
    planning_nearby_count_5y: Mapped[int | None] = mapped_column(sa.Integer)
    large_schemes_1km: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=sa.text("'{}'::jsonb"))
    computed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class PropertySummary(Base):
    """Precomputed hover-card payload (< 100 ms path, no joins)."""

    __tablename__ = "property_summary"

    property_id: Mapped[int] = mapped_column(
        sa.ForeignKey("property.id", ondelete="CASCADE"), primary_key=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    data_version: Mapped[str] = mapped_column(sa.Text)
    computed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class PriceHex(Base):
    __tablename__ = "price_hex"

    h3: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    window: Mapped[HexWindow] = mapped_column(pg_enum(HexWindow, "hex_window"), primary_key=True)
    segment: Mapped[Segment] = mapped_column(SEGMENT, primary_key=True)
    resolution: Mapped[int] = mapped_column(sa.SmallInteger)
    n: Mapped[int] = mapped_column(sa.Integer)
    median_price: Mapped[Decimal | None] = mapped_column(MONEY)
    suppressed: Mapped[bool] = mapped_column(sa.Boolean)
    geom: Mapped[Any] = mapped_column(multipolygon(4326))

    __table_args__ = (gist("price_hex", "geom"),)


class PlanningApplication(Base):
    """National Planning Applications (CC BY 4.0).

    Applicant name/address fields exist upstream but are deliberately NOT modelled (D-017).
    """

    __tablename__ = "planning_application"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    source_ref: Mapped[str] = mapped_column(sa.Text, unique=True, comment="authority+number")
    planning_authority: Mapped[str] = mapped_column(sa.Text)
    application_number: Mapped[str] = mapped_column(sa.Text)
    description: Mapped[str | None] = mapped_column(sa.Text)
    dev_address: Mapped[str | None] = mapped_column(sa.Text)
    dev_address_key: Mapped[str | None] = mapped_column(sa.Text, index=True)
    eircode: Mapped[str | None] = mapped_column(sa.CHAR(7), index=True)
    geom: Mapped[Any | None] = mapped_column(point_4326())
    status: Mapped[str | None] = mapped_column(sa.Text)
    application_type: Mapped[str | None] = mapped_column(sa.Text)
    decision: Mapped[str | None] = mapped_column(sa.Text)
    received_date: Mapped[date | None] = mapped_column(sa.Date, index=True)
    decision_date: Mapped[date | None] = mapped_column(sa.Date)
    grant_date: Mapped[date | None] = mapped_column(sa.Date)
    withdrawn_date: Mapped[date | None] = mapped_column(sa.Date)
    expiry_date: Mapped[date | None] = mapped_column(sa.Date)
    appeal_ref: Mapped[str | None] = mapped_column(sa.Text)
    appeal_status: Mapped[str | None] = mapped_column(sa.Text)
    appeal_decision: Mapped[str | None] = mapped_column(sa.Text)
    land_use_code: Mapped[str | None] = mapped_column(sa.Text)
    site_area: Mapped[Decimal | None] = mapped_column(sa.Numeric)
    num_residential_units: Mapped[int | None] = mapped_column(sa.Integer)
    one_off_house: Mapped[bool | None] = mapped_column(sa.Boolean)
    floor_area: Mapped[Decimal | None] = mapped_column(sa.Numeric)
    link_url: Mapped[str | None] = mapped_column(sa.Text)
    etl_date: Mapped[date | None] = mapped_column(sa.Date)

    __table_args__ = (gist("planning_application", "geom"),)


class PropertyPlanning(Base):
    __tablename__ = "property_planning"

    property_id: Mapped[int] = mapped_column(
        sa.ForeignKey("property.id", ondelete="CASCADE"), primary_key=True
    )
    planning_application_id: Mapped[int] = mapped_column(
        sa.ForeignKey("planning_application.id", ondelete="CASCADE"), primary_key=True
    )
    match_kind: Mapped[PlanningMatchKind] = mapped_column(
        pg_enum(PlanningMatchKind, "planning_match_kind")
    )
    distance_m: Mapped[int | None] = mapped_column(sa.Integer)


class EnvironmentLayer(Base):
    """Radon grid, noise contours and GZT zoning polygons (D-018)."""

    __tablename__ = "environment_layer"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    kind: Mapped[EnvironmentLayerKind] = mapped_column(
        pg_enum(EnvironmentLayerKind, "environment_layer_kind"), index=True
    )
    value_text: Mapped[str | None] = mapped_column(sa.Text)
    value_num: Mapped[Decimal | None] = mapped_column(sa.Numeric)
    geom: Mapped[Any] = mapped_column(multipolygon(4326))
    source: Mapped[str] = mapped_column(sa.Text)
    as_of: Mapped[date] = mapped_column(sa.Date)
    licence: Mapped[str] = mapped_column(sa.Text)

    __table_args__ = (gist("environment_layer", "geom"),)


class BenchmarkSeries(Base):
    """CSO RPPI, CSO routing-key medians and RTB rents (D-019)."""

    __tablename__ = "benchmark_series"

    source: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    series_key: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    period: Mapped[date] = mapped_column(sa.Date, primary_key=True)
    value: Mapped[Decimal] = mapped_column(sa.Numeric)
    unit: Mapped[str] = mapped_column(sa.Text)
    as_of: Mapped[date] = mapped_column(sa.Date)
