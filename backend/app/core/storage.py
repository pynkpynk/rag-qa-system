from __future__ import annotations

import os
import pathlib
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Optional

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError


@dataclass(frozen=True)
class StoredFile:
    storage_key: str
    size_bytes: int


def _safe_filename(name: str) -> str:
    base = pathlib.Path(name or "").name
    base = base.replace("\x00", "").strip()
    return base or "uploaded.pdf"


class S3Storage:
    def __init__(self) -> None:
        self.bucket = os.environ["S3_BUCKET"]
        self.prefix = os.environ.get("S3_PREFIX", "uploads").strip("/")

        self.region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "ap-southeast-1"
        self.presign_expires = int(os.environ.get("S3_PRESIGN_EXPIRES", "900"))

        # 署名URLはclock skewに弱いので、リトライ/タイムアウトはやや優しめ
        self._client = boto3.client(
            "s3",
            region_name=self.region,
            config=BotoConfig(
                retries={"max_attempts": 5, "mode": "standard"},
                connect_timeout=5,
                read_timeout=60,
            ),
        )

    def make_pdf_key(self, content_hash: str, filename: str) -> str:
        fn = _safe_filename(filename)
        # prefix分散
        return f"{self.prefix}/{content_hash[:2]}/{content_hash}/{fn}"

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as e:
            code = (e.response.get("Error") or {}).get("Code")
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def upload_file(self, local_path: str, key: str) -> int:
        # サイズ計測
        size = os.stat(local_path).st_size
        self._client.upload_file(
            Filename=local_path,
            Bucket=self.bucket,
            Key=key,
            ExtraArgs={
                "ContentType": "application/pdf",
            },
        )
        return size

    @contextmanager
    def download_to_temp(self, key: str) -> Iterator[str]:
        fd, tmp_path = tempfile.mkstemp(prefix="ragqa_", suffix=".pdf")
        os.close(fd)
        try:
            self._client.download_file(self.bucket, key, tmp_path)
            yield tmp_path
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    def presign_get_url(self, key: str, filename: str, inline: bool) -> str:
        safe = _safe_filename(filename)
        dispo = "inline" if inline else "attachment"
        return self._client.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ResponseContentType": "application/pdf",
                "ResponseContentDisposition": f'{dispo}; filename="{safe}"',
            },
            ExpiresIn=self.presign_expires,
        )


def get_storage_backend() -> Optional[S3Storage]:
    backend = (os.environ.get("STORAGE_BACKEND") or "").lower().strip()
    if backend == "s3":
        return S3Storage()
    return None
