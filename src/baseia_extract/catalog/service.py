from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import distinct, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..identity import artifact_uuid
from .contracts import (
    ArtifactInput,
    BootstrapBatch,
    SnapshotActivation,
    SnapshotCreate,
    StageRunComplete,
    StageRunCreate,
    StageRunFail,
    StageRunHeartbeat,
    StageRunRead,
)
from .models import (
    Artifact,
    Collection,
    Document,
    DocumentRevision,
    InventorySnapshot,
    InventorySnapshotArtifact,
    InventorySnapshotRevision,
    OutboxEvent,
    StageRun,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def _outbox(
    session: AsyncSession,
    *,
    topic: str,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    event_key: str,
    payload: dict[str, Any],
) -> None:
    statement = (
        insert(OutboxEvent)
        .values(
            topic=topic,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_key=event_key,
            payload=payload,
        )
        .on_conflict_do_nothing(
            constraint="uq_outbox_event",
        )
    )
    await session.execute(statement)


async def create_snapshot(
    session: AsyncSession,
    request: SnapshotCreate,
) -> InventorySnapshot:
    statement = (
        insert(InventorySnapshot)
        .values(
            id=request.id,
            scope=request.scope,
            status="loading",
            source=request.source,
            manifest_key=request.manifest_key,
            inventory_sha256=request.inventory_sha256,
            expected_document_count=request.expected_document_count,
            expected_artifact_count=request.expected_artifact_count,
        )
        .on_conflict_do_nothing(index_elements=[InventorySnapshot.id])
        .returning(InventorySnapshot.id)
    )
    inserted = (await session.execute(statement)).scalar_one_or_none()
    snapshot = await session.get(InventorySnapshot, request.id)
    if snapshot is None:
        raise RuntimeError("Snapshot não pôde ser criado.")
    expected = (
        request.scope,
        request.source,
        request.manifest_key,
        request.inventory_sha256,
        request.expected_document_count,
        request.expected_artifact_count,
    )
    actual = (
        snapshot.scope,
        snapshot.source,
        snapshot.manifest_key,
        snapshot.inventory_sha256,
        snapshot.expected_document_count,
        snapshot.expected_artifact_count,
    )
    if inserted is None and actual != expected:
        raise HTTPException(
            status_code=409,
            detail="O snapshot já existe com outro conteúdo.",
        )
    return snapshot


async def add_bootstrap_batch(
    session: AsyncSession,
    snapshot_id: uuid.UUID,
    batch: BootstrapBatch,
) -> dict[str, int]:
    snapshot = await session.get(
        InventorySnapshot,
        snapshot_id,
        with_for_update=True,
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot não encontrado.")
    if snapshot.status != "loading":
        raise HTTPException(
            status_code=409,
            detail=f"Snapshot não aceita documentos no status {snapshot.status!r}.",
        )

    artifact_rows: list[dict[str, Any]] = []
    revision_memberships: list[dict[str, uuid.UUID]] = []
    artifact_memberships: list[dict[str, Any]] = []
    for item in batch.documents:
        collection_id = (
            await session.execute(
                insert(Collection)
                .values(
                    id=item.collection_id,
                    slug=item.collection_slug,
                    name=item.collection_name,
                    storage_prefix=item.collection_storage_prefix,
                )
                .on_conflict_do_update(
                    index_elements=[Collection.slug],
                    set_={
                        "name": item.collection_name,
                        "storage_prefix": item.collection_storage_prefix,
                    },
                )
                .returning(Collection.id)
            )
        ).scalar_one()
        if collection_id != item.collection_id:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"A coleção {item.collection_slug!r} já existe com outro id."
                ),
            )

        document_id = (
            await session.execute(
                insert(Document)
                .values(
                    id=item.document_id,
                    collection_id=item.collection_id,
                    relative_path=item.relative_path,
                    filename=item.filename,
                )
                .on_conflict_do_update(
                    constraint="uq_documents_collection_path",
                    set_={
                        "filename": item.filename,
                        "updated_at": func.now(),
                    },
                )
                .returning(Document.id)
            )
        ).scalar_one()
        if document_id != item.document_id:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"O documento {item.relative_path!r} já existe com outro id."
                ),
            )

        await session.execute(
            insert(DocumentRevision)
            .values(
                id=item.revision_id,
                document_id=item.document_id,
                inventory_snapshot_id=snapshot_id,
                sha256=item.sha256,
                size_bytes=item.size_bytes,
                source_object_key=item.source_object_key,
            )
            .on_conflict_do_nothing(index_elements=[DocumentRevision.id])
        )
        revision = await session.get(DocumentRevision, item.revision_id)
        if revision is None or (
            revision.document_id,
            revision.sha256,
            revision.size_bytes,
            revision.source_object_key,
        ) != (
            item.document_id,
            item.sha256,
            item.size_bytes,
            item.source_object_key,
        ):
            raise HTTPException(
                status_code=409,
                detail=f"A revisão {item.revision_id} conflita com o catálogo.",
            )
        revision_memberships.append(
            {
                "inventory_snapshot_id": snapshot_id,
                "document_revision_id": item.revision_id,
            }
        )

        for artifact in item.artifacts:
            expected_id = artifact_uuid(item.revision_id, artifact.object_key)
            if artifact.id is not None and artifact.id != expected_id:
                raise HTTPException(
                    status_code=422,
                    detail=f"Id de artefato inválido para {artifact.object_key!r}.",
                )
            artifact_rows.append(
                {
                    "id": expected_id,
                    "document_revision_id": item.revision_id,
                    "stage_run_id": None,
                    "kind": artifact.kind,
                    "object_key": artifact.object_key,
                    "checksum_sha256": artifact.checksum_sha256,
                    "size_bytes": artifact.size_bytes,
                    "content_type": artifact.content_type,
                    "origin": "bootstrap",
                    "canonical": artifact.canonical,
                }
            )
            artifact_memberships.append(
                {
                    "inventory_snapshot_id": snapshot_id,
                    "artifact_id": expected_id,
                    "document_revision_id": item.revision_id,
                    "kind": artifact.kind,
                    "object_key": artifact.object_key,
                    "checksum_sha256": artifact.checksum_sha256,
                    "size_bytes": artifact.size_bytes,
                    "content_type": artifact.content_type,
                    "origin": "bootstrap",
                    "canonical": artifact.canonical,
                }
            )

    for index in range(0, len(revision_memberships), 1000):
        await session.execute(
            insert(InventorySnapshotRevision)
            .values(revision_memberships[index : index + 1000])
            .on_conflict_do_nothing()
        )

    for index in range(0, len(artifact_rows), 1000):
        statement = insert(Artifact).values(
            artifact_rows[index : index + 1000]
        )
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[Artifact.id],
                set_={
                    "stage_run_id": statement.excluded.stage_run_id,
                    "kind": statement.excluded.kind,
                    "checksum_sha256": statement.excluded.checksum_sha256,
                    "size_bytes": statement.excluded.size_bytes,
                    "content_type": statement.excluded.content_type,
                    "origin": statement.excluded.origin,
                    "canonical": statement.excluded.canonical,
                },
            )
        )
    immutable_fields = (
        "artifact_id",
        "document_revision_id",
        "kind",
        "object_key",
        "checksum_sha256",
        "size_bytes",
        "content_type",
        "origin",
        "canonical",
    )
    for index in range(0, len(artifact_memberships), 1000):
        chunk = artifact_memberships[index : index + 1000]
        artifact_ids = [item["artifact_id"] for item in chunk]
        object_keys = [item["object_key"] for item in chunk]
        existing = (
            (
                await session.execute(
                    select(InventorySnapshotArtifact).where(
                        InventorySnapshotArtifact.inventory_snapshot_id
                        == snapshot_id,
                        or_(
                            InventorySnapshotArtifact.artifact_id.in_(
                                artifact_ids
                            ),
                            InventorySnapshotArtifact.object_key.in_(
                                object_keys
                            ),
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        expected_by_id = {
            item["artifact_id"]: item
            for item in chunk
        }
        for membership in existing:
            expected = expected_by_id.get(membership.artifact_id)
            if expected is None or any(
                getattr(membership, field) != expected[field]
                for field in immutable_fields
            ):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "O snapshot já contém outro fato imutável para "
                        f"{membership.object_key!r}."
                    ),
                )
        await session.execute(
            insert(InventorySnapshotArtifact)
            .values(chunk)
            .on_conflict_do_nothing()
        )

    return {
        "documents": len(batch.documents),
        "artifacts": len(artifact_rows),
    }


async def activate_snapshot(
    session: AsyncSession,
    snapshot_id: uuid.UUID,
    request: SnapshotActivation,
) -> InventorySnapshot:
    snapshot = await session.get(
        InventorySnapshot,
        snapshot_id,
        with_for_update=True,
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot não encontrado.")
    if snapshot.status == "active":
        expected = (
            snapshot.expected_document_count,
            snapshot.expected_artifact_count,
            snapshot.document_count,
            snapshot.artifact_count,
        )
        requested = (
            request.expected_document_count,
            request.expected_artifact_count,
        )
        if (
            expected[0] != requested[0]
            or expected[1] != requested[1]
            or expected[2] != requested[0]
            or expected[3] != requested[1]
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Snapshot ativo diverge da reativação.",
                    "expected_documents": expected[0],
                    "actual_documents": expected[2],
                    "requested_documents": requested[0],
                    "expected_artifacts": expected[1],
                    "actual_artifacts": expected[3],
                    "requested_artifacts": requested[1],
                },
            )
        return snapshot
    if snapshot.status != "loading":
        raise HTTPException(
            status_code=409,
            detail=f"Snapshot não pode ser ativado no status {snapshot.status!r}.",
        )

    document_count = int(
        (
            await session.execute(
                select(func.count(distinct(DocumentRevision.document_id))).where(
                    DocumentRevision.id.in_(
                        select(
                            InventorySnapshotRevision.document_revision_id
                        ).where(
                            InventorySnapshotRevision.inventory_snapshot_id
                            == snapshot_id
                        )
                    )
                )
            )
        ).scalar_one()
    )
    artifact_count = int(
        (
            await session.execute(
                select(func.count(InventorySnapshotArtifact.artifact_id)).where(
                    InventorySnapshotArtifact.inventory_snapshot_id
                    == snapshot_id
                )
            )
        ).scalar_one()
    )
    expected = (
        snapshot.expected_document_count,
        snapshot.expected_artifact_count,
        request.expected_document_count,
        request.expected_artifact_count,
    )
    if (
        len({expected[0], expected[2], document_count}) != 1
        or len({expected[1], expected[3], artifact_count}) != 1
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Contagens do snapshot divergem.",
                "expected_documents": expected[0],
                "requested_documents": expected[2],
                "actual_documents": document_count,
                "expected_artifacts": expected[1],
                "requested_artifacts": expected[3],
                "actual_artifacts": artifact_count,
            },
        )

    await session.execute(
        update(InventorySnapshot)
        .where(
            InventorySnapshot.status == "active",
            InventorySnapshot.scope == snapshot.scope,
            InventorySnapshot.id != snapshot_id,
        )
        .values(status="superseded")
    )
    snapshot.status = "active"
    snapshot.document_count = document_count
    snapshot.artifact_count = artifact_count
    snapshot.activated_at = _utcnow()
    await _outbox(
        session,
        topic="inventory.snapshot.activated",
        aggregate_type="inventory_snapshot",
        aggregate_id=snapshot.id,
        event_key="activated",
        payload={
            "snapshot_id": str(snapshot.id),
            "scope": snapshot.scope,
            "document_count": document_count,
            "artifact_count": artifact_count,
            "manifest_key": snapshot.manifest_key,
        },
    )
    return snapshot


def _stage_identity(run: StageRun) -> tuple[Any, ...]:
    return (
        run.document_revision_id,
        run.stage,
        run.processor,
        run.processor_version,
        run.config_hash,
        sorted(run.input_hashes),
        run.idempotency_key,
    )


async def get_or_create_stage_run(
    session: AsyncSession,
    request: StageRunCreate,
) -> tuple[StageRun, bool]:
    revision = await session.get(DocumentRevision, request.document_revision_id)
    if revision is None:
        raise HTTPException(
            status_code=404,
            detail="Revisão de documento não encontrada.",
        )
    run_id = uuid.uuid4()
    await session.execute(
        insert(StageRun)
        .values(
            id=run_id,
            document_revision_id=request.document_revision_id,
            stage=request.stage,
            processor=request.processor,
            processor_version=request.processor_version,
            config_hash=request.config_hash,
            input_hashes=request.input_hashes,
            idempotency_key=request.idempotency_key,
            status="accepted",
        )
        .on_conflict_do_nothing(index_elements=[StageRun.idempotency_key])
    )
    run = (
        await session.execute(
            select(StageRun)
            .where(StageRun.idempotency_key == request.idempotency_key)
            .with_for_update()
        )
    ).scalar_one()
    expected = (
        request.document_revision_id,
        request.stage,
        request.processor,
        request.processor_version,
        request.config_hash,
        sorted(request.input_hashes),
        request.idempotency_key,
    )
    if _stage_identity(run) != expected:
        raise HTTPException(
            status_code=409,
            detail="A idempotency_key já existe com outro contrato de execução.",
        )
    created = run.id == run_id
    now = _utcnow()
    previous_owner = run.lease_owner
    previous_until = run.lease_until
    claimed = (
        run.status not in {"completed", "failed", "cancelled"}
        and (
            created
            or run.lease_owner == request.lease_owner
            or run.lease_until is None
            or run.lease_until <= now
        )
    )
    if claimed:
        if created:
            run.attempt = 1
        elif (
            previous_owner != request.lease_owner
            or previous_until is None
            or previous_until <= now
        ):
            run.attempt += 1
        run.lease_owner = request.lease_owner
        run.lease_until = now + timedelta(seconds=request.lease_seconds)
    if created:
        await _outbox(
            session,
            topic="stage.accepted",
            aggregate_type="stage_run",
            aggregate_id=run.id,
            event_key="accepted",
            payload={
                "stage_run_id": str(run.id),
                "document_revision_id": str(run.document_revision_id),
                "stage": run.stage,
                "idempotency_key": run.idempotency_key,
            },
        )
    elif claimed:
        await _outbox(
            session,
            topic="stage.claimed",
            aggregate_type="stage_run",
            aggregate_id=run.id,
            event_key=f"claimed:{run.attempt}",
            payload={
                "stage_run_id": str(run.id),
                "lease_owner": request.lease_owner,
                "lease_until": run.lease_until.isoformat(),
            },
        )
    run._baseia_created = created
    run._baseia_claimed = claimed
    return run, created


async def get_stage_run_by_key(
    session: AsyncSession,
    idempotency_key: str,
) -> StageRun:
    run = (
        await session.execute(
            select(StageRun).where(StageRun.idempotency_key == idempotency_key)
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Stage run não encontrado.")
    return run


async def stage_run_read(
    session: AsyncSession,
    run: StageRun,
    *,
    created: bool = False,
    claimed: bool | None = None,
) -> StageRunRead:
    artifacts = (
        (
            await session.execute(
                select(Artifact)
                .where(Artifact.stage_run_id == run.id)
                .order_by(Artifact.object_key)
            )
        )
        .scalars()
        .all()
    )
    return StageRunRead(
        id=run.id,
        document_revision_id=run.document_revision_id,
        stage=run.stage,
        processor=run.processor,
        processor_version=run.processor_version,
        config_hash=run.config_hash,
        input_hashes=list(run.input_hashes),
        idempotency_key=run.idempotency_key,
        status=run.status,
        attempt=run.attempt,
        error=run.error,
        lease_owner=run.lease_owner,
        lease_until=run.lease_until,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        artifacts=[
            ArtifactInput(
                id=item.id,
                kind=item.kind,
                object_key=item.object_key,
                checksum_sha256=item.checksum_sha256,
                size_bytes=item.size_bytes,
                content_type=item.content_type,
                canonical=item.canonical,
            )
            for item in artifacts
        ],
        created=created,
        claimed=(
            bool(getattr(run, "_baseia_claimed", False))
            if claimed is None
            else claimed
        ),
    )


_TRANSITIONS = {
    "accepted": {"queued", "processing", "cancelled"},
    "queued": {"processing", "cancelled"},
    "processing": {"uploading", "cancelled", "orphaned"},
    "uploading": {"cataloging", "orphaned"},
    "cataloging": {"orphaned"},
    "orphaned": {"processing", "cancelled"},
}
_PROGRESS_ORDER = {
    "processing": 0,
    "uploading": 1,
    "cataloging": 2,
}


def _require_lease(
    run: StageRun,
    *,
    lease_owner: str,
    lease_attempt: int,
) -> None:
    if (
        run.lease_owner != lease_owner
        or run.attempt != lease_attempt
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Lease obsoleto para o stage run: "
                f"owner={lease_owner!r}, attempt={lease_attempt}."
            ),
        )


async def transition_stage_run(
    session: AsyncSession,
    run_id: uuid.UUID,
    status: str,
    *,
    lease_owner: str,
    lease_attempt: int,
    lease_seconds: int,
) -> StageRun:
    run = await session.get(StageRun, run_id, with_for_update=True)
    if run is None:
        raise HTTPException(status_code=404, detail="Stage run não encontrado.")
    _require_lease(
        run,
        lease_owner=lease_owner,
        lease_attempt=lease_attempt,
    )
    if run.status == status:
        if status == "orphaned":
            run.lease_owner = None
            run.lease_until = _utcnow()
        return run
    if (
        status in _PROGRESS_ORDER
        and (
            run.status == "completed"
            or (
                run.status in _PROGRESS_ORDER
                and _PROGRESS_ORDER[status] < _PROGRESS_ORDER[run.status]
            )
        )
    ):
        # A worker may lose the HTTP response after a durable transition and
        # repeat an earlier publication step. Fencing still proves ownership;
        # the retry is an idempotent no-op and never regresses catalog state.
        return run
    if status not in _TRANSITIONS.get(run.status, set()):
        raise HTTPException(
            status_code=409,
            detail=f"Transição inválida: {run.status!r} -> {status!r}.",
        )
    run.lease_until = _utcnow() + timedelta(seconds=lease_seconds)
    run.status = status
    if status == "processing":
        run.started_at = run.started_at or _utcnow()
        run.finished_at = None
    if status in {"cancelled", "orphaned"}:
        run.finished_at = _utcnow()
    if status == "orphaned":
        # O próprio holder declarou que não pode continuar. Libera o lease
        # imediatamente; fencing pelo attempt ainda bloqueia o worker antigo.
        run.lease_owner = None
        run.lease_until = _utcnow()
    await _outbox(
        session,
        topic=f"stage.{status}",
        aggregate_type="stage_run",
        aggregate_id=run.id,
        event_key=f"{status}:{run.attempt}",
        payload={
            "stage_run_id": str(run.id),
            "status": status,
            "attempt": run.attempt,
        },
    )
    return run


async def heartbeat_stage_run(
    session: AsyncSession,
    run_id: uuid.UUID,
    request: StageRunHeartbeat,
) -> StageRun:
    run = await session.get(StageRun, run_id, with_for_update=True)
    if run is None:
        raise HTTPException(status_code=404, detail="Stage run não encontrado.")
    if run.status in {"completed", "failed", "cancelled"}:
        raise HTTPException(
            status_code=409,
            detail=f"Stage run terminal no status {run.status!r}.",
        )
    _require_lease(
        run,
        lease_owner=request.lease_owner,
        lease_attempt=request.lease_attempt,
    )
    run.lease_until = _utcnow() + timedelta(seconds=request.lease_seconds)
    return run


async def complete_stage_run(
    session: AsyncSession,
    run_id: uuid.UUID,
    request: StageRunComplete,
) -> StageRun:
    run = await session.get(StageRun, run_id, with_for_update=True)
    if run is None:
        raise HTTPException(status_code=404, detail="Stage run não encontrado.")
    if run.status == "completed":
        return run
    _require_lease(
        run,
        lease_owner=request.lease_owner,
        lease_attempt=request.lease_attempt,
    )
    if run.status not in {"processing", "uploading", "cataloging"}:
        raise HTTPException(
            status_code=409,
            detail=f"Stage run não pode concluir no status {run.status!r}.",
        )
    artifact_rows: list[dict[str, Any]] = []
    for artifact in request.artifacts:
        expected_id = artifact_uuid(
            run.document_revision_id,
            artifact.object_key,
        )
        if artifact.id is not None and artifact.id != expected_id:
            raise HTTPException(
                status_code=422,
                detail=f"Id de artefato inválido para {artifact.object_key!r}.",
            )
        artifact_rows.append(
            {
                "id": expected_id,
                "document_revision_id": run.document_revision_id,
                "stage_run_id": run.id,
                "kind": artifact.kind,
                "object_key": artifact.object_key,
                "checksum_sha256": artifact.checksum_sha256,
                "size_bytes": artifact.size_bytes,
                "content_type": artifact.content_type,
                "origin": "stage",
                "canonical": artifact.canonical,
            }
        )
    for index in range(0, len(artifact_rows), 1000):
        statement = insert(Artifact).values(
            artifact_rows[index : index + 1000]
        )
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[Artifact.id],
                set_={
                    "stage_run_id": statement.excluded.stage_run_id,
                    "kind": statement.excluded.kind,
                    "checksum_sha256": statement.excluded.checksum_sha256,
                    "size_bytes": statement.excluded.size_bytes,
                    "content_type": statement.excluded.content_type,
                    "origin": statement.excluded.origin,
                    "canonical": statement.excluded.canonical,
                },
            )
        )
    run.status = "completed"
    run.finished_at = _utcnow()
    run.error = None
    await _outbox(
        session,
        topic="stage.completed",
        aggregate_type="stage_run",
        aggregate_id=run.id,
        event_key=f"completed:{run.attempt}",
        payload={
            "stage_run_id": str(run.id),
            "document_revision_id": str(run.document_revision_id),
            "artifact_count": len(request.artifacts),
        },
    )
    return run


async def fail_stage_run(
    session: AsyncSession,
    run_id: uuid.UUID,
    request: StageRunFail,
) -> StageRun:
    run = await session.get(StageRun, run_id, with_for_update=True)
    if run is None:
        raise HTTPException(status_code=404, detail="Stage run não encontrado.")
    if run.status == "failed":
        return run
    if run.status in {"completed", "cancelled"}:
        raise HTTPException(
            status_code=409,
            detail=f"Stage run terminal no status {run.status!r}.",
        )
    _require_lease(
        run,
        lease_owner=request.lease_owner,
        lease_attempt=request.lease_attempt,
    )
    run.status = "failed"
    run.finished_at = _utcnow()
    run.error = {
        "type": request.error_type,
        "message": request.message,
        "retryable": request.retryable,
    }
    await _outbox(
        session,
        topic="stage.failed",
        aggregate_type="stage_run",
        aggregate_id=run.id,
        event_key=f"failed:{run.attempt}",
        payload={
            "stage_run_id": str(run.id),
            "attempt": run.attempt,
            "error": run.error,
        },
    )
    return run
