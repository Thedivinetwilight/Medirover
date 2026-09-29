"""initial schema: nodes, runtime state, telemetry, events, faults, audit

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "nodes",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("node_type", sa.String(length=16), nullable=False),
        sa.Column("firmware_version", sa.String(length=32), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("first_seen_at", sa.String(length=40), nullable=False),
        sa.Column("last_identified_at", sa.String(length=40), nullable=False),
    )
    op.create_table(
        "node_runtime_state",
        sa.Column(
            "node_id",
            sa.String(length=64),
            sa.ForeignKey("nodes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("connectivity", sa.String(length=16), nullable=False),
        sa.Column("safety_state", sa.String(length=20), nullable=False),
        sa.Column("source_kind", sa.String(length=16), nullable=False),
        sa.Column("last_heartbeat_at", sa.String(length=40), nullable=True),
        sa.Column("last_message_at", sa.String(length=40), nullable=True),
        sa.Column("last_sequence", sa.Integer(), nullable=False),
        sa.Column("battery_voltage", sa.Float(), nullable=True),
        sa.Column("uptime_s", sa.Float(), nullable=False),
        sa.Column("last_telemetry", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
    )
    op.create_table(
        "telemetry_readings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("node_id", sa.String(length=64), sa.ForeignKey("nodes.id"), nullable=False),
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("sensor_id", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("quality", sa.String(length=8), nullable=False),
        sa.Column("received_at", sa.String(length=40), nullable=False),
        sa.UniqueConstraint("node_id", "message_id", "sensor_id", name="uq_telemetry_dedup"),
        sa.Index("ix_telemetry_node_time", "node_id", "received_at"),
    )
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.String(length=40), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("node_id", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=8), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("correlation_id", sa.String(length=32), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=True),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Index("ix_events_time", "timestamp"),
    )
    op.create_table(
        "faults",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("node_id", sa.String(length=64), nullable=True),
        sa.Column("fault_code", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("detected_at", sa.String(length=40), nullable=False),
        sa.Column("cleared_at", sa.String(length=40), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
    )
    op.create_table(
        "audit",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.String(length=40), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=128), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit")
    op.drop_table("faults")
    op.drop_table("events")
    op.drop_table("telemetry_readings")
    op.drop_table("node_runtime_state")
    op.drop_table("nodes")
