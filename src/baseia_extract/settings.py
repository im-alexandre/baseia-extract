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


def _tuple_env(name: str) -> tuple[str, ...]:
    value = os.getenv(name, "")
    return tuple(
        item.strip().rstrip("/")
        for item in value.replace(";", ",").split(",")
        if item.strip()
    )


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
    mineru_concurrency_per_pod: int
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
    audit_textless_page_warn_ratio: float
    audit_min_middle_bytes: int
    audit_review_sample_size: int
    runpod_template_name: str
    runpod_workload: str
    runpod_hardware_profile: str
    runpod_min_vram_gb: int
    runpod_min_vcpu_count: int
    runpod_min_memory_gb: int
    runpod_max_cost_per_hour: float
    runpod_min_cuda_version: str
    runpod_cloud_type: str
    runpod_pod_count: int
    runpod_gpu_count: int
    runpod_container_disk_gb: int
    runpod_docker_args: str
    runpod_api_port: int
    runpod_name_prefix: str
    runpod_network_volume_id: str
    runpod_volume_disk_gb: int
    runpod_startup_timeout_seconds: float
    runpod_startup_poll_seconds: float
    runpod_serverless_endpoint_id: str
    runpod_serverless_client_concurrency: int
    runpod_serverless_inline_input_mb: int
    object_storage_credentials_path: Path | None


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
        mineru_output_dir=_path_env(
            "MINERU_OUTPUT_DIR",
            data_dir / "mineru",
        ),
        audit_dir=data_dir / "audit",
        ir_dir=data_dir / "ir",
        structure_dir=data_dir / "structure",
        chunks_dir=data_dir / "chunks",
        mineru_api_urls=_tuple_env("MINERU_API_URLS"),
        mineru_concurrency_per_pod=_int_env(
            "MINERU_CONCURRENCY_PER_POD",
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
        runpod_workload=os.getenv(
            "RUNPOD_WORKLOAD",
            "computer-vision",
        )
        .strip()
        .lower(),
        runpod_hardware_profile=os.getenv(
            "RUNPOD_HARDWARE_PROFILE",
            "mineru-budget-24",
        )
        .strip()
        .lower(),
        runpod_min_vram_gb=_int_env("RUNPOD_MIN_VRAM_GB", 16),
        runpod_min_vcpu_count=_int_env("RUNPOD_MIN_VCPU_COUNT", 16),
        runpod_min_memory_gb=_int_env("RUNPOD_MIN_MEMORY_GB", 64),
        runpod_max_cost_per_hour=_float_env(
            "RUNPOD_MAX_COST_PER_HOUR",
            1.05,
        ),
        runpod_min_cuda_version=os.getenv(
            "RUNPOD_MIN_CUDA_VERSION",
            "12.8",
        ).strip(),
        runpod_cloud_type=os.getenv(
            "RUNPOD_CLOUD_TYPE",
            "SECURE",
        )
        .strip()
        .upper(),
        runpod_pod_count=_int_env("RUNPOD_POD_COUNT", 1),
        runpod_gpu_count=_int_env("RUNPOD_GPU_COUNT", 1),
        runpod_container_disk_gb=_int_env("RUNPOD_CONTAINER_DISK_GB", 40),
        runpod_docker_args=os.getenv("RUNPOD_DOCKER_ARGS", "").strip(),
        runpod_api_port=_int_env("RUNPOD_API_PORT", 8000),
        runpod_name_prefix=os.getenv(
            "RUNPOD_NAME_PREFIX",
            "baseia-mineru",
        ).strip(),
        runpod_network_volume_id=os.getenv(
            "RUNPOD_NETWORK_VOLUME_ID",
            "",
        ).strip(),
        runpod_volume_disk_gb=_int_env("RUNPOD_VOLUME_DISK_GB", 100),
        runpod_startup_timeout_seconds=_float_env(
            "RUNPOD_STARTUP_TIMEOUT_SECONDS",
            1800.0,
        ),
        runpod_startup_poll_seconds=_float_env(
            "RUNPOD_STARTUP_POLL_SECONDS",
            10.0,
        ),
        runpod_serverless_endpoint_id=os.getenv(
            "RUNPOD_SERVERLESS_ENDPOINT_ID",
            "",
        ).strip(),
        runpod_serverless_client_concurrency=_int_env(
            "RUNPOD_SERVERLESS_CLIENT_CONCURRENCY",
            9,
        ),
        runpod_serverless_inline_input_mb=_int_env(
            "RUNPOD_SERVERLESS_INLINE_INPUT_MB",
            14,
        ),
        object_storage_credentials_path=(
            _path_env(
                "OBJECT_STORAGE_CREDENTIALS_FILE",
                project_root / ".object-storage.json",
            )
            if os.getenv("OBJECT_STORAGE_CREDENTIALS_FILE")
            else None
        ),
    )

    if result.mineru_concurrency_per_pod < 1:
        raise ValueError("MINERU_CONCURRENCY_PER_POD deve ser maior que zero.")
    if result.mineru_retries < 0:
        raise ValueError("MINERU_RETRIES não pode ser negativo.")
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
    if result.runpod_pod_count < 0:
        raise ValueError("RUNPOD_POD_COUNT não pode ser negativo.")
    if result.runpod_min_vram_gb < 1:
        raise ValueError("RUNPOD_MIN_VRAM_GB deve ser maior que zero.")
    if result.runpod_hardware_profile not in {
        "mineru-24",
        "mineru-50",
        "mineru-80",
        "mineru-budget-24",
    }:
        raise ValueError(
            f"RUNPOD_HARDWARE_PROFILE inválido: {result.runpod_hardware_profile!r}."
        )
    if result.runpod_min_vcpu_count < 1:
        raise ValueError("RUNPOD_MIN_VCPU_COUNT deve ser maior que zero.")
    if result.runpod_min_memory_gb < 1:
        raise ValueError("RUNPOD_MIN_MEMORY_GB deve ser maior que zero.")
    if result.runpod_max_cost_per_hour <= 0:
        raise ValueError("RUNPOD_MAX_COST_PER_HOUR deve ser maior que zero.")
    if result.runpod_cloud_type not in {"SECURE", "COMMUNITY"}:
        raise ValueError("RUNPOD_CLOUD_TYPE deve ser SECURE ou COMMUNITY.")
    if result.runpod_workload not in {
        "computer-vision",
        "data-processing",
        "image-generation",
        "llm-inference-small",
        "llm-inference-large",
        "llm-training",
        "3d-rendering",
    }:
        raise ValueError(f"RUNPOD_WORKLOAD inválido: {result.runpod_workload!r}.")
    if result.runpod_gpu_count < 1:
        raise ValueError("RUNPOD_GPU_COUNT deve ser maior que zero.")
    if result.runpod_container_disk_gb < 1:
        raise ValueError("RUNPOD_CONTAINER_DISK_GB deve ser maior que zero.")
    if result.runpod_volume_disk_gb < 1:
        raise ValueError("RUNPOD_VOLUME_DISK_GB deve ser maior que zero.")
    if result.runpod_api_port < 1:
        raise ValueError("RUNPOD_API_PORT deve ser maior que zero.")
    if result.runpod_serverless_client_concurrency < 1:
        raise ValueError(
            "RUNPOD_SERVERLESS_CLIENT_CONCURRENCY deve ser maior que zero."
        )
    if result.runpod_serverless_inline_input_mb < 1:
        raise ValueError("RUNPOD_SERVERLESS_INLINE_INPUT_MB deve ser maior que zero.")

    return result


settings = get_settings()
