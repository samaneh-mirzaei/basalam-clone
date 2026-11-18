from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column

from app.data.base import Base


class Refund(Base):
    __tablename__ = "refunds"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_refund_amount"),
        CheckConstraint("(reason = 'return_accepted') = (return_request_id IS NOT NULL)", name="ck_refund_return_link"),
        Index("ix_refunds_parcel_id", "parcel_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    parcel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("order_parcels.id", ondelete="RESTRICT"), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str] = mapped_column(ENUM("parcel_cancelled", "return_accepted", "goodwill", name="refund_reason", create_type=False), nullable=False)
    return_request_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("return_requests.id", ondelete="RESTRICT"), unique=True)
    wallet_transaction_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("wallet_transactions.id", ondelete="RESTRICT"), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
