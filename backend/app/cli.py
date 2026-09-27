"""Management commands: `python -m app.cli --help`."""

import json

import sqlalchemy as sa
import typer
from sqlalchemy.dialects.postgresql import insert

from app.auth.permissions import ROLE_PERMISSIONS, Perm, Role
from app.config import get_settings
from app.models.users import Permission, RolePermission
from app.models.users import Role as RoleRow

cli = typer.Typer(no_args_is_help=True)


@cli.callback()
def main() -> None:
    """PPR Map backend management commands."""


@cli.command("sync-permissions")
def sync_permissions() -> None:
    """Upsert roles, permissions and the role-permission matrix from app/auth/permissions.py."""
    # The anonymous role is implicit (never assigned to a user) and is not stored.
    stored_roles = [r for r in Role if r is not Role.ANONYMOUS]
    engine = sa.create_engine(get_settings().database_url)
    with engine.begin() as conn:
        conn.execute(
            insert(RoleRow)
            .values([{"name": r.value} for r in stored_roles])
            .on_conflict_do_nothing()
        )
        conn.execute(
            insert(Permission).values([{"code": p.value} for p in Perm]).on_conflict_do_nothing()
        )
        role_ids = {name: id_ for name, id_ in conn.execute(sa.select(RoleRow.name, RoleRow.id))}
        perm_ids = {
            code: id_ for code, id_ in conn.execute(sa.select(Permission.code, Permission.id))
        }
        wanted = {
            (role_ids[r.value], perm_ids[p.value])
            for r in stored_roles
            for p in ROLE_PERMISSIONS[r]
        }
        existing = {
            (role_id, perm_id)
            for role_id, perm_id in conn.execute(
                sa.select(RolePermission.role_id, RolePermission.permission_id)
            )
        }
        for role_id, perm_id in existing - wanted:
            conn.execute(
                sa.delete(RolePermission).where(
                    RolePermission.role_id == role_id, RolePermission.permission_id == perm_id
                )
            )
        if missing := wanted - existing:
            conn.execute(
                insert(RolePermission).values(
                    [{"role_id": r, "permission_id": p} for r, p in sorted(missing)]
                )
            )
    typer.echo(f"Synced {len(stored_roles)} roles, {len(Perm)} permissions, {len(wanted)} grants.")


# Daily housekeeping (D-041): what is past its retention period, as (label, statement).
EXPIRED = [
    (
        "expired sessions",
        "DELETE FROM user_session WHERE expires_at < now() OR last_seen_at < now() - :idle",
    ),
    (
        "used or expired email links",
        "DELETE FROM email_verification_token WHERE used_at IS NOT NULL OR expires_at < now()",
    ),
    (
        "used or expired reset links",
        "DELETE FROM password_reset_token WHERE used_at IS NOT NULL OR expires_at < now()",
    ),
    ("views older than 12 months", "DELETE FROM view_history WHERE viewed_at < now() - :keep"),
]


@cli.command("purge-deleted")
def purge_deleted(days: int = 30) -> None:
    """Daily: delete accounts closed more than `days` ago, with everything they own (cascade),
    and everything else past its retention period (sessions, email links, view history)."""
    from app.api.v1.me import HISTORY_KEEP
    from app.auth.sessions import IDLE

    engine = sa.create_engine(get_settings().database_url)
    with engine.begin() as conn:
        n = conn.execute(
            sa.text(
                "DELETE FROM app_user WHERE deleted_at IS NOT NULL "
                "AND deleted_at < now() - make_interval(days => :d)"
            ),
            {"d": days},
        ).rowcount
        typer.echo(f"Purged {n} closed accounts.")
        for label, sql in EXPIRED:
            n = conn.execute(sa.text(sql), {"idle": IDLE, "keep": HISTORY_KEEP}).rowcount
            typer.echo(f"Purged {n} {label}.")


@cli.command("openapi")
def openapi() -> None:
    """Print the OpenAPI schema; `make api-types` writes it to frontend/openapi.json."""
    from app.main import create_app

    typer.echo(json.dumps(create_app().openapi(), indent=2, sort_keys=True))


if __name__ == "__main__":
    cli()
