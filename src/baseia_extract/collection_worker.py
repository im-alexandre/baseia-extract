from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .audit import audit_extraction, audit_inventory
from .bootstrap_s3 import promote_s3
from .collection import (
    STAGES,
    _inventory_fingerprint,
    load_collection_config,
    rebuild_collection_inventory,
)
from .ingest import ingest
from .render import render
from .settings import settings
from .tasks import run_extract


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
            newline="\n",
        ) as handle:
            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _ensure_success(summary: dict[str, Any], *, stage: str) -> None:
    failed = int(summary.get("failed", 0))
    if failed:
        raise RuntimeError(
            f"A auditoria de {stage} encontrou {failed} documento(s) "
            "com falha. Consulte o diretório de auditoria antes de continuar."
        )


def _ingest_policy_path(
    *,
    config_path: Path,
    configured: str,
) -> Path | None:
    value = (
        os.getenv("BASEIA_INGEST_POLICY", "").strip()
        or configured.strip()
    )
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = config_path.parent / path
    return path.resolve()


def run(
    *,
    config_path: Path,
    through: str,
    workers: int,
    api_urls: tuple[str, ...],
    sample: bool = False,
) -> dict[str, Any]:
    if through not in STAGES:
        raise ValueError(f"Etapa inválida: {through!r}")
    loaded = load_collection_config(config_path)
    if settings.data_dir.resolve() != loaded.state_dir.resolve():
        raise RuntimeError(
            "O worker foi iniciado fora do contexto da coleção: "
            f"BASEIA_DATA_DIR={settings.data_dir}, "
            f"esperado={loaded.state_dir}."
        )
    if not loaded.inventory_path.is_file():
        rebuild_collection_inventory(loaded, workers=workers)
    selected_inventory = (
        loaded.state_dir / "inventory" / "sample.csv"
        if sample
        else loaded.inventory_path
    )
    if sample and not selected_inventory.is_file():
        raise FileNotFoundError(
            "Amostra ausente. Execute `poe sample --collection NOME` "
            "antes de usar `poe pipeline --sample`."
        )
    if sample and through == "promote":
        raise ValueError(
            "Uma seleção de amostra não pode substituir o snapshot ativo "
            "da coleção. Crie uma coleção própria para promover esse "
            "conjunto ou execute sem --sample."
        )

    started_at = _now()
    results: dict[str, Any] = {}
    inventory_summary = audit_inventory(selected_inventory)
    results["inventory"] = inventory_summary
    if int(inventory_summary["invalid_rows"]):
        raise RuntimeError(
            "O pipeline não continua com documentos inválidos: "
            f"{inventory_summary['invalid_rows']} ocorrência(s)."
        )

    target_index = STAGES.index(through)
    resolved_urls = (
        api_urls
        or tuple(loaded.config.services.mineru_api_urls)
        or (settings.mineru_api_url,)
    )
    if target_index >= STAGES.index("extract"):
        results["extract"] = run_extract(
            api_urls=resolved_urls,
            workers=workers,
            sample=sample,
        )
        extraction_audit = audit_extraction(
            require_render=False,
            inventory_path=selected_inventory,
        )
        _ensure_success(extraction_audit, stage="extração")
        results["extract_audit"] = extraction_audit

    if target_index >= STAGES.index("render"):
        results["render"] = render(
            workers=workers,
            inventory_path=selected_inventory,
        )
        render_audit = audit_extraction(
            require_render=True,
            inventory_path=selected_inventory,
        )
        _ensure_success(render_audit, stage="render")
        results["render_audit"] = render_audit

    policy_path = _ingest_policy_path(
        config_path=config_path,
        configured=loaded.config.strategy.ingest_policy,
    )
    should_ingest = target_index >= STAGES.index("ingest")
    if should_ingest and policy_path is None:
        raise RuntimeError(
            "As etapas ingest e promote exigem strategy.ingest_policy "
            "no YAML da coleção ou BASEIA_INGEST_POLICY. A promoção não "
            "pode anteceder a ingestão vetorial."
        )
    if should_ingest:
        results["ingest"] = ingest(
            "apply",
            policy_path=str(policy_path),
            inventory=str(selected_inventory),
            collection=loaded.config.name,
            qdrant_url=loaded.config.services.qdrant_url,
            workers=workers,
        )

    if target_index >= STAGES.index("promote"):
        results["promotion"] = promote_s3(
            "apply",
            inventory=str(loaded.inventory_path),
            scope=loaded.config.slug,
        )

    collection_inventory = pd.read_csv(
        loaded.inventory_path,
        dtype=str,
        keep_default_na=False,
    )
    selected_inventory_frame = (
        pd.read_csv(
            selected_inventory,
            dtype=str,
            keep_default_na=False,
        )
        if sample
        else collection_inventory
    )
    collection_fingerprint = _inventory_fingerprint(collection_inventory)
    report = {
        "schema_version": 1,
        "collection_id": loaded.config.id,
        "collection": loaded.config.name,
        "collection_slug": loaded.config.slug,
        "through": through,
        "selection": "sample" if sample else "collection",
        # Mantido como fingerprint da coleção para compatibilidade com a
        # detecção de snapshots promovidos.
        "inventory_fingerprint": collection_fingerprint,
        "collection_inventory_fingerprint": collection_fingerprint,
        "selection_inventory_fingerprint": _inventory_fingerprint(
            selected_inventory_frame
        ),
        "started_at": started_at,
        "completed_at": _now(),
        "results": results,
        "next_stage": {
            "name": (
                "promote"
                if through == "ingest"
                else None
            ),
            "available": through == "ingest",
            "reason": (
                "O próximo checkpoint publica os artefatos já "
                "embeddados no S3/catálogo."
                if through == "ingest"
                else None
            ),
        },
    }
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    reports_dir = loaded.state_dir / "pipeline" / "runs"
    report_path = reports_dir / f"{timestamp}.json"
    _atomic_json(report_path, report)
    _atomic_json(loaded.state_dir / "pipeline" / "latest.json", report)
    print(f"Pipeline concluído até {through}: {report_path}", flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Worker interno do pipeline de uma coleção BaseIA."
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--through", required=True, choices=STAGES)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--sample", action="store_true")
    parser.add_argument(
        "--api-url",
        action="append",
        default=[],
        dest="api_urls",
    )
    arguments = parser.parse_args()
    if arguments.workers < 1:
        parser.error("--workers deve ser maior que zero.")
    run(
        config_path=arguments.config.expanduser().resolve(),
        through=arguments.through,
        workers=arguments.workers,
        api_urls=tuple(arguments.api_urls),
        sample=arguments.sample,
    )


if __name__ == "__main__":
    main()
