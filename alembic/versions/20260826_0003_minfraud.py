"""Add minFraud assessment storage.

Revision ID: 20260826_0003
Revises: 20260823_0002
Create Date: 2026-08-26
"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260826_0003"
down_revision: str | Sequence[str] | None = "20260823_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "minfraud_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("service", sa.String(16), nullable=False),
        sa.Column("minfraud_id", sa.String(36), nullable=True),
        sa.Column("risk_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("disposition_action", sa.String(32), nullable=True),
        sa.Column("disposition_reason", sa.String(32), nullable=True),
        sa.Column("disposition_rule_label", sa.String(80), nullable=True),
        sa.Column("ip_risk", sa.Numeric(5, 2), nullable=True),
        sa.Column("warning_codes", sa.JSON(), nullable=False),
        sa.Column("risk_reason_codes", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uq_minfraud_assessments_order_id"),
    )
    op.create_index(
        "ix_minfraud_assessments_order_id", "minfraud_assessments", ["order_id"]
    )
    op.create_index(
        "ix_minfraud_assessments_minfraud_id", "minfraud_assessments", ["minfraud_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_minfraud_assessments_minfraud_id", table_name="minfraud_assessments")
    op.drop_index("ix_minfraud_assessments_order_id", table_name="minfraud_assessments")
    op.drop_table("minfraud_assessments")
