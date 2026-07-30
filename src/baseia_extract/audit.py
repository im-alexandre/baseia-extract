from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .layout import document_layout
from .schemas import ExtractionManifest
from .settings import settings


KNOWN_BLOCK_TYPES = {
    "abstract",
    "aside_text",
    "chart",
    "code",
    "footer",
    "header",
    "image",
    "interline_equation",
    "list",
    "page_footnote",
    "page_number",
    "ref_text",
    "table",
    "text",
    "title",
}

KNOWN_SPAN_TYPES = {
    "inline_equation",
    "interline_equation",
    "text",
}

ASSET_BLOCK_TYPES = {
    "chart",
    "code",
    "image",
    "interline_equation",
    "table",
}

REQUIRED_INVENTORY_COLUMNS = {
    "document_id",
    "sha256",
    "path",
    "filename",
    "relative_path",
    "page_count",
    "status",
}


@dataclass(slots=True)
class SchemaCounts:
    root_keys: Counter[str] = field(default_factory=Counter)
    page_keys: Counter[str] = field(default_factory=Counter)
    block_keys: Counter[str] = field(default_factory=Counter)
    line_keys: Counter[str] = field(default_factory=Counter)
    span_keys: Counter[str] = field(default_factory=Counter)
    block_types: Counter[str] = field(default_factory=Counter)
    span_types: Counter[str] = field(default_factory=Counter)

    def merge(self, other: "SchemaCounts") -> None:
        self.root_keys.update(other.root_keys)
        self.page_keys.update(other.page_keys)
        self.block_keys.update(other.block_keys)
        self.line_keys.update(other.line_keys)
        self.span_keys.update(other.span_keys)
        self.block_types.update(other.block_types)
        self.span_types.update(other.span_types)

    def as_dict(self) -> dict[str, dict[str, int]]:
        return {
            "root_keys": dict(self.root_keys.most_common()),
            "page_keys": dict(self.page_keys.most_common()),
            "block_keys": dict(self.block_keys.most_common()),
            "line_keys": dict(self.line_keys.most_common()),
            "span_keys": dict(self.span_keys.most_common()),
            "block_types": dict(self.block_types.most_common()),
            "span_types": dict(self.span_types.most_common()),
        }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_frame(frame: pd.DataFrame, csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")

    try:
        frame.to_parquet(csv_path.with_suffix(".parquet"), index=False)
    except (ImportError, ValueError, TypeError):
        pass


def _normalized_string(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _page_count(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _extract_pages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("pdf_info", "pages", "page_info"):
        candidate = payload.get(key)
        if isinstance(candidate, list):
            return [page for page in candidate if isinstance(page, dict)]

    if any(
        key in payload
        for key in ("para_blocks", "discarded_blocks", "preproc_blocks")
    ):
        return [payload]

    raise ValueError(
        "Não foi possível localizar páginas em pdf_info, pages ou page_info."
    )


def _iter_container(
    page: dict[str, Any],
    key: str,
) -> Iterable[dict[str, Any]]:
    value = page.get(key, [])
    if not isinstance(value, list):
        raise TypeError(f"{key} não é uma lista.")
    return (item for item in value if isinstance(item, dict))


def _inspect_block(
    block: dict[str, Any],
    schema: SchemaCounts,
    *,
    count_text: bool,
) -> dict[str, int]:
    schema.block_keys.update(block.keys())

    block_type = str(
        block.get("type")
        or block.get("block_type")
        or "unknown"
    )
    schema.block_types[block_type] += 1

    text_chars = 0
    line_count = 0
    span_count = 0

    lines = block.get("lines", [])
    if not isinstance(lines, list):
        raise TypeError("lines não é uma lista.")

    for line in lines:
        if not isinstance(line, dict):
            continue

        line_count += 1
        schema.line_keys.update(line.keys())

        spans = line.get("spans", [])
        if not isinstance(spans, list):
            raise TypeError("spans não é uma lista.")

        for span in spans:
            if not isinstance(span, dict):
                continue

            span_count += 1
            schema.span_keys.update(span.keys())

            span_type = str(span.get("type") or "unknown")
            schema.span_types[span_type] += 1

            if count_text:
                text = span.get("text")
                if text is None:
                    text = span.get("content")
                if isinstance(text, str):
                    text_chars += len(text)

    return {
        "text_chars": text_chars,
        "line_count": line_count,
        "span_count": span_count,
        "asset_count": int(
            block_type in ASSET_BLOCK_TYPES
            or bool(block.get("image_path"))
            or bool(block.get("html"))
            or bool(block.get("latex"))
        ),
    }


def _inspect_middle(
    middle_path: Path,
    expected_pages: int | None,
    schema: SchemaCounts,
) -> tuple[dict[str, Any], list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []
    document_schema = SchemaCounts()

    metrics: dict[str, Any] = {
        "middle_path": str(middle_path),
        "middle_size_bytes": middle_path.stat().st_size,
        "json_valid": False,
        "extracted_pages": None,
        "content_blocks": None,
        "discarded_blocks": None,
        "preproc_blocks": None,
        "line_count": None,
        "span_count": None,
        "text_chars": None,
        "asset_count": None,
        "empty_pages": None,
        "textless_pages": None,
        "empty_page_ratio": None,
        "unknown_block_types": "",
        "unknown_span_types": "",
    }

    try:
        payload = json.loads(middle_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        failures.append(f"invalid_json:{type(error).__name__}")
        return metrics, failures, warnings

    if not isinstance(payload, dict):
        failures.append("invalid_root")
        return metrics, failures, warnings

    metrics["json_valid"] = True
    document_schema.root_keys.update(payload.keys())

    try:
        pages = _extract_pages(payload)
    except (TypeError, ValueError) as error:
        failures.append(f"pages_not_found:{error}")
        return metrics, failures, warnings

    extracted_pages = len(pages)
    metrics["extracted_pages"] = extracted_pages

    if extracted_pages == 0:
        failures.append("zero_pages")

    if expected_pages is not None and extracted_pages != expected_pages:
        failures.append(
            f"page_count_mismatch:{expected_pages}!={extracted_pages}"
        )

    content_blocks = 0
    discarded_blocks = 0
    preproc_blocks = 0
    line_count = 0
    span_count = 0
    text_chars = 0
    asset_count = 0
    empty_pages = 0
    textless_pages = 0

    for page in pages:
        document_schema.page_keys.update(page.keys())

        page_blocks = 0
        page_text_chars = 0

        for key, count_text in (
            ("para_blocks", True),
            ("discarded_blocks", True),
            ("preproc_blocks", False),
        ):
            try:
                blocks = list(_iter_container(page, key))
            except TypeError as error:
                failures.append(f"invalid_{key}:{error}")
                blocks = []

            if key == "para_blocks":
                content_blocks += len(blocks)
            elif key == "discarded_blocks":
                discarded_blocks += len(blocks)
            else:
                preproc_blocks += len(blocks)

            page_blocks += len(blocks)

            for block in blocks:
                try:
                    block_metrics = _inspect_block(
                        block,
                        document_schema,
                        count_text=count_text,
                    )
                except TypeError as error:
                    failures.append(f"invalid_block_structure:{error}")
                    continue

                line_count += block_metrics["line_count"]
                span_count += block_metrics["span_count"]
                asset_count += block_metrics["asset_count"]

                if count_text:
                    text_chars += block_metrics["text_chars"]
                    page_text_chars += block_metrics["text_chars"]

        if page_blocks == 0:
            empty_pages += 1

        if page_text_chars == 0:
            textless_pages += 1

    metrics.update(
        {
            "content_blocks": content_blocks,
            "discarded_blocks": discarded_blocks,
            "preproc_blocks": preproc_blocks,
            "line_count": line_count,
            "span_count": span_count,
            "text_chars": text_chars,
            "asset_count": asset_count,
            "empty_pages": empty_pages,
            "textless_pages": textless_pages,
            "empty_page_ratio": (
                round(textless_pages / extracted_pages, 6)
                if extracted_pages
                else None
            ),
        }
    )

    if content_blocks + discarded_blocks + preproc_blocks == 0:
        failures.append("no_blocks")

    if text_chars == 0:
        if asset_count:
            warnings.append("no_text_with_assets")
        else:
            failures.append("no_text_or_assets")

    if (
        extracted_pages
        and textless_pages / extracted_pages
        >= settings.audit_textless_page_warn_ratio
    ):
        warnings.append("high_textless_page_ratio")

    if middle_path.stat().st_size < settings.audit_min_middle_bytes:
        warnings.append("small_middle_json")

    unknown_block_types = sorted(
        block_type
        for block_type in document_schema.block_types
        if block_type not in KNOWN_BLOCK_TYPES
    )
    unknown_span_types = sorted(
        span_type
        for span_type in document_schema.span_types
        if span_type not in KNOWN_SPAN_TYPES
    )

    metrics["unknown_block_types"] = "|".join(unknown_block_types)
    metrics["unknown_span_types"] = "|".join(unknown_span_types)

    if unknown_block_types:
        warnings.append("unknown_block_types")
    if unknown_span_types:
        warnings.append("unknown_span_types")

    schema.merge(document_schema)
    return metrics, failures, warnings


def _load_runs() -> pd.DataFrame:
    path = settings.extraction_dir / "runs.csv"
    if not path.exists():
        return pd.DataFrame()

    runs = pd.read_csv(path)
    if "document_id" not in runs.columns:
        return pd.DataFrame()

    runs["document_id"] = runs["document_id"].map(_normalized_string)
    runs = runs[runs["document_id"].ne("")].copy()
    return runs.drop_duplicates("document_id", keep="last")


def audit_inventory() -> dict[str, Any]:
    if not settings.inventory_path.exists():
        raise FileNotFoundError(
            f"Manifesto não encontrado: {settings.inventory_path}"
        )

    inventory = pd.read_csv(settings.inventory_path)
    missing_columns = REQUIRED_INVENTORY_COLUMNS.difference(inventory.columns)
    if missing_columns:
        raise ValueError(
            f"Colunas ausentes no inventário: {sorted(missing_columns)}"
        )

    inventory = inventory.copy()
    inventory["document_id"] = inventory["document_id"].map(
        _normalized_string
    )
    inventory["sha256"] = inventory["sha256"].map(_normalized_string)
    inventory["path_exists"] = inventory["path"].map(
        lambda value: Path(str(value)).expanduser().is_file()
    )
    inventory["page_count_valid"] = inventory["page_count"].map(
        lambda value: (_page_count(value) or 0) > 0
    )

    invalid_mask = (
        inventory["document_id"].eq("")
        | inventory["sha256"].eq("")
        | inventory["status"].astype(str).ne("ok")
        | ~inventory["path_exists"]
        | ~inventory["page_count_valid"]
    )
    invalid = inventory[invalid_mask].copy()

    duplicates = inventory[
        inventory["sha256"].ne("")
        & inventory.duplicated("sha256", keep=False)
    ].sort_values(["sha256", "path"])

    valid = inventory[~invalid_mask].copy()
    extraction_manifest = (
        valid.drop_duplicates("document_id", keep="first")
        .sort_values(["relative_path", "filename"])
        .reset_index(drop=True)
    )

    output_dir = settings.audit_dir / "inventory"
    output_dir.mkdir(parents=True, exist_ok=True)

    _write_frame(invalid, output_dir / "invalid_documents.csv")
    _write_frame(duplicates, output_dir / "duplicate_documents.csv")
    _write_frame(
        extraction_manifest,
        output_dir / "extraction_manifest.csv",
    )

    summary = {
        "inventory_rows": int(len(inventory)),
        "valid_rows": int(len(valid)),
        "invalid_rows": int(len(invalid)),
        "unique_documents": int(len(extraction_manifest)),
        "duplicate_rows": int(len(valid) - len(extraction_manifest)),
        "expected_pages": int(
            pd.to_numeric(
                extraction_manifest["page_count"],
                errors="coerce",
            ).fillna(0).sum()
        ),
        "extraction_manifest_path": str(
            (output_dir / "extraction_manifest.csv").resolve()
        ),
    }
    _write_json(output_dir / "summary.json", summary)

    if extraction_manifest.empty:
        raise RuntimeError("Nenhum documento válido para extração.")

    return summary


def _status(
    failures: list[str],
    warnings: list[str],
) -> str:
    if failures:
        return "FAIL"
    if warnings:
        return "WARN"
    return "PASS"


def _outliers(documents: pd.DataFrame) -> pd.DataFrame:
    if documents.empty:
        return documents.copy()

    frames: list[pd.DataFrame] = []
    for column in (
        "text_chars",
        "middle_size_bytes",
        "content_blocks",
        "duration_seconds",
        "empty_page_ratio",
    ):
        if column not in documents.columns:
            continue

        numeric = pd.to_numeric(documents[column], errors="coerce")
        valid = documents[numeric.notna()].copy()
        if valid.empty:
            continue

        valid[column] = pd.to_numeric(valid[column], errors="coerce")
        smallest = valid.nsmallest(min(10, len(valid)), column).copy()
        smallest["outlier_reason"] = f"{column}:smallest"
        largest = valid.nlargest(min(10, len(valid)), column).copy()
        largest["outlier_reason"] = f"{column}:largest"
        frames.extend([smallest, largest])

    if not frames:
        return pd.DataFrame(columns=[*documents.columns, "outlier_reason"])

    return (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(["document_id", "outlier_reason"])
        .reset_index(drop=True)
    )


def _review_sample(
    documents: pd.DataFrame,
    outliers: pd.DataFrame,
) -> pd.DataFrame:
    if documents.empty:
        return documents.copy()

    selected: list[pd.DataFrame] = [
        documents[documents["audit_status"].eq("FAIL")],
        documents[documents["audit_status"].eq("WARN")],
    ]

    if not outliers.empty:
        selected.append(
            outliers[documents.columns.intersection(outliers.columns)]
        )

    pass_rows = documents[documents["audit_status"].eq("PASS")]
    remaining = max(
        0,
        settings.audit_review_sample_size
        - sum(len(frame) for frame in selected),
    )

    if remaining and not pass_rows.empty:
        selected.append(
            pass_rows.sample(
                n=min(remaining, len(pass_rows)),
                random_state=42,
            )
        )

    return (
        pd.concat(selected, ignore_index=True)
        .drop_duplicates("document_id")
        .reset_index(drop=True)
    )


def audit_extraction() -> dict[str, Any]:
    inventory_summary = audit_inventory()
    manifest_path = Path(inventory_summary["extraction_manifest_path"])
    manifest = pd.read_csv(manifest_path)
    runs = _load_runs()

    documents_root = settings.document_store_dir
    output_dir = settings.audit_dir / "extraction"
    output_dir.mkdir(parents=True, exist_ok=True)

    extraction_exists = (
        any(documents_root.rglob("*_middle.json"))
        or (settings.extraction_dir / "runs.csv").exists()
    )

    if not extraction_exists:
        summary = {
            "available": False,
            "message": (
                "Nenhuma extração encontrada; "
                "somente o inventário foi auditado."
            ),
            **inventory_summary,
        }
        _write_json(output_dir / "summary.json", summary)
        return summary

    runs_by_id: dict[str, dict[str, Any]] = {}
    if not runs.empty:
        runs_by_id = {
            row["document_id"]: row.to_dict()
            for _, row in runs.iterrows()
        }

    schema = SchemaCounts()
    rows: list[dict[str, Any]] = []

    for index, inventory_row in manifest.iterrows():
        document_id = _normalized_string(inventory_row["document_id"])
        expected_pages = _page_count(inventory_row.get("page_count"))
        layout = document_layout(inventory_row.to_dict())
        source_path = (
            layout.pdf_path
            if layout.pdf_path.is_file()
            else Path(str(inventory_row["path"])).expanduser()
        )
        document_dir = layout.document_dir
        middle_paths = sorted(layout.mineru_dir.rglob("*_middle.json"))
        failures: list[str] = []
        warnings: list[str] = []
        manifest_valid = False

        if not source_path.is_file():
            failures.append("source_missing")

        if not document_dir.exists():
            failures.append("output_directory_missing")

        if not layout.manifest_path.is_file():
            failures.append("manifest_missing")
        else:
            try:
                canonical_manifest = (
                    ExtractionManifest.model_validate_json(
                        layout.manifest_path.read_text(encoding="utf-8")
                    )
                )
                manifest_valid = (
                    canonical_manifest.sha256
                    == _normalized_string(inventory_row.get("sha256"))
                    and canonical_manifest.path.resolve()
                    == layout.pdf_path.resolve()
                    and canonical_manifest.output_dir.resolve()
                    == layout.mineru_dir.resolve()
                )
                if not manifest_valid:
                    failures.append("manifest_identity_mismatch")
            except (OSError, ValueError):
                failures.append("manifest_invalid")

        nested_manifests = list(layout.mineru_dir.rglob("manifest.json"))
        if nested_manifests:
            failures.append(
                f"multiple_document_manifests:{1 + len(nested_manifests)}"
            )

        if len(middle_paths) == 0:
            failures.append("middle_json_missing")
        elif len(middle_paths) > 1:
            failures.append(f"multiple_middle_json:{len(middle_paths)}")

        metrics: dict[str, Any] = {
            "middle_path": None,
            "manifest_path": str(layout.manifest_path),
            "manifest_valid": manifest_valid,
            "middle_size_bytes": None,
            "json_valid": False,
            "extracted_pages": None,
            "content_blocks": None,
            "discarded_blocks": None,
            "preproc_blocks": None,
            "line_count": None,
            "span_count": None,
            "text_chars": None,
            "asset_count": None,
            "empty_pages": None,
            "textless_pages": None,
            "empty_page_ratio": None,
            "unknown_block_types": "",
            "unknown_span_types": "",
        }

        if len(middle_paths) == 1:
            metrics, middle_failures, middle_warnings = _inspect_middle(
                middle_paths[0],
                expected_pages,
                schema,
            )
            failures.extend(middle_failures)
            warnings.extend(middle_warnings)

        run = runs_by_id.get(document_id, {})
        run_status = _normalized_string(run.get("status"))
        if run_status == "ok" and failures:
            failures.append("run_ok_but_artifact_invalid")
        elif run_status == "error" and not failures:
            warnings.append("run_error_but_artifact_valid")

        failures = list(dict.fromkeys(failures))
        warnings = list(dict.fromkeys(warnings))

        rows.append(
            {
                "document_position": index,
                "document_id": document_id,
                "sha256": inventory_row.get("sha256"),
                "filename": inventory_row.get("filename"),
                "source_path": str(source_path),
                "expected_pages": expected_pages,
                "audit_status": _status(failures, warnings),
                "failure_reasons": "|".join(failures),
                "warning_reasons": "|".join(warnings),
                "middle_json_count": len(middle_paths),
                "run_status": run_status or None,
                "duration_seconds": run.get("duration_seconds"),
                "attempts": run.get("attempts"),
                "pod_number": run.get("pod_number"),
                **metrics,
            }
        )

        if (index + 1) % 100 == 0 or index + 1 == len(manifest):
            print(f"Auditados: {index + 1}/{len(manifest)}")

    documents = pd.DataFrame(rows)
    _write_frame(documents, output_dir / "documents.csv")

    failures = documents[documents["audit_status"].eq("FAIL")].copy()
    warnings = documents[documents["audit_status"].eq("WARN")].copy()
    _write_frame(failures, output_dir / "failures.csv")
    _write_frame(warnings, output_dir / "warnings.csv")

    retry_ids = set(failures["document_id"])
    retry_manifest = manifest[
        manifest["document_id"].astype(str).isin(retry_ids)
    ].copy()
    _write_frame(retry_manifest, output_dir / "retry_manifest.csv")

    block_counts = pd.DataFrame(
        schema.block_types.most_common(),
        columns=["block_type", "count"],
    )
    span_counts = pd.DataFrame(
        schema.span_types.most_common(),
        columns=["span_type", "count"],
    )
    _write_frame(block_counts, output_dir / "block_type_counts.csv")
    _write_frame(span_counts, output_dir / "span_type_counts.csv")
    _write_json(output_dir / "schema_observed.json", schema.as_dict())

    outliers = _outliers(documents)
    _write_frame(outliers, output_dir / "outliers.csv")

    review_sample = _review_sample(documents, outliers)
    _write_frame(review_sample, output_dir / "review_sample.csv")

    catalog = pd.read_csv(settings.inventory_path)
    expected_manifest_paths = {
        document_layout(row.to_dict()).manifest_path.resolve()
        for _, row in catalog.iterrows()
        if len(_normalized_string(row.get("sha256"))) == 64
        and Path(str(row.get("path"))).is_file()
    }
    orphan_rows: list[dict[str, str]] = []
    if documents_root.exists():
        for path in documents_root.rglob("manifest.json"):
            if path.resolve() not in expected_manifest_paths:
                orphan_rows.append(
                    {
                        "document_id": path.parent.name,
                        "path": str(path.resolve()),
                    }
                )
    orphans = pd.DataFrame(orphan_rows)
    _write_frame(orphans, output_dir / "orphan_outputs.csv")

    expected_pages_total = int(
        pd.to_numeric(
            documents["expected_pages"],
            errors="coerce",
        ).fillna(0).sum()
    )
    extracted_pages_total = int(
        pd.to_numeric(
            documents["extracted_pages"],
            errors="coerce",
        ).fillna(0).sum()
    )

    summary = {
        "available": True,
        **inventory_summary,
        "audited_documents": int(len(documents)),
        "passed": int(documents["audit_status"].eq("PASS").sum()),
        "warnings": int(documents["audit_status"].eq("WARN").sum()),
        "failed": int(documents["audit_status"].eq("FAIL").sum()),
        "expected_pages": expected_pages_total,
        "extracted_pages": extracted_pages_total,
        "page_difference": extracted_pages_total - expected_pages_total,
        "unknown_block_types": sorted(
            block_type
            for block_type in schema.block_types
            if block_type not in KNOWN_BLOCK_TYPES
        ),
        "unknown_span_types": sorted(
            span_type
            for span_type in schema.span_types
            if span_type not in KNOWN_SPAN_TYPES
        ),
        "orphan_outputs": int(len(orphans)),
        "retry_manifest_path": str(
            (output_dir / "retry_manifest.csv").resolve()
        ),
        "review_sample_path": str(
            (output_dir / "review_sample.csv").resolve()
        ),
    }
    _write_json(output_dir / "summary.json", summary)
    return summary


def audit() -> dict[str, Any]:
    summary = audit_extraction()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary
