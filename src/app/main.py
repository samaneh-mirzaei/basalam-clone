from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from app.api.endpoints.v1.router import router
from app.core.errors import (
    APIError,
    domain_error,
    http_error,
    unexpected_error,
    validation_error,
)

app = FastAPI(title="Basalam Marketplace")
app.add_exception_handler(HTTPException, http_error)
app.add_exception_handler(RequestValidationError, validation_error)
app.add_exception_handler(APIError, domain_error)
app.add_exception_handler(Exception, unexpected_error)


@app.middleware("http")
async def request_identity(request: Request, call_next):
    request.state.request_id = f"req_{uuid4().hex}"
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    if request.headers.get("authorization") or request.url.path.endswith("/auth/tokens"):
        response.headers["Cache-Control"] = "private, no-store"
    return response
app.include_router(router)


@app.get(
    "/health",
    tags=["Operations"],
    summary="Check API process health",
    description="Returns `{\"status\":\"ok\"}` when the FastAPI process responds. This does not check PostgreSQL connectivity or migration state.",
)
def health() -> dict[str, str]:
    return {"status": "ok"}
