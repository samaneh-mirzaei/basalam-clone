from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column

from app.data.base import Base


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("customer_id", "checkout_key", name="uq_order_checkout_key"),
        CheckConstraint("total_amount > 0", name="ck_order_total"),
        CheckConstraint("(status = 'cancelled') = (cancelled_at IS NOT NULL)", name="ck_order_cancel_consistent"),
        CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name="ck_order_request_hash"),
        Index("ix_orders_customer_placed", "customer_id", "placed_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    customer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    checkout_key: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(ENUM("paid", "cancelled", name="order_status", create_type=False), nullable=False, server_default="paid")
    total_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ship_recipient_name: Mapped[str] = mapped_column(String(100), nullable=False)
    ship_recipient_phone: Mapped[str] = mapped_column(String(16), nullable=False)
    ship_province: Mapped[str] = mapped_column(String(50), nullable=False)
    ship_city: Mapped[str] = mapped_column(String(50), nullable=False)
    ship_address_line: Mapped[str] = mapped_column(String(300), nullable=False)
    ship_postal_code: Mapped[str] = mapped_column(String(10), nullable=False)
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_payment_amount"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("orders.id", ondelete="RESTRICT"), unique=True, nullable=False)
    wallet_transaction_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("wallet_transactions.id", ondelete="RESTRICT"), unique=True, nullable=False)
    method: Mapped[str] = mapped_column(ENUM("wallet", name="payment_method", create_type=False), nullable=False, server_default="wallet")
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
