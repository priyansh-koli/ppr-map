"""The append-only audit log (docs/data-model.md): every admin write records who did what,
to what, and the values before and after. Personal data about third parties (a requester's
email or reason) is never copied into it."""

import json
import uuid
from typing import Any

import sqlalchemy as sa
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import ip_hash


async def record(
    db: AsyncSession,
    request: Request,
    actor: uuid.UUID,
    action: str,
    target_kind: str,
    target_id: object,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    """Add an entry in the caller's transaction, so it commits (or not) with the change."""
    ip = request.client.host if request.client else None
    await db.execute(
        sa.text(
            "INSERT INTO audit_log (actor_user_id, action, target_kind, target_id, before, "
            "after, ip_hash) VALUES (:a, :action, :kind, :tid, CAST(:before AS jsonb), "
            "CAST(:after AS jsonb), :ip)"
        ),
        {
            "a": actor,
            "action": action,
            "kind": target_kind,
            "tid": str(target_id),
            "before": json.dumps(before, default=str) if before is not None else None,
            "after": json.dumps(after, default=str) if after is not None else None,
            "ip": ip_hash(ip),
        },
    )
