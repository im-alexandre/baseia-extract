from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Literal
from urllib.parse import urlsplit

import pandas as pd
import yaml
from filelock import FileLock, Timeout
from platformdirs import user_data_path
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .identity import collection_slug, collection_uuid
from .inventory import INVENTORY_COLUMNS, inspect_pdf, sample_inventory
from .layout import document_layout
from .settings import settings

CONFIG_FILENAME = "baseia.collection.yaml"
SCHEMA_VERSION = 1
STAGES = ("inventory", "extract", "render", "promote")
console = Console()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _normalized_prefix(value: str) -> str:
    raw = value.strip().replace("\\", "/").strip("/")
    if raw in {"", "."}:
        return ""
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Prefixo lógico inválido: {value!r}")
    return path.as_posix()


def _validated_url(value: str, *, field_name: str) -> str:
    normalized = value.strip().rstrip("/")
    if not normalized:
        return ""
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} deve ser uma URL HTTP(S).")
    if parsed.query or parsed.fragment:
        raise ValueError(
            f"{field_name} não pode conter query string ou fragmento."
        )
    return normalized


class CollectionSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    logical_prefix: str = ""
    recursive: bool = True

    @field_validator("path")
    @classmethod
    def _path_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("O path da fonte não pode ficar vazio.")
        return value.strip()

    @field_validator("logical_prefix")
    @classmethod
    def _prefix_is_relative(cls, value: str) -> str:
        return _normalized_prefix(value)


class ServiceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mineru_api_urls: list[str] = Field(default_factory=list)
    mineru_result_s3_endpoint_url: str = ""
    mineru_result_s3_bucket: str = ""
    mineru_result_s3_region: str = ""
    mineru_result_s3_access_key_env: str = (
        "MINERU_RESULT_S3_ACCESS_KEY_ID"
    )
    mineru_result_s3_secret_key_env: str = (
        "MINERU_RESULT_S3_SECRET_ACCESS_KEY"
    )
    catalog_api_url: str = ""
    catalog_token_env: str = "BASEIA_CATALOG_API_TOKEN"
    s3_endpoint_url: str = ""
    s3_bucket: str = "baseia"
    s3_region: str = "us-east-1"
    s3_access_key_env: str = "AWS_ACCESS_KEY_ID"
    s3_secret_key_env: str = "AWS_SECRET_ACCESS_KEY"
    qdrant_url: str = ""

    @field_validator("mineru_api_urls")
    @classmethod
    def _mineru_urls(cls, values: list[str]) -> list[str]:
        return list(
            dict.fromkeys(
                _validated_url(value, field_name="mineru_api_urls")
                for value in values
                if value.strip()
            )
        )

    @field_validator("catalog_api_url")
    @classmethod
    def _catalog_url(cls, value: str) -> str:
        return _validated_url(value, field_name="catalog_api_url")

    @field_validator("mineru_result_s3_endpoint_url")
    @classmethod
    def _mineru_result_s3_url(cls, value: str) -> str:
        return _validated_url(
            value,
            field_name="mineru_result_s3_endpoint_url",
        )

    @field_validator("s3_endpoint_url")
    @classmethod
    def _s3_url(cls, value: str) -> str:
        return _validated_url(value, field_name="s3_endpoint_url")

    @field_validator("qdrant_url")
    @classmethod
    def _qdrant_url(cls, value: str) -> str:
        return _validated_url(value, field_name="qdrant_url")


class StrategyProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "default"
    version: str = "1"


class CollectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = SCHEMA_VERSION
    id: str
    name: str
    slug: str
    origin: Literal["init", "promoted_inventory"] = "init"
    mode: Literal["local", "cataloged", "production"] = "local"
    resource_scope: Literal[
        "unassigned",
        "personal",
        "operator",
        "client",
    ] = "personal"
    topology: Literal["local", "services", "distributed"] = "local"
    target_stage: Literal["inventory", "extract", "render", "promote"] = (
        "inventory"
    )
    workers: int = Field(default=3, ge=1)
    state_dir: str = ".baseia"
    sources: list[CollectionSource] = Field(min_length=1)
    strategy: StrategyProfile = Field(default_factory=StrategyProfile)
    services: ServiceProfile = Field(default_factory=ServiceProfile)
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)

    @model_validator(mode="after")
    def _identity_is_consistent(self) -> CollectionConfig:
        expected_slug = collection_slug(self.name)
        if self.slug != expected_slug:
            raise ValueError(
                f"slug divergente: esperado {expected_slug!r}, "
                f"recebido {self.slug!r}."
            )
        expected_id = str(collection_uuid(self.slug))
        if self.id != expected_id:
            raise ValueError(
                f"id divergente: esperado {expected_id!r}, "
                f"recebido {self.id!r}."
            )
        return self


class RegistryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    config_path: str


class CollectionRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = SCHEMA_VERSION
    current: str = ""
    collections: dict[str, RegistryEntry] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LoadedCollection:
    config: CollectionConfig
    config_path: Path

    @property
    def state_dir(self) -> Path:
        return _resolve_from_config(self.config_path, self.config.state_dir)

    @property
    def inventory_path(self) -> Path:
        return self.state_dir / "inventory" / "inventory.csv"

    @property
    def source_roots(self) -> tuple[Path, ...]:
        roots: list[Path] = []
        for source in self.config.sources:
            resolved = _resolve_from_config(self.config_path, source.path)
            if resolved not in roots:
                roots.append(resolved)
        return tuple(roots)


@dataclass(frozen=True, slots=True)
class CollectionStatus:
    documents: int
    valid: int
    invalid: int
    extracted: int
    rendered: int
    stage: str


@dataclass(frozen=True, slots=True)
class CollectionCandidate:
    name: str
    slug: str
    loaded: LoadedCollection | None
    inventory: pd.DataFrame


def _registry_dir() -> Path:
    configured = os.getenv("BASEIA_COLLECTIONS_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (user_data_path("BaseIA", appauthor=False) / "collections").resolve()


def _registry_path() -> Path:
    return _registry_dir() / "registry.yaml"


def _registry_lock_path() -> Path:
    return _registry_dir() / "registry.lock"


def _collection_lock_path(slug: str) -> Path:
    return _registry_dir() / "locks" / f"{collection_slug(slug)}.lock"


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


def _yaml_payload(value: BaseModel) -> str:
    return yaml.safe_dump(
        value.model_dump(mode="json"),
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"YAML inválido: {path}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"YAML deve conter um objeto na raiz: {path}")
    return payload


def _load_registry_unlocked() -> CollectionRegistry:
    path = _registry_path()
    if not path.is_file():
        return CollectionRegistry()
    return CollectionRegistry.model_validate(_read_yaml(path))


def _save_registry_unlocked(registry: CollectionRegistry) -> None:
    _atomic_text(_registry_path(), _yaml_payload(registry))


def load_collection_config(path: str | Path) -> LoadedCollection:
    resolved = Path(path).expanduser().resolve()
    config = CollectionConfig.model_validate(_read_yaml(resolved))
    return LoadedCollection(config=config, config_path=resolved)


def save_collection_config(loaded: LoadedCollection) -> None:
    _atomic_text(loaded.config_path, _yaml_payload(loaded.config))


def _resolve_from_config(config_path: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = config_path.parent / path
    return path.resolve()


def _split_urls(value: str) -> list[str]:
    return [
        item
        for item in re.split(r"[\s,;]+", value.strip())
        if item
    ]


def _service_defaults(api_urls: Iterable[str] = ()) -> ServiceProfile:
    explicit = [str(value) for value in api_urls if str(value).strip()]
    inherited = _split_urls(os.getenv("MINERU_API_URLS", ""))
    if not inherited:
        single = os.getenv("MINERU_API_URL", "").strip()
        inherited = [single] if single else []
    return ServiceProfile(
        mineru_api_urls=explicit or inherited,
        mineru_result_s3_endpoint_url=os.getenv(
            "MINERU_RESULT_S3_ENDPOINT_URL",
            "",
        ),
        mineru_result_s3_bucket=os.getenv(
            "MINERU_RESULT_S3_BUCKET",
            "",
        ),
        mineru_result_s3_region=os.getenv(
            "MINERU_RESULT_S3_REGION",
            "",
        ),
        catalog_api_url=os.getenv(
            "BASEIA_CATALOG_API_URL",
            "http://127.0.0.1:8088",
        ),
        s3_endpoint_url=os.getenv(
            "BASEIA_S3_ENDPOINT_URL",
            "http://127.0.0.1:8333",
        ),
        s3_bucket=os.getenv("BASEIA_S3_BUCKET", "baseia"),
        s3_region=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
    )


def _prompt_services(
    defaults: ServiceProfile,
    *,
    require_catalog: bool,
) -> ServiceProfile:
    mineru_value = Prompt.ask(
        "URLs MinerU separadas por vírgula (- para nenhuma)",
        default=(
            ",".join(defaults.mineru_api_urls)
            if defaults.mineru_api_urls
            else "-"
        ),
    )
    updates: dict[str, Any] = {
        "mineru_api_urls": (
            []
            if mineru_value.strip() == "-"
            else _split_urls(mineru_value)
        )
    }
    if updates["mineru_api_urls"]:
        result_endpoint = Prompt.ask(
            "Endpoint S3 dos resultados MinerU "
            "(- usa o S3 canônico)",
            default=defaults.mineru_result_s3_endpoint_url or "-",
        )
        updates["mineru_result_s3_endpoint_url"] = (
            "" if result_endpoint.strip() == "-" else result_endpoint
        )
        if updates["mineru_result_s3_endpoint_url"]:
            result_bucket = Prompt.ask(
                "Bucket esperado dos resultados MinerU "
                "(- aceita o bucket retornado pelo servidor)",
                default=defaults.mineru_result_s3_bucket or "-",
            )
            updates["mineru_result_s3_bucket"] = (
                "" if result_bucket.strip() == "-" else result_bucket
            )
            updates["mineru_result_s3_access_key_env"] = Prompt.ask(
                "Variável da access key do result store MinerU",
                default=defaults.mineru_result_s3_access_key_env,
            )
            updates["mineru_result_s3_secret_key_env"] = Prompt.ask(
                "Variável da secret key do result store MinerU",
                default=defaults.mineru_result_s3_secret_key_env,
            )
    if require_catalog:
        updates.update(
            catalog_api_url=Prompt.ask(
                "URL da API do catálogo",
                default=defaults.catalog_api_url,
            ),
            catalog_token_env=Prompt.ask(
                "Variável de ambiente do token do catálogo",
                default=defaults.catalog_token_env,
            ),
            s3_endpoint_url=Prompt.ask(
                "Endpoint S3",
                default=defaults.s3_endpoint_url,
            ),
            s3_bucket=Prompt.ask(
                "Bucket S3",
                default=defaults.s3_bucket,
            ),
            s3_access_key_env=Prompt.ask(
                "Variável de ambiente da access key S3",
                default=defaults.s3_access_key_env,
            ),
            s3_secret_key_env=Prompt.ask(
                "Variável de ambiente da secret key S3",
                default=defaults.s3_secret_key_env,
            ),
        )
    updated = defaults.model_copy(update=updates)
    return ServiceProfile.model_validate(updated.model_dump(mode="json"))


def _legacy_inventory() -> pd.DataFrame:
    if not settings.inventory_path.is_file():
        return pd.DataFrame(columns=INVENTORY_COLUMNS)
    return pd.read_csv(
        settings.inventory_path,
        dtype=str,
        keep_default_na=False,
    ).reindex(columns=INVENTORY_COLUMNS)


def _registered_collections() -> dict[str, LoadedCollection]:
    registry = _load_registry_unlocked()
    loaded: dict[str, LoadedCollection] = {}
    for slug, entry in registry.collections.items():
        try:
            loaded[slug] = load_collection_config(entry.config_path)
        except FileNotFoundError:
            continue
    return loaded


def _candidate_inventory(
    loaded: LoadedCollection | None,
    legacy: pd.DataFrame,
    slug: str,
) -> pd.DataFrame:
    if loaded is not None and loaded.inventory_path.is_file():
        return pd.read_csv(
            loaded.inventory_path,
            dtype=str,
            keep_default_na=False,
        ).reindex(columns=INVENTORY_COLUMNS)
    if legacy.empty:
        return legacy.copy()
    return legacy.loc[
        legacy["collection_slug"].map(collection_slug).eq(slug)
    ].copy()


def _candidates() -> list[CollectionCandidate]:
    registry = _load_registry_unlocked()
    loaded_by_slug = _registered_collections()
    legacy = _legacy_inventory()
    names: dict[str, str] = {
        slug: item.config.name
        for slug, item in loaded_by_slug.items()
    }
    if not legacy.empty:
        for row in legacy[["collection", "collection_slug"]].itertuples(
            index=False
        ):
            slug = collection_slug(str(row.collection_slug or row.collection))
            names.setdefault(slug, str(row.collection))
    for slug, entry in registry.collections.items():
        names.setdefault(slug, entry.name)
    return [
        CollectionCandidate(
            name=names[slug],
            slug=slug,
            loaded=loaded_by_slug.get(slug),
            inventory=_candidate_inventory(
                loaded_by_slug.get(slug),
                legacy,
                slug,
            ),
        )
        for slug in sorted(names, key=lambda item: names[item].casefold())
    ]


def _promotion_known(
    *,
    slug: str,
    count: int,
    search_roots: Iterable[Path],
) -> bool:
    for root in search_roots:
        if not root.is_dir():
            continue
        reports = sorted(
            root.glob("*/promotion-report.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in reports:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                collection_counts = payload.get("collection_counts", {})
                if (
                    payload.get("catalog_activated") is True
                    and isinstance(collection_counts, dict)
                    and int(collection_counts.get(slug, -1)) == count
                ):
                    return True
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
    return False


def _inventory_fingerprint(inventory: pd.DataFrame) -> str:
    records = [
        {
            "document_id": str(row.document_id),
            "revision_id": str(row.revision_id),
            "sha256": str(row.sha256),
        }
        for row in inventory.loc[inventory["status"].eq("ok")].sort_values(
            ["document_id", "revision_id"]
        ).itertuples(index=False)
    ]
    payload = json.dumps(
        records,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _pipeline_promotion_known(
    loaded: LoadedCollection,
    inventory: pd.DataFrame,
) -> bool:
    pipeline_dir = loaded.state_dir / "pipeline"
    paths = [pipeline_dir / "latest.json"]
    runs_dir = pipeline_dir / "runs"
    if runs_dir.is_dir():
        paths.extend(
            sorted(
                runs_dir.glob("*.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        )
    fingerprint = _inventory_fingerprint(inventory)
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            continue
        if (
            payload.get("through") == "promote"
            and payload.get("selection", "collection") == "collection"
            and payload.get("inventory_fingerprint") == fingerprint
        ):
            return True
    return False


def _status(
    inventory: pd.DataFrame,
    *,
    loaded: LoadedCollection | None = None,
) -> CollectionStatus:
    documents = len(inventory)
    if inventory.empty:
        return CollectionStatus(0, 0, 0, 0, 0, "vazia")
    valid_rows = inventory.loc[inventory["status"].eq("ok")].to_dict("records")
    valid = len(valid_rows)
    invalid = documents - valid
    extracted = 0
    rendered = 0
    for row in valid_rows:
        layout = document_layout(row)
        if len(list(layout.mineru_dir.rglob("*_middle.json"))) == 1:
            extracted += 1
        if all(
            path.is_file()
            for path in (
                layout.ir_path,
                layout.structure_path,
                layout.markdown_path,
                layout.render_path,
            )
        ):
            rendered += 1

    if invalid:
        stage = "inventário com erro"
    elif extracted < valid:
        stage = (
            "inventário"
            if extracted == 0
            else f"extração {extracted}/{valid}"
        )
    elif rendered < valid:
        stage = (
            "extração"
            if rendered == 0
            else f"render {rendered}/{valid}"
        )
    else:
        promoted = (
            _pipeline_promotion_known(loaded, inventory)
            if loaded is not None
            else False
        )
        promotion_roots: list[Path] = []
        if (
            loaded is None
            or loaded.config.origin == "promoted_inventory"
        ):
            # Candidatos sem configuração vêm exclusivamente do inventário
            # promovido global e podem ser comparados ao snapshot correspondente.
            promotion_roots.append(settings.data_dir / "bootstrap" / "s3")
        stage = (
            "promoção"
            if (
                promoted
                or _promotion_known(
                    slug=(
                        loaded.config.slug
                        if loaded is not None
                        else collection_slug(
                            str(inventory.iloc[0]["collection"])
                        )
                    ),
                    count=valid,
                    search_roots=promotion_roots,
                )
            )
            else "render"
        )
    return CollectionStatus(
        documents=documents,
        valid=valid,
        invalid=invalid,
        extracted=extracted,
        rendered=rendered,
        stage=stage,
    )


def _stage_from_status(status: CollectionStatus) -> str:
    if status.stage == "promoção":
        return "promote"
    if status.rendered == status.valid and status.valid:
        return "render"
    if status.extracted == status.valid and status.valid:
        return "extract"
    return "inventory"


def _effective_stage(loaded: LoadedCollection) -> str:
    configured = loaded.config.target_stage
    if not loaded.inventory_path.is_file():
        return configured
    inventory = pd.read_csv(
        loaded.inventory_path,
        dtype=str,
        keep_default_na=False,
    ).reindex(columns=INVENTORY_COLUMNS)
    observed = _stage_from_status(_status(inventory, loaded=loaded))
    return STAGES[
        max(STAGES.index(configured), STAGES.index(observed))
    ]


def _root_from_legacy_row(row: dict[str, Any]) -> Path:
    path = Path(str(row["path"])).expanduser().resolve()
    relative = Path(str(row["collection_relative_path"]))
    root = path
    for _ in relative.parts:
        root = root.parent
    return root


def _write_inventory(path: Path, inventory: pd.DataFrame) -> None:
    normalized = inventory.reindex(columns=INVENTORY_COLUMNS).copy()
    if not normalized.empty:
        normalized = normalized.sort_values(
            ["relative_path", "filename"]
        ).reset_index(drop=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_text(
        path,
        normalized.to_csv(index=False, lineterminator="\n"),
    )
    _atomic_text(
        path.with_name("inventory_errors.csv"),
        normalized.loc[normalized["status"].ne("ok")].to_csv(
            index=False,
            lineterminator="\n",
        ),
    )


def _register(loaded: LoadedCollection, *, current: bool = False) -> None:
    _registry_dir().mkdir(parents=True, exist_ok=True)
    try:
        with FileLock(_registry_lock_path(), timeout=10):
            registry = _load_registry_unlocked()
            registry.collections[loaded.config.slug] = RegistryEntry(
                name=loaded.config.name,
                config_path=str(loaded.config_path),
            )
            if current:
                registry.current = loaded.config.slug
            _save_registry_unlocked(registry)
    except Timeout as error:
        raise RuntimeError("O registro de coleções está ocupado.") from error


def _materialize(candidate: CollectionCandidate) -> LoadedCollection:
    if candidate.loaded is not None:
        return candidate.loaded
    if candidate.inventory.empty:
        raise RuntimeError(
            f"A coleção {candidate.name!r} não possui inventário materializável."
        )
    roots = {
        _root_from_legacy_row(row)
        for row in candidate.inventory.to_dict("records")
    }
    if len(roots) != 1:
        raise RuntimeError(
            "O inventário promovido aponta para mais de uma raiz física; "
            "registre as fontes explicitamente com `poe init`."
        )
    source_root = next(iter(roots))
    config_path = source_root / CONFIG_FILENAME
    if config_path.is_file():
        loaded = load_collection_config(config_path)
        if loaded.config.slug != candidate.slug:
            raise RuntimeError(
                f"{config_path} pertence a outra coleção."
            )
        _register(loaded)
        return loaded
    status = _status(candidate.inventory)
    config = CollectionConfig(
        id=str(collection_uuid(candidate.slug)),
        name=candidate.name,
        slug=candidate.slug,
        origin="promoted_inventory",
        mode="cataloged",
        resource_scope="unassigned",
        topology="services",
        target_stage=_stage_from_status(status),
        state_dir=".baseia",
        sources=[
            CollectionSource(
                path=str(next(iter(roots))),
                logical_prefix="",
            )
        ],
        services=_service_defaults(),
    )
    loaded = LoadedCollection(config=config, config_path=config_path)
    save_collection_config(loaded)
    _write_inventory(loaded.inventory_path, candidate.inventory)
    _register(loaded)
    return loaded


def _resolve_candidate(value: str = "") -> CollectionCandidate:
    selector = value.strip() or os.getenv("BASEIA_COLLECTION", "").strip()
    registry = _load_registry_unlocked()
    if not selector:
        selector = registry.current
    if not selector:
        raise RuntimeError(
            "Nenhuma coleção está ativa. Use `poe collection ls` e "
            "`poe collection use \"NOME\"`."
        )
    try:
        slug = collection_slug(selector)
    except ValueError:
        slug = selector.casefold()
    for candidate in _candidates():
        if (
            candidate.slug == slug
            or candidate.name.casefold() == selector.casefold()
        ):
            return candidate
    raise KeyError(f"Coleção não encontrada: {selector!r}")


def resolve_collection(value: str = "") -> LoadedCollection:
    return _materialize(_resolve_candidate(value))


def _current_slug() -> str:
    return _load_registry_unlocked().current


def _print_collection_table(
    candidates: list[CollectionCandidate],
    *,
    numbered: bool = False,
) -> None:
    current = _current_slug()
    table = Table(title="Coleções BaseIA", header_style="bold")
    if numbered:
        table.add_column("#", justify="right")
    table.add_column("Atual", justify="center")
    table.add_column("Coleção")
    table.add_column("Documentos", justify="right")
    table.add_column("Etapa")
    table.add_column("Modo")
    table.add_column("Escopo")
    for index, candidate in enumerate(candidates, start=1):
        status = _status(candidate.inventory, loaded=candidate.loaded)
        row = [
            "●" if candidate.slug == current else "",
            candidate.name,
            str(status.documents),
            status.stage,
            candidate.loaded.config.mode if candidate.loaded else "cataloged",
            (
                candidate.loaded.config.resource_scope
                if candidate.loaded
                else "unassigned"
            ),
        ]
        if numbered:
            row.insert(0, str(index))
        table.add_row(*row)
    console.print(table)


def _show(loaded: LoadedCollection) -> None:
    status = _status(
        _candidate_inventory(loaded, _legacy_inventory(), loaded.config.slug),
        loaded=loaded,
    )
    console.print(f"[bold]{loaded.config.name}[/bold] ({loaded.config.slug})")
    console.print(f"Configuração: {loaded.config_path}")
    console.print(f"Estado local: {loaded.state_dir}")
    console.print(
        f"Etapa observada: {status.stage} | "
        f"documentos={status.documents} | válidos={status.valid} | "
        f"inválidos={status.invalid}"
    )
    console.print(_yaml_payload(loaded.config), markup=False)


def collection(
    action: str = "ls",
    name: str = "",
    mode: str = "keep",
    resource_scope: str = "keep",
    topology: str = "keep",
    target_stage: str = "keep",
    api_urls: Iterable[str] = (),
    catalog_api_url: str = "keep",
    s3_endpoint_url: str = "keep",
    s3_bucket: str = "keep",
    s3_access_key_env: str = "keep",
    s3_secret_key_env: str = "keep",
    mineru_result_s3_endpoint_url: str = "keep",
    mineru_result_s3_bucket: str = "keep",
    mineru_result_s3_access_key_env: str = "keep",
    mineru_result_s3_secret_key_env: str = "keep",
) -> None:
    """Lista, seleciona e inspeciona as coleções conhecidas localmente."""
    known_actions = {"ls", "use", "current", "show", "configure"}
    normalized = action.strip() or "ls"
    if normalized not in known_actions:
        if name:
            raise ValueError(
                "Use `poe collection use NOME` ou "
                "`poe collection NOME`, não ambos."
            )
        name = normalized
        normalized = "use"

    if normalized == "ls":
        _print_collection_table(_candidates())
        return
    if normalized == "current":
        candidate = _resolve_candidate("")
        loaded = _materialize(candidate)
        _show(loaded)
        return
    if not name.strip():
        raise ValueError(f"A ação {normalized!r} exige o nome da coleção.")
    candidate = _resolve_candidate(name)
    loaded = _materialize(candidate)
    if normalized == "show":
        _show(loaded)
        return
    if normalized == "configure":
        updates: dict[str, Any] = {}
        choices_by_field = {
            "mode": ["local", "cataloged", "production"],
            "resource_scope": ["personal", "operator", "client"],
            "topology": ["local", "services", "distributed"],
            "target_stage": list(STAGES),
        }
        requested = {
            "mode": mode,
            "resource_scope": resource_scope,
            "topology": topology,
            "target_stage": target_stage,
        }
        for field_name, value in requested.items():
            if value != "keep":
                updates[field_name] = value
                continue
            current_value = str(getattr(loaded.config, field_name))
            if (
                sys.stdin.isatty()
                and (
                    field_name == "resource_scope"
                    and current_value == "unassigned"
                )
            ):
                updates[field_name] = Prompt.ask(
                    "Escopo dos recursos",
                    choices=choices_by_field[field_name],
                    default="personal",
                )
        service_updates: dict[str, Any] = {}
        normalized_urls = [
            _validated_url(str(value), field_name="api_url")
            for value in api_urls
            if str(value).strip()
        ]
        if normalized_urls:
            service_updates["mineru_api_urls"] = list(
                dict.fromkeys(normalized_urls)
            )
        requested_services = {
            "catalog_api_url": catalog_api_url,
            "s3_endpoint_url": s3_endpoint_url,
            "s3_bucket": s3_bucket,
            "s3_access_key_env": s3_access_key_env,
            "s3_secret_key_env": s3_secret_key_env,
            "mineru_result_s3_endpoint_url": (
                mineru_result_s3_endpoint_url
            ),
            "mineru_result_s3_bucket": mineru_result_s3_bucket,
            "mineru_result_s3_access_key_env": (
                mineru_result_s3_access_key_env
            ),
            "mineru_result_s3_secret_key_env": (
                mineru_result_s3_secret_key_env
            ),
        }
        for field_name, value in requested_services.items():
            if value != "keep":
                service_updates[field_name] = (
                    "" if value.strip() == "-" else value.strip()
                )
        if service_updates:
            candidate_services = loaded.config.services.model_copy(
                update=service_updates
            )
            updates["services"] = ServiceProfile.model_validate(
                candidate_services.model_dump(mode="json")
            )
        if not updates:
            raise ValueError(
                "Nenhuma alteração informada. Use --mode, "
                "--resource-scope, --topology, --target-stage ou uma "
                "opção de serviço."
            )
        updated = loaded.config.model_copy(
            update={**updates, "updated_at": _now()}
        )
        loaded = LoadedCollection(
            config=CollectionConfig.model_validate(
                updated.model_dump(mode="json")
            ),
            config_path=loaded.config_path,
        )
        save_collection_config(loaded)
        _register(loaded)
        _show(loaded)
        return
    _register(loaded, current=True)
    console.print(
        f"Coleção atual: [bold]{loaded.config.name}[/bold] "
        f"({loaded.config.slug})"
    )


def _source_files(source_path: Path, *, recursive: bool) -> list[Path]:
    if source_path.is_file():
        if source_path.suffix.casefold() != ".pdf":
            raise ValueError(
                f"A fonte deve ser um PDF ou diretório: {source_path}"
            )
        return [source_path]
    if not source_path.is_dir():
        raise FileNotFoundError(f"Fonte não encontrada: {source_path}")
    if (source_path / "manifest.json").is_file():
        raise ValueError(
            "A fonte aponta para um diretório de artefatos de documento, "
            f"não para uma coleção: {source_path}"
        )
    iterator = (
        source_path.rglob("*.pdf")
        if recursive
        else source_path.glob("*.pdf")
    )
    return sorted(
        path
        for path in iterator
        if path.is_file()
        and not any(
            (parent / "manifest.json").is_file()
            for parent in path.parents
            if parent != source_path and source_path in parent.parents
        )
    )


def _scan_source(
    loaded: LoadedCollection,
    source: CollectionSource,
    *,
    workers: int,
) -> pd.DataFrame:
    source_path = _resolve_from_config(loaded.config_path, source.path)
    paths = _source_files(source_path, recursive=source.recursive)
    if not paths:
        raise RuntimeError(f"Nenhum PDF encontrado em {source_path}.")
    documents_dir = source_path if source_path.is_dir() else source_path.parent
    resolved_workers = max(1, workers)
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=resolved_workers) as executor:
        futures = {
            executor.submit(
                inspect_pdf,
                path,
                documents_dir,
                collection=loaded.config.name,
                logical_prefix=source.logical_prefix,
            ): path
            for path in paths
        }
        for index, future in enumerate(as_completed(futures), start=1):
            rows.append(future.result())
            if index % 100 == 0 or index == len(paths):
                print(
                    f"Inventariados em {source_path}: "
                    f"{index}/{len(paths)}",
                    flush=True,
                )
    return pd.DataFrame(rows).reindex(columns=INVENTORY_COLUMNS)


def _merge_inventory(
    current: pd.DataFrame,
    incoming: pd.DataFrame,
) -> pd.DataFrame:
    combined = pd.concat(
        [
            current.reindex(columns=INVENTORY_COLUMNS),
            incoming.reindex(columns=INVENTORY_COLUMNS),
        ],
        ignore_index=True,
    )
    if combined.empty:
        return combined
    valid_identity = combined["document_id"].astype(str).str.strip().ne("")
    collisions: dict[str, list[dict[str, str]]] = {}
    for document_id, group in combined.loc[valid_identity].groupby(
        "document_id",
        sort=False,
    ):
        identities = {
            (str(row.path), str(row.sha256))
            for row in group.itertuples(index=False)
        }
        if len(identities) > 1:
            collisions[str(document_id)] = [
                {"path": path, "sha256": sha256}
                for path, sha256 in sorted(identities)
            ]
    if collisions:
        raise RuntimeError(
            "Duas fontes produziram o mesmo path lógico na coleção. "
            "Use outro --prefix ou renomeie o documento: "
            f"{collisions}"
        )
    physical_keys = combined.loc[valid_identity, "path"].map(
        lambda value: str(
            Path(str(value)).expanduser().resolve()
        ).casefold()
    )
    physical_collisions = (
        combined.loc[valid_identity]
        .assign(_physical_path=physical_keys)
        .groupby("_physical_path")["document_id"]
        .nunique()
    )
    duplicated_physical = physical_collisions[
        physical_collisions.gt(1)
    ].index.tolist()
    if duplicated_physical:
        raise RuntimeError(
            "O mesmo PDF físico não pode ser registrado duas vezes com "
            f"paths lógicos diferentes: {duplicated_physical}"
        )
    valid_rows = combined.loc[valid_identity].drop_duplicates(
        "document_id",
        keep="last",
    )
    invalid_rows = combined.loc[~valid_identity].drop_duplicates(
        "path",
        keep="last",
    )
    return pd.concat([valid_rows, invalid_rows], ignore_index=True)


def rebuild_collection_inventory(
    loaded: LoadedCollection,
    *,
    workers: int = 3,
) -> Path:
    frames = [
        _scan_source(loaded, source, workers=workers)
        for source in loaded.config.sources
    ]
    inventory = _merge_inventory(
        pd.DataFrame(columns=INVENTORY_COLUMNS),
        pd.concat(frames, ignore_index=True),
    )
    _write_inventory(loaded.inventory_path, inventory)
    return loaded.inventory_path


def _source_mapping_for_path(
    loaded: LoadedCollection,
    path: Path,
    *,
    logical_prefix: str,
    recursive: bool,
) -> tuple[CollectionSource, bool]:
    for source in loaded.config.sources:
        registered = _resolve_from_config(loaded.config_path, source.path)
        if registered.is_file():
            if registered == path:
                return source, False
            continue
        try:
            relative = path.relative_to(registered)
        except ValueError:
            continue
        if path.is_file():
            relative_parent = relative.parent
        else:
            relative_parent = relative
        prefix_parts = [
            part
            for part in (
                source.logical_prefix,
                relative_parent.as_posix(),
            )
            if part not in {"", "."}
        ]
        mapped = CollectionSource(
            path=str(path),
            logical_prefix="/".join(prefix_parts),
            recursive=recursive,
        )
        return mapped, False
    return (
        CollectionSource(
            path=str(path),
            logical_prefix=logical_prefix,
            recursive=recursive,
        ),
        True,
    )


def _add_source(
    loaded: LoadedCollection,
    path: Path,
    *,
    logical_prefix: str,
    recursive: bool,
    workers: int,
) -> LoadedCollection:
    source, persist_source = _source_mapping_for_path(
        loaded,
        path,
        logical_prefix=logical_prefix,
        recursive=recursive,
    )
    incoming = _scan_source(loaded, source, workers=workers)
    current = (
        pd.read_csv(
            loaded.inventory_path,
            dtype=str,
            keep_default_na=False,
        ).reindex(columns=INVENTORY_COLUMNS)
        if loaded.inventory_path.is_file()
        else pd.DataFrame(columns=INVENTORY_COLUMNS)
    )
    merged = _merge_inventory(current, incoming)
    _write_inventory(loaded.inventory_path, merged)
    if not persist_source:
        return loaded
    updated = loaded.config.model_copy(
        update={
            "sources": [*loaded.config.sources, source],
            "updated_at": _now(),
        }
    )
    result = LoadedCollection(
        config=CollectionConfig.model_validate(
            updated.model_dump(mode="json")
        ),
        config_path=loaded.config_path,
    )
    save_collection_config(result)
    _register(result)
    return result


def _stage_choice(
    value: str,
    *,
    default: str,
    interactive: bool,
) -> str:
    if value == "auto":
        return default
    if value == "ingest":
        raise NotImplementedError(
            "A etapa de ingestão Qdrant ainda não está implementada. "
            "O pipeline disponível termina em `promote`."
        )
    if value not in STAGES:
        if interactive:
            return Prompt.ask(
                "Até qual etapa preparar a coleção?",
                choices=list(STAGES),
                default=default,
            )
        raise ValueError(f"Etapa inválida: {value!r}")
    return value


def _worker_environment(
    loaded: LoadedCollection,
    api_urls: tuple[str, ...],
) -> dict[str, str]:
    environment = os.environ.copy()
    environment["BASEIA_COLLECTION_CONFIG"] = str(loaded.config_path)
    environment["BASEIA_CONTEXT_ID"] = loaded.config.slug
    environment["BASEIA_DATA_DIR"] = str(loaded.state_dir)
    environment["EXTRACTION_OUTPUT_DIR"] = str(
        loaded.state_dir / "extraction"
    )
    roots = loaded.source_roots
    first_root = roots[0]
    environment["BASEIA_DOCUMENT_STORE_DIR"] = str(
        first_root if first_root.is_dir() else first_root.parent
    )
    environment["BASEIA_DOCUMENT_SOURCE_ROOTS"] = json.dumps(
        [str(path) for path in roots],
        ensure_ascii=False,
    )

    services = loaded.config.services
    resolved_urls = api_urls or tuple(services.mineru_api_urls)
    if resolved_urls:
        environment["MINERU_API_URL"] = resolved_urls[0]
    if services.catalog_api_url:
        environment["BASEIA_CATALOG_API_URL"] = services.catalog_api_url
    if services.s3_endpoint_url:
        environment["BASEIA_S3_ENDPOINT_URL"] = services.s3_endpoint_url
    if services.s3_bucket:
        environment["BASEIA_S3_BUCKET"] = services.s3_bucket
    if services.s3_region:
        environment["AWS_DEFAULT_REGION"] = services.s3_region
    result_endpoint = (
        services.mineru_result_s3_endpoint_url
        or services.s3_endpoint_url
    )
    result_bucket = (
        services.mineru_result_s3_bucket
        or services.s3_bucket
    )
    result_region = (
        services.mineru_result_s3_region
        or services.s3_region
    )
    if result_endpoint:
        environment["MINERU_RESULT_S3_ENDPOINT_URL"] = result_endpoint
    if result_bucket:
        environment["MINERU_RESULT_S3_BUCKET"] = result_bucket
    if result_region:
        environment["MINERU_RESULT_S3_REGION"] = result_region
    secret_mappings = {
        "BASEIA_CATALOG_API_TOKEN": services.catalog_token_env,
        "AWS_ACCESS_KEY_ID": services.s3_access_key_env,
        "AWS_SECRET_ACCESS_KEY": services.s3_secret_key_env,
        "MINERU_RESULT_S3_ACCESS_KEY_ID": (
            services.mineru_result_s3_access_key_env
        ),
        "MINERU_RESULT_S3_SECRET_ACCESS_KEY": (
            services.mineru_result_s3_secret_key_env
        ),
    }
    for destination, source in secret_mappings.items():
        if source and environment.get(source):
            environment[destination] = environment[source]
    return environment


def _run_pipeline(
    loaded: LoadedCollection,
    *,
    through: str,
    api_urls: tuple[str, ...],
    workers: int,
    sample: bool = False,
) -> None:
    if (
        through == "promote"
        and loaded.config.resource_scope == "unassigned"
    ):
        raise RuntimeError(
            "Defina o escopo dos recursos antes de promover: "
            f"`poe collection configure \"{loaded.config.name}\" "
            "--resource-scope personal|operator|client`."
        )
    if sample and through == "promote":
        raise ValueError(
            "Uma amostra não pode substituir o snapshot ativo da coleção. "
            "Crie uma coleção própria para promover esse conjunto ou "
            "execute sem --sample."
        )
    command = [
        sys.executable,
        "-m",
        "baseia_extract.collection_worker",
        "--config",
        str(loaded.config_path),
        "--through",
        through,
        "--workers",
        str(workers),
    ]
    if sample:
        command.append("--sample")
    for api_url in api_urls:
        command.extend(["--api-url", api_url])
    subprocess.run(
        command,
        check=True,
        env=_worker_environment(loaded, api_urls),
    )


def pipeline(
    collection_name: str = "",
    through: str = "auto",
    api_urls: Iterable[str] = (),
    workers: int = 3,
    refresh: bool = False,
    sample: bool = False,
) -> None:
    """Executa o pipeline disponível para uma coleção registrada."""
    loaded = resolve_collection(collection_name)
    resolved_stage = _stage_choice(
        through,
        default=loaded.config.target_stage,
        interactive=False,
    )
    if (
        resolved_stage == "promote"
        and loaded.config.resource_scope == "unassigned"
    ):
        raise RuntimeError(
            "Defina o escopo dos recursos antes de promover: "
            f"`poe collection configure \"{loaded.config.name}\" "
            "--resource-scope personal|operator|client`."
        )
    try:
        with FileLock(_collection_lock_path(loaded.config.slug), timeout=0):
            if refresh or not loaded.inventory_path.is_file():
                rebuild_collection_inventory(loaded, workers=workers)
            _register(loaded, current=True)
            _run_pipeline(
                loaded,
                through=resolved_stage,
                api_urls=tuple(api_urls),
                workers=workers,
                sample=sample,
            )
    except Timeout as error:
        raise RuntimeError(
            f"A coleção {loaded.config.name!r} já está em execução."
        ) from error


def sample(
    size: int = 100,
    seed: int = 42,
    collection_name: str = "",
) -> Path:
    """Amostra a coleção atual sem copiar documentos para o repositório."""
    selector = (
        collection_name.strip()
        or os.getenv("BASEIA_COLLECTION", "").strip()
        or _load_registry_unlocked().current
    )
    if not selector:
        return sample_inventory(size=size, seed=seed)
    loaded = resolve_collection(selector)
    try:
        with FileLock(_collection_lock_path(loaded.config.slug), timeout=10):
            if not loaded.inventory_path.is_file():
                rebuild_collection_inventory(
                    loaded,
                    workers=loaded.config.workers,
                )
            return sample_inventory(
                size=size,
                seed=seed,
                inventory_path=loaded.inventory_path,
                sample_path=loaded.state_dir / "inventory" / "sample.csv",
            )
    except Timeout as error:
        raise RuntimeError(
            f"A coleção {loaded.config.name!r} está em execução."
        ) from error


def _select_collection() -> CollectionCandidate | None:
    candidates = _candidates()
    _print_collection_table(candidates, numbered=True)
    console.print("  0  Criar uma nova coleção")
    choice = Prompt.ask(
        "A qual coleção esses documentos serão adicionados?",
        choices=[str(index) for index in range(0, len(candidates) + 1)],
        default="0",
    )
    if choice == "0":
        return None
    return candidates[int(choice) - 1]


def _prompt_value(
    value: str,
    *,
    question: str,
    choices: list[str],
    default: str,
    interactive: bool,
) -> str:
    if value != "ask":
        return value
    if interactive:
        return Prompt.ask(question, choices=choices, default=default)
    return default


def _new_collection(
    source_path: Path,
    *,
    name: str,
    mode: str,
    resource_scope: str,
    topology: str,
    through: str,
    api_urls: tuple[str, ...],
    recursive: bool,
    workers: int,
    interactive: bool,
) -> LoadedCollection:
    collection_name = name.strip()
    if not collection_name and interactive:
        collection_name = Prompt.ask("Nome da nova coleção")
    if not collection_name:
        raise ValueError("Informe --name para criar uma nova coleção.")
    resolved_mode = _prompt_value(
        mode,
        question="Modo de trabalho",
        choices=["local", "cataloged", "production"],
        default="local",
        interactive=interactive,
    )
    resolved_scope = _prompt_value(
        resource_scope,
        question="Escopo dos recursos",
        choices=["personal", "operator", "client"],
        default="personal",
        interactive=interactive,
    )
    resolved_topology = _prompt_value(
        topology,
        question="Topologia de execução",
        choices=["local", "services", "distributed"],
        default="local",
        interactive=interactive,
    )
    default_stage = (
        "inventory"
        if resolved_mode == "local"
        else "promote"
    )
    resolved_stage = (
        Prompt.ask(
            "Etapa-alvo padrão",
            choices=list(STAGES),
            default=default_stage,
        )
        if interactive and through == "auto"
        else _stage_choice(
            through,
            default=default_stage,
            interactive=False,
        )
    )
    root = source_path if source_path.is_dir() else source_path.parent
    config_path = root / CONFIG_FILENAME
    if config_path.exists():
        raise FileExistsError(
            f"Já existe uma configuração de coleção em {config_path}."
        )
    relative_source = (
        "."
        if source_path.is_dir()
        else source_path.name
    )
    slug = collection_slug(collection_name)
    services = _service_defaults(api_urls)
    if interactive:
        services = _prompt_services(
            services,
            require_catalog=(
                resolved_mode in {"cataloged", "production"}
                or resolved_stage == "promote"
            ),
        )
    config = CollectionConfig(
        id=str(collection_uuid(slug)),
        name=collection_name,
        slug=slug,
        mode=resolved_mode,
        resource_scope=resolved_scope,
        topology=resolved_topology,
        target_stage=resolved_stage,
        workers=workers,
        state_dir=".baseia",
        sources=[
            CollectionSource(
                path=relative_source,
                logical_prefix="",
                recursive=recursive,
            )
        ],
        services=services,
    )
    loaded = LoadedCollection(config=config, config_path=config_path)
    save_collection_config(loaded)
    _register(loaded, current=True)
    rebuild_collection_inventory(loaded, workers=workers)
    return loaded


def _complete_init(
    loaded: LoadedCollection,
    *,
    default_run: bool,
    interactive: bool,
    execute: str,
    through: str,
    api_urls: tuple[str, ...],
    workers: int,
    default_stage: str | None = None,
) -> None:
    # O inventário sempre é auditado, mesmo quando a coleção é apenas
    # registrada. Isso torna a configuração persistida imediatamente útil.
    _run_pipeline(
        loaded,
        through="inventory",
        api_urls=api_urls,
        workers=workers,
    )

    should_run = (
        execute == "run"
        or (execute == "auto" and default_run)
    )
    if interactive and execute == "auto" and not default_run:
        should_run = Confirm.ask(
            f"Executar agora até {default_stage or loaded.config.target_stage}?",
            default=False,
        )
    if execute not in {"auto", "run", "register"}:
        raise ValueError("execute deve ser auto, run ou register.")
    if should_run:
        resolved_stage = _stage_choice(
            through,
            default=default_stage or loaded.config.target_stage,
            interactive=False,
        )
        if resolved_stage != "inventory":
            _run_pipeline(
                loaded,
                through=resolved_stage,
                api_urls=api_urls,
                workers=workers,
            )
    console.print(
        f"Coleção registrada: [bold]{loaded.config.name}[/bold]\n"
        f"Configuração: {loaded.config_path}\n"
        f"Inventário: {loaded.inventory_path}"
    )


def init_source(
    path: str,
    collection_name: str = "",
    name: str = "",
    mode: str = "ask",
    resource_scope: str = "ask",
    topology: str = "ask",
    through: str = "auto",
    execute: str = "auto",
    api_urls: Iterable[str] = (),
    logical_prefix: str = "",
    workers: int = 3,
    recursive: bool = True,
) -> None:
    """Registra uma fonte local em coleção nova ou existente."""
    source_path = Path(path).expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Fonte não encontrada: {source_path}")
    if collection_name and name:
        raise ValueError("Use --collection ou --name, não ambos.")
    interactive = not collection_name.strip() and not name.strip()
    candidate = _select_collection() if interactive else None
    selected_existing = bool(collection_name.strip()) or candidate is not None
    normalized_urls = tuple(
        dict.fromkeys(
            _validated_url(str(value), field_name="api_url")
            for value in api_urls
            if str(value).strip()
        )
    )

    if selected_existing:
        loaded = (
            _materialize(candidate)
            if candidate is not None
            else resolve_collection(collection_name)
        )
        if interactive and loaded.config.resource_scope == "unassigned":
            updated = loaded.config.model_copy(
                update={
                    "resource_scope": Prompt.ask(
                        "Escopo dos recursos",
                        choices=["personal", "operator", "client"],
                        default="personal",
                    ),
                    "updated_at": _now(),
                }
            )
            loaded = LoadedCollection(
                config=CollectionConfig.model_validate(
                    updated.model_dump(mode="json")
                ),
                config_path=loaded.config_path,
            )
            save_collection_config(loaded)
            _register(loaded)
        existing_stage = _effective_stage(loaded)
        prefix = logical_prefix
        if interactive:
            prefix = Prompt.ask(
                "Prefixo lógico na coleção (. significa raiz)",
                default=".",
            )
        try:
            with FileLock(_collection_lock_path(loaded.config.slug), timeout=0):
                loaded = _add_source(
                    loaded,
                    source_path,
                    logical_prefix=_normalized_prefix(prefix),
                    recursive=recursive,
                    workers=workers,
                )
                _register(loaded, current=True)
                _complete_init(
                    loaded,
                    default_run=True,
                    interactive=interactive,
                    execute=execute,
                    through=through,
                    api_urls=normalized_urls,
                    workers=workers,
                    default_stage=existing_stage,
                )
        except Timeout as error:
            raise RuntimeError(
                f"A coleção {loaded.config.name!r} já está em execução."
            ) from error
        return
    else:
        loaded = _new_collection(
            source_path,
            name=name,
            mode=mode,
            resource_scope=resource_scope,
            topology=topology,
            through=through,
            api_urls=normalized_urls,
            recursive=recursive,
            workers=workers,
            interactive=interactive,
        )
        try:
            with FileLock(_collection_lock_path(loaded.config.slug), timeout=0):
                _complete_init(
                    loaded,
                    default_run=False,
                    interactive=interactive,
                    execute=execute,
                    through=through,
                    api_urls=normalized_urls,
                    workers=workers,
                )
        except Timeout as error:
            raise RuntimeError(
                f"A coleção {loaded.config.name!r} já está em execução."
            ) from error


def quick(
    path: str,
    collection_name: str = "",
    through: str = "auto",
    api_urls: Iterable[str] = (),
    logical_prefix: str = "",
    workers: int = 3,
    recursive: bool = True,
) -> None:
    """Adiciona PDFs e os leva imediatamente à etapa-alvo da coleção."""
    loaded = resolve_collection(collection_name)
    init_source(
        path,
        collection_name=loaded.config.name,
        through=through,
        execute="run",
        api_urls=api_urls,
        logical_prefix=logical_prefix,
        workers=workers,
        recursive=recursive,
    )
