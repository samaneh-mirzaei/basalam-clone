from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message


async def domain_error(request: Request, exc: APIError) -> JSONResponse:
    return error_response(request, exc.status, exc.code, exc.message)


def error_response(request: Request, status: int, code: str, message: str, details: list[dict] | None = None, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message, "details": details or [], "request_id": request.state.request_id}},
        status_code=status,
        headers={**(headers or {}), "X-Request-ID": request.state.request_id, "Cache-Control": "private, no-store"},
    )


async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    code = {404: "RESOURCE_NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 415: "UNSUPPORTED_MEDIA_TYPE"}.get(exc.status_code, "HTTP_ERROR")
    if isinstance(exc.detail, str) and exc.detail in {"ACCOUNT_INACTIVE"}:
        code = exc.detail
    message = str(exc.detail) if exc.status_code < 500 else "An unexpected error occurred."
    return error_response(request, exc.status_code, code, message, headers=exc.headers)


async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {"field": ".".join(str(part) for part in error["loc"] if part != "body"), "issue": error["msg"]}
        for error in exc.errors()
    ]
    return error_response(request, 422, "VALIDATION_FAILED", "Request validation failed.", details)


async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    return error_response(request, 500, "INTERNAL_ERROR", "An unexpected error occurred.")
