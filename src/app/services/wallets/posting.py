from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import APIError
from app.schemas.users.models import Wallet, WalletTransaction


def debit_order(session: Session, customer_id: int, order_id: int, amount: int) -> WalletTransaction:
    """Serialize debits on the wallet row and post one immutable order-payment entry."""
    wallet = session.scalar(select(Wallet).where(Wallet.user_id == customer_id).with_for_update())
    if wallet is None or wallet.balance < amount:
        raise APIError(409, "INSUFFICIENT_WALLET_BALANCE", "Wallet balance is insufficient.")
    wallet.balance -= amount
    wallet.updated_at = func.now()
    entry = WalletTransaction(wallet_id=wallet.id, reason="order_payment", reference_id=order_id, amount=-amount, balance_after=wallet.balance)
    session.add(entry)
    session.flush()
    return entry
