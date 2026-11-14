"""RFC 9457 problem+json errors (belge 06 s.3.5)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("seoa.presentation.api")

PROBLEM_CONTENT_TYPE = "application/problem+json"

TITLES: dict[str, str] = {
    "validation-error": "Invalid request",
    "target-rejected": "Target rejected",
    "not-found": "Not found",
    "audit-not-ready": "Report not ready",
    "audit-in-progress": "An audit for this target is already running",
    "idempotency-key-reuse": "Idempotency key reused with a different body",
    "snapshot-expired": "Stored data has expired",
    "report-invalid": "Report failed the quality gate",
    "internal-error": "Internal error",
    "method-not-allowed": "Method not allowed",
}


class ApiError(Exception):
    """Raise from routes or from the service; rendered as problem+json."""

    def __init__(
        self,
        code: str,
        status: int,
        detail: str = "",
        *,
        errors: list[dict[str, Any]] | None = None,
        extra: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail or code)
        self.code = code
        self.status = status
        self.detail = detail
        self.errors = errors
        self.extra = extra or {}
        self.headers = headers or {}


def problem(
    request: Request,
    status: int,
    code: str,
    detail: str = "",
    *,
    errors: list[dict[str, Any]] | None = None,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"/problems/{code}",
        "title": TITLES.get(code, code.replace("-", " ").capitalize()),
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        "code": code,
        "trace_id": uuid.uuid4().hex,
    }
    if errors:
        body["errors"] = errors
    for k, v in (extra or {}).items():
        body.setdefault(k, v)  # extra members may never override the RFC 9457 core members
    return JSONResponse(body, status_code=status, media_type=PROBLEM_CONTENT_TYPE, headers=headers)


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return problem(
            request,
            exc.status,
            exc.code,
            exc.detail,
            errors=exc.errors,
            extra=exc.extra,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errs = [
            {
                "field": ".".join(str(p) for p in e.get("loc", ())[1:]) or "body",
                "reason": str(e.get("type", "invalid")),
            }
            for e in exc.errors()
        ]
        return problem(
            request,
            422,
            "validation-error",
            "The request did not match the expected schema.",
            errors=errs,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = (
            "not-found"
            if exc.status_code == 404
            else "method-not-allowed"
            if exc.status_code == 405
            else "http-error"
        )
        return problem(
            request, exc.status_code, code, "" if exc.status_code == 404 else str(exc.detail)
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception(
            "unhandled error on %s", request.url.path
        )  # details stay in the log, not in the response
        return problem(request, 500, "internal-error", "An unexpected error occurred.")
