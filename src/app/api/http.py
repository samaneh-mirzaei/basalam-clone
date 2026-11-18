from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints
from starlette.exceptions import HTTPException


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


BigintId = Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]*$", max_length=19)]
CategoryId = Annotated[StrictInt, Field(gt=0)]
Money = Annotated[StrictInt, Field(ge=0)]


def supplied_patch_fields(body: BaseModel) -> dict[str, Any]:
    return body.model_dump(exclude_unset=True)


class ContractRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def checked(request: Request) -> Response:
            expected = {"PATCH": "application/merge-patch+json", "POST": "application/json", "PUT": "application/json"}.get(request.method)
            if expected and not (request.method == "PUT" and not await request.body()) and request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != expected:
                raise HTTPException(415, f"Content-Type must be {expected}.")
            return await handler(request)

        return checked


def created(resource: dict[str, Any], location: str) -> JSONResponse:
    return JSONResponse({"data": resource}, status_code=201, headers={"Location": location, "Cache-Control": "private, no-store"})


def replayed(resource: dict[str, Any]) -> JSONResponse:
    return JSONResponse({"data": resource}, status_code=200, headers={"Cache-Control": "private, no-store"})


def not_modified(etag: str, cache_control: str = "public, max-age=60, stale-while-revalidate=300") -> Response:
    return Response(status_code=304, headers={"ETag": etag, "Cache-Control": cache_control})
