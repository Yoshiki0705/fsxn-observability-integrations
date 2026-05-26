"""S3 Copy Lambda for FSxN Management Console.

Copies files from FSx ONTAP S3 Access Point to a standard S3 bucket
and generates presigned URLs for download. FSx ONTAP S3 APs do not
support presigned URLs directly, so the copy-to-bucket pattern is required.

Environment Variables:
    TEMP_BUCKET_NAME: Standard S3 bucket for temporary file storage.
    S3_ACCESS_POINT_ARN: Default S3 AP ARN (can be overridden per request).
    LOG_LEVEL: Logging level (default: INFO).
    PRESIGNED_URL_EXPIRY: Presigned URL expiry in seconds (default: 3600).
"""

import logging
import os
import re
import uuid
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, ConnectTimeoutError

# ─── Configuration from environment ────────────────────────────────────────

TEMP_BUCKET_NAME = os.environ.get("TEMP_BUCKET_NAME", "")
S3_ACCESS_POINT_ARN = os.environ.get("S3_ACCESS_POINT_ARN", "")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
PRESIGNED_URL_EXPIRY = int(os.environ.get("PRESIGNED_URL_EXPIRY", "3600"))

# ─── Constants ──────────────────────────────────────────────────────────────

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024 * 1024  # 5 GB
S3_AP_CONNECT_TIMEOUT = 10  # seconds
S3_AP_READ_TIMEOUT = 300  # seconds (large file copy)
S3_AP_ARN_PATTERN = re.compile(
    r"^arn:aws:s3:[a-z0-9-]+:\d{12}:accesspoint/[a-zA-Z0-9\-]+$"
)
# Path traversal patterns to reject in object keys
PATH_TRAVERSAL_PATTERN = re.compile(r"(^|/)\.\.(/|$)")

# ─── Logger setup ──────────────────────────────────────────────────────────

logger = logging.getLogger()
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

# ─── S3 Clients ────────────────────────────────────────────────────────────

# Client for S3 AP access — uses connect_timeout=10s for AP unreachable detection.
# This client routes through NAT Gateway for internet-origin S3 APs.
_s3_ap_config = Config(
    connect_timeout=S3_AP_CONNECT_TIMEOUT,
    read_timeout=S3_AP_READ_TIMEOUT,
    retries={"max_attempts": 2, "mode": "standard"},
)
_s3_ap_client = boto3.client("s3", config=_s3_ap_config)

# Client for temp bucket operations (presigned URL generation).
# Uses S3 Gateway Endpoint — no NAT Gateway needed.
_s3_temp_client = boto3.client("s3")


def validate_input(event: dict[str, Any]) -> tuple[str, str]:
    """Validate and extract S3 AP ARN and object key from the event.

    Args:
        event: Lambda event payload containing 's3_access_point_arn' and
            'object_key' fields.

    Returns:
        Tuple of (s3_access_point_arn, object_key).

    Raises:
        ValueError: If required fields are missing or invalid.
    """
    s3_ap_arn = event.get("s3_access_point_arn", "") or S3_ACCESS_POINT_ARN
    object_key = event.get("object_key", "")

    if not s3_ap_arn:
        raise ValueError("Missing required field: 's3_access_point_arn'")

    if not object_key:
        raise ValueError("Missing required field: 'object_key'")

    if not S3_AP_ARN_PATTERN.match(s3_ap_arn):
        raise ValueError(
            f"Invalid S3 Access Point ARN format: '{s3_ap_arn}'. "
            "Expected: arn:aws:s3:<region>:<account-id>:accesspoint/<name>"
        )

    # Reject path traversal attempts
    if PATH_TRAVERSAL_PATTERN.search(object_key):
        raise ValueError(
            f"Invalid object key: path traversal detected in '{object_key}'"
        )

    # Reject empty segments or leading/trailing slashes that could be suspicious
    if object_key.startswith("/"):
        raise ValueError(
            f"Invalid object key: must not start with '/': '{object_key}'"
        )

    return s3_ap_arn, object_key


def check_file_size(s3_ap_arn: str, object_key: str) -> int:
    """Check the file size via HeadObject on the S3 Access Point.

    Args:
        s3_ap_arn: S3 Access Point ARN to use as the Bucket parameter.
        object_key: Object key to check.

    Returns:
        File size in bytes.

    Raises:
        ValueError: If file exceeds 5 GB limit.
        ConnectionError: If S3 AP is unreachable within timeout.
        ClientError: If HeadObject fails for other reasons.
    """
    try:
        response = _s3_ap_client.head_object(Bucket=s3_ap_arn, Key=object_key)
    except ConnectTimeoutError as exc:
        raise ConnectionError(
            f"S3 Access Point unreachable within {S3_AP_CONNECT_TIMEOUT}s timeout. "
            "Verify VPC endpoint configuration and NAT Gateway connectivity."
        ) from exc
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code == "404" or error_code == "NoSuchKey":
            raise ValueError(
                f"Object not found: '{object_key}' in access point '{s3_ap_arn}'"
            ) from exc
        raise

    content_length = response.get("ContentLength", 0)

    if content_length > MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"File size {content_length / (1024**3):.2f} GB exceeds "
            f"maximum downloadable limit of 5 GB."
        )

    return content_length


def copy_object_to_temp_bucket(
    s3_ap_arn: str, object_key: str, request_id: str
) -> str:
    """Copy object from S3 Access Point to the temp bucket.

    Uses GetObject from S3 AP + PutObject to temp bucket (streaming copy).
    The temp bucket has a 24h lifecycle rule for automatic cleanup.

    Args:
        s3_ap_arn: S3 Access Point ARN.
        object_key: Source object key.
        request_id: Unique request ID for temp key namespacing.

    Returns:
        The destination key in the temp bucket.

    Raises:
        ConnectionError: If S3 AP is unreachable.
        RuntimeError: If copy operation fails.
    """
    # Generate a unique temp key to avoid collisions
    # Format: tmp/<request_id>/<original_filename>
    filename = object_key.rsplit("/", 1)[-1] if "/" in object_key else object_key
    temp_key = f"tmp/{request_id}/{filename}"

    logger.info(
        "Copying object from S3 AP to temp bucket",
        extra={
            "source_ap": s3_ap_arn,
            "source_key": object_key,
            "dest_bucket": TEMP_BUCKET_NAME,
            "dest_key": temp_key,
        },
    )

    try:
        # Get object from S3 AP (routes through NAT Gateway)
        get_response = _s3_ap_client.get_object(
            Bucket=s3_ap_arn, Key=object_key
        )

        # Stream to temp bucket (routes through S3 Gateway Endpoint)
        _s3_temp_client.put_object(
            Bucket=TEMP_BUCKET_NAME,
            Key=temp_key,
            Body=get_response["Body"].read(),
            ContentType=get_response.get("ContentType", "application/octet-stream"),
        )

    except ConnectTimeoutError as exc:
        raise ConnectionError(
            f"S3 Access Point unreachable within {S3_AP_CONNECT_TIMEOUT}s timeout. "
            "Verify VPC endpoint configuration and NAT Gateway connectivity."
        ) from exc
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        error_msg = exc.response.get("Error", {}).get("Message", "")
        raise RuntimeError(
            f"Copy operation failed: [{error_code}] {error_msg}"
        ) from exc

    logger.info(
        "Object copied successfully to temp bucket",
        extra={"dest_bucket": TEMP_BUCKET_NAME, "dest_key": temp_key},
    )

    return temp_key


def generate_presigned_url(temp_key: str) -> str:
    """Generate a presigned URL for the copied object in the temp bucket.

    Args:
        temp_key: Object key in the temp bucket.

    Returns:
        Presigned URL with configured expiry (default 3600s).
    """
    url = _s3_temp_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": TEMP_BUCKET_NAME, "Key": temp_key},
        ExpiresIn=PRESIGNED_URL_EXPIRY,
    )

    logger.info(
        "Presigned URL generated",
        extra={
            "temp_key": temp_key,
            "expiry_seconds": PRESIGNED_URL_EXPIRY,
        },
    )

    return url


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entry point for S3 copy and presigned URL generation.

    Copies a file from FSx ONTAP S3 Access Point to a standard S3 bucket
    and returns a presigned URL for download. This is required because
    FSx ONTAP S3 APs do not support presigned URLs directly.

    Args:
        event: Lambda event with fields:
            - s3_access_point_arn (str): S3 AP ARN (optional if env var set).
            - object_key (str): Object key to download.
        context: Lambda context object.

    Returns:
        Response dict with:
            - statusCode (int): HTTP status code.
            - body (dict): Contains 'presigned_url', 'object_key',
              'file_size_bytes', and 'expiry_seconds' on success,
              or 'error' and 'message' on failure.
    """
    request_id = getattr(context, "aws_request_id", str(uuid.uuid4()))

    logger.info(
        "S3 copy request received",
        extra={"request_id": request_id, "event_keys": list(event.keys())},
    )

    try:
        # Step 1: Validate input
        s3_ap_arn, object_key = validate_input(event)
        logger.info(
            "Input validated",
            extra={
                "request_id": request_id,
                "s3_ap_arn": s3_ap_arn,
                "object_key": object_key,
            },
        )

        # Step 2: Check file size (reject > 5 GB)
        file_size = check_file_size(s3_ap_arn, object_key)
        logger.info(
            "File size validated",
            extra={
                "request_id": request_id,
                "file_size_bytes": file_size,
                "file_size_mb": round(file_size / (1024 * 1024), 2),
            },
        )

        # Step 3: Copy object from S3 AP to temp bucket
        temp_key = copy_object_to_temp_bucket(s3_ap_arn, object_key, request_id)

        # Step 4: Generate presigned URL from temp bucket
        presigned_url = generate_presigned_url(temp_key)

        logger.info(
            "S3 copy request completed successfully",
            extra={"request_id": request_id, "object_key": object_key},
        )

        return {
            "statusCode": 200,
            "body": {
                "presigned_url": presigned_url,
                "object_key": object_key,
                "file_size_bytes": file_size,
                "expiry_seconds": PRESIGNED_URL_EXPIRY,
            },
        }

    except ValueError as exc:
        logger.warning(
            "Validation error",
            extra={"request_id": request_id, "error": str(exc)},
        )
        return {
            "statusCode": 400,
            "body": {
                "error": "ValidationError",
                "message": str(exc),
            },
        }

    except ConnectionError as exc:
        logger.error(
            "S3 Access Point connectivity error",
            extra={"request_id": request_id, "error": str(exc)},
        )
        return {
            "statusCode": 504,
            "body": {
                "error": "AccessPointUnreachable",
                "message": str(exc),
            },
        }

    except RuntimeError as exc:
        logger.error(
            "Copy operation failed",
            extra={"request_id": request_id, "error": str(exc)},
        )
        return {
            "statusCode": 502,
            "body": {
                "error": "CopyFailed",
                "message": str(exc),
            },
        }

    except Exception as exc:
        logger.exception(
            "Unexpected error during S3 copy",
            extra={"request_id": request_id},
        )
        return {
            "statusCode": 500,
            "body": {
                "error": "InternalError",
                "message": f"Unexpected error: {type(exc).__name__}: {exc}",
            },
        }
