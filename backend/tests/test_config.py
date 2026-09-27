import pytest
from pydantic import ValidationError

from app.config import REPO_ENV_FILE, Settings
from tests.conftest import REPO_ROOT


def test_env_file_is_found_from_any_working_directory() -> None:
    assert REPO_ENV_FILE == REPO_ROOT / ".env"


def test_production_refuses_to_start_without_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SESSION_SECRET", "CSRF_SECRET", "IP_HASH_SALT"):
        monkeypatch.setenv(name, "")
    with pytest.raises(ValidationError, match="SESSION_SECRET, CSRF_SECRET, IP_HASH_SALT"):
        Settings(environment="production", _env_file=None)
    assert Settings(environment="development", _env_file=None).environment == "development"
