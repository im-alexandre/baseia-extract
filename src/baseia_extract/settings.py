from __future__ import annotations

import os
import re
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


def _urls_env(name: str) -> tuple[str, ...]:
    value = os.getenv(name, "")
    urls: list[str] = []
    for candidate in re.split(r"[,;\s]+", value):
        normalized = candidate.strip().rstrip("/")
        if normalized and normalized not in urls:
            urls.append(normalized)
    return tuple(urls)


PROJECT_ROOT = _project_root()
_load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True, slots=True)
class Settings:
    project_root: Path
    corpus_dir: Path
    data_dir: Path
    artifacts_dir: Path
    inventory_dir: Path
    inventory_path: Path
    mineru_output_dir: Path
    ir_dir: Path
    structure_dir: Path
    chunks_dir: Path
    mineru_api_urls: tuple[str, ...]
    mineru_workers_per_pod: int
    mineru_retries: int
    mineru_backend: str
    mineru_overwrite: bool
    mineru_health_timeout_seconds: float
    mineru_submit_timeout_seconds: float
    mineru_poll_interval_seconds: float
    mineru_task_timeout_seconds: float
    mineru_result_timeout_seconds: float
    runpod_template_name: str
    runpod_gpu_id: str
    runpod_pod_count: int
    runpod_gpu_count: int
    runpod_api_port: int
    runpod_cloud_type: str
    runpod_terminate_after: str
    runpod_startup_timeout_seconds: float
    runpod_poll_interval_seconds: float


def get_settings() -> Settings:
    project_root = _project_root()
    data_dir = _path_env("BASEIA_DATA_DIR", project_root / "data")
    artifacts_dir = _path_env("BASEIA_ARTIFACTS_DIR", project_root / "artifacts")
    inventory_dir = _path_env("BASEIA_INVENTORY_DIR", data_dir / "inventory")

    result = Settings(
        project_root=project_root,
        corpus_dir=_path_env("BASEIA_CORPUS_DIR", project_root / "corpus"),
        data_dir=data_dir,
        artifacts_dir=artifacts_dir,
        inventory_dir=inventory_dir,
        inventory_path=_path_env("BASEIA_INVENTORY_PATH", inventory_dir / "inventory.csv"),
        mineru_output_dir=_path_env(
            "BASEIA_MINERU_OUTPUT_DIR", artifacts_dir / "mineru" / "extraction"
        ),
        ir_dir=_path_env("BASEIA_IR_DIR", artifacts_dir / "ir"),
        structure_dir=_path_env("BASEIA_STRUCTURE_DIR", artifacts_dir / "structure"),
        chunks_dir=_path_env("BASEIA_CHUNKS_DIR", artifacts_dir / "chunks"),
        mineru_api_urls=_urls_env("MINERU_API_URLS"),
        mineru_workers_per_pod=_int_env("MINERU_WORKERS_PER_POD", 8),
        mineru_retries=_int_env("MINERU_RETRIES", 2),
        mineru_backend=os.getenv("MINERU_BACKEND", "pipeline"),
        mineru_overwrite=_bool_env("MINERU_OVERWRITE", False),
        mineru_health_timeout_seconds=_float_env("MINERU_HEALTH_TIMEOUT_SECONDS", 30.0),
        mineru_submit_timeout_seconds=_float_env("MINERU_SUBMIT_TIMEOUT_SECONDS", 300.0),
        mineru_poll_interval_seconds=_float_env("MINERU_POLL_INTERVAL_SECONDS", 1.0),
        mineru_task_timeout_seconds=_float_env("MINERU_TASK_TIMEOUT_SECONDS", 3600.0),
        mineru_result_timeout_seconds=_float_env("MINERU_RESULT_TIMEOUT_SECONDS", 300.0),
        runpod_template_name=os.getenv("RUNPOD_TEMPLATE_NAME", "").strip(),
        runpod_gpu_id=os.getenv("RUNPOD_GPU_ID", "NVIDIA GeForce RTX 5090").strip(),
        runpod_pod_count=_int_env("RUNPOD_POD_COUNT", 1),
        runpod_gpu_count=_int_env("RUNPOD_GPU_COUNT", 1),
        runpod_api_port=_int_env("RUNPOD_API_PORT", 8000),
        runpod_cloud_type=os.getenv("RUNPOD_CLOUD_TYPE", "COMMUNITY").strip().upper(),
        runpod_terminate_after=os.getenv("RUNPOD_TERMINATE_AFTER", "12h").strip(),
        runpod_startup_timeout_seconds=_float_env("RUNPOD_STARTUP_TIMEOUT_SECONDS", 1800.0),
        runpod_poll_interval_seconds=_float_env("RUNPOD_POLL_INTERVAL_SECONDS", 10.0),
    )

    if result.mineru_workers_per_pod < 1:
        raise ValueError("MINERU_WORKERS_PER_POD deve ser maior que zero.")
    if result.mineru_retries < 0:
        raise ValueError("MINERU_RETRIES não pode ser negativo.")
    if result.runpod_pod_count < 1:
        raise ValueError("RUNPOD_POD_COUNT deve ser maior que zero.")
    if result.runpod_gpu_count < 1:
        raise ValueError("RUNPOD_GPU_COUNT deve ser maior que zero.")
    if result.runpod_cloud_type not in {"SECURE", "COMMUNITY"}:
        raise ValueError("RUNPOD_CLOUD_TYPE deve ser SECURE ou COMMUNITY.")

    return result


settings = get_settings()
