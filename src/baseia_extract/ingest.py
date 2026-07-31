"""Chunking local e ingestão vetorial configurável no Qdrant."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient, models

from .chunking import CHUNKER_VERSION, build_chunks
from .document_manifest import (
    document_storage_keys,
    write_document_manifest,
)
from .identity import canonical_json_sha256, collection_slug
from .ingest_models import IngestPolicy, load_ingest_policy
from .inventory_selection import select_inventory_rows
from .ir import DocumentIR
from .layout import DocumentLayout, document_layout
from .semantic_models import DocumentStructure
from .settings import settings
from .storage import file_sha256
from .structure import validate_structure

INGESTOR_VERSION = 1


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _collection_policy_path(collection_path: str) -> Path | None:
    raw_path = collection_path.strip()
    if not raw_path:
        return None
    root = Path(raw_path).expanduser().resolve()
    if root.is_file():
        root = root.parent
    config_path = root / "baseia.collection.yaml"
    if config_path.is_file():
        import yaml

        payload = yaml.safe_load(
            config_path.read_text(encoding="utf-8")
        )
        strategy = (
            payload.get("strategy")
            if isinstance(payload, Mapping)
            else None
        )
        configured = (
            strategy.get("ingest_policy")
            if isinstance(strategy, Mapping)
            else None
        )
        if isinstance(configured, str) and configured.strip():
            candidate = Path(configured.strip()).expanduser()
            if not candidate.is_absolute():
                candidate = config_path.parent / candidate
            resolved = candidate.resolve()
            if not resolved.is_file():
                raise FileNotFoundError(
                    "Política declarada em baseia.collection.yaml "
                    f"não encontrada: {resolved}"
                )
            return resolved
    conventional = root / ".baseia" / "embedding.yaml"
    return conventional.resolve() if conventional.is_file() else None


def _atomic_text(path: Path, content: str) -> None:
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
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    _atomic_text(
        path,
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )


def _atomic_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    _atomic_text(
        path,
        "".join(
            json.dumps(
                row,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
            for row in rows
        ),
    )


def _profile_slug(policy: IngestPolicy) -> str:
    return collection_slug(policy.name)


def _artifact_paths(
    layout: DocumentLayout,
    policy: IngestPolicy,
) -> tuple[Path, Path]:
    profile = _profile_slug(policy)
    return (
        layout.canonical_dir / "chunks" / f"{profile}.jsonl",
        layout.canonical_dir / "ingest" / f"{profile}.json",
    )


def _required_canonical_paths(
    layout: DocumentLayout,
) -> tuple[Path, ...]:
    return (
        layout.ir_path,
        layout.structure_path,
        layout.metadata_path,
        layout.markdown_path,
        layout.render_path,
    )


def _input_hashes(layout: DocumentLayout) -> dict[str, str]:
    paths = _required_canonical_paths(layout)
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Artefatos canônicos ausentes: "
            + ", ".join(str(path) for path in missing)
        )
    return {
        path.relative_to(layout.document_dir).as_posix(): file_sha256(path)
        for path in paths
    }


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} deve conter um objeto JSON.")
    return payload


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as source:
        for line_number, raw in enumerate(source, start=1):
            if not raw.strip():
                continue
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise TypeError(
                    f"{path}:{line_number} não contém um objeto JSON."
                )
            rows.append(payload)
    return rows


def _existing_manifest(layout: DocumentLayout) -> dict[str, Any] | None:
    try:
        payload = _load_json(layout.manifest_path)
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError):
        return None
    return payload


def _refresh_document_manifest(row: Mapping[str, Any]) -> None:
    layout = document_layout(row)
    existing = _existing_manifest(layout)
    stage_runs = (
        [
            item
            for item in existing.get("stage_runs", [])
            if isinstance(item, dict)
        ]
        if existing is not None
        and isinstance(existing.get("stage_runs"), list)
        else []
    )
    write_document_manifest(
        row,
        origin="stage",
        stage_runs=stage_runs,
        existing_manifest=existing,
    )


def _prepared_is_current(
    *,
    chunks_path: Path,
    ingest_path: Path,
    policy_hash: str,
    inputs: Mapping[str, str],
) -> bool:
    if not chunks_path.is_file() or not ingest_path.is_file():
        return False
    try:
        manifest = _load_json(ingest_path)
    except (OSError, json.JSONDecodeError, TypeError):
        return False
    return (
        manifest.get("ingestor_version") == INGESTOR_VERSION
        and manifest.get("chunker_version") == CHUNKER_VERSION
        and manifest.get("policy_hash") == policy_hash
        and manifest.get("input_hashes") == dict(inputs)
        and manifest.get("chunks_sha256") == file_sha256(chunks_path)
        and manifest.get("status") in {"prepared", "complete"}
    )


def _metadata_review(metadata: Mapping[str, Any]) -> dict[str, Any]:
    attributes = metadata.get("attributes")
    if not isinstance(attributes, Mapping):
        return {}
    review = attributes.get("review")
    return dict(review) if isinstance(review, Mapping) else {}


def _prepare_one(
    row: dict[str, Any],
    *,
    policy: IngestPolicy,
    policy_hash: str,
    overwrite: bool,
) -> dict[str, Any]:
    document_id = str(row["document_id"])
    layout = document_layout(row)
    chunks_path, ingest_path = _artifact_paths(layout, policy)
    try:
        inputs = _input_hashes(layout)
        if not overwrite and _prepared_is_current(
            chunks_path=chunks_path,
            ingest_path=ingest_path,
            policy_hash=policy_hash,
            inputs=inputs,
        ):
            chunks = _load_jsonl(chunks_path)
            metadata = _load_json(layout.metadata_path)
            return {
                "document_id": document_id,
                "status": "skipped",
                "chunks_path": str(chunks_path),
                "ingest_path": str(ingest_path),
                "metadata_review": _metadata_review(metadata),
                "chunks": chunks,
                "row": row,
            }

        document = DocumentIR.model_validate_json(
            layout.ir_path.read_text(encoding="utf-8")
        )
        structure = DocumentStructure.model_validate_json(
            layout.structure_path.read_text(encoding="utf-8")
        )
        structure_validation = validate_structure(document, structure)
        if not structure_validation["valid"]:
            raise ValueError(
                "Estrutura inválida: "
                f"{structure_validation['checks']}"
            )
        metadata = _load_json(layout.metadata_path)
        middle_path = Path(document.source_path)
        asset_root = (
            middle_path.parent
            if middle_path.is_file()
            else layout.mineru_dir
        )
        chunks = build_chunks(
            revision_id=str(row["revision_id"]),
            document=document,
            structure=structure,
            policy=policy,
            metadata=metadata,
            markdown_path=layout.markdown_path,
            asset_root=asset_root,
        )
        if not chunks:
            raise ValueError(
                "A política não produziu nenhum chunk textual."
            )
        source_key, artifact_prefix = document_storage_keys(row)
        bucket = os.getenv("BASEIA_S3_BUCKET", "").strip()
        for chunk in chunks:
            chunk.update(
                collection=str(row["collection"]),
                collection_slug=str(row["collection_slug"]),
                relative_path=str(row["collection_relative_path"]),
                source_pdf={
                    "object_key": source_key,
                    "bucket": bucket or None,
                    "uri": (
                        f"s3://{bucket}/{source_key}" if bucket else None
                    ),
                },
                artifact_prefix=artifact_prefix,
            )
        _atomic_jsonl(chunks_path, chunks)
        missing_assets = [
            asset["asset_id"]
            for chunk in chunks
            for asset in chunk.get("assets", [])
            if asset.get("missing")
        ]
        asset_payloads = [
            asset
            for chunk in chunks
            for asset in chunk.get("assets", [])
        ]
        manifest = {
            "schema_version": 1,
            "ingestor_version": INGESTOR_VERSION,
            "chunker_version": CHUNKER_VERSION,
            "document_id": document_id,
            "revision_id": str(row["revision_id"]),
            "profile": policy.name,
            "policy_hash": policy_hash,
            "input_hashes": inputs,
            "chunks_path": (
                chunks_path.relative_to(layout.document_dir).as_posix()
            ),
            "chunks_sha256": file_sha256(chunks_path),
            "chunks_bytes": chunks_path.stat().st_size,
            "chunk_count": len(chunks),
            "asset_payload_count": len(asset_payloads),
            "unique_asset_count": len(
                {
                    str(asset["asset_id"])
                    for asset in asset_payloads
                }
            ),
            "base64_payload_count": sum(
                bool(asset.get("data_base64"))
                for asset in asset_payloads
            ),
            "base64_characters": sum(
                len(str(asset.get("data_base64") or ""))
                for asset in asset_payloads
            ),
            "missing_asset_ids": missing_assets,
            "metadata_review": _metadata_review(metadata),
            "embedding": policy.embedding.model_dump(mode="json"),
            "qdrant": {
                "collection": policy.qdrant.collection,
                "distance": policy.qdrant.distance,
            },
            "status": "prepared",
            "prepared_at": _now(),
        }
        _atomic_json(ingest_path, manifest)
        _refresh_document_manifest(row)
        return {
            "document_id": document_id,
            "status": "prepared",
            "chunks_path": str(chunks_path),
            "ingest_path": str(ingest_path),
            "metadata_review": _metadata_review(metadata),
            "chunks": chunks,
            "row": row,
        }
    except Exception as error:
        return {
            "document_id": document_id,
            "status": "failed",
            "reason": f"{type(error).__name__}: {error}",
            "row": row,
        }


def _selected_rows(
    *,
    inventory_path: Path,
    collection: str,
    collection_path: str,
) -> list[dict[str, Any]]:
    return select_inventory_rows(
        inventory_path,
        collection=collection,
        collection_path=collection_path,
    )


def _embedding_client(policy: IngestPolicy) -> OpenAIEmbeddings:
    key = os.getenv(policy.embedding.api_key_env, "").strip()
    if not key:
        raise RuntimeError(
            "Credencial OpenRouter ausente na variável "
            f"{policy.embedding.api_key_env}."
        )
    return OpenAIEmbeddings(
        model=policy.embedding.model,
        dimensions=policy.embedding.dimensions,
        api_key=key,
        base_url=policy.embedding.base_url,
        chunk_size=policy.embedding.batch_size,
        max_retries=policy.embedding.max_retries,
        retry_min_seconds=max(
            1,
            int(policy.embedding.retry_min_seconds),
        ),
        retry_max_seconds=max(
            1,
            int(policy.embedding.retry_max_seconds),
        ),
        request_timeout=120,
        check_embedding_ctx_length=False,
        model_kwargs={"encoding_format": "float"},
    )


def _qdrant_client(
    policy: IngestPolicy,
    *,
    qdrant_url: str,
) -> QdrantClient:
    resolved_url = (
        qdrant_url.strip()
        or policy.qdrant.url.strip()
        or os.getenv("QDRANT_URL", "").strip()
    )
    if not resolved_url:
        raise RuntimeError(
            "Informe --qdrant-url, qdrant.url na política ou QDRANT_URL."
        )
    api_key = os.getenv(policy.qdrant.api_key_env, "").strip() or None
    return QdrantClient(
        url=resolved_url,
        api_key=api_key,
        timeout=120,
    )


def _vector_params(info: Any) -> models.VectorParams:
    vectors = info.config.params.vectors
    if isinstance(vectors, dict):
        if "" not in vectors:
            raise ValueError(
                "A coleção Qdrant não possui vetor denso sem nome."
            )
        return vectors[""]
    if not isinstance(vectors, models.VectorParams):
        raise TypeError("Configuração vetorial Qdrant inválida.")
    return vectors


def _ensure_collection(
    client: QdrantClient,
    policy: IngestPolicy,
    *,
    actual_dimensions: int,
) -> None:
    collection_name = policy.qdrant.collection
    if not client.collection_exists(collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=actual_dimensions,
                distance=models.Distance.COSINE,
            ),
            on_disk_payload=policy.qdrant.on_disk_payload,
        )
    params = _vector_params(client.get_collection(collection_name))
    if int(params.size) != actual_dimensions:
        raise ValueError(
            f"Coleção {collection_name!r} usa {params.size} dimensões; "
            f"a política exige {actual_dimensions}."
        )
    if params.distance != models.Distance.COSINE:
        raise ValueError(
            f"Coleção {collection_name!r} não usa distância COSINE."
        )
    for field_name in (
        "metadata.document_id",
        "metadata.collection_slug",
        "metadata.policy.name",
    ):
        try:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=models.PayloadSchemaType.KEYWORD,
                wait=True,
            )
        except Exception as error:
            # Versões standalone antigas podem não suportar índice aninhado.
            if "already exists" not in str(error).casefold():
                raise


def _document_filter(
    *,
    document_id: str,
    profile: str,
) -> models.Filter:
    return models.Filter(
        must=[
            models.FieldCondition(
                key="metadata.document_id",
                match=models.MatchValue(value=document_id),
            ),
            models.FieldCondition(
                key="metadata.policy.name",
                match=models.MatchValue(value=profile),
            ),
        ]
    )


def _existing_point_ids(
    client: QdrantClient,
    *,
    collection_name: str,
    document_id: str,
    profile: str,
) -> set[str]:
    result: set[str] = set()
    offset: Any = None
    while True:
        records, offset = client.scroll(
            collection_name=collection_name,
            scroll_filter=_document_filter(
                document_id=document_id,
                profile=profile,
            ),
            limit=256,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        result.update(str(record.id) for record in records)
        if offset is None:
            return result


def _mark_complete(
    prepared: dict[str, Any],
    *,
    policy: IngestPolicy,
    point_ids: list[str],
    stale_deleted: int,
) -> None:
    ingest_path = Path(str(prepared["ingest_path"]))
    payload = _load_json(ingest_path)
    payload.update(
        status="complete",
        completed_at=_now(),
        qdrant={
            **dict(payload.get("qdrant") or {}),
            "collection": policy.qdrant.collection,
            "point_count": len(point_ids),
            "stale_points_deleted": stale_deleted,
        },
        point_ids=point_ids,
    )
    _atomic_json(ingest_path, payload)
    _refresh_document_manifest(prepared["row"])


def _apply_prepared(
    prepared_documents: list[dict[str, Any]],
    *,
    policy: IngestPolicy,
    qdrant_url: str,
) -> list[dict[str, Any]]:
    embeddings = _embedding_client(policy)
    probe = embeddings.embed_query("BaseIA embedding dimension probe")
    actual_dimensions = len(probe)
    if actual_dimensions != policy.embedding.dimensions:
        raise ValueError(
            f"OpenRouter retornou {actual_dimensions} dimensões; "
            f"a política exige {policy.embedding.dimensions}."
        )
    client = _qdrant_client(policy, qdrant_url=qdrant_url)
    try:
        _ensure_collection(
            client,
            policy,
            actual_dimensions=actual_dimensions,
        )
        store = QdrantVectorStore(
            client=client,
            collection_name=policy.qdrant.collection,
            embedding=embeddings,
            validate_collection_config=False,
        )
        results: list[dict[str, Any]] = []
        for prepared in prepared_documents:
            if prepared["status"] == "failed":
                results.append(prepared)
                continue
            chunks = list(prepared["chunks"])
            expected = [str(chunk["chunk_id"]) for chunk in chunks]
            try:
                existing = _existing_point_ids(
                    client,
                    collection_name=policy.qdrant.collection,
                    document_id=str(prepared["document_id"]),
                    profile=policy.name,
                )
                added = store.add_texts(
                    texts=[str(chunk["text"]) for chunk in chunks],
                    metadatas=[
                        {
                            key: value
                            for key, value in chunk.items()
                            if key != "text"
                        }
                        for chunk in chunks
                    ],
                    ids=expected,
                    batch_size=policy.embedding.batch_size,
                    wait=True,
                )
                stale = (
                    existing - set(expected)
                    if policy.qdrant.replace_documents
                    else set()
                )
                if stale:
                    client.delete(
                        collection_name=policy.qdrant.collection,
                        points_selector=models.PointIdsList(
                            points=sorted(stale)
                        ),
                        wait=True,
                    )
                point_ids = [str(item) for item in added]
                _mark_complete(
                    prepared,
                    policy=policy,
                    point_ids=point_ids,
                    stale_deleted=len(stale),
                )
                results.append(
                    {
                        **prepared,
                        "status": "complete",
                        "point_count": len(point_ids),
                        "stale_points_deleted": len(stale),
                    }
                )
            except Exception as error:
                results.append(
                    {
                        **prepared,
                        "status": "failed",
                        "reason": f"{type(error).__name__}: {error}",
                    }
                )
        return results
    finally:
        client.close()


def ingest(
    action: str = "prepare",
    policy_path: str = "",
    inventory: str = "",
    collection: str = "",
    collection_path: str = "",
    qdrant_url: str = "",
    workers: int = 3,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Prepara chunks locais ou aplica embeddings/upserts no Qdrant."""
    normalized_action = action.strip().casefold() or "prepare"
    if normalized_action not in {"prepare", "apply"}:
        raise ValueError("Ação inválida. Use prepare ou apply.")
    discovered_policy = _collection_policy_path(collection_path)
    raw_policy_path = policy_path.strip() or (
        str(discovered_policy) if discovered_policy is not None else ""
    ) or os.getenv("BASEIA_INGEST_POLICY", "").strip()
    if not raw_policy_path:
        raise ValueError(
            "Informe --policy, grave .baseia/embedding.yaml sob --path "
            "ou defina BASEIA_INGEST_POLICY."
        )
    resolved_policy_path = Path(raw_policy_path).expanduser().resolve()
    policy = load_ingest_policy(resolved_policy_path)
    policy_hash = canonical_json_sha256(
        policy.model_dump(mode="json")
    )
    inventory_path = (
        Path(inventory).expanduser().resolve()
        if inventory.strip()
        else settings.inventory_path
    )
    rows = _selected_rows(
        inventory_path=inventory_path,
        collection=collection,
        collection_path=collection_path,
    )
    resolved_workers = max(1, workers)
    prepared: list[dict[str, Any] | None] = [None] * len(rows)
    with ThreadPoolExecutor(max_workers=resolved_workers) as executor:
        futures = {
            executor.submit(
                _prepare_one,
                row,
                policy=policy,
                policy_hash=policy_hash,
                overwrite=overwrite,
            ): index
            for index, row in enumerate(rows)
        }
        for future in as_completed(futures):
            index = futures[future]
            prepared[index] = future.result()
    prepared_documents = [
        item for item in prepared if item is not None
    ]
    if normalized_action == "apply" and not any(
        item["status"] == "failed" for item in prepared_documents
    ):
        try:
            results = _apply_prepared(
                prepared_documents,
                policy=policy,
                qdrant_url=qdrant_url,
            )
        except Exception as error:
            results = [
                {
                    **item,
                    "status": "failed",
                    "reason": f"{type(error).__name__}: {error}",
                }
                for item in prepared_documents
            ]
    else:
        results = prepared_documents
    counts = Counter(str(item["status"]) for item in results)
    serializable_documents = [
        {
            key: value
            for key, value in item.items()
            if key not in {"chunks", "row"}
        }
        for item in results
    ]
    review_documents = [
        {
            "document_id": item["document_id"],
            "relative_path": item.get("row", {}).get(
                "collection_relative_path"
            ),
            "review": item["metadata_review"],
        }
        for item in results
        if item.get("metadata_review")
    ]
    summary = {
        "schema_version": 1,
        "ingestor_version": INGESTOR_VERSION,
        "generated_at": _now(),
        "action": normalized_action,
        "inventory_path": str(inventory_path),
        "collection": collection or None,
        "policy_path": str(resolved_policy_path),
        "policy": policy.model_dump(mode="json"),
        "policy_hash": policy_hash,
        "counts": dict(sorted(counts.items())),
        "metadata_review": {
            "required_documents": len(review_documents),
            "documents": review_documents,
        },
        "documents": serializable_documents,
    }
    summary_path = (
        settings.data_dir
        / "ingest"
        / f"{_profile_slug(policy)}-{normalized_action}.json"
    )
    _atomic_json(summary_path, summary)
    print(
        "Ingestão "
        f"{normalized_action}: "
        + ", ".join(
            f"{status}={count}"
            for status, count in sorted(counts.items())
        ),
        flush=True,
    )
    print(f"Resumo: {summary_path}", flush=True)
    if counts.get("failed"):
        raise RuntimeError(
            f"A ingestão falhou em {counts['failed']} documento(s). "
            f"Consulte {summary_path}."
        )
    return summary


__all__ = ["INGESTOR_VERSION", "ingest"]
