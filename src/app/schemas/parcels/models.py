from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column

from app.data.base import Base


class OrderParcel(Base):
    __tablename__ = "order_parcels"
    __table_args__ = (
        UniqueConstraint("order_id", "shop_id", name="uq_order_parcel_shop"),
        UniqueConstraint("id", "shop_id", name="uq_parcel_id_shop"),
        CheckConstraint("shipping_fee >= 0", name="ck_parcel_ship_fee"),
        CheckConstraint("(status = 'cancelled') = (cancelled_at IS NOT NULL)", name="ck_parcel_cancel_consistent"),
        CheckConstraint("settled_at IS NULL OR status = 'delivered'", name="ck_parcel_settle_after_delivery"),
        Index("ix_parcels_shop_status", "shop_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False)
    shop_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shops.id", ondelete="RESTRICT"), nullable=False)
    shipping_fee: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(ENUM("pending", "preparing", "shipped", "delivered", "cancelled", name="parcel_status", create_type=False), nullable=False, server_default="pending")
    tracking_code: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        UniqueConstraint("parcel_id", "product_id", name="uq_order_item_product"),
        ForeignKeyConstraint(["parcel_id", "shop_id"], ["order_parcels.id", "order_parcels.shop_id"], name="fk_order_item_parcel_shop", ondelete="RESTRICT"),
        ForeignKeyConstraint(["product_id", "shop_id"], ["products.id", "products.shop_id"], name="fk_order_item_product_shop", ondelete="RESTRICT"),
        CheckConstraint("quantity > 0", name="ck_item_qty"),
        CheckConstraint("unit_price >= 0", name="ck_item_price"),
        Index("ix_order_items_product_id", "product_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    parcel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    shop_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    product_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    product_title: Mapped[str] = mapped_column(String(200), nullable=False)
    unit_price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
