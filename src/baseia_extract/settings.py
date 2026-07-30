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
    data_dir: Path
    inventory_dir: Path
    inventory_path: Path
    sample_path: Path
    document_store_dir: Path
    extraction_dir: Path
    audit_dir: Path
    mineru_api_url: str
    mineru_concurrency_per_endpoint: int
    mineru_retries: int
    mineru_backend: str
    mineru_overwrite: bool
    mineru_health_timeout_seconds: float
    mineru_submit_timeout_seconds: float
    mineru_poll_interval_seconds: float
    mineru_task_timeout_seconds: float
    mineru_result_timeout_seconds: float
    mineru_circuit_failure_threshold: int
    mineru_circuit_window_seconds: float
    mineru_circuit_cooldown_seconds: float
    mineru_circuit_recovery_successes: int
    mineru_autotune_settling_seconds: float
    mineru_autotune_window_seconds: float
    mineru_autotune_min_samples: int
    mineru_autotune_cpu_high_percent: int
    mineru_autotune_cpu_high_samples: int
    mineru_autotune_cpu_recovery_percent: int
    mineru_endpoint_wait_timeout_seconds: float
    mineru_shared_results: bool
    audit_textless_page_warn_ratio: float
    audit_min_middle_bytes: int
    audit_review_sample_size: int


def get_settings() -> Settings:
    project_root = _project_root()
    data_dir = _path_env("BASEIA_DATA_DIR", project_root / "data")
    inventory_dir = data_dir / "inventory"

    result = Settings(
        project_root=project_root,
        data_dir=data_dir,
        inventory_dir=inventory_dir,
        inventory_path=inventory_dir / "inventory.csv",
        sample_path=inventory_dir / "sample.csv",
        document_store_dir=data_dir / "documents",
        extraction_dir=_path_env(
            "EXTRACTION_OUTPUT_DIR",
            data_dir / "extraction",
        ),
        audit_dir=data_dir / "audit",
        mineru_api_url=(
            os.getenv("MINERU_API_URL", "").strip().rstrip("/")
            or "http://127.0.0.1:8000"
        ),
        mineru_concurrency_per_endpoint=_int_env(
            "MINERU_CONCURRENCY_PER_ENDPOINT",
            16,
        ),
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
            3600.0,
        ),
        mineru_circuit_failure_threshold=_int_env(
            "MINERU_CIRCUIT_FAILURE_THRESHOLD", 3
        ),
        mineru_circuit_window_seconds=_float_env(
            "MINERU_CIRCUIT_WINDOW_SECONDS", 60.0
        ),
        mineru_circuit_cooldown_seconds=_float_env(
            "MINERU_CIRCUIT_COOLDOWN_SECONDS", 30.0
        ),
        mineru_circuit_recovery_successes=_int_env(
            "MINERU_CIRCUIT_RECOVERY_SUCCESSES", 2
        ),
        mineru_autotune_settling_seconds=_float_env(
            "MINERU_AUTOTUNE_SETTLING_SECONDS", 30.0
        ),
        mineru_autotune_window_seconds=_float_env(
            "MINERU_AUTOTUNE_WINDOW_SECONDS", 120.0
        ),
        mineru_autotune_min_samples=_int_env(
            "MINERU_AUTOTUNE_MIN_SAMPLES", 16
        ),
        mineru_autotune_cpu_high_percent=_int_env(
            "MINERU_AUTOTUNE_CPU_HIGH_PERCENT", 90
        ),
        mineru_autotune_cpu_high_samples=_int_env(
            "MINERU_AUTOTUNE_CPU_HIGH_SAMPLES", 3
        ),
        mineru_autotune_cpu_recovery_percent=_int_env(
            "MINERU_AUTOTUNE_CPU_RECOVERY_PERCENT", 85
        ),
        mineru_endpoint_wait_timeout_seconds=_float_env(
            "MINERU_ENDPOINT_WAIT_TIMEOUT_SECONDS", 300.0
        ),
        mineru_shared_results=_bool_env(
            "MINERU_SHARED_RESULTS",
            False,
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
    )

    if result.mineru_concurrency_per_endpoint < 1:
        raise ValueError(
            "MINERU_CONCURRENCY_PER_ENDPOINT deve ser maior que zero."
        )
    if result.mineru_retries < 0:
        raise ValueError("MINERU_RETRIES não pode ser negativo.")
    if result.mineru_endpoint_wait_timeout_seconds <= 0:
        raise ValueError(
            "MINERU_ENDPOINT_WAIT_TIMEOUT_SECONDS deve ser maior que zero."
        )
    if result.mineru_circuit_failure_threshold < 1:
        raise ValueError("MINERU_CIRCUIT_FAILURE_THRESHOLD deve ser maior que zero.")
    if result.mineru_circuit_window_seconds <= 0:
        raise ValueError("MINERU_CIRCUIT_WINDOW_SECONDS deve ser maior que zero.")
    if result.mineru_circuit_cooldown_seconds <= 0:
        raise ValueError("MINERU_CIRCUIT_COOLDOWN_SECONDS deve ser maior que zero.")
    if result.mineru_circuit_recovery_successes < 1:
        raise ValueError("MINERU_CIRCUIT_RECOVERY_SUCCESSES deve ser maior que zero.")
    if result.mineru_autotune_settling_seconds < 0:
        raise ValueError("MINERU_AUTOTUNE_SETTLING_SECONDS não pode ser negativo.")
    if result.mineru_autotune_window_seconds <= 0:
        raise ValueError("MINERU_AUTOTUNE_WINDOW_SECONDS deve ser maior que zero.")
    if result.mineru_autotune_min_samples < 1:
        raise ValueError("MINERU_AUTOTUNE_MIN_SAMPLES deve ser maior que zero.")
    if not 0 <= result.mineru_autotune_cpu_high_percent <= 100:
        raise ValueError(
            "MINERU_AUTOTUNE_CPU_HIGH_PERCENT deve estar entre 0 e 100."
        )
    if result.mineru_autotune_cpu_high_samples < 1:
        raise ValueError(
            "MINERU_AUTOTUNE_CPU_HIGH_SAMPLES deve ser maior que zero."
        )
    if not 0 <= result.mineru_autotune_cpu_recovery_percent < result.mineru_autotune_cpu_high_percent:
        raise ValueError(
            "MINERU_AUTOTUNE_CPU_RECOVERY_PERCENT deve estar entre 0 e o limiar alto."
        )
    if not 0 <= result.audit_textless_page_warn_ratio <= 1:
        raise ValueError("AUDIT_TEXTLESS_PAGE_WARN_RATIO deve estar entre 0 e 1.")
    if result.audit_min_middle_bytes < 0:
        raise ValueError("AUDIT_MIN_MIDDLE_BYTES não pode ser negativo.")
    if result.audit_review_sample_size < 1:
        raise ValueError("AUDIT_REVIEW_SAMPLE_SIZE deve ser maior que zero.")
    return result


settings = get_settings()
