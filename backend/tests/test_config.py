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


def test_check_email_points_to_mailpit_only_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.v1 import auth

    monkeypatch.delenv("MAIL_INBOX_URL", raising=False)
    monkeypatch.setattr(auth, "get_settings", lambda: Settings(_env_file=None))
    assert auth.check_email() == "Check your email to continue."

    dev = Settings(_env_file=None, mail_inbox_url="http://localhost:8025")
    monkeypatch.setattr(auth, "get_settings", lambda: dev)
    assert auth.check_email().startswith("Check your email to continue. ")
    assert "Mailpit at http://localhost:8025" in auth.check_email("A reset link is on its way.")


def test_caddy_lets_through_exactly_the_tile_filters() -> None:
    """Caddy refuses unknown tile parameters (P1 #9), so its list must follow SalesFilter."""
    import re

    from app.schemas.properties import SalesFilter

    caddyfile = (REPO_ROOT / "infra" / "caddy" / "Caddyfile").read_text()
    found = re.search(r'\{query\}\.matches\("\^\(\(([^)]*)\)=', caddyfile)
    assert found is not None
    names = {f.alias or n for n, f in SalesFilter.model_fields.items()}
    assert set(found.group(1).split("|")) == names | {"v"}
