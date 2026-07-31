from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .semantic_models import BlockRole


class SplitterKind(StrEnum):
    RECURSIVE_CHARACTER = "recursive_character"


class TokenizerName(StrEnum):
    CL100K_BASE = "cl100k_base"


class BlockAction(StrEnum):
    EMBED = "embed"
    PAYLOAD = "payload"
    PLACEHOLDER = "placeholder"
    EXCLUDE = "exclude"


class BlockPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: BlockAction
    placeholder: str | None = None

    @model_validator(mode="after")
    def placeholder_only_when_needed(self) -> BlockPolicy:
        if self.action is BlockAction.PLACEHOLDER and not self.placeholder:
            raise ValueError("placeholder é obrigatório para action=placeholder")
        if self.action is not BlockAction.PLACEHOLDER and self.placeholder:
            raise ValueError("placeholder só pode ser definido para placeholder")
        return self


class SplitterPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: SplitterKind = SplitterKind.RECURSIVE_CHARACTER
    tokenizer: TokenizerName = TokenizerName.CL100K_BASE
    chunk_size: int = Field(default=700, ge=1)
    chunk_overlap: int = Field(default=100, ge=0)

    @model_validator(mode="after")
    def overlap_is_smaller(self) -> SplitterPolicy:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap deve ser menor que chunk_size")
        return self


class EmbeddingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["openrouter"] = "openrouter"
    model: str = "openai/text-embedding-3-small"
    dimensions: int = Field(default=1536, ge=1)
    base_url: str = "https://openrouter.ai/api/v1"
    api_key_env: str = "OPENROUTER_API_KEY"
    batch_size: int = Field(default=64, ge=1, le=2048)
    max_retries: int = Field(default=3, ge=0, le=20)
    retry_min_seconds: float = Field(default=1.0, ge=0)
    retry_max_seconds: float = Field(default=30.0, ge=0)

    @field_validator("model", "api_key_env")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("valor não pode ser vazio")
        return value.strip()


class QdrantPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = ""
    api_key_env: str = "QDRANT_API_KEY"
    collection: str = Field(min_length=1)
    distance: Literal["cosine"] = "cosine"
    on_disk_payload: bool = True
    replace_documents: bool = True


class IngestPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    name: str = Field(min_length=1)
    version: str = "1"
    contextual_prefix: bool = False
    include_title_payload: bool = True
    include_abstract_payload: bool = True
    include_references_payload: bool = True
    base64_assets: bool = True
    splitter: SplitterPolicy = Field(default_factory=SplitterPolicy)
    embedding: EmbeddingPolicy = Field(default_factory=EmbeddingPolicy)
    qdrant: QdrantPolicy
    blocks: dict[BlockRole, BlockPolicy]

    @model_validator(mode="after")
    def required_asset_placeholders(self) -> IngestPolicy:
        for role in (BlockRole.FIGURE, BlockRole.TABLE, BlockRole.EQUATION):
            policy = self.blocks.get(role)
            if policy is None or policy.action is not BlockAction.PLACEHOLDER:
                raise ValueError(f"{role.value} deve usar placeholder")
        missing_roles = set(BlockRole) - set(self.blocks)
        if missing_roles:
            raise ValueError(
                "A política deve declarar todos os papéis: "
                + ", ".join(sorted(role.value for role in missing_roles))
            )
        return self


def load_ingest_policy(path: str | Path) -> IngestPolicy:
    import yaml

    source = Path(path).expanduser().resolve()
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    return IngestPolicy.model_validate(payload)
