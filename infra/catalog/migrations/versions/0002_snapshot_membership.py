"""Preserve exact revision and artifact membership for each snapshot.

Revision ID: 0002_snapshot_membership
Revises: 0001_catalog
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_snapshot_membership"
down_revision: str | None = "0001_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inventory_snapshot_revisions",
        sa.Column(
            "inventory_snapshot_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "document_revision_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["inventory_snapshot_id"],
            ["inventory_snapshots.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_revision_id"],
            ["document_revisions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "inventory_snapshot_id",
            "document_revision_id",
        ),
    )
    op.create_index(
        "ix_inventory_snapshot_revisions_revision",
        "inventory_snapshot_revisions",
        ["document_revision_id"],
    )
    op.create_table(
        "inventory_snapshot_artifacts",
        sa.Column(
            "inventory_snapshot_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "artifact_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["inventory_snapshot_id"],
            ["inventory_snapshots.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["artifacts.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "inventory_snapshot_id",
            "artifact_id",
        ),
    )
    op.create_index(
        "ix_inventory_snapshot_artifacts_artifact",
        "inventory_snapshot_artifacts",
        ["artifact_id"],
    )

    op.execute(
        """
        INSERT INTO inventory_snapshot_revisions (
            inventory_snapshot_id,
            document_revision_id
        )
        SELECT inventory_snapshot_id, id
        FROM document_revisions
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO inventory_snapshot_artifacts (
            inventory_snapshot_id,
            artifact_id
        )
        SELECT revisions.inventory_snapshot_id, artifacts.id
        FROM artifacts
        JOIN document_revisions AS revisions
          ON revisions.id = artifacts.document_revision_id
        WHERE artifacts.origin = 'bootstrap'
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_inventory_snapshot_artifacts_artifact",
        table_name="inventory_snapshot_artifacts",
    )
    op.drop_table("inventory_snapshot_artifacts")
    op.drop_index(
        "ix_inventory_snapshot_revisions_revision",
        table_name="inventory_snapshot_revisions",
    )
    op.drop_table("inventory_snapshot_revisions")
