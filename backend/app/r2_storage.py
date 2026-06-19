"""
Cloudflare R2 Storage Client
Wraps aioboto3 (S3-compatible) for async upload, download, and delete operations.
R2 uses the S3 API — the only difference is the custom endpoint_url.
"""
import logging
import mimetypes
from typing import Optional

import aioboto3
from botocore.exceptions import ClientError

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Shared aioboto3 session (cheap to create, holds no connections itself)
_session = aioboto3.Session()


def _client():
    """Return a context manager that yields an authenticated S3-compatible storage client."""
    return _session.client(
        "s3",
        endpoint_url=settings.storage_endpoint_url,
        aws_access_key_id=settings.storage_access_key_id,
        aws_secret_access_key=settings.storage_secret_access_key,
        # Supabase S3 uses us-east-1 as the region identifier
        region_name="us-east-1",
    )


async def upload_file(
    file_bytes: bytes,
    key: str,
    content_type: Optional[str] = None,
) -> str:
    """
    Upload raw bytes to R2 under the given object key.

    Args:
        file_bytes: The file content to upload.
        key: The R2 object key (e.g. ``"uploads/abc123_report.pdf"``).
        content_type: MIME type; guessed from the key extension if omitted.

    Returns:
        The object key (same as ``key``), for storing in the database.
    """
    if content_type is None:
        content_type, _ = mimetypes.guess_type(key)
        content_type = content_type or "application/octet-stream"

    async with _client() as s3:
        await s3.put_object(
            Bucket=settings.storage_bucket_name,
            Key=key,
            Body=file_bytes,
            ContentType=content_type,
        )

    logger.info(f"R2 upload: key='{key}' size={len(file_bytes)} bytes")
    return key


async def download_file(key: str) -> bytes:
    """
    Download an object from R2 and return its raw bytes.

    Args:
        key: The R2 object key stored in the database.

    Returns:
        File contents as bytes.

    Raises:
        FileNotFoundError: If the object does not exist in R2.
    """
    try:
        async with _client() as s3:
            response = await s3.get_object(
                Bucket=settings.storage_bucket_name,
                Key=key,
            )
            body = response["Body"]
            data = await body.read()
        logger.info(f"R2 download: key='{key}' size={len(data)} bytes")
        return data
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            raise FileNotFoundError(f"R2 object not found: {key}") from e
        raise


async def delete_file(key: str) -> None:
    """
    Delete an object from R2.

    Args:
        key: The R2 object key to remove.
    """
    try:
        async with _client() as s3:
            await s3.delete_object(
                Bucket=settings.storage_bucket_name,
                Key=key,
            )
        logger.info(f"R2 delete: key='{key}'")
    except ClientError as e:
        # Log but don't raise — a missing key is not fatal on delete
        logger.warning(f"R2 delete warning for key='{key}': {e}")


async def get_presigned_url(key: str, expiry_seconds: int = 3600) -> str:
    """
    Generate a time-limited pre-signed URL for direct client download.

    Args:
        key: The R2 object key.
        expiry_seconds: URL validity window (default 1 hour).

    Returns:
        A pre-signed HTTPS URL string.
    """
    async with _client() as s3:
        url = await s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.r2_bucket_name, "Key": key},
            ExpiresIn=expiry_seconds,
        )
    return url
