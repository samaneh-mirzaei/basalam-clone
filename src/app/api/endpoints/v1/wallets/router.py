from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from sqlalchemy import select, tuple_

from app.api.catalog import decode_cursor, encode_cursor, page_response
from app.api.dependencies import CurrentUser, SessionDep
from app.api.http import ContractRoute
from app.api.representations import wallet_data, wallet_transaction_data
from app.core.errors import APIError
from app.schemas.users.models import Wallet, WalletTransaction

router = APIRouter(tags=["Wallets"], route_class=ContractRoute)
Reason = Literal["initial_credit", "order_payment", "order_refund", "sale_settlement", "adjustment"]


def owned_wallet(user_id: int, session: SessionDep) -> Wallet:
    wallet = session.scalar(select(Wallet).where(Wallet.user_id == user_id))
    if wallet is None:
        raise APIError(404, "WALLET_NOT_FOUND", "Wallet not found.")
    return wallet


@router.get("/users/me/wallet", summary="Read my wallet", description="Return the authenticated user's cached balance in integer Toman. This is a private, no-store response.")
def get_wallet(user: CurrentUser, session: SessionDep):
    return {"data": wallet_data(owned_wallet(user.id, session))}


@router.get("/users/me/wallet/transactions", summary="List my wallet ledger", description="Read the authenticated user's immutable ledger entries, newest first. Filter by reason or timestamp range and use the returned cursor with the same filters for the next page.")
def list_transactions(
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    reason: Reason | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    if any(value is not None and value.tzinfo is None for value in (created_from, created_to)):
        raise APIError(422, "VALIDATION_FAILED", "Timestamp filters require a timezone.")
    if created_from and created_to and created_from > created_to:
        raise APIError(422, "VALIDATION_FAILED", "created_from must be before created_to.")
    wallet = owned_wallet(user.id, session)
    filters = {"user_id": user.id, "reason": reason, "created_from": created_from.isoformat() if created_from else None, "created_to": created_to.isoformat() if created_to else None}
    marker = decode_cursor(cursor, filters)
    query = select(WalletTransaction).where(WalletTransaction.wallet_id == wallet.id)
    if reason:
        query = query.where(WalletTransaction.reason == reason)
    if created_from:
        query = query.where(WalletTransaction.created_at >= created_from)
    if created_to:
        query = query.where(WalletTransaction.created_at <= created_to)
    if marker:
        try:
            cursor_time = datetime.fromisoformat(marker[0])
            cursor_id = int(marker[1])
        except (IndexError, TypeError, ValueError) as exc:
            raise APIError(400, "INVALID_CURSOR", "Invalid ledger cursor.") from exc
        query = query.where(tuple_(WalletTransaction.created_at, WalletTransaction.id) < (cursor_time, cursor_id))
    rows = session.scalars(query.order_by(WalletTransaction.created_at.desc(), WalletTransaction.id.desc()).limit(limit + 1)).all()
    last = rows[limit - 1] if len(rows) > limit else None
    next_cursor = encode_cursor(filters, [last.created_at.isoformat(), last.id]) if last else None
    return page_response(request, [wallet_transaction_data(entry) for entry in rows[:limit]], limit, next_cursor, private=True)
