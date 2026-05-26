"""Unit tests for S3 Copy Lambda handler.

Tests cover:
- Successful copy + presigned URL generation
- File size validation (reject > 5 GB)
- S3 AP unreachable (timeout handling)
- Copy-to-bucket failure
- Invalid input (missing AP ARN, missing key, path traversal)
"""

import importlib
import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError, ConnectTimeoutError

# Add lambda directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "lambda"))


@pytest.fixture
def reload_handler(mock_env_vars):
    """Reload the handler module to pick up mocked env vars."""
    if "s3_copy_handler" in sys.modules:
        del sys.modules["s3_copy_handler"]
    import s3_copy_handler

    return s3_copy_handler


class TestValidateInput:
    """Tests for input validation logic."""

    def test_valid_input(self, reload_handler):
        """Valid S3 AP ARN and object key are accepted."""
        handler = reload_handler
        event = {
            "s3_access_point_arn": "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap",
            "object_key": "audit/svm-prod-01/2026/01/15/audit.json",
        }
        arn, key = handler.validate_input(event)
        assert arn == event["s3_access_point_arn"]
        assert key == event["object_key"]

    def test_missing_object_key(self, reload_handler):
        """Missing object_key raises ValueError."""
        handler = reload_handler
        event = {
            "s3_access_point_arn": "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap",
            "object_key": "",
        }
        with pytest.raises(ValueError, match="Missing required field: 'object_key'"):
            handler.validate_input(event)

    def test_missing_ap_arn_with_no_env(self, reload_handler, monkeypatch):
        """Missing AP ARN with no env var raises ValueError."""
        handler = reload_handler
        handler.S3_ACCESS_POINT_ARN = ""
        event = {"s3_access_point_arn": "", "object_key": "test.json"}
        with pytest.raises(ValueError, match="Missing required field: 's3_access_point_arn'"):
            handler.validate_input(event)

    def test_invalid_arn_format(self, reload_handler):
        """Invalid ARN format raises ValueError."""
        handler = reload_handler
        event = {
            "s3_access_point_arn": "not-a-valid-arn",
            "object_key": "test.json",
        }
        with pytest.raises(ValueError, match="Invalid S3 Access Point ARN format"):
            handler.validate_input(event)

    def test_path_traversal_rejected(self, reload_handler):
        """Path traversal in object key is rejected."""
        handler = reload_handler
        event = {
            "s3_access_point_arn": "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap",
            "object_key": "audit/../../../etc/passwd",
        }
        with pytest.raises(ValueError, match="path traversal detected"):
            handler.validate_input(event)

    def test_leading_slash_rejected(self, reload_handler):
        """Object key starting with '/' is rejected."""
        handler = reload_handler
        event = {
            "s3_access_point_arn": "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap",
            "object_key": "/absolute/path/file.json",
        }
        with pytest.raises(ValueError, match="must not start with '/'"):
            handler.validate_input(event)

    def test_falls_back_to_env_var_arn(self, reload_handler):
        """When event has no AP ARN, falls back to env var."""
        handler = reload_handler
        handler.S3_ACCESS_POINT_ARN = (
            "arn:aws:s3:us-east-1:123456789012:accesspoint/env-ap"
        )
        event = {"object_key": "test.json"}
        arn, key = handler.validate_input(event)
        assert arn == "arn:aws:s3:us-east-1:123456789012:accesspoint/env-ap"
        assert key == "test.json"


class TestCheckFileSize:
    """Tests for file size validation."""

    def test_file_within_limit(self, reload_handler):
        """File under 5 GB passes validation."""
        handler = reload_handler
        mock_response = {"ContentLength": 1024 * 1024 * 100}  # 100 MB
        handler._s3_ap_client = MagicMock()
        handler._s3_ap_client.head_object.return_value = mock_response

        size = handler.check_file_size(
            "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/test-ap",
            "test.json",
        )
        assert size == 1024 * 1024 * 100

    def test_file_exceeds_5gb(self, reload_handler):
        """File over 5 GB raises ValueError."""
        handler = reload_handler
        mock_response = {"ContentLength": 6 * 1024 * 1024 * 1024}  # 6 GB
        handler._s3_ap_client = MagicMock()
        handler._s3_ap_client.head_object.return_value = mock_response

        with pytest.raises(ValueError, match="exceeds maximum downloadable limit of 5 GB"):
            handler.check_file_size(
                "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/test-ap",
                "large-file.bin",
            )

    def test_ap_unreachable_timeout(self, reload_handler):
        """S3 AP timeout raises ConnectionError."""
        handler = reload_handler
        handler._s3_ap_client = MagicMock()
        handler._s3_ap_client.head_object.side_effect = ConnectTimeoutError(
            endpoint_url="https://s3.amazonaws.com"
        )

        with pytest.raises(ConnectionError, match="unreachable within 10s timeout"):
            handler.check_file_size(
                "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/test-ap",
                "test.json",
            )

    def test_object_not_found(self, reload_handler):
        """Non-existent object raises ValueError."""
        handler = reload_handler
        handler._s3_ap_client = MagicMock()
        handler._s3_ap_client.head_object.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}},
            "HeadObject",
        )

        with pytest.raises(ValueError, match="Object not found"):
            handler.check_file_size(
                "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/test-ap",
                "nonexistent.json",
            )


class TestCopyObjectToTempBucket:
    """Tests for the copy operation."""

    def test_successful_copy(self, reload_handler):
        """Successful copy returns temp key."""
        handler = reload_handler
        handler.TEMP_BUCKET_NAME = "test-temp-bucket"

        mock_body = MagicMock()
        mock_body.read.return_value = b"file content"

        handler._s3_ap_client = MagicMock()
        handler._s3_ap_client.get_object.return_value = {
            "Body": mock_body,
            "ContentType": "application/json",
        }
        handler._s3_temp_client = MagicMock()

        temp_key = handler.copy_object_to_temp_bucket(
            "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/test-ap",
            "audit/2026/01/15/audit.json",
            "req-123",
        )

        assert temp_key == "tmp/req-123/audit.json"
        handler._s3_temp_client.put_object.assert_called_once_with(
            Bucket="test-temp-bucket",
            Key="tmp/req-123/audit.json",
            Body=b"file content",
            ContentType="application/json",
        )

    def test_copy_ap_timeout(self, reload_handler):
        """S3 AP timeout during copy raises ConnectionError."""
        handler = reload_handler
        handler._s3_ap_client = MagicMock()
        handler._s3_ap_client.get_object.side_effect = ConnectTimeoutError(
            endpoint_url="https://s3.amazonaws.com"
        )

        with pytest.raises(ConnectionError, match="unreachable within 10s timeout"):
            handler.copy_object_to_temp_bucket(
                "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/test-ap",
                "test.json",
                "req-123",
            )

    def test_copy_client_error(self, reload_handler):
        """ClientError during copy raises RuntimeError."""
        handler = reload_handler
        handler._s3_ap_client = MagicMock()
        handler._s3_ap_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
            "GetObject",
        )

        with pytest.raises(RuntimeError, match="Copy operation failed.*AccessDenied"):
            handler.copy_object_to_temp_bucket(
                "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/test-ap",
                "test.json",
                "req-123",
            )


class TestGeneratePresignedUrl:
    """Tests for presigned URL generation."""

    def test_generates_url(self, reload_handler):
        """Presigned URL is generated with correct parameters."""
        handler = reload_handler
        handler.TEMP_BUCKET_NAME = "test-temp-bucket"
        handler.PRESIGNED_URL_EXPIRY = 3600

        handler._s3_temp_client = MagicMock()
        handler._s3_temp_client.generate_presigned_url.return_value = (
            "https://test-temp-bucket.s3.amazonaws.com/tmp/req-123/audit.json?signature=abc"
        )

        url = handler.generate_presigned_url("tmp/req-123/audit.json")

        assert "https://" in url
        handler._s3_temp_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "test-temp-bucket", "Key": "tmp/req-123/audit.json"},
            ExpiresIn=3600,
        )


class TestLambdaHandler:
    """Integration tests for the full Lambda handler flow."""

    def test_successful_flow(self, reload_handler, mock_context):
        """Full successful flow returns 200 with presigned URL."""
        handler = reload_handler
        handler.TEMP_BUCKET_NAME = "test-temp-bucket"

        mock_body = MagicMock()
        mock_body.read.return_value = b"audit log content"

        handler._s3_ap_client = MagicMock()
        handler._s3_ap_client.head_object.return_value = {"ContentLength": 1024}
        handler._s3_ap_client.get_object.return_value = {
            "Body": mock_body,
            "ContentType": "application/json",
        }

        handler._s3_temp_client = MagicMock()
        handler._s3_temp_client.generate_presigned_url.return_value = (
            "https://test-temp-bucket.s3.amazonaws.com/tmp/test-request-id-12345/audit.json?sig=x"
        )

        event = {
            "s3_access_point_arn": "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap",
            "object_key": "audit/svm-prod-01/2026/01/15/audit.json",
        }

        result = handler.lambda_handler(event, mock_context)

        assert result["statusCode"] == 200
        assert "presigned_url" in result["body"]
        assert result["body"]["object_key"] == "audit/svm-prod-01/2026/01/15/audit.json"
        assert result["body"]["file_size_bytes"] == 1024
        assert result["body"]["expiry_seconds"] == 3600

    def test_validation_error_returns_400(self, reload_handler, mock_context):
        """Invalid input returns 400."""
        handler = reload_handler
        handler.S3_ACCESS_POINT_ARN = ""

        event = {"s3_access_point_arn": "", "object_key": ""}

        result = handler.lambda_handler(event, mock_context)

        assert result["statusCode"] == 400
        assert result["body"]["error"] == "ValidationError"

    def test_size_limit_returns_400(self, reload_handler, mock_context):
        """File exceeding 5 GB returns 400."""
        handler = reload_handler

        handler._s3_ap_client = MagicMock()
        handler._s3_ap_client.head_object.return_value = {
            "ContentLength": 6 * 1024 * 1024 * 1024,
        }

        event = {
            "s3_access_point_arn": "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap",
            "object_key": "large-file.bin",
        }

        result = handler.lambda_handler(event, mock_context)

        assert result["statusCode"] == 400
        assert result["body"]["error"] == "ValidationError"
        assert "5 GB" in result["body"]["message"]

    def test_ap_unreachable_returns_504(self, reload_handler, mock_context):
        """S3 AP timeout returns 504."""
        handler = reload_handler

        handler._s3_ap_client = MagicMock()
        handler._s3_ap_client.head_object.side_effect = ConnectTimeoutError(
            endpoint_url="https://s3.amazonaws.com"
        )

        event = {
            "s3_access_point_arn": "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap",
            "object_key": "test.json",
        }

        result = handler.lambda_handler(event, mock_context)

        assert result["statusCode"] == 504
        assert result["body"]["error"] == "AccessPointUnreachable"

    def test_copy_failure_returns_502(self, reload_handler, mock_context):
        """Copy failure returns 502."""
        handler = reload_handler

        handler._s3_ap_client = MagicMock()
        handler._s3_ap_client.head_object.return_value = {"ContentLength": 1024}
        handler._s3_ap_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "InternalError", "Message": "Service error"}},
            "GetObject",
        )

        event = {
            "s3_access_point_arn": "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap",
            "object_key": "test.json",
        }

        result = handler.lambda_handler(event, mock_context)

        assert result["statusCode"] == 502
        assert result["body"]["error"] == "CopyFailed"

    def test_path_traversal_returns_400(self, reload_handler, mock_context):
        """Path traversal attempt returns 400."""
        handler = reload_handler

        event = {
            "s3_access_point_arn": "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap",
            "object_key": "audit/../../etc/passwd",
        }

        result = handler.lambda_handler(event, mock_context)

        assert result["statusCode"] == 400
        assert result["body"]["error"] == "ValidationError"
        assert "path traversal" in result["body"]["message"]
