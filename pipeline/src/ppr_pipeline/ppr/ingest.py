"""PPR ingest run: download, skip if unchanged, parse, load, record (D-001)."""

import hashlib
import io
import os
import time
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import sqlalchemy as sa
from app.models.data import IngestRowError, IngestRun
from app.models.enums import IngestKind, IngestStatus

from ppr_pipeline.ppr.load import load
from ppr_pipeline.ppr.parse import ParsedRow, RowError, parse, read_rows
from ppr_pipeline.sources import load_sources

USER_AGENT = "ppr-map/0.1 (data pipeline)"  # product name pending (Q-07)


@dataclass(frozen=True, slots=True)
class RunSummary:
    run_id: int
    status: IngestStatus
    rows_read: int
    rows_inserted: int
    rows_withdrawn: int
    rows_failed: int
    stats: dict[str, Any]


def source_url() -> str:
    return os.environ.get("PPR_DOWNLOAD_URL") or load_sources()["ppr"].url


def download(url: str, dest: Path) -> bytes:
    with httpx.Client(follow_redirects=True, timeout=300, headers={"User-Agent": USER_AGENT}) as c:
        resp = c.get(url)
        resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return resp.content


def csv_bytes(payload: bytes) -> bytes:
    """Accept the PSRA zip (one CSV inside) or a bare CSV."""
    if not payload.startswith(b"PK"):
        return payload
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"expected one CSV in the PPR zip, found {names}")
        return zf.read(names[0])


def _last_succeeded_sha(conn: sa.Connection) -> str | None:
    return conn.execute(
        sa.select(IngestRun.source_sha256)
        .where(IngestRun.kind == IngestKind.PPR, IngestRun.status == IngestStatus.SUCCEEDED)
        .order_by(IngestRun.started_at.desc(), IngestRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _finish(conn: sa.Connection, run_id: int, **values: Any) -> None:
    conn.execute(
        sa.update(IngestRun)
        .where(IngestRun.id == run_id)
        .values(finished_at=datetime.now(UTC), **values)
    )


def ingest_ppr(engine: sa.Engine, payload: bytes, url: str, *, force: bool = False) -> RunSummary:
    """Load one PPR file (zip or CSV bytes). Re-running the same file changes nothing."""
    sha = hashlib.sha256(payload).hexdigest()
    with engine.begin() as conn:
        unchanged = not force and _last_succeeded_sha(conn) == sha
        run_id: int = conn.execute(
            sa.insert(IngestRun)
            .values(
                kind=IngestKind.PPR,
                status=IngestStatus.RUNNING,
                source_url=url,
                source_sha256=sha,
                source_bytes=len(payload),
            )
            .returning(IngestRun.id)
        ).scalar_one()
        if unchanged:
            _finish(conn, run_id, status=IngestStatus.SKIPPED_UNCHANGED)
            return RunSummary(run_id, IngestStatus.SKIPPED_UNCHANGED, 0, 0, 0, 0, {})

    started = time.monotonic()
    errors: list[RowError] = []
    read = 0

    def parsed_rows() -> Any:
        nonlocal read
        for item in parse(read_rows(csv_bytes(payload))):
            read += 1
            if isinstance(item, ParsedRow):
                yield item
            else:
                errors.append(item)

    try:
        with engine.begin() as conn:
            result = load(conn, parsed_rows(), run_id)
            if errors:
                conn.execute(
                    sa.insert(IngestRowError),
                    [
                        {
                            "ingest_run_id": run_id,
                            "line_no": e.line_no,
                            "raw_line": e.raw_line,
                            "error": e.error,
                        }
                        for e in errors
                    ],
                )
            stats = {**asdict(result), "seconds": round(time.monotonic() - started, 1)}
            _finish(
                conn,
                run_id,
                status=IngestStatus.SUCCEEDED,
                rows_read=read,
                rows_inserted=result.sales_inserted,
                rows_withdrawn=result.sales_withdrawn,
                rows_failed=len(errors),
                stats=stats,
            )
    except Exception as exc:
        with engine.begin() as conn:
            _finish(
                conn,
                run_id,
                status=IngestStatus.FAILED,
                rows_read=read,
                stats={"error": f"{type(exc).__name__}: {exc}"},
            )
        raise
    return RunSummary(
        run_id,
        IngestStatus.SUCCEEDED,
        read,
        result.sales_inserted,
        result.sales_withdrawn,
        len(errors),
        stats,
    )
