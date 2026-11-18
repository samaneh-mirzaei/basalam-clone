from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import Field

from app.api.http import ContractRoute, StrictBody, created, not_modified, replayed, supplied_patch_fields
from app.main import app


class Write(StrictBody):
    price: int = Field(ge=0)
    name: str | None = None


class Patch(StrictBody):
    name: str | None = None


router = APIRouter(prefix="/__contract", route_class=ContractRoute)


@router.post("")
def create(body: Write):
    return created({"id": "9007199254740993", "name": body.name, "price": body.price}, "/__contract/9007199254740993")


@router.put("")
def replay(body: Write):
    return replayed({"id": "9007199254740993", "name": body.name, "price": body.price})


@router.patch("")
def patch(body: Patch):
    return {"data": supplied_patch_fields(body)}


@router.get("")
def conditional():
    return not_modified('"v1"')


app.include_router(router)


def test_creation_and_replay():
    with TestClient(app) as client:
        first = client.post("/__contract", json={"price": 0})
        again = client.put("/__contract", json={"price": 0})
    assert first.status_code == 201
    assert first.headers["location"] == "/__contract/9007199254740993"
    assert first.json()["data"] == {"id": "9007199254740993", "name": None, "price": 0}
    assert again.status_code == 200
    assert "location" not in again.headers


def test_merge_patch_omission_null_and_media_type():
    with TestClient(app) as client:
        omitted = client.patch("/__contract", content="{}", headers={"Content-Type": "application/merge-patch+json"})
        cleared = client.patch("/__contract", content='{"name":null}', headers={"Content-Type": "application/merge-patch+json"})
        wrong = client.patch("/__contract", json={"name": "x"})
    assert omitted.json() == {"data": {}}
    assert cleared.json() == {"data": {"name": None}}
    assert wrong.status_code == 415


def test_validation_redaction_and_correlation():
    with TestClient(app) as client:
        response = client.post("/__contract", json={"price": -1, "unexpected": "private"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]
    assert response.headers["cache-control"] == "private, no-store"
    assert "private" not in response.text
    assert {detail["field"] for detail in response.json()["error"]["details"]} == {"price", "unexpected"}


def test_method_and_bodyless_304():
    with TestClient(app) as client:
        invalid = client.delete("/__contract")
        conditional = client.get("/__contract")
    assert invalid.status_code == 405
    assert "POST" in invalid.headers["allow"]
    assert conditional.status_code == 304
    assert conditional.content == b""
    assert conditional.headers["etag"] == '"v1"'
