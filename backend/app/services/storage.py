import boto3
from botocore.config import Config
from app.config import settings


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
    return client.generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.r2_bucket_name, "Key": key, "ContentType": content_type},
        ExpiresIn=3600,
    )


def generate_download_url(key: str, expires_in: int = 3600) -> str:
    """Generate a presigned GET URL for R2 download."""
    client = get_r2_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.r2_bucket_name, "Key": key},
        ExpiresIn=expires_in,
    )


def delete_object(key: str) -> None:
    client = get_r2_client()
    client.delete_object(Bucket=settings.r2_bucket_name, Key=key)


def generate_multipart_upload_id(key: str) -> str:
    """Initiate S3 multipart upload, return UploadId."""
    client = get_r2_client()
    response = client.create_multipart_upload(
        Bucket=settings.r2_bucket_name,
        Key=key,
        ContentType="video/mp4",
    )
    return response["UploadId"]


def sign_multipart_part(key: str, upload_id: str, part_number: int) -> str:
    """Generate a presigned URL for uploading a single multipart part."""
    client = get_r2_client()
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


def complete_multipart_upload(key: str, upload_id: str, parts: list[dict]) -> None:
    """Complete a multipart upload. parts = [{"ETag": "...", "PartNumber": 1}, ...]"""
    client = get_r2_client()
    client.complete_multipart_upload(
        Bucket=settings.r2_bucket_name,
        Key=key,
        UploadId=upload_id,
        MultipartUpload={"Parts": parts},
    )


def abort_multipart_upload(key: str, upload_id: str) -> None:
    client = get_r2_client()
    client.abort_multipart_upload(
        Bucket=settings.r2_bucket_name, Key=key, UploadId=upload_id
    )
