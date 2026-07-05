from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import BinaryIO

import boto3
from botocore.client import BaseClient

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class ObjectStoreConfig:
    provider: str
    bucket: str
    region: str | None
    endpoint_url: str | None
    access_key: str | None
    secret_key: str | None


def _resolve_object_store_config(settings: Settings) -> ObjectStoreConfig:
    if settings.object_store_provider == "tos":
        return ObjectStoreConfig(
            provider="tos",
            bucket=settings.tos_bucket or settings.object_store_bucket,
            region=settings.tos_region or settings.object_store_region,
            endpoint_url=settings.tos_endpoint or settings.s3_endpoint_url,
            access_key=settings.tos_access_key or settings.aws_access_key_id,
            secret_key=settings.tos_secret_key or settings.aws_secret_access_key,
        )

    return ObjectStoreConfig(
        provider="s3",
        bucket=settings.object_store_bucket,
        region=settings.object_store_region,
        endpoint_url=settings.s3_endpoint_url,
        access_key=settings.aws_access_key_id,
        secret_key=settings.aws_secret_access_key,
    )


def build_s3_client() -> BaseClient:
    settings = get_settings()
    cfg = _resolve_object_store_config(settings)

    session = boto3.session.Session()
    return session.client(
        "s3",
        region_name=cfg.region,
        endpoint_url=cfg.endpoint_url,
        aws_access_key_id=cfg.access_key,
        aws_secret_access_key=cfg.secret_key,
    )


def tenant_key(tenant_id: uuid.UUID | str, prefix: str, filename: str) -> str:
    tenant_str = str(tenant_id)
    safe_prefix = prefix if prefix.endswith("/") else f"{prefix}/"
    return f"{tenant_str}/{safe_prefix}{filename}"


def upload_bytesio(
    *,
    tenant_id: uuid.UUID | str,
    prefix: str,
    filename: str,
    fileobj: BinaryIO,
    content_type: str | None,
) -> tuple[str, str]:
    settings = get_settings()
    cfg = _resolve_object_store_config(settings)
    client = build_s3_client()
    key = tenant_key(tenant_id, prefix, filename)

    extra_args = {"ContentType": content_type} if content_type else None
    client.upload_fileobj(fileobj, cfg.bucket, key, ExtraArgs=extra_args or {})
    return cfg.bucket, key


def create_multipart_upload(
    *,
    tenant_id: uuid.UUID | str,
    prefix: str,
    filename: str,
    content_type: str | None,
) -> tuple[str, str, str]:
    settings = get_settings()
    cfg = _resolve_object_store_config(settings)
    client = build_s3_client()
    key = tenant_key(tenant_id, prefix, filename)

    params: dict[str, object] = {
        "Bucket": cfg.bucket,
        "Key": key,
    }
    if content_type:
        params["ContentType"] = content_type
    resp = client.create_multipart_upload(**params)
    upload_id = str(resp["UploadId"])
    return cfg.bucket, key, upload_id


def generate_multipart_upload_url(
    *,
    bucket: str,
    key: str,
    upload_id: str,
    part_number: int,
    expires_seconds: int = 3600,
) -> str:
    client = build_s3_client()
    return str(
        client.generate_presigned_url(
            ClientMethod="upload_part",
            Params={
                "Bucket": bucket,
                "Key": key,
                "UploadId": upload_id,
                "PartNumber": part_number,
            },
            ExpiresIn=expires_seconds,
        )
    )


def complete_multipart_upload(
    *,
    bucket: str,
    key: str,
    upload_id: str,
    parts: list[dict[str, object]],
) -> None:
    client = build_s3_client()
    normalized = sorted(
        [
            {
                "PartNumber": int(part["PartNumber"]),
                "ETag": str(part["ETag"]),
            }
            for part in parts
        ],
        key=lambda item: item["PartNumber"],
    )
    client.complete_multipart_upload(
        Bucket=bucket,
        Key=key,
        UploadId=upload_id,
        MultipartUpload={"Parts": normalized},
    )


def abort_multipart_upload(
    *,
    bucket: str,
    key: str,
    upload_id: str,
) -> None:
    client = build_s3_client()
    client.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=upload_id)


def head_object(
    *,
    bucket: str,
    key: str,
) -> dict[str, str | int | None]:
    client = build_s3_client()
    resp = client.head_object(Bucket=bucket, Key=key)
    return {
        "etag": str(resp.get("ETag") or "").strip('"') or None,
        "content_type": resp.get("ContentType"),
        "size_bytes": int(resp.get("ContentLength") or 0),
    }


def download_object_bytes(
    *, bucket: str, key: str, max_bytes: int | None = None
) -> bytes:
    client = build_s3_client()
    resp = client.get_object(Bucket=bucket, Key=key)
    body = resp["Body"]
    if max_bytes is None:
        return body.read()
    return body.read(max_bytes)


def stream_object(
    *, bucket: str, key: str
) -> BinaryIO:
    client = build_s3_client()
    resp = client.get_object(Bucket=bucket, Key=key)
    return resp["Body"]
