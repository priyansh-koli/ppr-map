"""YAML files under config/ (rates.yaml, sources.yaml), read once and kept.

A file that is missing, not valid YAML or not the expected shape raises `ConfigUnavailable`,
which the API turns into a 503 (P2 #41: a YAML syntax error was a 500). A failure is kept
for a minute rather than re-read on every request, then the file is tried again, so a fixed
file is picked up without a restart.
"""

import time
from collections.abc import Callable

import yaml
from pydantic import ValidationError

from app.config import get_settings

RETRY_AFTER_S = 60.0


class ConfigUnavailable(Exception):
    pass


class ConfigFile[T]:
    def __init__(self, filename: str, parse: Callable[[object], T]) -> None:
        self.filename = filename
        self._parse = parse
        self._value: T | None = None
        self._error: ConfigUnavailable | None = None
        self._failed_at = 0.0

    def __call__(self) -> T:
        if self._value is not None:
            return self._value
        if self._error is not None and time.monotonic() - self._failed_at < RETRY_AFTER_S:
            raise self._error
        path = get_settings().ppr_config_dir / self.filename
        try:
            self._value = self._parse(yaml.safe_load(path.read_text(encoding="utf-8")))
        except (OSError, yaml.YAMLError, ValidationError) as exc:
            self._error = ConfigUnavailable(f"{self.filename}: {exc}")
            self._failed_at = time.monotonic()
            raise self._error from exc
        self._error = None
        return self._value

    def cache_clear(self) -> None:
        self._value, self._error = None, None
