from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from urllib.parse import unquote, urlparse

from minio import Minio
from minio.error import S3Error
from pydantic import BaseModel, SecretStr

from .schemas import DocumentRecord


class ObjectStorageCredentials(BaseModel):
    endpoint: str
    bucket: str
    access_key: str
    secret_key: SecretStr


class ObjectStorage:
    """Adaptador fino sobre o SDK oficial do MinIO."""

    def __init__(self, credentials_path: Path) -> None:
        credentials = ObjectStorageCredentials.model_validate_json(
            credentials_path.read_text(encoding="utf-8")
        )
        endpoint = urlparse(credentials.endpoint)
        if endpoint.scheme not in {"http", "https"} or not endpoint.netloc:
            raise ValueError("Endpoint MinIO inválido.")
        if endpoint.path not in {"", "/"}:
            raise ValueError("Endpoint MinIO não deve conter caminho.")

        self.bucket = credentials.bucket
        self._client = Minio(
            endpoint.netloc,
            access_key=credentials.access_key,
            secret_key=credentials.secret_key.get_secret_value(),
            secure=endpoint.scheme == "https",
            region="us-east-1",
        )

    def source_location(
        self,
        document: DocumentRecord,
    ) -> tuple[str, str]:
        object_name = (
            f"inputs/{document.sha256[:2]}/{document.sha256}.pdf"
        )
        expected_size = document.size_bytes or document.path.stat().st_size
        upload = False
        try:
            stat = self._client.stat_object(self.bucket, object_name)
            upload = stat.size != expected_size
        except S3Error as error:
            if error.code not in {"NoSuchKey", "NoSuchObject"}:
                raise
            upload = True

        if upload:
            self._client.fput_object(
                self.bucket,
                object_name,
                str(document.path),
                content_type="application/pdf",
                metadata={"sha256": document.sha256},
            )

        url = self._client.presigned_get_object(
            self.bucket,
            object_name,
            expires=timedelta(hours=2),
        )
        return f"s3://{self.bucket}/{object_name}", url

    def artifact_uri(self, result: dict[str, object]) -> str:
        from mineru_client import MineruClient

        entry = MineruClient.first(result)
        tarball_url = entry.get("tarball_url")
        if not isinstance(tarball_url, str) or not tarball_url:
            raise ValueError("Resultado Serverless sem tarball_url.")
        path = unquote(urlparse(tarball_url).path).lstrip("/")
        bucket_prefix = f"{self.bucket}/"
        if not path.startswith(bucket_prefix):
            raise ValueError("tarball_url não pertence ao bucket configurado.")
        return f"s3://{path}"
