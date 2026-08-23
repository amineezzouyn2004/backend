"""Phase 3 foundation schema.

Revision ID: 20260823_0001
Revises:
Create Date: 2026-08-23
"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260823_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

order_status = sa.Enum(
    "PENDING",
    "CONFIRMED",
    "CANCELLED",
    "PROCESSING",
    "SHIPPED",
    "OUT_FOR_DELIVERY",
    "DELIVERED",
    "RETURNED",
    name="order_status",
    native_enum=False,
    length=32,
)
delivery_status = sa.Enum(
    "PENDING", "SENT", "FAILED", "DEAD",
    name="delivery_status",
    native_enum=False,
    length=16,
)


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("public_reference", sa.String(64), nullable=False),
        sa.Column("status", order_status, nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("phone_e164", sa.String(20), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("subtotal_minor", sa.Integer(), nullable=False),
        sa.Column("discount_minor", sa.Integer(), nullable=False),
        sa.Column("shipping_minor", sa.Integer(), nullable=True),
        sa.Column("tax_minor", sa.Integer(), nullable=True),
        sa.Column("total_minor", sa.Integer(), nullable=False),
        sa.Column("total_is_final", sa.Boolean(), nullable=False),
        sa.Column("offer_code", sa.String(32), nullable=False),
        sa.Column("offer_version", sa.Integer(), nullable=False),
        sa.Column("upsell_selected", sa.Boolean(), nullable=False),
        sa.Column("consent_snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("attribution_id", sa.Uuid(), nullable=True),
        sa.Column("utm_source", sa.String(100), nullable=True),
        sa.Column("utm_medium", sa.String(100), nullable=True),
        sa.Column("utm_campaign", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("subtotal_minor >= 0", name="ck_orders_subtotal_nonnegative"),
        sa.CheckConstraint("discount_minor >= 0", name="ck_orders_discount_nonnegative"),
        sa.CheckConstraint("total_minor >= 0", name="ck_orders_total_nonnegative"),
        sa.CheckConstraint("subtotal_minor - discount_minor = total_minor", name="ck_orders_merchandise_total"),
        sa.CheckConstraint("currency = 'MAD'", name="ck_orders_currency_mad"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_reference"),
    )
    op.create_index("ix_orders_public_reference", "orders", ["public_reference"], unique=True)
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index("ix_orders_status_created_at", "orders", ["status", "created_at"])
    op.create_index("ix_orders_phone_created_at", "orders", ["phone_e164", "created_at"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("product_slug", sa.String(160), nullable=True),
        sa.Column("sku_snapshot", sa.String(80), nullable=True),
        sa.Column("name_snapshot_ar", sa.String(200), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_minor", sa.Integer(), nullable=False),
        sa.Column("line_total_minor", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        sa.CheckConstraint("unit_minor >= 0", name="ck_order_items_unit_nonnegative"),
        sa.CheckConstraint("line_total_minor >= 0", name="ck_order_items_total_nonnegative"),
        sa.CheckConstraint("unit_minor * quantity = line_total_minor", name="ck_order_items_line_total"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])

    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(50), nullable=False),
        sa.Column("key", sa.String(200), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", "key", name="uq_idempotency_scope_key"),
    )
    op.create_index("ix_idempotency_expires_at", "idempotency_records", ["expires_at"])

    op.create_table(
        "tracking_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("internal_event_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("payload_version", sa.Integer(), nullable=False),
        sa.Column("consent_snapshot_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("internal_event_id"),
    )
    op.create_index("ix_tracking_events_internal_event_id", "tracking_events", ["internal_event_id"], unique=True)
    op.create_index("ix_tracking_events_order_id", "tracking_events", ["order_id"])

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("internal_event_id", sa.Uuid(), nullable=False),
        sa.Column("aggregate_type", sa.String(50), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("destination", sa.String(40), nullable=False),
        sa.Column("payload_version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", delivery_status, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["internal_event_id"], ["tracking_events.internal_event_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("internal_event_id", "destination", name="uq_outbox_event_destination"),
    )
    op.create_index("ix_outbox_status_next_attempt", "outbox_events", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_table("tracking_events")
    op.drop_table("idempotency_records")
    op.drop_table("order_items")
    op.drop_table("orders")
