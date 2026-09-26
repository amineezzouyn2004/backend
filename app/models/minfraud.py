import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MinFraudAssessment(Base):
    """Stored minFraud Score/Insights/Factors outcome. No raw PII columns."""

    __tablename__ = "minfraud_assessments"
    __table_args__ = (UniqueConstraint("order_id", name="uq_minfraud_assessments_order_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), index=True
    )
    service: Mapped[str] = mapped_column(String(16))
    minfraud_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    risk_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    disposition_action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    disposition_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    disposition_rule_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ip_risk: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    warning_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    risk_reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    assessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
