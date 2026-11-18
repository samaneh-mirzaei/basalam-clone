from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.schemas.users.models import Cart, User, Wallet, WalletTransaction


def provision_user(session: Session, mobile: str, full_name: str, password: str, role: str = "customer") -> tuple[User, Wallet]:
    """Create an account and its shopping state in the caller's transaction."""
    user = User(mobile=mobile, full_name=full_name, role=role, password_hash=hash_password(password))
    session.add(user)
    session.flush()
    wallet = Wallet(user_id=user.id, balance=1_000_000)
    session.add(wallet)
    session.flush()
    session.add(WalletTransaction(wallet_id=wallet.id, reason="initial_credit", amount=1_000_000, balance_after=1_000_000))
    session.add(Cart(user_id=user.id))
    return user, wallet
