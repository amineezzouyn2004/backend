import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index,
    Integer, String, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    RETURNED = "returned"


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("subtotal_minor >= 0", name="ck_orders_subtotal_nonnegative"),
        CheckConstraint("discount_minor >= 0", name="ck_orders_discount_nonnegative"),
        CheckConstraint("total_minor >= 0", name="ck_orders_total_nonnegative"),
        CheckConstraint("subtotal_minor - discount_minor = total_minor", name="ck_orders_merchandise_total"),
        CheckConstraint("currency = 'MAD'", name="ck_orders_currency_mad"),
        Index("ix_orders_status_created_at", "status", "created_at"),
        Index("ix_orders_phone_created_at", "phone_e164", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    public_reference: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status", native_enum=False, length=32),
        default=OrderStatus.PENDING, index=True,
    )
    full_name: Mapped[str] = mapped_column(String(120))
    phone_e164: Mapped[str] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(String(3), default="MAD")
    subtotal_minor: Mapped[int] = mapped_column(Integer)
    discount_minor: Mapped[int] = mapped_column(Integer)
    shipping_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tax_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_minor: Mapped[int] = mapped_column(Integer)
    total_is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    offer_code: Mapped[str] = mapped_column(String(32))
    offer_version: Mapped[int] = mapped_column(Integer)
    upsell_selected: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("consent_records.id", ondelete="RESTRICT"), nullable=True
    )
    attribution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("attribution_records.id", ondelete="RESTRICT"), nullable=True
    )
    utm_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", order_by="OrderItem.created_at")
    status_history: Mapped[list["OrderStatusHistory"]] = relationship(
        back_populates="order", order_by="OrderStatusHistory.occurred_at"
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        CheckConstraint("offer_quantity > 0", name="ck_order_items_offer_quantity_positive"),
        CheckConstraint("unit_minor >= 0", name="ck_order_items_unit_nonnegative"),
        CheckConstraint("line_total_minor >= 0", name="ck_order_items_total_nonnegative"),
        CheckConstraint("unit_minor * quantity = line_total_minor", name="ck_order_items_line_total"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), index=True)
    product_slug: Mapped[str | None] = mapped_column(String(160), nullable=True)
    sku_snapshot: Mapped[str | None] = mapped_column(String(80), nullable=True)
    name_snapshot_ar: Mapped[str] = mapped_column(String(200))
    offer_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    offer_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    offer_quantity: Mapped[int] = mapped_column(Integer, default=1)
    role: Mapped[str] = mapped_column(String(20), default="primary")
    quantity: Mapped[int] = mapped_column(Integer)
    unit_minor: Mapped[int] = mapped_column(Integer)
    line_total_minor: Mapped[int] = mapped_column(Integer)
    saving_minor: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    order: Mapped[Order] = relationship(back_populates="items")


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"
    __table_args__ = (Index("ix_order_history_order_occurred", "order_id", "occurred_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"))
    from_status: Mapped[OrderStatus | None] = mapped_column(
        Enum(OrderStatus, name="order_status_history_from", native_enum=False, length=32), nullable=True
    )
    to_status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status_history_to", native_enum=False, length=32)
    )
    reason_code: Mapped[str] = mapped_column(String(80))
    actor_type: Mapped[str] = mapped_column(String(40))
    actor_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    safe_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    order: Mapped[Order] = relationship(back_populates="status_history")


class ConsentRecord(Base):
    __tablename__ = "consent_records"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    notice_version: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(20))
    advertising: Mapped[bool] = mapped_column(Boolean)
    source: Mapped[str] = mapped_column(String(20))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AttributionRecord(Base):
    __tablename__ = "attribution_records"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source: Mapped[str | None] = mapped_column(String(80), nullable=True)
    landing_page: Mapped[str | None] = mapped_column(String(500), nullable=True)
    utm_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_term: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_content: Mapped[str | None] = mapped_column(String(100), nullable=True)
    fbclid: Mapped[str | None] = mapped_column(String(300), nullable=True)
    fbc: Mapped[str | None] = mapped_column(String(300), nullable=True)
    fbp: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ttclid: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ttp: Mapped[str | None] = mapped_column(String(300), nullable=True)
    snap_click_id: Mapped[str | None] = mapped_column(String(300), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("scope", "key", name="uq_idempotency_scope_key"),
        Index("ix_idempotency_expires_at", "expires_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    scope: Mapped[str] = mapped_column(String(50))
    key: Mapped[str] = mapped_column(String(200))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"))
    response_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
