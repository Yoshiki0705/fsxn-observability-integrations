"""Unit tests for the Splunk HEC token validator.

Tests validate_hec_token function for correct handling of valid tokens,
invalid formats, empty values, and Secrets Manager errors.

Requirements: 1.4
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from scripts.verification.splunk_token_validator import (
    ValidationResult,
    _extract_token,
    validate_hec_token,
)


class TestValidateHecTokenSuccess:
    """Test successful token validation with valid UUID tokens."""

    @patch("scripts.verification.splunk_token_validator.boto3")
    def test_valid_uuid_token_passes(self, mock_boto3: MagicMock) -> None:
        """Valid UUID token → status='pass', token_format_valid=True."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.get_secret_value.return_value = {
            "SecretString": "12345678-1234-1234-1234-123456789abc"
        }

        result = validate_hec_token("arn:aws:secretsmanager:us-east-1:123:secret:test")

        assert result.status == "pass"
        assert result.token_format_valid is True
        assert result.error is None

    @patch("scripts.verification.splunk_token_validator.boto3")
    def test_valid_uppercase_uuid_passes(self, mock_boto3: MagicMock) -> None:
        """Valid UUID with uppercase hex → status='pass'."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.get_secret_value.return_value = {
            "SecretString": "ABCDEF01-2345-6789-ABCD-EF0123456789"
        }

        result = validate_hec_token("arn:aws:secretsmanager:us-east-1:123:secret:test")

        assert result.status == "pass"
        assert result.token_format_valid is True

    @patch("scripts.verification.splunk_token_validator.boto3")
    def test_valid_json_format_secret(self, mock_boto3: MagicMock) -> None:
        """JSON-formatted secret with hec_token key → status='pass'."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.get_secret_value.return_value = {
            "SecretString": '{"hec_token": "abcdef01-2345-6789-abcd-ef0123456789"}'
        }

        result = validate_hec_token("arn:aws:secretsmanager:us-east-1:123:secret:test")

        assert result.status == "pass"
        assert result.token_format_valid is True


class TestValidateHecTokenInvalidFormat:
    """Test token validation with invalid formats."""

    @patch("scripts.verification.splunk_token_validator.boto3")
    def test_empty_token_fails(self, mock_boto3: MagicMock) -> None:
        """Empty string token → status='fail', error mentions empty."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.get_secret_value.return_value = {"SecretString": ""}

        result = validate_hec_token("arn:aws:secretsmanager:us-east-1:123:secret:test")

        assert result.status == "fail"
        assert result.token_format_valid is False
        assert "empty" in result.error.lower()

    @patch("scripts.verification.splunk_token_validator.boto3")
    def test_whitespace_only_token_fails(self, mock_boto3: MagicMock) -> None:
        """Whitespace-only token → status='fail'."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.get_secret_value.return_value = {"SecretString": "   \t\n  "}

        result = validate_hec_token("arn:aws:secretsmanager:us-east-1:123:secret:test")

        assert result.status == "fail"
        assert result.token_format_valid is False

    @patch("scripts.verification.splunk_token_validator.boto3")
    def test_non_uuid_string_fails(self, mock_boto3: MagicMock) -> None:
        """Non-UUID string → status='fail', error mentions UUID format."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.get_secret_value.return_value = {
            "SecretString": "not-a-valid-token"
        }

        result = validate_hec_token("arn:aws:secretsmanager:us-east-1:123:secret:test")

        assert result.status == "fail"
        assert result.token_format_valid is False
        assert "UUID" in result.error

    @patch("scripts.verification.splunk_token_validator.boto3")
    def test_partial_uuid_fails(self, mock_boto3: MagicMock) -> None:
        """Partial UUID (missing last segment) → status='fail'."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.get_secret_value.return_value = {
            "SecretString": "12345678-1234-1234-1234"
        }

        result = validate_hec_token("arn:aws:secretsmanager:us-east-1:123:secret:test")

        assert result.status == "fail"
        assert result.token_format_valid is False

    @patch("scripts.verification.splunk_token_validator.boto3")
    def test_uuid_with_invalid_chars_fails(self, mock_boto3: MagicMock) -> None:
        """UUID with non-hex characters → status='fail'."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.get_secret_value.return_value = {
            "SecretString": "1234567g-1234-1234-1234-123456789abc"
        }

        result = validate_hec_token("arn:aws:secretsmanager:us-east-1:123:secret:test")

        assert result.status == "fail"
        assert result.token_format_valid is False


class TestValidateHecTokenSecretsManagerErrors:
    """Test handling of Secrets Manager errors."""

    @patch("scripts.verification.splunk_token_validator.boto3")
    def test_resource_not_found_fails(self, mock_boto3: MagicMock) -> None:
        """ResourceNotFoundException → status='fail' with error code."""
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.get_secret_value.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}},
            "GetSecretValue",
        )

        result = validate_hec_token("arn:aws:secretsmanager:us-east-1:123:secret:test")

        assert result.status == "fail"
        assert result.token_format_valid is False
        assert "ResourceNotFoundException" in result.error

    @patch("scripts.verification.splunk_token_validator.boto3")
    def test_access_denied_fails(self, mock_boto3: MagicMock) -> None:
        """AccessDeniedException → status='fail' with error code."""
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.get_secret_value.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Access denied"}},
            "GetSecretValue",
        )

        result = validate_hec_token("arn:aws:secretsmanager:us-east-1:123:secret:test")

        assert result.status == "fail"
        assert result.token_format_valid is False
        assert "AccessDeniedException" in result.error


class TestValidateHecTokenResultMetadata:
    """Test that ValidationResult contains correct metadata."""

    @patch("scripts.verification.splunk_token_validator.boto3")
    def test_result_contains_secret_arn(self, mock_boto3: MagicMock) -> None:
        """Result always contains the secret_arn that was validated."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.get_secret_value.return_value = {
            "SecretString": "12345678-1234-1234-1234-123456789abc"
        }

        arn = "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:splunk/hec"
        result = validate_hec_token(arn)

        assert result.secret_arn == arn


class TestExtractToken:
    """Test the _extract_token helper function."""

    def test_plain_string(self) -> None:
        """Plain string is returned as-is."""
        assert _extract_token("my-token") == "my-token"

    def test_json_with_hec_token_key(self) -> None:
        """JSON with hec_token key extracts the value."""
        assert _extract_token('{"hec_token": "abc-123"}') == "abc-123"

    def test_json_with_splunk_hec_token_key(self) -> None:
        """JSON with SPLUNK_HEC_TOKEN key extracts the value."""
        assert _extract_token('{"SPLUNK_HEC_TOKEN": "xyz-789"}') == "xyz-789"

    def test_json_without_known_keys_returns_raw(self) -> None:
        """JSON without known keys returns the raw string."""
        raw = '{"other_key": "value"}'
        assert _extract_token(raw) == raw

    def test_invalid_json_returns_raw(self) -> None:
        """Invalid JSON returns the raw string."""
        raw = "not-json-at-all"
        assert _extract_token(raw) == raw
