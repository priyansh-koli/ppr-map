"""Daily housekeeping (D-041, D-042): delete what is past its retention period."""

import sqlalchemy as sa

from app.config import get_settings

# What is past its retention period, as (label, statement).
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
    (
        "searches older than 12 months",
        "DELETE FROM search_history WHERE searched_at < now() - :keep",
    ),
]


def purge_expired(days: int = 30) -> dict[str, int]:
    """Accounts closed more than `days` ago, with everything they own (cascade), and every
    other row past its retention period. Returns the number removed per kind."""
    from app.api.v1.me import HISTORY_KEEP
    from app.auth.sessions import IDLE

    engine = sa.create_engine(get_settings().database_url)
    out: dict[str, int] = {}
    try:
        with engine.begin() as conn:
            out["closed accounts"] = conn.execute(
                sa.text(
                    "DELETE FROM app_user WHERE deleted_at IS NOT NULL "
                    "AND deleted_at < now() - make_interval(days => :d)"
                ),
                {"d": days},
            ).rowcount
            for label, sql in EXPIRED:
                out[label] = conn.execute(
                    sa.text(sql), {"idle": IDLE, "keep": HISTORY_KEEP}
                ).rowcount
    finally:
        engine.dispose()
    return out
