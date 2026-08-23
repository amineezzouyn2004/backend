import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    DEAD = "dead"


class TrackingEvent(Base):
    __tablename__ = "tracking_events"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    internal_event_id: Mapped[uuid.UUID] = mapped_column(unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80))
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(30), default="server")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    payload_version: Mapped[int] = mapped_column(Integer, default=1)
    consent_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("consent_records.id", ondelete="RESTRICT"), nullable=True
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        UniqueConstraint("internal_event_id", "destination", name="uq_outbox_event_destination"),
        Index("ix_outbox_status_next_attempt", "status", "next_attempt_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    internal_event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tracking_events.internal_event_id", ondelete="RESTRICT"))
    aggregate_type: Mapped[str] = mapped_column(String(50))
    aggregate_id: Mapped[uuid.UUID] = mapped_column()
    event_type: Mapped[str] = mapped_column(String(80))
    destination: Mapped[str] = mapped_column(String(40), default="tracking_noop")
    payload_version: Mapped[int] = mapped_column(Integer, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[DeliveryStatus] = mapped_column(
        Enum(DeliveryStatus, name="delivery_status", native_enum=False, length=16),
        default=DeliveryStatus.PENDING,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WebhookReceipt(Base):
    __tablename__ = "webhook_receipts"
    __table_args__ = (
        UniqueConstraint("provider", "external_event_id", name="uq_webhook_provider_event"),
        Index("ix_webhook_received_at", "received_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(40))
    external_event_id: Mapped[str] = mapped_column(String(200))
    signature_version: Mapped[str] = mapped_column(String(40))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
