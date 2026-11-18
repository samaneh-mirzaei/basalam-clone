from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import ENUM

from app.data.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("mobile ~ '^09[0-9]{9}$'", name="ck_users_mobile"),
        CheckConstraint("role IN ('customer', 'operator')", name="ck_users_role"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    mobile: Mapped[str] = mapped_column(String(11), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(ENUM("customer", "operator", name="user_role", create_type=False), nullable=False, server_default="customer")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Wallet(Base):
    __tablename__ = "wallets"
    __table_args__ = (CheckConstraint("balance >= 0", name="ck_wallet_balance"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), unique=True, nullable=False)
    balance: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"
    __table_args__ = (
        CheckConstraint("amount <> 0 AND balance_after >= 0", name="ck_wtx_nonzero"),
        CheckConstraint("(reason = 'order_payment' AND amount < 0) OR (reason IN ('order_refund', 'sale_settlement', 'initial_credit') AND amount > 0) OR reason = 'adjustment'", name="ck_wtx_sign_by_reason"),
        CheckConstraint("reason IN ('initial_credit', 'adjustment') OR reference_id IS NOT NULL", name="ck_wtx_reference_required"),
        CheckConstraint("reason <> 'adjustment' OR (note IS NOT NULL AND length(btrim(note)) > 0)", name="ck_wtx_adjustment_note"),
        UniqueConstraint("wallet_id", "reason", "reference_id", name="uq_wallet_txn_idempotency"),
        Index("uq_wtx_one_initial_credit", "wallet_id", unique=True, postgresql_where=text("reason = 'initial_credit'")),
        Index("ix_wallet_transactions_wallet_created", "wallet_id", "created_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    wallet_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("wallets.id", ondelete="RESTRICT"), nullable=False)
    reason: Mapped[str] = mapped_column(ENUM("initial_credit", "order_payment", "order_refund", "sale_settlement", "adjustment", name="wallet_txn_reason", create_type=False), nullable=False)
    reference_id: Mapped[int | None] = mapped_column(BigInteger)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False)
    note: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Cart(Base):
    __tablename__ = "carts"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
