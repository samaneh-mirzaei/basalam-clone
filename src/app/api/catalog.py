import base64
import hashlib
import json

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from app.core.errors import APIError

PUBLIC_CACHE = "public, max-age=60, stale-while-revalidate=300"
PRIVATE_CACHE = "private, no-store"


def tag(kind: str, identifier: int, version: int) -> str:
    return f'"{kind}-{identifier}-{version}"'


def catalog_response(request: Request, data, etag: str | None = None, private: bool = False) -> Response:
    headers = {"Cache-Control": PRIVATE_CACHE if private else PUBLIC_CACHE}
    if etag is None and not private:
        encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
        etag = '"' + hashlib.sha256(encoded).hexdigest() + '"'
    if etag:
        headers["ETag"] = etag
        if not private and request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
    return JSONResponse({"data": data}, headers=headers)


def page_response(request: Request, data: list, limit: int, next_cursor: str | None, private: bool = False) -> Response:
    page = {"limit": limit, "next_cursor": next_cursor, "has_more": next_cursor is not None}
    payload = {"data": data, "page": page}
    if private:
        return JSONResponse(payload, headers={"Cache-Control": PRIVATE_CACHE})
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    etag = '"' + hashlib.sha256(encoded).hexdigest() + '"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": PUBLIC_CACHE})
    return JSONResponse(payload, headers={"ETag": etag, "Cache-Control": PUBLIC_CACHE})


def filter_key(filters: dict) -> str:
    return hashlib.sha256(json.dumps(filters, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def encode_cursor(filters: dict, values: list) -> str:
    raw = json.dumps({"f": filter_key(filters), "v": values}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str | None, filters: dict) -> list | None:
    if cursor is None:
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        if data["f"] == filter_key(filters) and isinstance(data["v"], list):
            return data["v"]
    except (ValueError, KeyError, TypeError):
        pass
    raise APIError(400, "INVALID_CURSOR", "Cursor does not match the query.")
