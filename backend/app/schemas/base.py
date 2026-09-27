from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer, field_validator
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    """Base for every API schema: snake_case in Python, camelCase on the wire."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    @field_validator("*", mode="after")
    @classmethod
    def _no_nul(cls, value: object) -> object:
        # Postgres text cannot hold NUL; refuse it here (422) rather than fail in the database.
        items = value if isinstance(value, list) else [value]
        if any(isinstance(v, str) and "\x00" in v for v in items):
            raise ValueError("must not contain NUL characters")
        return value


class Problem(ApiModel):
    """RFC 9457 problem details."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    errors: list[dict[str, object]] | None = None


# Money is Decimal in Python (never float arithmetic) and a plain JSON number on the wire.
Money = Annotated[Decimal, PlainSerializer(lambda v: float(v), return_type=float, when_used="json")]
