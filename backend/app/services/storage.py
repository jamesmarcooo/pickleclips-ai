import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from functools import lru_cache
from app.config import settings


class StorageError(Exception):
    """Raised when an R2 operation fails."""


@lru_cache(maxsize=1)
def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def generate_upload_url(key: str, content_type: str = "video/mp4") -> str:
    """Generate a presigned PUT URL for direct R2 upload."""
    client = get_r2_client()
    try:
        return client.generate_presigned_url(
            "put_object",
            Params={"Bucket": settings.r2_bucket_name, "Key": key, "ContentType": content_type},
            ExpiresIn=3600,
        )
    except ClientError as exc:
        raise StorageError(f"Failed to generate upload URL for {key!r}") from exc


def generate_download_url(key: str, expires_in: int = 3600) -> str:
    """Generate a presigned GET URL for R2 download."""
    client = get_r2_client()
    try:
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.r2_bucket_name, "Key": key},
            ExpiresIn=expires_in,
        )
    except ClientError as exc:
        raise StorageError(f"Failed to generate download URL for {key!r}") from exc


def delete_object(key: str) -> None:
    """Delete an object from R2. No-ops silently if the key does not exist (R2 returns 204 either way)."""
    client = get_r2_client()
    try:
        client.delete_object(Bucket=settings.r2_bucket_name, Key=key)
    except ClientError as exc:
        raise StorageError(f"Failed to delete {key!r}") from exc


def generate_multipart_upload_id(key: str) -> str:
    """Initiate S3 multipart upload, return UploadId."""
    client = get_r2_client()
    try:
        response = client.create_multipart_upload(
            Bucket=settings.r2_bucket_name,
            Key=key,
            ContentType="video/mp4",
        )
        return response["UploadId"]
    except ClientError as exc:
        raise StorageError(f"Failed to initiate multipart upload for {key!r}") from exc


def sign_multipart_part(key: str, upload_id: str, part_number: int) -> str:
    """Generate a presigned URL for uploading a single multipart part."""
    client = get_r2_client()
    try:
        return client.generate_presigned_url(
            "upload_part",
            Params={
                "Bucket": settings.r2_bucket_name,
                "Key": key,
                "UploadId": upload_id,
                "PartNumber": part_number,
            },
            ExpiresIn=3600,
        )
    except ClientError as exc:
        raise StorageError(f"Failed to sign part {part_number} for {key!r}") from exc


def complete_multipart_upload(key: str, upload_id: str, parts: list[dict]) -> None:
    """Complete a multipart upload. parts = [{"ETag": "...", "PartNumber": 1}, ...]"""
    client = get_r2_client()
    try:
        client.complete_multipart_upload(
            Bucket=settings.r2_bucket_name,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )
    except ClientError as exc:
        raise StorageError(f"Failed to complete multipart upload for {key!r}") from exc


def abort_multipart_upload(key: str, upload_id: str) -> None:
    """Abort a multipart upload and release R2's stored parts. Call this on any upload failure
    to avoid being charged for incomplete parts left on R2."""
    client = get_r2_client()
    try:
        client.abort_multipart_upload(
            Bucket=settings.r2_bucket_name, Key=key, UploadId=upload_id
        )
    except ClientError as exc:
        raise StorageError(f"Failed to abort multipart upload for {key!r}") from exc
