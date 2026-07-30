"""Create the canonical catalog.

Revision ID: 0001_catalog
Revises:
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_catalog"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=96), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("storage_prefix", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
        sa.UniqueConstraint("storage_prefix"),
    )
    op.create_table(
        "inventory_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default="loading",
            nullable=False,
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("manifest_key", sa.Text(), nullable=False),
        sa.Column("inventory_sha256", sa.String(length=64), nullable=False),
        sa.Column("expected_document_count", sa.Integer(), nullable=False),
        sa.Column("expected_artifact_count", sa.Integer(), nullable=False),
        sa.Column("document_count", sa.Integer()),
        sa.Column("artifact_count", sa.Integer()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN "
            "('loading', 'verified', 'active', 'superseded', 'failed')",
            name="ck_inventory_snapshots_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("manifest_key"),
    )
    op.create_index(
        "uq_inventory_snapshots_one_active",
        "inventory_snapshots",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["collections.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "collection_id",
            "relative_path",
            name="uq_documents_collection_path",
        ),
    )
    op.create_index(
        "ix_documents_collection_id",
        "documents",
        ["collection_id"],
    )
    op.create_table(
        "document_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "inventory_snapshot_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("source_object_key", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["inventory_snapshot_id"],
            ["inventory_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "sha256",
            name="uq_document_revisions_document_sha",
        ),
    )
    op.create_index(
        "ix_document_revisions_document_id",
        "document_revisions",
        ["document_id"],
    )
    op.create_index(
        "ix_document_revisions_inventory_snapshot_id",
        "document_revisions",
        ["inventory_snapshot_id"],
    )
    op.create_index(
        "ix_document_revisions_sha256",
        "document_revisions",
        ["sha256"],
    )
    op.create_table(
        "stage_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "document_revision_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("processor", sa.String(length=128), nullable=False),
        sa.Column("processor_version", sa.String(length=128), nullable=False),
        sa.Column("config_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "input_hashes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default="accepted",
            nullable=False,
        ),
        sa.Column(
            "attempt",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("error", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("lease_owner", sa.String(length=255)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN "
            "('accepted', 'queued', 'processing', 'uploading', "
            "'cataloging', 'completed', 'failed', 'cancelled', 'orphaned')",
            name="ck_stage_runs_status",
        ),
        sa.ForeignKeyConstraint(
            ["document_revision_id"],
            ["document_revisions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_stage_runs_document_revision_id",
        "stage_runs",
        ["document_revision_id"],
    )
    op.create_index(
        "ix_stage_runs_document_stage",
        "stage_runs",
        ["document_revision_id", "stage"],
    )
    op.create_table(
        "artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "document_revision_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("stage_run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("kind", sa.String(length=96), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("origin", sa.String(length=24), nullable=False),
        sa.Column(
            "canonical",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "origin IN ('bootstrap', 'stage')",
            name="ck_artifacts_origin",
        ),
        sa.ForeignKeyConstraint(
            ["document_revision_id"],
            ["document_revisions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["stage_run_id"],
            ["stage_runs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_revision_id",
            "object_key",
            name="uq_artifacts_revision_key",
        ),
    )
    op.create_index(
        "ix_artifacts_document_revision_id",
        "artifacts",
        ["document_revision_id"],
    )
    op.create_index(
        "ix_artifacts_stage_run_id",
        "artifacts",
        ["stage_run_id"],
    )
    op.create_index(
        "ix_artifacts_stage_kind",
        "artifacts",
        ["stage_run_id", "kind"],
    )
    op.create_table(
        "outbox",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("topic", sa.String(length=128), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_key", sa.String(length=128), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'published', 'failed')",
            name="ck_outbox_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "topic",
            "aggregate_id",
            "event_key",
            name="uq_outbox_event",
        ),
    )
    op.create_index(
        "ix_outbox_dispatch",
        "outbox",
        ["status", "available_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_dispatch", table_name="outbox")
    op.drop_table("outbox")
    op.drop_index("ix_artifacts_stage_kind", table_name="artifacts")
    op.drop_index("ix_artifacts_stage_run_id", table_name="artifacts")
    op.drop_index("ix_artifacts_document_revision_id", table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_index("ix_stage_runs_document_stage", table_name="stage_runs")
    op.drop_index("ix_stage_runs_document_revision_id", table_name="stage_runs")
    op.drop_table("stage_runs")
    op.drop_index(
        "ix_document_revisions_sha256",
        table_name="document_revisions",
    )
    op.drop_index(
        "ix_document_revisions_inventory_snapshot_id",
        table_name="document_revisions",
    )
    op.drop_index(
        "ix_document_revisions_document_id",
        table_name="document_revisions",
    )
    op.drop_table("document_revisions")
    op.drop_index("ix_documents_collection_id", table_name="documents")
    op.drop_table("documents")
    op.drop_index(
        "uq_inventory_snapshots_one_active",
        table_name="inventory_snapshots",
    )
    op.drop_table("inventory_snapshots")
    op.drop_table("collections")
