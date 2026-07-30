from __future__ import annotations

import os
import secrets
import uuid
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .contracts import (
    BootstrapBatch,
    SnapshotActivation,
    SnapshotCreate,
    SnapshotRead,
    StageRunComplete,
    StageRunCreate,
    StageRunFail,
    StageRunHeartbeat,
    StageRunRead,
    StageRunStatusUpdate,
)
from .database import session_dependency
from .service import (
    activate_snapshot,
    add_bootstrap_batch,
    complete_stage_run,
    create_snapshot,
    fail_stage_run,
    get_or_create_stage_run,
    get_stage_run_by_key,
    heartbeat_stage_run,
    stage_run_read,
    transition_stage_run,
)


async def require_catalog_token(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    if request.url.path == "/health":
        return
    expected = os.getenv("BASEIA_CATALOG_API_TOKEN", "").strip()
    if not expected:
        return
    scheme, _, supplied = (authorization or "").partition(" ")
    if (
        scheme.casefold() != "bearer"
        or not supplied
        or not secrets.compare_digest(supplied, expected)
    ):
        raise HTTPException(
            status_code=401,
            detail="Token do catálogo inválido.",
            headers={"WWW-Authenticate": "Bearer"},
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    require_token = (
        os.getenv("BASEIA_REQUIRE_CATALOG_TOKEN", "false").strip().casefold()
        in {"1", "true", "yes", "on"}
    )
    if require_token and not os.getenv(
        "BASEIA_CATALOG_API_TOKEN", ""
    ).strip():
        raise RuntimeError(
            "BASEIA_REQUIRE_CATALOG_TOKEN exige BASEIA_CATALOG_API_TOKEN."
        )
    yield


app = FastAPI(
    title="BaseIA Catalog API",
    version="0.1.0",
    description=(
        "Único writer do catálogo canônico de documentos, revisões, "
        "execuções e artefatos."
    ),
    dependencies=[Depends(require_catalog_token)],
    lifespan=lifespan,
)
Session = Annotated[AsyncSession, Depends(session_dependency)]


@app.get("/health")
async def health(session: Session) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post(
    "/v1/inventory-snapshots",
    response_model=SnapshotRead,
)
async def post_snapshot(
    request: SnapshotCreate,
    session: Session,
) -> SnapshotRead:
    async with session.begin():
        snapshot = await create_snapshot(session, request)
    return SnapshotRead.model_validate(snapshot)


@app.post("/v1/inventory-snapshots/{snapshot_id}/documents")
async def post_snapshot_documents(
    snapshot_id: uuid.UUID,
    request: BootstrapBatch,
    session: Session,
) -> dict[str, int]:
    async with session.begin():
        return await add_bootstrap_batch(session, snapshot_id, request)


@app.post(
    "/v1/inventory-snapshots/{snapshot_id}/activate",
    response_model=SnapshotRead,
)
async def post_snapshot_activation(
    snapshot_id: uuid.UUID,
    request: SnapshotActivation,
    session: Session,
) -> SnapshotRead:
    async with session.begin():
        snapshot = await activate_snapshot(session, snapshot_id, request)
    return SnapshotRead.model_validate(snapshot)


@app.post(
    "/v1/stage-runs/get-or-create",
    response_model=StageRunRead,
)
async def post_stage_run(
    request: StageRunCreate,
    session: Session,
) -> StageRunRead:
    async with session.begin():
        run, created = await get_or_create_stage_run(session, request)
    return await stage_run_read(
        session,
        run,
        created=created,
        claimed=bool(getattr(run, "_baseia_claimed", False)),
    )


@app.get(
    "/v1/stage-runs/by-idempotency/{idempotency_key}",
    response_model=StageRunRead,
)
async def get_stage_run(
    idempotency_key: str,
    session: Session,
) -> StageRunRead:
    run = await get_stage_run_by_key(session, idempotency_key)
    return await stage_run_read(session, run)


@app.post(
    "/v1/stage-runs/{run_id}/status",
    response_model=StageRunRead,
)
async def post_stage_run_status(
    run_id: uuid.UUID,
    request: StageRunStatusUpdate,
    session: Session,
) -> StageRunRead:
    async with session.begin():
        run = await transition_stage_run(
            session,
            run_id,
            request.status,
            lease_owner=request.lease_owner,
            lease_attempt=request.lease_attempt,
            lease_seconds=request.lease_seconds,
        )
    return await stage_run_read(session, run)


@app.post(
    "/v1/stage-runs/{run_id}/heartbeat",
    response_model=StageRunRead,
)
async def post_stage_run_heartbeat(
    run_id: uuid.UUID,
    request: StageRunHeartbeat,
    session: Session,
) -> StageRunRead:
    async with session.begin():
        run = await heartbeat_stage_run(session, run_id, request)
    return await stage_run_read(session, run)


@app.post(
    "/v1/stage-runs/{run_id}/complete",
    response_model=StageRunRead,
)
async def post_stage_run_completion(
    run_id: uuid.UUID,
    request: StageRunComplete,
    session: Session,
) -> StageRunRead:
    async with session.begin():
        run = await complete_stage_run(session, run_id, request)
    return await stage_run_read(session, run)


@app.post(
    "/v1/stage-runs/{run_id}/fail",
    response_model=StageRunRead,
)
async def post_stage_run_failure(
    run_id: uuid.UUID,
    request: StageRunFail,
    session: Session,
) -> StageRunRead:
    async with session.begin():
        run = await fail_stage_run(session, run_id, request)
    return await stage_run_read(session, run)
