import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnalyticsEvent(Base):
    """First-party pageviews for admin KPIs. Raw IP is never stored."""

    __tablename__ = "analytics_events"
    __table_args__ = (
        Index("ix_analytics_events_accepted_created", "accepted", "created_at"),
        Index("ix_analytics_events_path_created", "path", "created_at"),
        Index("ix_analytics_events_visitor_created", "visitor_hash", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    path: Mapped[str] = mapped_column(String(500))
    product_slug: Mapped[str | None] = mapped_column(String(160), nullable=True)
    visitor_hash: Mapped[str] = mapped_column(String(64))
    ip_hash: Mapped[str] = mapped_column(String(64))
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    vpn_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    proxy_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    anonymous_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    hosting_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(40), default="first_party")
    reject_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
