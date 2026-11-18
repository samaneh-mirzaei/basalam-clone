from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column

from app.data.base import Base


class ReturnRequest(Base):
    __tablename__ = "return_requests"
    __table_args__ = (
        CheckConstraint("(status = 'requested') = (decided_at IS NULL)", name="ck_return_decision_consistent"),
        CheckConstraint("status <> 'rejected' OR response_note IS NOT NULL", name="ck_return_rejection_note"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    parcel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("order_parcels.id", ondelete="RESTRICT"), unique=True, nullable=False)
    reason_text: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(ENUM("requested", "approved", "rejected", name="return_status", create_type=False), nullable=False, server_default="requested")
    response_note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
