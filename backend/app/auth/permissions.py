"""Roles and permissions: the source of truth (docs/permissions.md must agree; a test checks).

Roles are additive except admin, which is separate; admins also hold the user role.
Sync to the database with `python -m app.cli sync-permissions` (idempotent).
"""

from enum import StrEnum
from typing import Final


class Role(StrEnum):
    ANONYMOUS = "anonymous"
    USER = "user"
    PRO = "pro"
    ADMIN = "admin"


class Perm(StrEnum):
    MAP_READ = "map:read"
    SEARCH_READ = "search:read"
    AREA_READ = "area:read"
    TOOLS_USE = "tools:use"
    REPORT_CREATE = "report:create"
    WISHLIST_WRITE = "wishlist:write"
    HISTORY_WRITE = "history:write"
    SAVED_SEARCH_WRITE = "saved_search:write"
    ALERT_RECEIVE = "alert:receive"
    EXPORT_CSV = "export:csv"
    API_KEY_MANAGE = "api_key:manage"
    API_ACCESS = "api:access"
    ANALYTICS_ADVANCED = "analytics:advanced"
    ADMIN_INGEST = "admin:ingest"
    ADMIN_GEOCODE = "admin:geocode"
    ADMIN_REMOVALS = "admin:removals"
    ADMIN_USERS = "admin:users"
    ADMIN_AUDIT = "admin:audit"


_PUBLIC: Final = frozenset(
    {Perm.MAP_READ, Perm.SEARCH_READ, Perm.AREA_READ, Perm.TOOLS_USE, Perm.REPORT_CREATE}
)
_USER: Final = _PUBLIC | {
    Perm.WISHLIST_WRITE,
    Perm.HISTORY_WRITE,
    Perm.SAVED_SEARCH_WRITE,
    Perm.ALERT_RECEIVE,
    Perm.EXPORT_CSV,
}
_ADMIN_ONLY: Final = frozenset(
    {
        Perm.ADMIN_INGEST,
        Perm.ADMIN_GEOCODE,
        Perm.ADMIN_REMOVALS,
        Perm.ADMIN_USERS,
        Perm.ADMIN_AUDIT,
    }
)

ROLE_PERMISSIONS: Final[dict[Role, frozenset[Perm]]] = {
    Role.ANONYMOUS: _PUBLIC,
    Role.USER: frozenset(_USER),
    Role.PRO: frozenset(_USER | {Perm.API_KEY_MANAGE, Perm.API_ACCESS, Perm.ANALYTICS_ADVANCED}),
    Role.ADMIN: frozenset(_USER | {Perm.ANALYTICS_ADVANCED} | _ADMIN_ONLY),
}

# Per-role limits referenced by docs/permissions.md. None = not allowed.
EXPORT_ROWS_PER_EXPORT: Final[dict[Role, int | None]] = {
    Role.ANONYMOUS: None,
    Role.USER: 500,
    Role.PRO: 50_000,
    Role.ADMIN: 50_000,
}
EXPORTS_PER_DAY: Final[dict[Role, int | None]] = {
    Role.ANONYMOUS: None,
    Role.USER: 10,
    Role.PRO: 100,
    Role.ADMIN: 100,
}


def permissions_for(roles: set[Role]) -> frozenset[Perm]:
    """Union of permissions; every caller (even signed out) gets the anonymous set."""
    granted: set[Perm] = set(ROLE_PERMISSIONS[Role.ANONYMOUS])
    for role in roles:
        granted |= ROLE_PERMISSIONS[role]
    return frozenset(granted)
