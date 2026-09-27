"""audit_log: let a purged account's actor id become NULL (D-041)

The append-only trigger also blocked the `ON DELETE SET NULL` of `actor_user_id`, so
`app.cli purge-deleted` failed for any account with an audit entry. The trigger now allows
exactly that one change and still blocks every other UPDATE and every DELETE.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-27 20:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ALLOW_ACTOR_PURGE = """
CREATE OR REPLACE FUNCTION audit_log_block_changes() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.actor_user_id IS NOT NULL AND NEW.actor_user_id IS NULL
       AND to_jsonb(NEW) - 'actor_user_id' = to_jsonb(OLD) - 'actor_user_id' THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'audit_log is append-only';
END;
$$;
"""

BLOCK_ALL = """
CREATE OR REPLACE FUNCTION audit_log_block_changes() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only';
END;
$$;
"""


def upgrade() -> None:
    op.execute(ALLOW_ACTOR_PURGE)


def downgrade() -> None:
    op.execute(BLOCK_ALL)
