"""audit_log: block TRUNCATE as well (P2 #42)

The append-only trigger fires for each row on UPDATE and DELETE, and TRUNCATE fires no row
triggers, so the table owner could still empty it in one statement (a `TRUNCATE app_user
CASCADE` would too). A statement trigger now refuses it. The service roles cannot truncate
it anyway (migration 0014); this covers the owner, short of disabling the trigger.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-04 23:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The function only looks at OLD and NEW for an UPDATE, so it serves TRUNCATE as it is.
    op.execute(
        "CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log "
        "FOR EACH STATEMENT EXECUTE FUNCTION audit_log_block_changes()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER audit_log_no_truncate ON audit_log")
