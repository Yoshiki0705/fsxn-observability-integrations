"""Shared fixtures for CrowdStrike LogScale integration tests."""

import os
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Set required environment variables for handler import."""
    monkeypatch.setenv("LOGSCALE_URL", "https://cloud.us.humio.com")
    monkeypatch.setenv("INGEST_TOKEN_SECRET_ARN", "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:test-token")
    monkeypatch.setenv("S3_ACCESS_POINT_ARN", "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/test-ap")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")


@pytest.fixture
def mock_boto3_clients(monkeypatch):
    """Mock boto3 clients."""
    mock_secrets = MagicMock()
    mock_secrets.get_secret_value.return_value = {"SecretString": "test-ingest-token-abc123"}

    mock_s3 = MagicMock()

    with patch("boto3.client") as mock_client:
        def client_factory(service, **kwargs):
            if service == "secretsmanager":
                return mock_secrets
            elif service == "s3":
                return mock_s3
            return MagicMock()

        mock_client.side_effect = client_factory
        yield {"secrets": mock_secrets, "s3": mock_s3}


@pytest.fixture
def sample_xml_audit_log():
    """Sample ONTAP XML audit log content."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<Events>
  <Event>
    <System>
      <Provider Name="NetApp-Security-Auditing"/>
      <EventID>4663</EventID>
      <TimeCreated SystemTime="2026-06-01T10:00:00.000000Z"/>
      <Computer>TestSVM</Computer>
    </System>
    <EventData>
      <Data Name="SubjectUserName">CORP\\testuser</Data>
      <Data Name="ObjectName">/share/test/document.xlsx</Data>
      <Data Name="ObjectType">File</Data>
      <Data Name="IpAddress">10.0.1.100</Data>
      <Data Name="HandleID">0x00000001</Data>
    </EventData>
    <Keywords>Audit Success</Keywords>
  </Event>
</Events>"""


@pytest.fixture
def sample_json_audit_logs():
    """Sample audit logs in JSON format."""
    return (
        '{"EventID":"4663","timestamp":"2026-06-01T10:00:00Z","SVMName":"TestSVM",'
        '"UserName":"testuser","ObjectName":"/share/test/file.txt","ClientIP":"10.0.1.100",'
        '"Operation":"ReadData","Result":"Success"}\n'
        '{"EventID":"4656","timestamp":"2026-06-01T10:01:00Z","SVMName":"TestSVM",'
        '"UserName":"admin","ObjectName":"/share/admin/config.json","ClientIP":"10.0.2.50",'
        '"Operation":"OpenObject","Result":"Success"}'
    )
