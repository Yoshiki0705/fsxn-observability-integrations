"""Shared pytest fixtures for management-console tests."""

import os
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Set required environment variables for all tests."""
    monkeypatch.setenv("TEMP_BUCKET_NAME", "test-temp-bucket")
    monkeypatch.setenv(
        "S3_ACCESS_POINT_ARN",
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap",
    )
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("PRESIGNED_URL_EXPIRY", "3600")


@pytest.fixture
def mock_context():
    """Create a mock Lambda context object."""
    context = MagicMock()
    context.aws_request_id = "test-request-id-12345"
    context.function_name = "fsxn-mgmt-s3-copy"
    context.memory_limit_in_mb = 512
    context.invoked_function_arn = (
        "arn:aws:lambda:ap-northeast-1:123456789012:function:fsxn-mgmt-s3-copy"
    )
    return context


@pytest.fixture
def valid_event():
    """Create a valid Lambda event for S3 copy."""
    return {
        "s3_access_point_arn": "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap",
        "object_key": "audit/svm-prod-01/2026/01/15/audit.json",
    }
