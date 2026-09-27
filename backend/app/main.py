from collections.abc import Mapping
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import router as v1_router
from app.schemas.base import Problem

API_PREFIX = "/api/v1"
PROBLEM_JSON = "application/problem+json"


def _problem(problem: Problem, headers: Mapping[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        problem.model_dump(by_alias=True, exclude_none=True),
        status_code=problem.status,
        media_type=PROBLEM_JSON,
        headers=headers,
    )


def _phrase(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Error"


async def http_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    title = _phrase(exc.status_code)
    detail = str(exc.detail) if exc.detail and exc.detail != title else None
    return _problem(Problem(title=title, status=exc.status_code, detail=detail), exc.headers)


async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    # Starlette still re-raises the exception afterwards, so it is logged as before.
    return _problem(Problem(title="Internal Server Error", status=500))


async def validation_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
    return _problem(Problem(title="Request validation failed", status=422, errors=errors))


def create_app() -> FastAPI:
    app = FastAPI(
        title="PPR Map API",
        version="0.1.0",
        description=(
            "Ireland's Property Price Register, made usable. Contains Residential Property Price "
            "Register data © Property Services Regulatory Authority; it may contain errors."
        ),
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
    )
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.include_router(v1_router, prefix=API_PREFIX)
    return app


app = create_app()
