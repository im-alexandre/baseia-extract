from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Carrega um .env simples sem adicionar dependência externa."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _project_root() -> Path:
    configured = os.getenv("BASEIA_PROJECT_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def _path_env(name: str, default: Path) -> Path:
    value = os.getenv(name)
    return Path(value).expanduser().resolve() if value else default.resolve()


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value not in (None, "") else default


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value not in (None, "") else default


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


PROJECT_ROOT = _project_root()
_load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True, slots=True)
class Settings:
    project_root: Path
    corpus_dir: Path
    data_dir: Path
    inventory_dir: Path
    inventory_path: Path
    sample_path: Path
    mineru_output_dir: Path
    audit_dir: Path
    ir_dir: Path
    structure_dir: Path
    chunks_dir: Path
    mineru_api_urls: tuple[str, ...]
    mineru_version: str
    mineru_workers_per_pod: int
    mineru_retries: int
    mineru_backend: str
    mineru_overwrite: bool
    mineru_health_timeout_seconds: float
    mineru_submit_timeout_seconds: float
    mineru_poll_interval_seconds: float
    mineru_task_timeout_seconds: float
    mineru_result_timeout_seconds: float
    mineru_api_task_retention_seconds: int
    mineru_api_task_cleanup_interval_seconds: int
    audit_textless_page_warn_ratio: float
    audit_min_middle_bytes: int
    audit_review_sample_size: int
    runpod_template_name: str
    runpod_gpu_id: str
    runpod_pod_count: int
    runpod_gpu_count: int
    runpod_api_port: int
    runpod_name_prefix: str
    network_volume_id: str
    runpod_terminate_after: str
    runpod_startup_timeout_seconds: float
    runpod_startup_poll_seconds: float


def get_settings() -> Settings:
    project_root = _project_root()
    data_dir = _path_env("BASEIA_DATA_DIR", project_root / "data")
    inventory_dir = data_dir / "inventory"

    result = Settings(
        project_root=project_root,
        corpus_dir=_path_env("BASEIA_CORPUS_DIR", project_root / "corpus"),
        data_dir=data_dir,
        inventory_dir=inventory_dir,
        inventory_path=inventory_dir / "inventory.csv",
        sample_path=inventory_dir / "sample.csv",
        mineru_output_dir=data_dir / "mineru",
        audit_dir=data_dir / "audit",
        ir_dir=data_dir / "ir",
        structure_dir=data_dir / "structure",
        chunks_dir=data_dir / "chunks",
        mineru_api_urls=(),
        mineru_version=os.getenv("MINERU_VERSION", "3.4.0").strip(),
        mineru_workers_per_pod=_int_env("MINERU_WORKERS_PER_POD", 8),
        mineru_retries=_int_env("MINERU_RETRIES", 2),
        mineru_backend=os.getenv("MINERU_BACKEND", "pipeline"),
        mineru_overwrite=_bool_env("MINERU_OVERWRITE", False),
        mineru_health_timeout_seconds=_float_env(
            "MINERU_HEALTH_TIMEOUT_SECONDS",
            30.0,
        ),
        mineru_submit_timeout_seconds=_float_env(
            "MINERU_SUBMIT_TIMEOUT_SECONDS",
            300.0,
        ),
        mineru_poll_interval_seconds=_float_env(
            "MINERU_POLL_INTERVAL_SECONDS",
            1.0,
        ),
        mineru_task_timeout_seconds=_float_env(
            "MINERU_TASK_TIMEOUT_SECONDS",
            3600.0,
        ),
        mineru_result_timeout_seconds=_float_env(
            "MINERU_RESULT_TIMEOUT_SECONDS",
            300.0,
        ),
        mineru_api_task_retention_seconds=_int_env(
            "MINERU_API_TASK_RETENTION_SECONDS",
            600,
        ),
        mineru_api_task_cleanup_interval_seconds=_int_env(
            "MINERU_API_TASK_CLEANUP_INTERVAL_SECONDS",
            60,
        ),
        audit_textless_page_warn_ratio=_float_env(
            "AUDIT_TEXTLESS_PAGE_WARN_RATIO",
            0.5,
        ),
        audit_min_middle_bytes=_int_env(
            "AUDIT_MIN_MIDDLE_BYTES",
            1024,
        ),
        audit_review_sample_size=_int_env(
            "AUDIT_REVIEW_SAMPLE_SIZE",
            75,
        ),
        runpod_template_name=os.getenv(
            "RUNPOD_TEMPLATE_NAME",
            "",
        ).strip(),
        runpod_gpu_id=os.getenv(
            "RUNPOD_GPU_ID",
            "NVIDIA GeForce RTX 5090",
        ).strip(),
        runpod_pod_count=_int_env("RUNPOD_POD_COUNT", 1),
        runpod_gpu_count=_int_env("RUNPOD_GPU_COUNT", 1),
        runpod_api_port=_int_env("RUNPOD_API_PORT", 8000),
        runpod_name_prefix=os.getenv(
            "RUNPOD_NAME_PREFIX",
            "baseia-mineru",
        ).strip(),
        network_volume_id=os.getenv(
            "NETWORK_VOLUME_ID",
            "",
        ).strip(),
        runpod_terminate_after=os.getenv(
            "RUNPOD_TERMINATE_AFTER",
            "12h",
        ).strip(),
        runpod_startup_timeout_seconds=_float_env(
            "RUNPOD_STARTUP_TIMEOUT_SECONDS",
            1800.0,
        ),
        runpod_startup_poll_seconds=_float_env(
            "RUNPOD_STARTUP_POLL_SECONDS",
            10.0,
        ),
    )

    if not result.mineru_version:
        raise ValueError("MINERU_VERSION não pode ficar vazio.")
    if result.mineru_workers_per_pod < 1:
        raise ValueError("MINERU_WORKERS_PER_POD deve ser maior que zero.")
    if result.mineru_retries < 0:
        raise ValueError("MINERU_RETRIES não pode ser negativo.")
    if result.mineru_api_task_retention_seconds < 0:
        raise ValueError(
            "MINERU_API_TASK_RETENTION_SECONDS não pode ser negativo."
        )
    if result.mineru_api_task_cleanup_interval_seconds < 1:
        raise ValueError(
            "MINERU_API_TASK_CLEANUP_INTERVAL_SECONDS deve ser maior que zero."
        )
    if not 0 <= result.audit_textless_page_warn_ratio <= 1:
        raise ValueError(
            "AUDIT_TEXTLESS_PAGE_WARN_RATIO deve estar entre 0 e 1."
        )
    if result.audit_min_middle_bytes < 0:
        raise ValueError("AUDIT_MIN_MIDDLE_BYTES não pode ser negativo.")
    if result.audit_review_sample_size < 1:
        raise ValueError("AUDIT_REVIEW_SAMPLE_SIZE deve ser maior que zero.")
    if result.runpod_pod_count < 1:
        raise ValueError("RUNPOD_POD_COUNT deve ser maior que zero.")
    if result.runpod_gpu_count < 1:
        raise ValueError("RUNPOD_GPU_COUNT deve ser maior que zero.")
    if result.runpod_api_port < 1:
        raise ValueError("RUNPOD_API_PORT deve ser maior que zero.")

    return result


settings = get_settings()
