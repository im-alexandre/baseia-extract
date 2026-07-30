from __future__ import annotations

import hashlib
import mimetypes
import os
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import boto3
from boto3.s3.transfer import TransferConfig, create_transfer_manager
from botocore.config import Config
from botocore.exceptions import ClientError

from .identity import normalize_relative_path, validate_sha256


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    bucket: str
    key: str
    sha256: str
    size_bytes: int
    content_type: str
    etag: str | None = None

    @property
    def uri(self) -> str:
        return f"s3://{self.bucket}/{self.key}"


@dataclass(frozen=True, slots=True)
class UploadRequest:
    source: Path
    key: str
    sha256: str | None = None
    content_type: str | None = None


@dataclass(frozen=True, slots=True)
class DownloadRequest:
    key: str
    destination: Path
    sha256: str | None = None


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


class S3ArtifactStore:
    """S3 compatível, usando o SDK oficial e checksums próprios.

    ETag não é tratado como MD5: multipart e implementações compatíveis podem
    usar outra semântica. O SHA-256 fica nos metadados e no catálogo.
    """

    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        region: str = "us-east-1",
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        max_concurrency: int = 16,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency deve ser positivo.")
        self.endpoint_url = endpoint_url.rstrip("/")
        self.bucket = bucket.strip()
        self.region = region.strip() or "us-east-1"
        self.max_concurrency = max_concurrency
        if not self.endpoint_url or not self.bucket:
            raise ValueError("endpoint_url e bucket são obrigatórios.")
        self.client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            region_name=self.region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(
                retries={"max_attempts": 8, "mode": "adaptive"},
                max_pool_connections=max(16, max_concurrency * 2),
                s3={"addressing_style": "path"},
            ),
        )

    @classmethod
    def from_env(
        cls,
        *,
        max_concurrency: int | None = None,
    ) -> S3ArtifactStore:
        endpoint_url = os.getenv(
            "BASEIA_S3_ENDPOINT_URL",
            "http://127.0.0.1:8333",
        )
        access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
        secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        endpoint_host = (urlparse(endpoint_url).hostname or "").casefold()
        if (
            not access_key_id
            and not secret_access_key
            and endpoint_host in {"127.0.0.1", "localhost", "::1"}
        ):
            access_key_id = "baseia"
            secret_access_key = "baseia-secret"
        return cls(
            endpoint_url=endpoint_url,
            bucket=os.getenv("BASEIA_S3_BUCKET", "baseia"),
            region=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            max_concurrency=(
                max_concurrency
                if max_concurrency is not None
                else int(os.getenv("BASEIA_S3_MAX_CONCURRENCY", "16"))
            ),
        )

    @classmethod
    def from_result_env(
        cls,
        *,
        bucket: str,
        max_concurrency: int | None = None,
    ) -> S3ArtifactStore:
        """Cria o store usado para materializar resultados remotos do MinerU.

        Por padrão, o result store é o mesmo S3 canônico. As variáveis
        MINERU_RESULT_S3_* permitem que um servidor de GPU use outro endpoint
        sem alterar o destino da promoção da coleção.
        """
        canonical_endpoint = os.getenv(
            "BASEIA_S3_ENDPOINT_URL",
            "http://127.0.0.1:8333",
        ).rstrip("/")
        endpoint_url = os.getenv(
            "MINERU_RESULT_S3_ENDPOINT_URL",
            canonical_endpoint,
        ).rstrip("/")
        expected_bucket = os.getenv(
            "MINERU_RESULT_S3_BUCKET",
            "",
        ).strip()
        if expected_bucket and expected_bucket != bucket:
            raise RuntimeError(
                "Bucket retornado pelo MinerU diverge do result store "
                f"configurado: recebido={bucket!r}, "
                f"configurado={expected_bucket!r}."
            )

        access_key_id = os.getenv("MINERU_RESULT_S3_ACCESS_KEY_ID")
        secret_access_key = os.getenv(
            "MINERU_RESULT_S3_SECRET_ACCESS_KEY"
        )
        if (
            not access_key_id
            and not secret_access_key
            and endpoint_url == canonical_endpoint
        ):
            access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
            secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")

        return cls(
            endpoint_url=endpoint_url,
            bucket=bucket,
            region=os.getenv(
                "MINERU_RESULT_S3_REGION",
                os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            ),
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            max_concurrency=(
                max_concurrency
                if max_concurrency is not None
                else int(os.getenv("BASEIA_S3_MAX_CONCURRENCY", "16"))
            ),
        )

    def ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return
        except ClientError as error:
            status = int(
                error.response.get("ResponseMetadata", {}).get(
                    "HTTPStatusCode",
                    0,
                )
            )
            if status == 403:
                raise RuntimeError(
                    "S3 rejeitou o acesso ao bucket "
                    f"{self.bucket!r} em {self.endpoint_url!r}. "
                    "Configure AWS_ACCESS_KEY_ID e "
                    "AWS_SECRET_ACCESS_KEY para esse endpoint."
                ) from error
            if status not in {400, 404}:
                raise
        self.client.create_bucket(Bucket=self.bucket)
        self.client.head_bucket(Bucket=self.bucket)

    def close(self) -> None:
        self.client.close()

    def head(self, key: str) -> ArtifactRef | None:
        normalized = normalize_relative_path(key)
        try:
            response = self.client.head_object(
                Bucket=self.bucket,
                Key=normalized,
            )
        except ClientError as error:
            status = int(
                error.response.get("ResponseMetadata", {}).get(
                    "HTTPStatusCode",
                    0,
                )
            )
            if status == 404:
                return None
            raise
        metadata = {
            str(name).casefold(): str(value)
            for name, value in response.get("Metadata", {}).items()
        }
        checksum = metadata.get("sha256")
        if checksum is None:
            return None
        return ArtifactRef(
            bucket=self.bucket,
            key=normalized,
            sha256=validate_sha256(checksum),
            size_bytes=int(response["ContentLength"]),
            content_type=str(
                response.get("ContentType") or "application/octet-stream"
            ),
            etag=str(response.get("ETag", "")).strip('"') or None,
        )

    def is_current(
        self,
        *,
        key: str,
        sha256: str,
        size_bytes: int,
    ) -> bool:
        current = self.head(key)
        return (
            current is not None
            and current.sha256 == validate_sha256(sha256)
            and current.size_bytes == size_bytes
        )

    def upload_many(
        self,
        requests: Iterable[UploadRequest],
        *,
        check_existing: bool = True,
    ) -> list[ArtifactRef]:
        prepared: list[tuple[UploadRequest, ArtifactRef]] = []
        for request in requests:
            source = request.source.resolve()
            if not source.is_file():
                raise FileNotFoundError(source)
            key = normalize_relative_path(request.key)
            checksum = (
                validate_sha256(request.sha256)
                if request.sha256 is not None
                else file_sha256(source)
            )
            content_type = (
                request.content_type
                or mimetypes.guess_type(source.name)[0]
                or "application/octet-stream"
            )
            prepared.append(
                (
                    UploadRequest(
                        source=source,
                        key=key,
                        sha256=checksum,
                        content_type=content_type,
                    ),
                    ArtifactRef(
                        bucket=self.bucket,
                        key=key,
                        sha256=checksum,
                        size_bytes=source.stat().st_size,
                        content_type=content_type,
                    ),
                )
            )

        pending = (
            [
                (request, reference)
                for request, reference in prepared
                if not self.is_current(
                    key=reference.key,
                    sha256=reference.sha256,
                    size_bytes=reference.size_bytes,
                )
            ]
            if check_existing
            else prepared
        )
        if pending:
            manager = create_transfer_manager(
                self.client,
                TransferConfig(
                    multipart_threshold=16 * 1024 * 1024,
                    multipart_chunksize=16 * 1024 * 1024,
                    max_concurrency=self.max_concurrency,
                ),
            )
            try:
                futures = [
                    manager.upload(
                        str(request.source),
                        self.bucket,
                        reference.key,
                        extra_args={
                            "ContentType": reference.content_type,
                            "Metadata": {"sha256": reference.sha256},
                        },
                    )
                    for request, reference in pending
                ]
                for future in futures:
                    future.result()
            finally:
                manager.shutdown()

        verified: list[ArtifactRef] = []
        for _, expected in prepared:
            actual = self.head(expected.key)
            if (
                actual is None
                or actual.sha256 != expected.sha256
                or actual.size_bytes != expected.size_bytes
            ):
                raise RuntimeError(
                    f"Objeto S3 não confirmou checksum/tamanho: {expected.key}"
                )
            verified.append(actual)
        return verified

    def upload_file(
        self,
        source: Path,
        key: str,
        *,
        sha256: str | None = None,
        content_type: str | None = None,
    ) -> ArtifactRef:
        return self.upload_many(
            [
                UploadRequest(
                    source=source,
                    key=key,
                    sha256=sha256,
                    content_type=content_type,
                )
            ]
        )[0]

    def download_file(
        self,
        key: str,
        destination: Path,
        *,
        expected_sha256: str | None = None,
    ) -> ArtifactRef:
        return self.download_many(
            [
                DownloadRequest(
                    key=key,
                    destination=destination,
                    sha256=expected_sha256,
                )
            ]
        )[0]

    def download_many(
        self,
        requests: Iterable[DownloadRequest],
    ) -> list[ArtifactRef]:
        prepared: list[tuple[DownloadRequest, ArtifactRef, Path]] = []
        destinations: dict[str, Path] = {}
        for request in requests:
            normalized = normalize_relative_path(request.key)
            reference = self.head(normalized)
            if reference is None:
                raise FileNotFoundError(
                    f"s3://{self.bucket}/{normalized}"
                )
            required_hash = (
                validate_sha256(request.sha256)
                if request.sha256 is not None
                else reference.sha256
            )
            if reference.sha256 != required_hash:
                raise RuntimeError(
                    f"Checksum S3 divergiu antes do download: {normalized}"
                )
            destination = request.destination.resolve()
            destination_key = str(destination).casefold()
            if destination_key in destinations:
                raise ValueError(
                    "Colisão de destino de download: "
                    f"{destinations[destination_key]} e {destination}"
                )
            destinations[destination_key] = destination
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(
                f".{destination.name}.{uuid.uuid4().hex}.downloading"
            )
            prepared.append(
                (
                    DownloadRequest(
                        key=normalized,
                        destination=destination,
                        sha256=required_hash,
                    ),
                    reference,
                    temporary,
                )
            )

        if not prepared:
            return []
        manager = create_transfer_manager(
            self.client,
            TransferConfig(
                multipart_threshold=16 * 1024 * 1024,
                multipart_chunksize=16 * 1024 * 1024,
                max_concurrency=self.max_concurrency,
            ),
        )
        try:
            try:
                futures = [
                    manager.download(
                        self.bucket,
                        request.key,
                        str(temporary),
                    )
                    for request, _, temporary in prepared
                ]
                for future in futures:
                    future.result()
            finally:
                manager.shutdown()
            for request, reference, temporary in prepared:
                if (
                    temporary.stat().st_size != reference.size_bytes
                    or file_sha256(temporary) != request.sha256
                ):
                    raise RuntimeError(
                        "Download S3 divergente: "
                        f"s3://{self.bucket}/{request.key}"
                    )
            for request, _, temporary in prepared:
                os.replace(temporary, request.destination)
        finally:
            for _, _, temporary in prepared:
                temporary.unlink(missing_ok=True)
        return [reference for _, reference, _ in prepared]

    def iter_objects(self, prefix: str = "") -> Iterator[dict[str, object]]:
        normalized = (
            normalize_relative_path(prefix)
            if prefix.strip("/")
            else ""
        )
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(
            Bucket=self.bucket,
            Prefix=normalized,
        ):
            for item in page.get("Contents", []):
                if isinstance(item, dict) and item.get("Key"):
                    yield item
