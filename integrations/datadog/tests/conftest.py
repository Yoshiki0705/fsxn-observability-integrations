"""Pytest configuration and shared fixtures for Datadog integration tests."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def env_vars(monkeypatch):
    """Set required environment variables for all tests."""
    monkeypatch.setenv("DATADOG_SITE", "datadoghq.com")
    monkeypatch.setenv("API_KEY_SECRET_ARN", "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:dd-api-key")
    monkeypatch.setenv("S3_ACCESS_POINT_ARN", "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DD_SOURCE", "fsxn")
    monkeypatch.setenv("DD_SERVICE", "ontap-audit")
    monkeypatch.setenv("ENV", "test")


@pytest.fixture
def sample_s3_event():
    """Sample S3 event notification."""
    return {
        "Records": [
            {
                "eventVersion": "2.1",
                "eventSource": "aws:s3",
                "awsRegion": "ap-northeast-1",
                "eventTime": "2026-01-15T12:00:00.000Z",
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {
                        "name": "fsxn-audit-logs-bucket",
                        "arn": "arn:aws:s3:::fsxn-audit-logs-bucket",
                    },
                    "object": {
                        "key": "audit/svm1/2026/01/15/audit_log_001.json",
                        "size": 1024,
                    },
                },
            }
        ]
    }


@pytest.fixture
def sample_eventbridge_event():
    """Sample EventBridge event for S3 object creation."""
    return {
        "version": "0",
        "id": "12345678-1234-1234-1234-123456789012",
        "detail-type": "Object Created",
        "source": "aws.s3",
        "account": "123456789012",
        "time": "2026-01-15T12:00:00Z",
        "region": "ap-northeast-1",
        "detail": {
            "bucket": {"name": "fsxn-audit-logs-bucket"},
            "object": {
                "key": "audit/svm1/2026/01/15/audit_log_001.json",
                "size": 1024,
            },
        },
    }


@pytest.fixture
def sample_json_audit_logs():
    """Sample FSx ONTAP audit logs in JSON format."""
    logs = [
        {
            "timestamp": "2026-01-15T12:00:01Z",
            "EventID": "4663",
            "SVMName": "svm-prod-01",
            "UserName": "admin@corp.local",
            "ClientIP": "10.0.1.50",
            "Operation": "ReadData",
            "ObjectName": "/vol/data/reports/quarterly.xlsx",
            "Result": "Success",
        },
        {
            "timestamp": "2026-01-15T12:00:02Z",
            "EventID": "4663",
            "SVMName": "svm-prod-01",
            "UserName": "user1@corp.local",
            "ClientIP": "10.0.1.51",
            "Operation": "WriteData",
            "ObjectName": "/vol/data/shared/document.docx",
            "Result": "Success",
        },
        {
            "timestamp": "2026-01-15T12:00:03Z",
            "EventID": "4656",
            "SVMName": "svm-prod-01",
            "UserName": "unknown@external.com",
            "ClientIP": "192.168.1.100",
            "Operation": "Open",
            "ObjectName": "/vol/data/confidential/secret.pdf",
            "Result": "Failure",
        },
    ]
    return "\n".join(json.dumps(log) for log in logs)


@pytest.fixture
def mock_boto3_clients():
    """Mock boto3 clients for S3 and Secrets Manager."""
    with patch("handler.s3_client") as mock_s3, \
         patch("handler.secrets_client") as mock_secrets:
        mock_secrets.get_secret_value.return_value = {
            "SecretString": json.dumps({"api_key": "test-dd-api-key-12345"})
        }
        yield {"s3": mock_s3, "secrets": mock_secrets}
