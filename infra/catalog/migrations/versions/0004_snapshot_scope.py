"""Scope active inventory snapshots independently.

Revision ID: 0004_snapshot_scope
Revises: 0003_snapshot_artifact_facts
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_snapshot_scope"
down_revision: str | None = "0003_snapshot_artifact_facts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "inventory_snapshots"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("scope", sa.String(length=128), nullable=True),
    )
    op.execute(
        "UPDATE inventory_snapshots SET scope = 'default' WHERE scope IS NULL"
    )
    op.alter_column(TABLE, "scope", nullable=False)
    op.drop_index(
        "uq_inventory_snapshots_one_active",
        table_name=TABLE,
    )
    op.create_index(
        "uq_inventory_snapshots_scope_active",
        TABLE,
        ["scope"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE inventory_snapshots
        SET status = 'superseded'
        WHERE status = 'active'
          AND id NOT IN (
              SELECT id
              FROM inventory_snapshots
              WHERE status = 'active'
              ORDER BY activated_at DESC NULLS LAST, created_at DESC
              LIMIT 1
          )
        """
    )
    op.drop_index(
        "uq_inventory_snapshots_scope_active",
        table_name=TABLE,
    )
    op.create_index(
        "uq_inventory_snapshots_one_active",
        TABLE,
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.drop_column(TABLE, "scope")
