"""Admin: ingest runs, geocode corrections, removal requests, users and the audit log
(docs/api.md, Admin; D-052). Each endpoint needs its own `admin:*` permission, and every
write adds an audit-log entry in the same transaction."""

import contextlib
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

import sqlalchemy as sa
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app import jobs
from app.api.v1.properties import _meta
from app.api.v1.reports import reference_of
from app.auth.deps import require
from app.auth.passwords import verify_password
from app.auth.permissions import Perm, Role
from app.auth.sessions import CurrentUser, forget_cached_user, revoke_sessions
from app.db import get_session
from app.redis_client import REDIS_ERRORS, get_redis
from app.schemas.base import ApiModel
from app.schemas.search import Page
from app.services import audit
from app.services import email as mail

router = APIRouter(prefix="/admin", tags=["admin"])

Db = Annotated[AsyncSession, Depends(get_session)]
Cache = Annotated[Redis | None, Depends(get_redis)]
Mailer = Annotated[mail.Mailer, Depends(mail.get_mailer)]
IngestAdmin = Annotated[CurrentUser, Depends(require(Perm.ADMIN_INGEST))]
GeocodeAdmin = Annotated[CurrentUser, Depends(require(Perm.ADMIN_GEOCODE))]
RemovalsAdmin = Annotated[CurrentUser, Depends(require(Perm.ADMIN_REMOVALS))]
UsersAdmin = Annotated[CurrentUser, Depends(require(Perm.ADMIN_USERS))]
AuditAdmin = Annotated[CurrentUser, Depends(require(Perm.ADMIN_AUDIT))]
PageNo = Annotated[int, Query(ge=1, le=10_000)]
PageSize = Annotated[int, Query(alias="pageSize", ge=1, le=100)]
NOT_FOUND = HTTPException(404, "Not found")


def _offset(page: int, size: int) -> dict[str, int]:
    return {"limit": size, "offset": (page - 1) * size}


# --- overview -----------------------------------------------------------------------------


class AdminOverview(ApiModel):
    users: int
    unverified_users: int
    open_requests: int
    low_confidence_properties: int
    routing_key_conflicts: int
    last_runs: list[dict[str, Any]]
    data_version: str | None


@router.get("/overview", response_model=AdminOverview)
async def overview(
    user: Annotated[CurrentUser, Depends(require(Perm.ADMIN_AUDIT))], db: Db
) -> AdminOverview:
    row = (
        await db.execute(
            sa.text(
                "SELECT (SELECT count(*) FROM app_user WHERE deleted_at IS NULL), "
                "(SELECT count(*) FROM app_user WHERE deleted_at IS NULL "
                " AND email_verified_at IS NULL), "
                "(SELECT count(*) FROM removal_request WHERE status IN ('new', 'in_review')), "
                "(SELECT count(*) FROM property WHERE geocode_confidence IN "
                " ('routing_key', 'county', 'unmatched')), "
                "(SELECT count(DISTINCT property_id) FROM geocode_attempt "
                " WHERE method = 'check:routing_key')"
            )
        )
    ).one()
    runs = (
        (
            await db.execute(
                sa.text(
                    "SELECT DISTINCT ON (kind) kind::text, id, status::text, started_at, "
                    "finished_at FROM ingest_run ORDER BY kind, id DESC"
                )
            )
        )
        .mappings()
        .all()
    )
    version = None
    with contextlib.suppress(HTTPException):
        version = (await _meta(db)).data_version
    return AdminOverview(
        users=row[0],
        unverified_users=row[1],
        open_requests=row[2],
        low_confidence_properties=row[3],
        routing_key_conflicts=row[4],
        last_runs=[dict(r) for r in runs],
        data_version=version,
    )


# --- ingest runs --------------------------------------------------------------------------


class IngestRunOut(ApiModel):
    id: int
    kind: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    source_url: str | None
    rows_read: int
    rows_inserted: int
    rows_withdrawn: int
    rows_failed: int
    stats: dict[str, Any]
    triggered_by: str | None


class RowError(ApiModel):
    line_no: int
    raw_line: str
    error: str


class IngestRunDetail(IngestRunOut):
    row_errors: list[RowError]


class RunRequest(ApiModel):
    step: Literal["ppr", "gazetteer", "geocode", "enrich", "aggregate", "monthly"]


class Job(ApiModel):
    id: str
    status: str
    description: str | None = None
    enqueued_at: str | None = None
    ended_at: str | None = None


RUNS = """
SELECT r.id, r.kind::text, r.status::text, r.started_at, r.finished_at, r.source_url,
       r.rows_read, r.rows_inserted, r.rows_withdrawn, r.rows_failed, r.stats, u.email
FROM ingest_run r LEFT JOIN app_user u ON u.id = r.triggered_by
WHERE (CAST(:kind AS text) IS NULL OR r.kind::text = :kind) {extra}
ORDER BY r.id DESC
"""


def _run(r: Any) -> IngestRunOut:
    return IngestRunOut(
        id=r[0],
        kind=r[1],
        status=r[2],
        started_at=r[3],
        finished_at=r[4],
        source_url=r[5],
        rows_read=r[6],
        rows_inserted=r[7],
        rows_withdrawn=r[8],
        rows_failed=r[9],
        stats=r[10] or {},
        triggered_by=r[11],
    )


@router.get("/ingest-runs", response_model=Page[IngestRunOut])
async def ingest_runs(
    user: IngestAdmin, db: Db, kind: str | None = None, page: PageNo = 1, page_size: PageSize = 50
) -> Page[IngestRunOut]:
    """Every pipeline run, newest first: rows read, loaded and failed, and each step's stats
    (a geocode run's `stats.confidence` is its success by confidence level)."""
    total: int = (
        await db.execute(
            sa.text(
                "SELECT count(*) FROM ingest_run "
                "WHERE CAST(:kind AS text) IS NULL OR kind::text = :kind"
            ),
            {"kind": kind},
        )
    ).scalar_one()
    rows = (
        await db.execute(
            sa.text(RUNS.format(extra="") + " LIMIT :limit OFFSET :offset"),
            {"kind": kind, **_offset(page, page_size)},
        )
    ).all()
    return Page[IngestRunOut](
        items=[_run(r) for r in rows], total=total, page=page, page_size=page_size
    )


@router.get("/ingest-runs/{run_id}", response_model=IngestRunDetail)
async def ingest_run(run_id: int, user: IngestAdmin, db: Db) -> IngestRunDetail:
    row = (
        await db.execute(sa.text(RUNS.format(extra="AND r.id = :id")), {"kind": None, "id": run_id})
    ).one_or_none()
    if row is None:
        raise NOT_FOUND
    errors = (
        await db.execute(
            sa.text(
                "SELECT line_no, raw_line, error FROM ingest_row_error "
                "WHERE ingest_run_id = :id ORDER BY line_no LIMIT 200"
            ),
            {"id": run_id},
        )
    ).all()
    return IngestRunDetail(
        **_run(row).model_dump(),
        row_errors=[RowError(line_no=e[0], raw_line=e[1], error=e[2]) for e in errors],
    )


@router.post("/ingest-runs", status_code=202, response_model=Job)
async def start_run(body: RunRequest, request: Request, user: IngestAdmin, db: Db) -> Job:
    """Queue a pipeline step (or `monthly`, all of them) for the worker (D-051)."""
    try:
        job = await run_in_threadpool(jobs.enqueue_pipeline, body.step, str(user.id))
    except REDIS_ERRORS as exc:
        raise HTTPException(503, "The job queue is not available") from exc
    await audit.record(
        db, request, user.id, "ingest.queue", "job", job.id, after={"step": body.step}
    )
    await db.commit()
    return Job(id=job.id, status="queued", description=job.description)


@router.get("/jobs", response_model=list[Job])
async def recent_jobs(user: IngestAdmin) -> list[Job]:
    try:
        found = await run_in_threadpool(jobs.recent_jobs)
    except REDIS_ERRORS as exc:
        raise HTTPException(503, "The job queue is not available") from exc
    return [Job.model_validate(j) for j in found]


# --- geocode review -----------------------------------------------------------------------


class QueueItem(ApiModel):
    id: str
    address: str
    county: str
    confidence: str
    method: str | None
    lat: float | None
    lng: float | None
    locked: bool
    latest_sale: str | None
    n_sales: int
    conflict_m: int | None = Field(None, description="Distance from its routing key's median")


class GeocodeFix(ApiModel):
    lat: float = Field(ge=51.2, le=55.5)
    lng: float = Field(ge=-10.8, le=-5.3)
    confidence: Literal["exact", "street", "locality"]
    note: str = Field(min_length=3, max_length=500)


class GeocodeFixed(ApiModel):
    id: str
    confidence: str
    in_reported_county: bool
    areas: list[str]


QUEUE = """
SELECT p.public_id, p.address_display, p.county::text, p.geocode_confidence::text,
       p.geocode_method, ST_Y(p.geom), ST_X(p.geom), p.geocode_locked,
       (SELECT max(s.sale_date)::text FROM sale s WHERE s.property_id = p.id),
       (SELECT count(*) FROM sale s WHERE s.property_id = p.id),
       c.distance_m, count(*) OVER ()
FROM property p
LEFT JOIN LATERAL (
    SELECT round(ST_Distance(p.geom::geography, g.candidate_geom::geography))::int AS distance_m
    FROM geocode_attempt g
    WHERE g.property_id = p.id AND g.method = 'check:routing_key'
    ORDER BY g.id DESC LIMIT 1
) c ON true
WHERE NOT p.is_suppressed
  AND (CAST(:county AS text) IS NULL OR p.county::text = :county)
  AND {which}
ORDER BY (SELECT max(s.sale_date) FROM sale s WHERE s.property_id = p.id) DESC NULLS LAST, p.id
LIMIT :limit OFFSET :offset
"""
WHICH = {
    "conflict": "c.distance_m IS NOT NULL",
    "low": "p.geocode_confidence IN ('routing_key', 'county', 'unmatched')",
    "locality": "p.geocode_confidence = 'locality'",
    "locked": "p.geocode_locked",
}


@router.get("/geocode/queue", response_model=Page[QueueItem])
async def geocode_queue(
    user: GeocodeAdmin,
    db: Db,
    kind: Literal["conflict", "low", "locality", "locked"] = "conflict",
    county: str | None = Query(None, pattern=r"^[a-z]+$"),
    page: PageNo = 1,
    page_size: PageSize = 50,
) -> Page[QueueItem]:
    """Properties to check, most recently sold first: `conflict` (a precise point far from
    its Eircode routing key, D-035), `low` (placed only by routing key or county, or not at
    all), `locality` (town or townland), `locked` (already corrected by hand)."""
    rows = (
        await db.execute(
            sa.text(QUEUE.format(which=WHICH[kind])),
            {"county": county, **_offset(page, page_size)},
        )
    ).all()
    return Page[QueueItem](
        items=[
            QueueItem(
                id=r[0],
                address=r[1],
                county=r[2],
                confidence=r[3],
                method=r[4],
                lat=r[5],
                lng=r[6],
                locked=r[7],
                latest_sale=r[8],
                n_sales=r[9],
                conflict_m=r[10],
            )
            for r in rows
        ],
        total=rows[0][11] if rows else 0,
        page=page,
        page_size=page_size,
    )


# Point-in-polygon on the ITM pieces (area_part), as the pipeline joins them (D-033, D-035):
# Small Area and ED only for exact and street points.
FIX = """
WITH pt AS (SELECT ST_SetSRID(ST_MakePoint(:lng, :lat), 4326) AS g,
                   ST_Transform(ST_SetSRID(ST_MakePoint(:lng, :lat), 4326), 2157) AS itm),
hit AS (
    SELECT ap.kind::text AS kind, min(ap.area_id) AS area_id
    FROM area_part ap, pt WHERE ST_Contains(ap.geom, pt.itm) GROUP BY ap.kind
)
UPDATE property p SET
    geom = pt.g, geocode_confidence = CAST(:conf AS geocode_confidence),
    geocode_method = 'admin:manual', geocode_source = 'correction by an administrator',
    geocoded_at = now(), geocode_locked = true, updated_at = now(),
    small_area_id = CASE WHEN :precise THEN (SELECT area_id FROM hit WHERE kind = 'small_area') END,
    ed_id = CASE WHEN :precise THEN (SELECT area_id FROM hit WHERE kind = 'electoral_division') END,
    townland_id = (SELECT area_id FROM hit WHERE kind = 'townland'),
    settlement_id = (SELECT area_id FROM hit WHERE kind = 'settlement'),
    h3_r8 = NULL
FROM pt WHERE p.public_id = :id
RETURNING p.id,
    EXISTS (SELECT 1 FROM hit JOIN area a ON a.id = hit.area_id
            WHERE hit.kind = 'county' AND a.code = p.county::text),
    (SELECT array_agg(a.name || ' (' || hit.kind || ')' ORDER BY hit.kind)
     FROM hit JOIN area a ON a.id = hit.area_id)
"""


@router.put("/properties/{property_id}/geocode", response_model=GeocodeFixed)
async def fix_geocode(
    property_id: str, body: GeocodeFix, request: Request, user: GeocodeAdmin, db: Db, cache: Cache
) -> GeocodeFixed:
    """Place a property by hand and lock it, so later geocoding runs leave it alone. Its
    hover card shows the new precision at once; distances and the map's price hexes follow
    at the next monthly run."""
    before = (
        await db.execute(
            sa.text(
                "SELECT ST_Y(geom), ST_X(geom), geocode_confidence::text, geocode_method, "
                "geocode_locked FROM property WHERE public_id = :id"
            ),
            {"id": property_id},
        )
    ).one_or_none()
    if before is None:
        raise NOT_FOUND
    row = (
        await db.execute(
            sa.text(FIX),
            {
                "lat": body.lat,
                "lng": body.lng,
                "conf": body.confidence,
                "precise": body.confidence in ("exact", "street"),
                "id": property_id,
            },
        )
    ).one()
    await db.execute(
        sa.text(
            "INSERT INTO geocode_attempt (property_id, step, method, query, candidate_geom, "
            "candidate_type, confidence, accepted) VALUES (:pid, 99, 'admin', :note, "
            "ST_SetSRID(ST_MakePoint(:lng, :lat), 4326), 'manual', "
            "CAST(:conf AS geocode_confidence), true)"
        ),
        {
            "pid": row[0],
            "note": body.note,
            "lat": body.lat,
            "lng": body.lng,
            "conf": body.confidence,
        },
    )
    await db.execute(
        sa.text(
            "UPDATE property_summary SET payload = jsonb_set(payload, '{confidence}', "
            "to_jsonb(CAST(:conf AS text))) WHERE property_id = :pid"
        ),
        {"conf": body.confidence, "pid": row[0]},
    )
    await audit.record(
        db,
        request,
        user.id,
        "property.geocode.correct",
        "property",
        property_id,
        before={"lat": before[0], "lng": before[1], "confidence": before[2], "method": before[3]},
        after={"lat": body.lat, "lng": body.lng, "confidence": body.confidence, "note": body.note},
    )
    await db.commit()
    await _forget_summary(db, cache, property_id)
    return GeocodeFixed(
        id=property_id, confidence=body.confidence, in_reported_county=row[1], areas=row[2] or []
    )


async def _forget_summary(db: AsyncSession, cache: Redis | None, property_id: str) -> None:
    if cache is None:
        return
    with contextlib.suppress(HTTPException, *REDIS_ERRORS):
        await cache.delete(f"summary:{property_id}:{(await _meta(db)).data_version}")


# --- removal and correction requests ------------------------------------------------------


class RemovalOut(ApiModel):
    id: uuid.UUID
    reference: str
    property_id: str | None
    property_address: str | None
    property_suppressed: bool | None
    submitted_address: str
    requester_email: str | None
    relationship: str
    reason: str | None
    request_type: str
    status: str
    created_at: datetime
    decided_by: str | None
    decided_at: datetime | None
    decision_note: str | None


class RemovalDecision(ApiModel):
    status: Literal["in_review", "approved", "rejected"]
    decision_note: str | None = Field(None, max_length=2000)


REMOVALS = """
SELECT r.id, p.public_id, p.address_display, p.is_suppressed, r.submitted_address,
       r.requester_email, r.requester_relationship::text, r.reason, r.request_type::text,
       r.status::text, r.created_at, u.email, r.decided_at, r.decision_note,
       count(*) OVER ()
FROM removal_request r
LEFT JOIN property p ON p.id = r.property_id
LEFT JOIN app_user u ON u.id = r.decided_by
WHERE {where}
ORDER BY r.created_at DESC, r.id
LIMIT :limit OFFSET :offset
"""


def _removal(r: Any) -> RemovalOut:
    return RemovalOut(
        id=r[0],
        reference=reference_of(r[0]),
        property_id=r[1],
        property_address=r[2],
        property_suppressed=r[3],
        submitted_address=r[4],
        requester_email=r[5],
        relationship=r[6],
        reason=r[7],
        request_type=r[8],
        status=r[9],
        created_at=r[10],
        decided_by=r[11],
        decided_at=r[12],
        decision_note=r[13],
    )


@router.get("/removal-requests", response_model=Page[RemovalOut])
async def removal_requests(
    user: RemovalsAdmin,
    db: Db,
    status: Literal[
        "open", "new", "in_review", "approved", "rejected", "withdrawn", "all"
    ] = "open",
    page: PageNo = 1,
    page_size: PageSize = 50,
) -> Page[RemovalOut]:
    where = {
        "open": "r.status IN ('new', 'in_review')",
        "all": "true",
    }.get(status, "r.status = CAST(:status AS removal_status)")
    rows = (
        await db.execute(
            sa.text(REMOVALS.format(where=where)), {"status": status, **_offset(page, page_size)}
        )
    ).all()
    return Page[RemovalOut](
        items=[_removal(r) for r in rows],
        total=rows[0][14] if rows else 0,
        page=page,
        page_size=page_size,
    )


@router.patch("/removal-requests/{request_id}", response_model=RemovalOut)
async def decide_removal(
    request_id: uuid.UUID,
    body: RemovalDecision,
    request: Request,
    user: RemovalsAdmin,
    db: Db,
    cache: Cache,
    mailer: Mailer,
    background: BackgroundTasks,
) -> RemovalOut:
    """Take a request into review, or decide it. Approving a request to stop showing an
    address hides the property from the map, search, lists and pages at once (its sales
    stay in area figures). A decided request cannot be changed; the requester is emailed."""
    current = (
        await db.execute(
            sa.text(
                "SELECT r.status::text, r.request_type::text, p.public_id, r.requester_email "
                "FROM removal_request r LEFT JOIN property p ON p.id = r.property_id "
                "WHERE r.id = :id FOR UPDATE OF r"
            ),
            {"id": request_id},
        )
    ).one_or_none()
    if current is None:
        raise NOT_FOUND
    status, kind, public_id, email = current
    if status in ("approved", "rejected", "withdrawn"):
        raise HTTPException(409, f"This request is already {status}")
    closing = body.status in ("approved", "rejected")
    await db.execute(
        sa.text(
            "UPDATE removal_request SET status = CAST(:s AS removal_status), "
            "decision_note = coalesce(:note, decision_note), updated_at = now(), "
            "decided_by = CASE WHEN :closing THEN CAST(:u AS uuid) ELSE decided_by END, "
            "decided_at = CASE WHEN :closing THEN now() ELSE decided_at END, "
            "closed_at = CASE WHEN :closing THEN now() ELSE closed_at END WHERE id = :id"
        ),
        {
            "s": body.status,
            "note": body.decision_note,
            "closing": closing,
            "u": user.id,
            "id": request_id,
        },
    )
    suppressed = body.status == "approved" and kind == "suppress_display" and public_id
    if suppressed:
        await db.execute(
            sa.text(
                "UPDATE property SET is_suppressed = true, updated_at = now() WHERE public_id = :p"
            ),
            {"p": public_id},
        )
    await audit.record(
        db,
        request,
        user.id,
        f"removal.{body.status}",
        "removal_request",
        request_id,
        before={"status": status},
        after={"status": body.status, "propertyHidden": bool(suppressed)},
    )
    await db.commit()
    if suppressed:
        await _forget_summary(db, cache, public_id)
    if closing and email:
        background.add_task(
            mailer.send,
            mail.report_decided(
                email, reference_of(request_id), body.status == "approved", body.decision_note
            ),
        )
    row = (
        await db.execute(
            sa.text(REMOVALS.format(where="r.id = :id")),
            {"id": request_id, "limit": 1, "offset": 0},
        )
    ).one()
    return _removal(row)


# --- users --------------------------------------------------------------------------------


class AdminUser(ApiModel):
    id: uuid.UUID
    email: str
    full_name: str
    roles: list[str]
    email_verified: bool
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None
    closed_at: datetime | None


class UserChange(ApiModel):
    is_active: bool | None = None
    roles: list[Literal["user", "pro", "admin"]] | None = None
    password: str | None = Field(
        None, max_length=128, description="Your own password: needed to change roles"
    )


USERS = """
SELECT u.id, u.email, u.full_name,
       coalesce(array_agg(r.name ORDER BY r.name) FILTER (WHERE r.name IS NOT NULL), '{{}}'),
       u.email_verified_at IS NOT NULL, u.is_active, u.created_at, u.last_login_at,
       u.deleted_at, count(*) OVER ()
FROM app_user u
LEFT JOIN user_role ur ON ur.user_id = u.id
LEFT JOIN role r ON r.id = ur.role_id
WHERE {where}
GROUP BY u.id
ORDER BY u.created_at DESC, u.id
LIMIT :limit OFFSET :offset
"""


def _user(r: Any) -> AdminUser:
    return AdminUser(
        id=r[0],
        email=r[1],
        full_name=r[2],
        roles=list(r[3]),
        email_verified=r[4],
        is_active=r[5],
        created_at=r[6],
        last_login_at=r[7],
        closed_at=r[8],
    )


@router.get("/users", response_model=Page[AdminUser])
async def users(
    user: UsersAdmin,
    db: Db,
    q: Annotated[str | None, Query(max_length=100)] = None,
    page: PageNo = 1,
    page_size: PageSize = 50,
) -> Page[AdminUser]:
    where = "(CAST(:q AS text) IS NULL OR u.email ILIKE :like OR u.full_name ILIKE :like)"
    like = f"%{q.replace('%', '').replace('_', '')}%" if q else None
    rows = (
        await db.execute(
            sa.text(USERS.format(where=where)), {"q": q, "like": like, **_offset(page, page_size)}
        )
    ).all()
    return Page[AdminUser](
        items=[_user(r) for r in rows],
        total=rows[0][9] if rows else 0,
        page=page,
        page_size=page_size,
    )


@router.patch("/users/{user_id}", response_model=AdminUser)
async def change_user(
    user_id: uuid.UUID, body: UserChange, request: Request, user: UsersAdmin, db: Db, cache: Cache
) -> AdminUser:
    """Activate or deactivate an account, or change its roles. A role change needs your own
    password again. Nobody can deactivate themselves, and the last active admin cannot lose
    the role. Deactivating signs the account out everywhere."""
    target = (
        await db.execute(
            sa.text(USERS.format(where="u.id = :id")), {"id": user_id, "limit": 1, "offset": 0}
        )
    ).one_or_none()
    if target is None:
        raise NOT_FOUND
    before = _user(target)
    after: dict[str, Any] = {}
    if body.roles is not None:
        if not body.password:
            raise HTTPException(403, "Enter your password to change roles")
        hash_: str = (
            await db.execute(
                sa.text("SELECT password_hash FROM app_user WHERE id = :u"), {"u": user.id}
            )
        ).scalar_one()
        if not await verify_password(hash_, body.password):
            raise HTTPException(403, "The password is wrong")
        roles = sorted({*body.roles, Role.USER.value})  # everyone keeps the user role
        if "admin" in before.roles and "admin" not in roles:
            await _keep_an_admin(db, user_id)
        await db.execute(sa.text("DELETE FROM user_role WHERE user_id = :u"), {"u": user_id})
        await db.execute(
            sa.text(
                "INSERT INTO user_role (user_id, role_id) SELECT :u, id FROM role "
                "WHERE name = ANY(:roles)"
            ),
            {"u": user_id, "roles": roles},
        )
        after["roles"] = roles
    if body.is_active is not None and body.is_active != before.is_active:
        if user_id == user.id:
            raise HTTPException(409, "You cannot deactivate your own account")
        if not body.is_active and "admin" in before.roles:
            await _keep_an_admin(db, user_id)
        await db.execute(
            sa.text("UPDATE app_user SET is_active = :a, updated_at = now() WHERE id = :u"),
            {"a": body.is_active, "u": user_id},
        )
        after["isActive"] = body.is_active
    if after:
        await audit.record(
            db,
            request,
            user.id,
            "user.change",
            "user",
            user_id,
            before={k: getattr(before, "is_active" if k == "isActive" else k) for k in after},
            after=after,
        )
    await db.commit()
    if after.get("isActive") is False:
        await revoke_sessions(db, cache, user_id)
    elif "roles" in after:
        await forget_cached_user(cache, db, user_id)
    row = (
        await db.execute(
            sa.text(USERS.format(where="u.id = :id")), {"id": user_id, "limit": 1, "offset": 0}
        )
    ).one()
    return _user(row)


async def _keep_an_admin(db: AsyncSession, losing: uuid.UUID) -> None:
    others: int = (
        await db.execute(
            sa.text(
                "SELECT count(*) FROM user_role ur JOIN role r ON r.id = ur.role_id "
                "JOIN app_user u ON u.id = ur.user_id WHERE r.name = 'admin' "
                "AND u.is_active AND u.deleted_at IS NULL AND u.id <> :u"
            ),
            {"u": losing},
        )
    ).scalar_one()
    if not others:
        raise HTTPException(409, "There must always be at least one active admin")


# --- audit log ----------------------------------------------------------------------------


class AuditEntry(ApiModel):
    id: int
    actor: str | None
    action: str
    target_kind: str
    target_id: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    created_at: datetime


@router.get("/audit-log", response_model=Page[AuditEntry])
async def audit_log(
    user: AuditAdmin,
    db: Db,
    actor: Annotated[str | None, Query(max_length=200, description="Email address")] = None,
    target_kind: Annotated[str | None, Query(alias="targetKind", max_length=50)] = None,
    target: Annotated[str | None, Query(max_length=100, description="Target id")] = None,
    page: PageNo = 1,
    page_size: PageSize = 50,
) -> Page[AuditEntry]:
    rows = (
        await db.execute(
            sa.text(
                "SELECT a.id, u.email, a.action, a.target_kind, a.target_id, a.before, a.after, "
                "a.created_at, count(*) OVER () FROM audit_log a "
                "LEFT JOIN app_user u ON u.id = a.actor_user_id "
                "WHERE (CAST(:actor AS text) IS NULL OR u.email = :actor) "
                "AND (CAST(:kind AS text) IS NULL OR a.target_kind = :kind) "
                "AND (CAST(:target AS text) IS NULL OR a.target_id = :target) "
                "ORDER BY a.id DESC LIMIT :limit OFFSET :offset"
            ),
            {"actor": actor, "kind": target_kind, "target": target, **_offset(page, page_size)},
        )
    ).all()
    return Page[AuditEntry](
        items=[
            AuditEntry(
                id=r[0],
                actor=r[1],
                action=r[2],
                target_kind=r[3],
                target_id=r[4],
                before=r[5],
                after=r[6],
                created_at=r[7],
            )
            for r in rows
        ],
        total=rows[0][8] if rows else 0,
        page=page,
        page_size=page_size,
    )
