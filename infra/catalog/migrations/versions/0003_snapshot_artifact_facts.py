"""Freeze artifact metadata inside every inventory snapshot.

Revision ID: 0003_snapshot_artifact_facts
Revises: 0002_snapshot_membership
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_snapshot_artifact_facts"
down_revision: str | None = "0002_snapshot_membership"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "inventory_snapshot_artifacts"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column(
            "document_revision_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        TABLE,
        sa.Column("kind", sa.String(length=96), nullable=True),
    )
    op.add_column(
        TABLE,
        sa.Column("object_key", sa.Text(), nullable=True),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "checksum_sha256",
            sa.String(length=64),
            nullable=True,
        ),
    )
    op.add_column(
        TABLE,
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "content_type",
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        TABLE,
        sa.Column("origin", sa.String(length=24), nullable=True),
    )
    op.add_column(
        TABLE,
        sa.Column("canonical", sa.Boolean(), nullable=True),
    )
    op.execute(
        """
        UPDATE inventory_snapshot_artifacts AS snapshot_artifact
        SET
            document_revision_id = artifact.document_revision_id,
            kind = artifact.kind,
            object_key = artifact.object_key,
            checksum_sha256 = artifact.checksum_sha256,
            size_bytes = artifact.size_bytes,
            content_type = artifact.content_type,
            origin = artifact.origin,
            canonical = artifact.canonical
        FROM artifacts AS artifact
        WHERE artifact.id = snapshot_artifact.artifact_id
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM inventory_snapshot_artifacts
                WHERE document_revision_id IS NULL
                   OR kind IS NULL
                   OR object_key IS NULL
                   OR checksum_sha256 IS NULL
                   OR size_bytes IS NULL
                   OR content_type IS NULL
                   OR origin IS NULL
                   OR canonical IS NULL
            ) THEN
                RAISE EXCEPTION
                    'snapshot artifact facts could not be backfilled';
            END IF;
        END
        $$;
        """
    )
    for column in (
        "document_revision_id",
        "kind",
        "object_key",
        "checksum_sha256",
        "size_bytes",
        "content_type",
        "origin",
        "canonical",
    ):
        op.alter_column(TABLE, column, nullable=False)

    op.drop_constraint(
        "inventory_snapshot_artifacts_artifact_id_fkey",
        TABLE,
        type_="foreignkey",
    )
    op.create_foreign_key(
        "inventory_snapshot_artifacts_artifact_id_fkey",
        TABLE,
        "artifacts",
        ["artifact_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "inventory_snapshot_artifacts_document_revision_id_fkey",
        TABLE,
        "document_revisions",
        ["document_revision_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_inventory_snapshot_artifacts_origin",
        TABLE,
        "origin IN ('bootstrap', 'stage')",
    )
    op.create_unique_constraint(
        "uq_inventory_snapshot_artifacts_key",
        TABLE,
        ["inventory_snapshot_id", "object_key"],
    )
    op.create_index(
        "ix_inventory_snapshot_artifacts_revision",
        TABLE,
        ["document_revision_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_inventory_snapshot_artifacts_revision",
        table_name=TABLE,
    )
    op.drop_constraint(
        "uq_inventory_snapshot_artifacts_key",
        TABLE,
        type_="unique",
    )
    op.drop_constraint(
        "ck_inventory_snapshot_artifacts_origin",
        TABLE,
        type_="check",
    )
    op.drop_constraint(
        "inventory_snapshot_artifacts_document_revision_id_fkey",
        TABLE,
        type_="foreignkey",
    )
    op.drop_constraint(
        "inventory_snapshot_artifacts_artifact_id_fkey",
        TABLE,
        type_="foreignkey",
    )
    op.create_foreign_key(
        "inventory_snapshot_artifacts_artifact_id_fkey",
        TABLE,
        "artifacts",
        ["artifact_id"],
        ["id"],
        ondelete="CASCADE",
    )
    for column in (
        "canonical",
        "origin",
        "content_type",
        "size_bytes",
        "checksum_sha256",
        "object_key",
        "kind",
        "document_revision_id",
    ):
        op.drop_column(TABLE, column)
