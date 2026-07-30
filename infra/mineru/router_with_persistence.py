"""Launch MinerU's official router with durable result hooks."""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import os
from pathlib import Path

import persistent_results
from mineru.cli import router
from mineru.version import __version__


EXPECTED_VERSION = "3.4.4"
_idempotency_key: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "baseia_idempotency_key", default=None
)
_submit_locks: dict[str, asyncio.Lock] = {}
_submit_lock_references: dict[str, int] = {}
_submit_locks_guard = asyncio.Lock()


def _file_sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


class _PersistentWorkerDirectory:
    """Implements the small TemporaryDirectory surface used by MinerU.stop."""

    def __init__(self, server_id: str) -> None:
        self.name = str(
            Path(os.environ.get("MINERU_LOCAL_WORK_ROOT", "/tmp/mineru-active"))
            / server_id
        )
        Path(self.name).mkdir(parents=True, exist_ok=True)

    def cleanup(self) -> None:
        # Results are retained until the independent reconciler has persisted
        # their package; this method is invoked by MinerU while stopping.
        return None


def _patch_router() -> None:
    if __version__ != EXPECTED_VERSION:
        raise RuntimeError(f"MinerU {EXPECTED_VERSION} obrigatório; encontrado {__version__}.")
    if getattr(router, "_baseia_persistence_patch", False):
        return

    async def start(self, client, port=None):
        if self.is_running():
            return
        self.temp_dir = _PersistentWorkerDirectory(self.server_id)
        output_root = Path(self.temp_dir.name) / "output"
        output_root.mkdir(parents=True, exist_ok=True)
        resolved_port = port if port is not None else router.find_free_port()
        remaining_cli_args = router.strip_local_api_network_args(self.extra_cli_args)
        worker_cli_args = router.build_local_api_cli_args(
            remaining_cli_args,
            enable_vlm_preload=self.enable_vlm_preload,
        )
        self.base_url = f"http://{self.connect_host}:{resolved_port}"
        env = os.environ.copy()
        env["MINERU_API_OUTPUT_ROOT"] = str(output_root)
        env["MINERU_API_DISABLE_ACCESS_LOG"] = "1"
        env["MINERU_PERSISTENCE_WORKER_ID"] = self.server_id
        if self.gpu is not None:
            env[router.get_local_device_visible_env_name()] = str(self.gpu)
        command = [
            router.sys.executable,
            "-m",
            "mineru.cli.fast_api",
            "--host",
            self.worker_host,
            "--port",
            str(resolved_port),
            *worker_cli_args,
        ]
        self.process = router.subprocess.Popen(
            command,
            cwd=os.getcwd(),
            env=env,
            **router.build_managed_process_popen_kwargs(),
        )
        self.process_group_id = self.process.pid
        try:
            await self.wait_until_ready(client)
        except Exception:
            self.stop()
            raise

    original_register = router.RouterTaskRegistry.register

    async def register(self, **kwargs):
        task = await original_register(self, **kwargs)
        external_id = _idempotency_key.get()
        if external_id is not None:
            async with self._lock:
                generated_id = task.task_id
                existing = self._tasks.get(external_id)
                if existing is not None and existing is not task:
                    self._tasks.pop(generated_id, None)
                    return existing
                task.task_id = external_id
                self._tasks.pop(generated_id, None)
                self._tasks[external_id] = task
        persistent_results.register_task(task, idempotency_key=external_id)
        return task

    router.ManagedLocalServer.start = start
    router.RouterTaskRegistry.register = register

    original_submit_router_task = router.submit_router_task

    def task_from_manifest(manifest):
        return router.RouterTaskRecord(
            task_id=str(manifest["task_id"]),
            upstream_server_id=str(manifest["upstream_server_id"]),
            upstream_task_id=str(manifest["upstream_task_id"]),
            upstream_base_url=str(manifest["upstream_base_url"]),
            backend=str(manifest.get("backend", "pipeline")),
            file_names=list(manifest.get("source_filenames", [])),
            created_at=str(manifest["created_at"]),
            status=str(manifest.get("status", "pending")),
            started_at=manifest.get("started_at"),
            completed_at=manifest.get("completed_at"),
            error=manifest.get("error"),
        )

    async def existing_task(request, key):
        manifest = await asyncio.to_thread(
            persistent_results.find_or_alias_idempotency_key, key
        )
        registry = request.app.state.router_task_registry
        if manifest is None:
            # register_task may have accepted the upstream task and then
            # failed while publishing its shared-volume index. Reuse the
            # in-memory record and repair the durable mapping before any
            # second upstream POST.
            async with registry._lock:
                current = registry._tasks.get(key)
            if current is None:
                return None
            await asyncio.to_thread(
                persistent_results.register_task,
                current,
                idempotency_key=key,
            )
            return current
        async with registry._lock:
            current = registry._tasks.get(key)
            if current is None:
                current = task_from_manifest(manifest)
                registry._tasks[key] = current
            return current

    async def acquire_submit_lock(key):
        async with _submit_locks_guard:
            lock = _submit_locks.setdefault(key, asyncio.Lock())
            _submit_lock_references[key] = _submit_lock_references.get(key, 0) + 1
            return lock

    async def release_submit_lock(key, lock):
        async with _submit_locks_guard:
            remaining = _submit_lock_references[key] - 1
            if remaining:
                _submit_lock_references[key] = remaining
            elif not lock.locked():
                _submit_lock_references.pop(key, None)
                _submit_locks.pop(key, None)
            else:
                _submit_lock_references[key] = 0

    async def submit_router_task(request, payload):
        key = request.headers.get("Idempotency-Key")
        if key is None:
            return await original_submit_router_task(request, payload)
        if len(key) != 64 or any(char not in "0123456789abcdef" for char in key.lower()):
            raise router.HTTPException(
                status_code=400,
                detail="Idempotency-Key deve ser um SHA-256 hexadecimal.",
            )
        key = key.lower()
        if len(payload.uploads) != 1:
            raise router.HTTPException(status_code=400, detail="Idempotency-Key exige exatamente um arquivo.")
        upload = payload.uploads[0]
        upload_name = Path(upload.upload_name).name
        if upload_name != upload.upload_name or Path(upload_name).suffix.lower() != ".pdf" or Path(upload_name).stem.lower() != key:
            raise router.HTTPException(status_code=400, detail="Idempotency-Key deve coincidir com o stem SHA-256 do PDF.")
        actual_sha256 = await asyncio.to_thread(_file_sha256, Path(upload.path))
        if actual_sha256 != key:
            raise router.HTTPException(
                status_code=422,
                detail="Idempotency-Key não corresponde ao conteúdo do PDF.",
            )
        lock = await acquire_submit_lock(key)
        try:
            async with lock:
                current = await existing_task(request, key)
                if current is not None:
                    return current
                # Deliberately no pre-upstream durable reservation: there is
                # no transaction spanning this Volume and MinerU's upstream
                # POST. A reservation could survive a crash before POST and
                # falsely claim a task exists, blocking all future retries.
                # We fail closed on Volume errors instead of claiming that
                # such a distributed guarantee exists.
                token = _idempotency_key.set(key)
                try:
                    return await original_submit_router_task(request, payload)
                finally:
                    _idempotency_key.reset(token)
        except persistent_results.VolumeUnavailable as error:
            raise router.HTTPException(status_code=503, detail="Índice de idempotência indisponível; tente novamente.") from error
        finally:
            await release_submit_lock(key, lock)

    router.submit_router_task = submit_router_task

    original_create_app = router.create_app

    def create_app(settings=None):
        app = original_create_app(settings)

        @app.get("/persisted-tasks/{correlation_key}")
        async def get_persisted_tasks(correlation_key: str):
            try:
                tasks = persistent_results.find_by_correlation(correlation_key)
            except persistent_results.VolumeUnavailable as error:
                raise router.HTTPException(
                    status_code=503,
                    detail="Índice persistente indisponível; tente novamente.",
                ) from error
            if not tasks:
                raise router.HTTPException(status_code=404, detail="Persisted task not found")
            return {
                "correlation_key": correlation_key,
                "tasks": tasks,
            }

        return app

    router.create_app = create_app
    router._baseia_persistence_patch = True


def main() -> None:
    os.environ.setdefault("MINERU_PERSISTENT_RESULTS_ROOT", "/workspace/results")
    os.environ.setdefault("MINERU_LOCAL_WORK_ROOT", "/tmp/mineru-active")
    _patch_router()
    router.main()


if __name__ == "__main__":
    main()
