"""Pytest fixtures for New Relic integration tests."""

import json
import pytest


@pytest.fixture(autouse=True)
def env_vars(monkeypatch):
    monkeypatch.setenv("NEW_RELIC_REGION", "US")
    monkeypatch.setenv("API_KEY_SECRET_ARN", "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:nr-key")
    monkeypatch.setenv("S3_ACCESS_POINT_ARN", "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit")
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
         "UserName": "admin@corp.local", "ClientIP": "10.0.1.50", "Operation": "ReadData",
         "ObjectName": "/vol/data/file.txt", "Result": "Success"},
        {"timestamp": "2026-01-15T12:00:02Z", "EventID": "4656", "SVMName": "svm-prod-01",
         "UserName": "user1@corp.local", "ClientIP": "10.0.1.51", "Operation": "Open",
         "ObjectName": "/vol/data/secret.pdf", "Result": "Failure"},
    ]
    return "\n".join(json.dumps(l) for l in logs)
