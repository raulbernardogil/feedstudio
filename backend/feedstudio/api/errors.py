"""Structured error responses: ``{"error": {"code", "message", "details"}}``."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("feedstudio.api")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | list | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


def _body(code: str, message: str, details=None) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


def _clean_errors(errors: list[dict]) -> list[dict]:
    return [{"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")} for e in errors]


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return JSONResponse(_body(exc.code, exc.message, exc.details), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        return JSONResponse(_body("validation_error", "La solicitud no es válida", _clean_errors(exc.errors())), status_code=422)

    @app.exception_handler(ValidationError)
    async def _pydantic(_: Request, exc: ValidationError):
        return JSONResponse(_body("validation_error", "La definición no es válida", _clean_errors(exc.errors())), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        return JSONResponse(_body("http_error", str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse(_body("internal_error", "Error interno del servidor"), status_code=500)
