"""Correction and removal requests from the public (docs/api.md; D-052).

No account is needed. A hidden field catches simple bots: filled in, the request is answered
as if accepted and nothing is stored. Requests are limited per IP."""

from typing import Annotated, Literal

import sqlalchemy as sa
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import EmailStr, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require
from app.auth.permissions import Perm
from app.auth.ratelimit import limit
from app.auth.tokens import ip_hash
from app.db import get_session
from app.redis_client import get_redis
from app.schemas.base import ApiModel
from app.services import email as mail

router = APIRouter(tags=["reports"], dependencies=[Depends(require(Perm.REPORT_CREATE))])
Db = Annotated[AsyncSession, Depends(get_session)]
Cache = Annotated[Redis | None, Depends(get_redis)]
Mailer = Annotated[mail.Mailer, Depends(mail.get_mailer)]
PER_HOUR = 5


class ReportIn(ApiModel):
    property_id: str | None = Field(None, max_length=64)
    address: str = Field(min_length=3, max_length=300)
    request_type: Literal["suppress_display", "correct_location", "correct_details"]
    relationship: Literal["owner", "occupant", "other"]
    reason: str | None = Field(None, max_length=2000)
    email: EmailStr | None = None
    website: str | None = Field(None, description="Leave empty (a trap for bots)")


class ReportAccepted(ApiModel):
    reference: str


@router.post("/reports", status_code=202, response_model=ReportAccepted)
async def report(
    body: ReportIn,
    request: Request,
    db: Db,
    cache: Cache,
    mailer: Mailer,
    background: BackgroundTasks,
) -> ReportAccepted:
    """Ask for an address to stop being shown, or for a location or detail to be corrected.
    The answer is the same whether or not the property exists."""
    ip = request.client.host if request.client else "unknown"
    await limit(cache, f"report:{ip_hash(ip)}", PER_HOUR, 3600)
    if body.website:
        return ReportAccepted(reference="R-00000000")
    property_row = None
    if body.property_id:
        property_row = (
            await db.execute(
                sa.text("SELECT id FROM property WHERE public_id = :p"), {"p": body.property_id}
            )
        ).one_or_none()
        if property_row is None:
            raise HTTPException(404, "No such property")
    rid: object = (
        await db.execute(
            sa.text(
                "INSERT INTO removal_request (property_id, submitted_address, requester_email, "
                "requester_relationship, reason, request_type, status) VALUES (:p, :a, :e, "
                "CAST(:rel AS removal_relationship), :r, CAST(:t AS removal_request_type), "
                "'new') "
                "RETURNING id"
            ),
            {
                "p": property_row[0] if property_row else None,
                "a": body.address.strip(),
                "e": body.email,
                "rel": body.relationship,
                "r": body.reason,
                "t": body.request_type,
            },
        )
    ).scalar_one()
    await db.commit()
    reference = reference_of(rid)
    if body.email:
        background.add_task(
            mailer.send,
            mail.report_received(body.email, reference, body.request_type, body.address.strip()),
        )
    return ReportAccepted(reference=reference)


def reference_of(request_id: object) -> str:
    return f"R-{str(request_id)[:8].upper()}"
