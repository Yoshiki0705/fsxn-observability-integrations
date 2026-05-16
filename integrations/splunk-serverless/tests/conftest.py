"""Pytest fixtures for Splunk Serverless integration tests."""

import json
import pytest


@pytest.fixture(autouse=True)
def env_vars(monkeypatch):
    monkeypatch.setenv("SPLUNK_HEC_ENDPOINT", "https://splunk.example.com:8088")
    monkeypatch.setenv("API_KEY_SECRET_ARN", "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:splunk-hec")
    monkeypatch.setenv("S3_ACCESS_POINT_ARN", "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit")
    monkeypatch.setenv("SPLUNK_INDEX", "fsxn_audit")
    monkeypatch.setenv("SPLUNK_SOURCETYPE", "fsxn:ontap:audit")
    monkeypatch.setenv("SPLUNK_SOURCE", "fsxn-observability")
    monkeypatch.setenv("VERIFY_SSL", "true")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")


@pytest.fixture
def sample_s3_event():
    return {
        "Records": [{
            "s3": {
                "bucket": {"name": "fsxn-audit-logs"},
                "object": {"key": "audit/svm1/2026/01/15/audit.json"},
            }
        }]
    }


@pytest.fixture
def sample_logs():
    logs = [
        {"timestamp": "2026-01-15T12:00:01Z", "EventID": "4663", "SVMName": "svm-prod-01",
         "UserName": "admin@corp.local", "Operation": "ReadData",
         "ObjectName": "/vol/data/file.txt", "Result": "Success"},
    ]
    return "\n".join(json.dumps(l) for l in logs)
