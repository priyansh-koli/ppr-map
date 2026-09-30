"""Accounts, roles, sessions, consent and per-user activity. See docs/data-model.md."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, TimestampMixin, pg_enum
from app.models.enums import (
    AlertFrequency,
    ConsentKind,
    County,
    PropertyInterest,
    RemovalRelationship,
    RemovalRequestType,
    RemovalStatus,
    UserType,
    WishlistTargetKind,
)

GEN_UUID = sa.text("gen_random_uuid()")


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=GEN_UUID)


def user_fk(**kwargs: Any) -> Mapped[uuid.UUID]:
    return mapped_column(sa.ForeignKey("app_user.id", ondelete="CASCADE"), **kwargs)


class User(Base, TimestampMixin):
    # "user" is reserved in Postgres, hence app_user.
    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    password_hash: Mapped[str] = mapped_column(sa.Text, comment="argon2id")
    full_name: Mapped[str] = mapped_column(sa.Text)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.true())
    history_enabled: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.true())
    marketing_opt_in: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.false())
    last_login_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), comment="soft delete; hard purge after 30 days"
    )


class UserProfile(Base, TimestampMixin):
    """Optional sign-up preferences. Every field is optional."""

    __tablename__ = "user_profile"

    user_id: Mapped[uuid.UUID] = user_fk(primary_key=True)
    user_type: Mapped[UserType | None] = mapped_column(pg_enum(UserType, "user_type"))
    counties: Mapped[list[County] | None] = mapped_column(
        ARRAY(pg_enum(County, "county"), dimensions=1)
    )
    area_ids: Mapped[list[int] | None] = mapped_column(ARRAY(sa.BigInteger, dimensions=1))
    budget_min: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 2))
    budget_max: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 2))
    property_interest: Mapped[PropertyInterest | None] = mapped_column(
        pg_enum(PropertyInterest, "property_interest")
    )


class Role(Base):
    __tablename__ = "role"

    id: Mapped[int] = mapped_column(sa.SmallInteger, sa.Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(sa.Text, unique=True)


class Permission(Base):
    __tablename__ = "permission"

    id: Mapped[int] = mapped_column(sa.SmallInteger, sa.Identity(), primary_key=True)
    code: Mapped[str] = mapped_column(sa.Text, unique=True)


class UserRole(Base):
    __tablename__ = "user_role"

    user_id: Mapped[uuid.UUID] = user_fk(primary_key=True)
    role_id: Mapped[int] = mapped_column(
        sa.ForeignKey("role.id", ondelete="CASCADE"), primary_key=True
    )


class RolePermission(Base):
    __tablename__ = "role_permission"

    role_id: Mapped[int] = mapped_column(
        sa.ForeignKey("role.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[int] = mapped_column(
        sa.ForeignKey("permission.id", ondelete="CASCADE"), primary_key=True
    )


class UserSession(Base, CreatedAtMixin):
    """Opaque server-side session (D-008). Only a hash of the cookie value is stored."""

    __tablename__ = "user_session"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    token_hash: Mapped[str] = mapped_column(sa.CHAR(64), unique=True)
    user_id: Mapped[uuid.UUID] = user_fk(index=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), index=True)
    ip_hash: Mapped[str | None] = mapped_column(sa.CHAR(64))
    user_agent: Mapped[str | None] = mapped_column(sa.Text)


class EmailVerificationToken(Base, CreatedAtMixin):
    __tablename__ = "email_verification_token"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    user_id: Mapped[uuid.UUID] = user_fk(index=True)
    token_hash: Mapped[str] = mapped_column(sa.CHAR(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class PasswordResetToken(Base, CreatedAtMixin):
    __tablename__ = "password_reset_token"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    user_id: Mapped[uuid.UUID] = user_fk(index=True)
    token_hash: Mapped[str] = mapped_column(sa.CHAR(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class ConsentRecord(Base):
    """Append-only record of what was accepted, when, and which document version."""

    __tablename__ = "consent_record"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    user_id: Mapped[uuid.UUID] = user_fk(index=True)
    kind: Mapped[ConsentKind] = mapped_column(pg_enum(ConsentKind, "consent_kind"))
    document_version: Mapped[str] = mapped_column(sa.Text)
    granted: Mapped[bool] = mapped_column(sa.Boolean)
    recorded_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    ip_hash: Mapped[str | None] = mapped_column(sa.CHAR(64))
    user_agent: Mapped[str | None] = mapped_column(sa.Text)


class WishlistItem(Base, CreatedAtMixin):
    __tablename__ = "wishlist_item"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    user_id: Mapped[uuid.UUID] = user_fk()
    target_kind: Mapped[WishlistTargetKind] = mapped_column(
        pg_enum(WishlistTargetKind, "wishlist_target_kind")
    )
    property_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("property.id", ondelete="CASCADE")
    )
    area_id: Mapped[int | None] = mapped_column(sa.ForeignKey("area.id", ondelete="CASCADE"))
    note: Mapped[str | None] = mapped_column(sa.Text)

    __table_args__ = (
        sa.CheckConstraint(
            "(target_kind = 'property' AND property_id IS NOT NULL AND area_id IS NULL) OR "
            "(target_kind = 'area' AND area_id IS NOT NULL AND property_id IS NULL)",
            name="one_target",
        ),
        sa.CheckConstraint("char_length(note) <= 2000", name="note_length"),
        sa.UniqueConstraint(
            "user_id", "target_kind", "property_id", "area_id", postgresql_nulls_not_distinct=True
        ),
    )


class ViewHistory(Base):
    """Retention 12 months; nothing is written when history is off."""

    __tablename__ = "view_history"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    user_id: Mapped[uuid.UUID] = user_fk()
    property_id: Mapped[int] = mapped_column(sa.ForeignKey("property.id", ondelete="CASCADE"))
    viewed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )

    __table_args__ = (sa.Index("ix_view_history_user_id_viewed_at", "user_id", "viewed_at"),)


class SearchHistory(Base):
    __tablename__ = "search_history"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    user_id: Mapped[uuid.UUID] = user_fk()
    query: Mapped[dict[str, Any]] = mapped_column(JSONB)
    searched_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )

    __table_args__ = (sa.Index("ix_search_history_user_id_searched_at", "user_id", "searched_at"),)


class SavedSearch(Base, TimestampMixin):
    __tablename__ = "saved_search"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk(index=True)
    name: Mapped[str] = mapped_column(sa.Text)
    query: Mapped[dict[str, Any]] = mapped_column(JSONB)
    alert_frequency: Mapped[AlertFrequency] = mapped_column(
        pg_enum(AlertFrequency, "alert_frequency"), default=AlertFrequency.OFF
    )
    last_alerted_data_version: Mapped[str | None] = mapped_column(sa.Text)
    alerted_through_run_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, comment="PPR ingest run already checked; later runs' sales are new"
    )
    last_alerted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    __table_args__ = (sa.Index("ix_saved_search_alert_frequency", "alert_frequency"),)


class AlertDelivery(Base):
    __tablename__ = "alert_delivery"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    saved_search_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("saved_search.id", ondelete="CASCADE")
    )
    data_version: Mapped[str] = mapped_column(sa.Text)
    n_matches: Mapped[int] = mapped_column(sa.Integer)
    sent_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    status: Mapped[str] = mapped_column(sa.Text)

    __table_args__ = (sa.UniqueConstraint("saved_search_id", "data_version"),)


class ApiKey(Base, CreatedAtMixin):
    __tablename__ = "api_key"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    user_id: Mapped[uuid.UUID] = user_fk(index=True)
    prefix: Mapped[str] = mapped_column(sa.CHAR(8))
    key_hash: Mapped[str] = mapped_column(sa.CHAR(64), unique=True)
    name: Mapped[str] = mapped_column(sa.Text)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(sa.Text, dimensions=1))
    last_used_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class AuditLog(Base, CreatedAtMixin):
    """Append-only; a trigger in the initial migration blocks UPDATE and DELETE."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("app_user.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(sa.Text)
    target_kind: Mapped[str] = mapped_column(sa.Text)
    target_id: Mapped[str] = mapped_column(sa.Text)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip_hash: Mapped[str | None] = mapped_column(sa.CHAR(64))

    __table_args__ = (
        sa.Index("ix_audit_log_target_kind_target_id", "target_kind", "target_id"),
        sa.Index("ix_audit_log_actor_user_id_created_at", "actor_user_id", "created_at"),
    )


class RemovalRequest(Base, TimestampMixin):
    """Requester PII is deleted 12 months after closure."""

    __tablename__ = "removal_request"

    id: Mapped[uuid.UUID] = uuid_pk()
    property_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("property.id", ondelete="SET NULL"), index=True
    )
    submitted_address: Mapped[str] = mapped_column(sa.Text)
    requester_email: Mapped[str | None] = mapped_column(CITEXT)
    requester_relationship: Mapped[RemovalRelationship] = mapped_column(
        pg_enum(RemovalRelationship, "removal_relationship")
    )
    reason: Mapped[str | None] = mapped_column(sa.Text)
    request_type: Mapped[RemovalRequestType] = mapped_column(
        pg_enum(RemovalRequestType, "removal_request_type")
    )
    status: Mapped[RemovalStatus] = mapped_column(
        pg_enum(RemovalStatus, "removal_status"), default=RemovalStatus.NEW, index=True
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("app_user.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(sa.Text)
    closed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
