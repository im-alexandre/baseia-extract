"""Small HTTP adapter for the BaseIA catalog.

The GPU image keeps this adapter separate from MinerU internals.  If
``BASEIA_CATALOG_API_URL`` is unset, catalog integration is disabled and the
result publisher still commits to its configured artifact store.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


class CatalogUnavailable(RuntimeError):
    pass


def enabled() -> bool:
    return bool(os.environ.get("BASEIA_CATALOG_API_URL", "").strip())


def _request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_url = os.environ.get("BASEIA_CATALOG_API_URL", "").strip().rstrip("/")
    if not base_url:
        raise CatalogUnavailable("BASEIA_CATALOG_API_URL não configurada.")
    body = (
        json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if payload is not None
        else None
    )
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    token = os.environ.get("BASEIA_CATALOG_API_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{base_url}/{path.lstrip('/')}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:2000]
        if error.code >= 500:
            raise CatalogUnavailable(
                f"Catálogo respondeu HTTP {error.code}: {detail}"
            ) from error
        raise RuntimeError(
            f"Catálogo rejeitou HTTP {error.code}: {detail}"
        ) from error
    except (
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
    ) as error:
        raise CatalogUnavailable(
            f"Catálogo indisponível: {type(error).__name__}: {error}"
        ) from error
    if not isinstance(value, dict):
        raise CatalogUnavailable("Catálogo retornou JSON inválido.")
    return value


def _retry(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    for attempt in Retrying(
        retry=retry_if_exception_type(CatalogUnavailable),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(5),
        reraise=True,
    ):
        with attempt:
            return _request(method, path, payload)
    raise AssertionError("Retry do catálogo terminou inesperadamente.")


def get_or_create_stage_run(metadata: dict[str, str]) -> dict[str, Any] | None:
    if not enabled():
        return None
    return _retry(
        "POST",
        "/v1/stage-runs/get-or-create",
        {
            "document_revision_id": metadata["document_revision_id"],
            "stage": metadata["stage"],
            "processor": metadata["processor"],
            "processor_version": metadata["processor_version"],
            "config_hash": metadata["config_hash"],
            "input_hashes": [metadata["content_sha256"]],
            "idempotency_key": metadata["idempotency_key"],
            "lease_owner": metadata["lease_owner"],
            "lease_seconds": int(
                os.environ.get("BASEIA_STAGE_LEASE_SECONDS", "7200")
            ),
        },
    )


def get_stage_run(idempotency_key: str) -> dict[str, Any] | None:
    if not enabled():
        return None
    try:
        return _retry(
            "GET",
            f"/v1/stage-runs/by-idempotency/{idempotency_key}",
        )
    except RuntimeError as error:
        if "HTTP 404" in str(error):
            return None
        raise


def transition(
    stage_run_id: str | None,
    status: str,
    *,
    lease_owner: str,
    lease_attempt: int,
) -> None:
    if not enabled() or not stage_run_id:
        return
    _retry(
        "POST",
        f"/v1/stage-runs/{stage_run_id}/status",
        {
            "status": status,
            "lease_owner": lease_owner,
            "lease_attempt": lease_attempt,
            "lease_seconds": int(
                os.environ.get("BASEIA_STAGE_LEASE_SECONDS", "7200")
            ),
        },
    )


def heartbeat(
    stage_run_id: str | None,
    *,
    lease_owner: str,
    lease_attempt: int,
) -> None:
    if not enabled() or not stage_run_id:
        return
    _retry(
        "POST",
        f"/v1/stage-runs/{stage_run_id}/heartbeat",
        {
            "lease_owner": lease_owner,
            "lease_attempt": lease_attempt,
            "lease_seconds": int(
                os.environ.get("BASEIA_STAGE_LEASE_SECONDS", "7200")
            ),
        },
    )


def complete(
    stage_run_id: str | None,
    artifacts: list[dict[str, Any]],
    *,
    lease_owner: str,
    lease_attempt: int,
) -> None:
    if not enabled() or not stage_run_id:
        return
    _retry(
        "POST",
        f"/v1/stage-runs/{stage_run_id}/complete",
        {
            "artifacts": artifacts,
            "lease_owner": lease_owner,
            "lease_attempt": lease_attempt,
        },
    )


def fail(
    stage_run_id: str | None,
    *,
    error_type: str,
    message: str,
    retryable: bool,
    lease_owner: str,
    lease_attempt: int,
) -> None:
    if not enabled() or not stage_run_id:
        return
    _retry(
        "POST",
        f"/v1/stage-runs/{stage_run_id}/fail",
        {
            "error_type": error_type,
            "message": message,
            "retryable": retryable,
            "lease_owner": lease_owner,
            "lease_attempt": lease_attempt,
        },
    )
