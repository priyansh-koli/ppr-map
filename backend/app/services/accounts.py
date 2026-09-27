"""Account reads shared by the auth and /me endpoints."""

import uuid
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import Role, permissions_for
from app.schemas.auth import Me, Profile

ME = """
SELECT u.id, u.email, u.full_name, u.email_verified_at IS NOT NULL, u.history_enabled,
       u.marketing_opt_in, u.created_at,
       coalesce(array_agg(r.name) FILTER (WHERE r.name IS NOT NULL), '{}') AS roles,
       p.user_type::text, p.counties::text[], p.budget_min, p.budget_max,
       p.property_interest::text
FROM app_user u
LEFT JOIN user_role ur ON ur.user_id = u.id
LEFT JOIN role r ON r.id = ur.role_id
LEFT JOIN user_profile p ON p.user_id = u.id
WHERE u.id = :u
GROUP BY u.id, p.user_id
"""


async def load_me(db: AsyncSession, user_id: uuid.UUID) -> Me:
    r = (await db.execute(sa.text(ME), {"u": user_id})).one()
    roles = {Role(x) for x in r[7] if x in Role.__members__.values()}
    return Me(
        id=str(r[0]),
        email=r[1],
        full_name=r[2],
        email_verified=r[3],
        history_enabled=r[4],
        marketing_opt_in=r[5],
        created_at=r[6],
        roles=sorted(roles),
        permissions=sorted(permissions_for(roles)),
        profile=Profile(
            user_type=r[8],
            counties=r[9],
            budget_min=r[10],
            budget_max=r[11],
            property_interest=r[12],
        ),
    )


# Every table that holds data about the user, with camelCase keys like the rest of the API.
# Hashes of secrets (password, session and key hashes) are left out: they are not the
# user's information and would only help an attacker. A property later withdrawn from the
# site (removal request) is listed without its address.
EXPORT_QUERIES = {
    "accountDetails": 'SELECT email_verified_at AS "emailVerifiedAt", '
    'last_login_at AS "lastLoginAt", deleted_at AS "closedAt", '
    'updated_at AS "updatedAt" FROM app_user WHERE id = :u',
    "profileAreas": "SELECT a.slug, a.name FROM user_profile p "
    "JOIN area a ON a.id = ANY(p.area_ids) WHERE p.user_id = :u ORDER BY a.name",
    "consents": 'SELECT kind::text, document_version AS "documentVersion", granted, '
    'recorded_at AS "recordedAt", ip_hash AS "ipHash", user_agent AS "userAgent" '
    "FROM consent_record WHERE user_id = :u ORDER BY recorded_at",
    "wishlist": "SELECT w.target_kind::text AS kind, "
    "CASE WHEN p.is_suppressed THEN NULL ELSE p.public_id END AS property, "
    "CASE WHEN p.is_suppressed THEN '(withdrawn from the site)' ELSE p.address_display END "
    'AS address, a.name AS area, w.note, w.created_at AS "createdAt" FROM wishlist_item w '
    "LEFT JOIN property p ON p.id = w.property_id LEFT JOIN area a ON a.id = w.area_id "
    "WHERE w.user_id = :u ORDER BY w.created_at",
    "viewHistory": "SELECT CASE WHEN p.is_suppressed THEN NULL ELSE p.public_id END AS property, "
    "CASE WHEN p.is_suppressed THEN '(withdrawn from the site)' ELSE p.address_display END "
    'AS address, v.viewed_at AS "viewedAt" '
    "FROM view_history v JOIN property p ON p.id = v.property_id WHERE v.user_id = :u "
    "AND v.viewed_at > now() - interval '365 days' ORDER BY v.viewed_at",
    "searchHistory": 'SELECT query, searched_at AS "searchedAt" FROM search_history '
    "WHERE user_id = :u ORDER BY searched_at",
    "savedSearches": 'SELECT name, query, alert_frequency::text AS "alertFrequency", '
    'created_at AS "createdAt" FROM saved_search WHERE user_id = :u ORDER BY created_at',
    "alertsSent": 'SELECT s.name AS "savedSearch", d.data_version AS "dataVersion", '
    'd.n_matches AS "matches", d.status, d.sent_at AS "sentAt" FROM alert_delivery d '
    "JOIN saved_search s ON s.id = d.saved_search_id WHERE s.user_id = :u ORDER BY d.sent_at",
    "sessions": 'SELECT created_at AS "createdAt", last_seen_at AS "lastSeenAt", '
    'expires_at AS "expiresAt", ip_hash AS "ipHash", user_agent AS "userAgent" '
    "FROM user_session WHERE user_id = :u AND expires_at > now() ORDER BY created_at",
    "apiKeys": 'SELECT name, prefix, scopes, created_at AS "createdAt", '
    'last_used_at AS "lastUsedAt", revoked_at AS "revokedAt" FROM api_key '
    "WHERE user_id = :u ORDER BY created_at",
    "auditEntries": 'SELECT action, target_kind AS "targetKind", target_id AS "targetId", '
    'created_at AS "createdAt" FROM audit_log WHERE actor_user_id = :u ORDER BY created_at',
}


async def export(db: AsyncSession, user_id: uuid.UUID) -> dict[str, Any]:
    """Everything stored about a user (GDPR access request), as plain JSON."""
    me = await load_me(db, user_id)
    out: dict[str, Any] = {"account": me.model_dump(mode="json", by_alias=True)}
    for key, sql in EXPORT_QUERIES.items():
        rows = (await db.execute(sa.text(sql), {"u": user_id})).mappings().all()
        out[key] = [{k: _json(v) for k, v in row.items()} for row in rows]
    return out


def _json(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, uuid.UUID | Decimal):
        return str(value)
    return value
