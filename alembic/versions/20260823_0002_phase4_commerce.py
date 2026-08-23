"""Phase 4 commerce, consent, attribution, lifecycle, and delivery.

Revision ID: 20260823_0002
Revises: 20260823_0001
Create Date: 2026-08-23
"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260823_0002"
down_revision: str | Sequence[str] | None = "20260823_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

history_from_status = sa.Enum(
    "PENDING", "CONFIRMED", "CANCELLED", "PROCESSING", "SHIPPED",
    "OUT_FOR_DELIVERY", "DELIVERED", "RETURNED",
    name="order_status_history_from", native_enum=False, length=32,
)
history_to_status = sa.Enum(
    "PENDING", "CONFIRMED", "CANCELLED", "PROCESSING", "SHIPPED",
    "OUT_FOR_DELIVERY", "DELIVERED", "RETURNED",
    name="order_status_history_to", native_enum=False, length=32,
)


def upgrade() -> None:
    with op.batch_alter_table("order_items") as batch:
        batch.add_column(sa.Column("offer_code", sa.String(32), nullable=True))
        batch.add_column(sa.Column("offer_version", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("offer_quantity", sa.Integer(), nullable=False, server_default="1")
        )
        batch.add_column(
            sa.Column("role", sa.String(20), nullable=False, server_default="primary")
        )
        batch.add_column(
            sa.Column("saving_minor", sa.Integer(), nullable=False, server_default="0")
        )
        batch.create_check_constraint(
            "ck_order_items_offer_quantity_positive", "offer_quantity > 0"
        )

    op.add_column(
        "tracking_events",
        sa.Column("source", sa.String(30), nullable=False, server_default="server"),
    )
    op.add_column(
        "outbox_events", sa.Column("last_error_code", sa.String(80), nullable=True)
    )
    op.add_column(
        "outbox_events", sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.create_table(
        "consent_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("notice_version", sa.String(40), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("advertising", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "attribution_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(80), nullable=True),
        sa.Column("landing_page", sa.String(500), nullable=True),
        sa.Column("utm_source", sa.String(100), nullable=True),
        sa.Column("utm_medium", sa.String(100), nullable=True),
        sa.Column("utm_campaign", sa.String(100), nullable=True),
        sa.Column("utm_term", sa.String(100), nullable=True),
        sa.Column("utm_content", sa.String(100), nullable=True),
        sa.Column("fbclid", sa.String(300), nullable=True),
        sa.Column("fbc", sa.String(300), nullable=True),
        sa.Column("fbp", sa.String(300), nullable=True),
        sa.Column("ttclid", sa.String(300), nullable=True),
        sa.Column("ttp", sa.String(300), nullable=True),
        sa.Column("snap_click_id", sa.String(300), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("orders") as batch:
        batch.create_foreign_key(
            "fk_orders_consent_snapshot",
            "consent_records",
            ["consent_snapshot_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_orders_attribution",
            "attribution_records",
            ["attribution_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    with op.batch_alter_table("tracking_events") as batch:
        batch.create_foreign_key(
            "fk_tracking_events_consent_snapshot",
            "consent_records",
            ["consent_snapshot_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_table(
        "order_status_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", history_from_status, nullable=True),
        sa.Column("to_status", history_to_status, nullable=False),
        sa.Column("reason_code", sa.String(80), nullable=False),
        sa.Column("actor_type", sa.String(40), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=True),
        sa.Column("safe_metadata", sa.JSON(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_order_history_order_occurred",
        "order_status_history",
        ["order_id", "occurred_at"],
    )
    op.create_table(
        "webhook_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("external_event_id", sa.String(200), nullable=False),
        sa.Column("signature_version", sa.String(40), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "external_event_id", name="uq_webhook_provider_event"
        ),
    )
    op.create_index("ix_webhook_received_at", "webhook_receipts", ["received_at"])


def downgrade() -> None:
    op.drop_table("webhook_receipts")
    op.drop_table("order_status_history")
    with op.batch_alter_table("tracking_events") as batch:
        batch.drop_constraint(
            "fk_tracking_events_consent_snapshot", type_="foreignkey"
        )
    with op.batch_alter_table("orders") as batch:
        batch.drop_constraint("fk_orders_attribution", type_="foreignkey")
        batch.drop_constraint("fk_orders_consent_snapshot", type_="foreignkey")
    op.drop_table("attribution_records")
    op.drop_table("consent_records")
    op.drop_column("outbox_events", "sent_at")
    op.drop_column("outbox_events", "last_error_code")
    op.drop_column("tracking_events", "source")
    with op.batch_alter_table("order_items") as batch:
        batch.drop_constraint(
            "ck_order_items_offer_quantity_positive", type_="check"
        )
        batch.drop_column("saving_minor")
        batch.drop_column("role")
        batch.drop_column("offer_quantity")
        batch.drop_column("offer_version")
        batch.drop_column("offer_code")
