"""Saved-search alerts (D-050): email a user when newly filed sales match a saved search.

A sale is new to a search when the PPR ingest run that first saw it is later than the run
the search was last checked against (`alerted_through_run_id`). Alerts go out only once the
data is complete: every property with a sale from the ingest has been through geocoding
(an unplaced one matches nothing, and once the search is checked past that run its sale
would never be reported), and a geocode run and then an aggregate run followed the ingest.
Only active accounts with a verified email and the `alert:receive` permission get them
(docs/permissions.md). Each search gets at most one alert per register update
(`alert_delivery` is unique on search and update).
"""

import hashlib
import hmac
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.schemas.properties import SalesFilter
from app.services import email as mail
from app.services import search

log = logging.getLogger(__name__)
LISTED = 20
SORTS = ("date", "-price", "price", "-change", "change")

# The newest PPR ingest that the pipeline has finished with: geocoding ran after it and the
# aggregate (the last step) after that, and none of its properties is waiting to be placed.
# An aggregate run straight after the ingest, before geocoding, is not enough (P1 #19).
READY_RUN = """
SELECT max(p.id) FROM ingest_run p
WHERE p.kind = 'ppr' AND p.status = 'succeeded'
  AND EXISTS (
      SELECT 1 FROM ingest_run g JOIN ingest_run a
        ON a.kind = 'aggregate' AND a.status = 'succeeded' AND a.started_at >= g.finished_at
      WHERE g.kind = 'geocode' AND g.status = 'succeeded' AND g.started_at >= p.finished_at)
  AND NOT EXISTS (
      SELECT 1 FROM property pr
      WHERE pr.geocoded_at IS NULL AND EXISTS (
          SELECT 1 FROM sale s
          WHERE s.property_id = pr.id AND s.first_seen_run_id <= p.id))
"""

DUE = """
SELECT ss.id, ss.name, ss.query, coalesce(ss.alerted_through_run_id, 0), u.email, u.full_name
FROM saved_search ss JOIN app_user u ON u.id = ss.user_id
WHERE ss.alert_frequency = CAST(:frequency AS alert_frequency)
  AND coalesce(ss.alerted_through_run_id, 0) < :ready
  AND u.is_active AND u.deleted_at IS NULL AND u.email_verified_at IS NOT NULL
  AND EXISTS (
      SELECT 1 FROM user_role ur
      JOIN role_permission rp ON rp.role_id = ur.role_id
      JOIN permission p ON p.id = rp.permission_id
      WHERE ur.user_id = u.id AND p.code = 'alert:receive')
ORDER BY ss.id
"""

# Matching properties whose latest matching sale was first seen after `since`.
NEW_MATCHES = """
SELECT m.public_id, p.address_display, m.sale_date, m.price_eur, count(*) OVER () AS total
FROM tile_matching_sales(ST_MakeEnvelope(:w, :s, :e, :n, 4326), CAST(:params AS json)) m
JOIN property p ON p.id = m.property_id
WHERE EXISTS (
    SELECT 1 FROM sale s
    WHERE s.property_id = m.property_id AND s.sale_date = m.sale_date
      AND s.price_eur = m.price_eur AND s.withdrawn_at IS NULL
      AND NOT s.is_possible_duplicate
      AND s.first_seen_run_id > :since AND s.first_seen_run_id <= :ready)
ORDER BY m.sale_date DESC, m.property_id
LIMIT :limit
"""

CLAIM = """
INSERT INTO alert_delivery (saved_search_id, data_version, n_matches, status)
VALUES (:id, :version, :n, :status)
ON CONFLICT (saved_search_id, data_version) DO NOTHING
RETURNING id
"""


@dataclass
class Result:
    checked: int = 0
    sent: int = 0
    no_matches: int = 0
    failed: int = 0
    skipped: int = 0


def unsubscribe_token(saved_search_id: uuid.UUID) -> str:
    """A link that switches off one alert without signing in; it cannot be forged."""
    key = (get_settings().session_secret or "development-only").encode()
    mac = hmac.new(key, f"unsubscribe:{saved_search_id}".encode(), hashlib.sha256)
    return f"{saved_search_id}.{mac.hexdigest()[:32]}"


def check_unsubscribe_token(token: str) -> uuid.UUID | None:
    sid, _, _ = token.partition(".")
    try:
        parsed = uuid.UUID(sid)
    except ValueError:
        return None
    # Bytes: compare_digest raises on a str with non-ASCII characters (P2 #40).
    good = hmac.compare_digest(unsubscribe_token(parsed).encode(), token.encode())
    return parsed if good else None


def parse_query(query: dict[str, str]) -> tuple[SalesFilter, str]:
    """A stored search as filters and a sort; raises ValidationError if it no longer parses."""
    params = {k: v for k, v in query.items() if k != "sort"}
    sort = query.get("sort", "-date")
    return SalesFilter.model_validate(params), sort if sort in SORTS else "-date"


def search_path(query: dict[str, str]) -> str:
    return "/search" + (f"?{urlencode(query)}" if query else "")


async def ready_run(session: AsyncSession) -> int | None:
    return (await session.execute(sa.text(READY_RUN))).scalar_one_or_none()


async def new_matches(
    session: AsyncSession, f: SalesFilter, since: int, ready: int, limit: int = LISTED
) -> tuple[int, list[Any]]:
    box = await search.envelope(session, f, None)
    if box is None:
        return 0, []
    w, s, e, n = box
    rows = (
        await session.execute(
            sa.text(NEW_MATCHES),
            {
                "w": w,
                "s": s,
                "e": e,
                "n": n,
                "params": json.dumps(f.to_params()),
                "since": since,
                "ready": ready,
                "limit": limit,
            },
        )
    ).all()
    return (int(rows[0].total) if rows else 0), list(rows)


async def send_alerts(session: AsyncSession, mailer: mail.Mailer, frequency: str) -> Result:
    """Check every due saved search with this frequency, and email the new matches."""
    result = Result()
    ready = await ready_run(session)
    if ready is None:
        return result
    due = (await session.execute(sa.text(DUE), {"frequency": frequency, "ready": ready})).all()
    await session.commit()
    for sid, name, query, since, to, full_name in due:
        result.checked += 1
        try:
            f, _ = parse_query(query)
        except ValidationError:
            log.warning("saved search %s no longer parses; skipped", sid)
            result.skipped += 1
            continue
        total, rows = await new_matches(session, f, since, ready)
        status = "pending" if total else "no_matches"
        claimed = (
            await session.execute(
                sa.text(CLAIM),
                {"id": sid, "version": f"ppr-r{ready}", "n": total, "status": status},
            )
        ).first()
        await session.execute(
            sa.text(
                "UPDATE saved_search SET alerted_through_run_id = :ready, "
                "last_alerted_at = CASE WHEN :sent THEN now() ELSE last_alerted_at END "
                "WHERE id = :id"
            ),
            {"ready": ready, "id": sid, "sent": bool(total and claimed)},
        )
        await session.commit()
        if claimed is None:
            result.skipped += 1  # another run already handled this update
            continue
        if not total:
            result.no_matches += 1
            continue
        sales = [
            (r[1], f"€{r[3]:,.0f}", f"{r[2].day} {r[2]:%b %Y}", f"/property/{r[0]}") for r in rows
        ]
        email = mail.search_alert(
            to, full_name, name, total, sales, search_path(query), unsubscribe_token(sid)
        )
        ok = await _send(mailer, email, sid)
        await session.execute(
            sa.text(
                "UPDATE alert_delivery SET status = :status, sent_at = CASE WHEN :ok "
                "THEN now() END WHERE id = :id"
            ),
            {"status": "sent" if ok else "failed", "ok": ok, "id": claimed[0]},
        )
        await session.commit()
        if ok:
            result.sent += 1
        else:
            result.failed += 1
    return result


async def _send(mailer: mail.Mailer, email: mail.Email, sid: uuid.UUID) -> bool:
    try:
        await mailer.deliver(email)
    except Exception:  # one failed email must not stop the others
        log.exception("alert email for saved search %s failed", sid)
        return False
    return True
