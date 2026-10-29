"""Admin sessions and first-party analytics events.

Revision ID: 20261028_0004
Revises: 20260826_0003
Create Date: 2026-10-28
"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261028_0004"
down_revision: str | Sequence[str] | None = "20260826_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("username", sa.String(80), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_admin_sessions_token_hash"),
    )
    op.create_index("ix_admin_sessions_expires_at", "admin_sessions", ["expires_at"])

    op.create_table(
        "analytics_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("product_slug", sa.String(160), nullable=True),
        sa.Column("visitor_hash", sa.String(64), nullable=False),
        sa.Column("ip_hash", sa.String(64), nullable=False),
        sa.Column("country", sa.String(2), nullable=True),
        sa.Column("vpn_flag", sa.Boolean(), nullable=True),
        sa.Column("proxy_flag", sa.Boolean(), nullable=True),
        sa.Column("anonymous_flag", sa.Boolean(), nullable=True),
        sa.Column("hosting_flag", sa.Boolean(), nullable=True),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("reject_reason", sa.String(80), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_analytics_events_accepted_created",
        "analytics_events",
        ["accepted", "created_at"],
    )
    op.create_index(
        "ix_analytics_events_path_created",
        "analytics_events",
        ["path", "created_at"],
    )
    op.create_index(
        "ix_analytics_events_visitor_created",
        "analytics_events",
        ["visitor_hash", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_analytics_events_visitor_created", table_name="analytics_events")
    op.drop_index("ix_analytics_events_path_created", table_name="analytics_events")
    op.drop_index("ix_analytics_events_accepted_created", table_name="analytics_events")
    op.drop_table("analytics_events")
    op.drop_index("ix_admin_sessions_expires_at", table_name="admin_sessions")
    op.drop_table("admin_sessions")
