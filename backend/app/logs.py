"""Logging that keeps personal data out (P2 #44; the privacy page)."""

import logging


class PrivateAccessLog(logging.Filter):
    """uvicorn's access line without the client's IP address or the query string. A query
    can hold a search, an email address or a one-time token; rate limits use a hashed IP
    and need no log line."""

    def filter(self, record: logging.LogRecord) -> bool:
        # uvicorn logs '%s - "%s %s HTTP/%s" %d' with (client, method, path?query, version, status).
        if isinstance(record.args, tuple) and len(record.args) == 5:
            _client, method, path, version, status = record.args
            record.args = ("-", method, str(path).split("?", 1)[0], version, status)
        return True


def keep_access_log_private() -> None:
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, PrivateAccessLog) for f in logger.filters):
        logger.addFilter(PrivateAccessLog())
