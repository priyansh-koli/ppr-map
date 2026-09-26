"""Import every model so Base.metadata is complete (Alembic and tests rely on this)."""

from app.models import data, users
from app.models.base import Base

__all__ = ["Base", "data", "users"]
