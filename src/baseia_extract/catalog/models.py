from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    slug: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_prefix: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class InventorySnapshot(Base):
    __tablename__ = "inventory_snapshots"
    __table_args__ = (
        CheckConstraint(
            "status IN ('loading', 'verified', 'active', 'superseded', 'failed')",
            name="ck_inventory_snapshots_status",
        ),
        Index(
            "uq_inventory_snapshots_scope_active",
            "scope",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    scope: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default="loading",
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    manifest_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    inventory_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_document_count: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_artifact_count: Mapped[int] = mapped_column(Integer, nullable=False)
    document_count: Mapped[int | None] = mapped_column(Integer)
    artifact_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint(
            "collection_id",
            "relative_path",
            name="uq_documents_collection_path",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("collections.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class DocumentRevision(Base):
    __tablename__ = "document_revisions"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "sha256",
            name="uq_document_revisions_document_sha",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    inventory_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inventory_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_object_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class StageRun(Base):
    __tablename__ = "stage_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN "
            "('accepted', 'queued', 'processing', 'uploading', "
            "'cataloging', 'completed', 'failed', 'cancelled', 'orphaned')",
            name="ck_stage_runs_status",
        ),
        Index("ix_stage_runs_document_stage", "document_revision_id", "stage"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    document_revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_revisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    processor: Mapped[str] = mapped_column(String(128), nullable=False)
    processor_version: Mapped[str] = mapped_column(String(128), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_hashes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
    )
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default="accepted",
    )
    attempt: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    lease_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        CheckConstraint(
            "origin IN ('bootstrap', 'stage')",
            name="ck_artifacts_origin",
        ),
        UniqueConstraint(
            "document_revision_id",
            "object_key",
            name="uq_artifacts_revision_key",
        ),
        Index("ix_artifacts_stage_kind", "stage_run_id", "kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    document_revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_revisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stage_runs.id", ondelete="SET NULL"),
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(96), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    origin: Mapped[str] = mapped_column(String(24), nullable=False)
    canonical: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class InventorySnapshotRevision(Base):
    __tablename__ = "inventory_snapshot_revisions"
    __table_args__ = (
        Index(
            "ix_inventory_snapshot_revisions_revision",
            "document_revision_id",
        ),
    )

    inventory_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inventory_snapshots.id", ondelete="CASCADE"),
        primary_key=True,
    )
    document_revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_revisions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class InventorySnapshotArtifact(Base):
    __tablename__ = "inventory_snapshot_artifacts"
    __table_args__ = (
        CheckConstraint(
            "origin IN ('bootstrap', 'stage')",
            name="ck_inventory_snapshot_artifacts_origin",
        ),
        UniqueConstraint(
            "inventory_snapshot_id",
            "object_key",
            name="uq_inventory_snapshot_artifacts_key",
        ),
        Index(
            "ix_inventory_snapshot_artifacts_artifact",
            "artifact_id",
        ),
        Index(
            "ix_inventory_snapshot_artifacts_revision",
            "document_revision_id",
        ),
    )

    inventory_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inventory_snapshots.id", ondelete="CASCADE"),
        primary_key=True,
    )
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("artifacts.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    document_revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(96), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    origin: Mapped[str] = mapped_column(String(24), nullable=False)
    canonical: Mapped[bool] = mapped_column(
        nullable=False,
        server_default="false",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class OutboxEvent(Base):
    __tablename__ = "outbox"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'published', 'failed')",
            name="ck_outbox_status",
        ),
        Index("ix_outbox_dispatch", "status", "available_at", "id"),
        UniqueConstraint(
            "topic",
            "aggregate_id",
            "event_key",
            name="uq_outbox_event",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    topic: Mapped[str] = mapped_column(String(128), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    event_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default="pending",
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
