"""Pytest fixtures for Grafana integration tests."""
import json
import pytest


@pytest.fixture(autouse=True)
def env_vars(monkeypatch):
    monkeypatch.setenv("LOKI_ENDPOINT", "https://logs-prod.grafana.net")
    monkeypatch.setenv("LOKI_TENANT_ID", "")
    monkeypatch.setenv("API_KEY_SECRET_ARN", "arn:aws:secretsmanager:ap-northeast-1:123:secret:grafana")
    monkeypatch.setenv("S3_ACCESS_POINT_ARN", "arn:aws:s3:ap-northeast-1:123:accesspoint/fsxn-audit")
    monkeypatch.setenv("S3_KEY_PREFIX", "audit/svm-prod-01/")
    monkeypatch.setenv("CHECKPOINT_PARAM_NAME", "/fsxn-grafana/test-stack/last-processed-key")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")


@pytest.fixture
def sample_logs():
    logs = [
        {"timestamp": "2026-01-15T12:00:01Z", "EventID": "4663", "SVMName": "svm-prod-01",
         "UserName": "admin@corp.local", "Operation": "ReadData", "Result": "Success"},
        {"timestamp": "2026-01-15T12:00:02Z", "EventID": "4656", "SVMName": "svm-prod-01",
         "UserName": "user1@corp.local", "Operation": "Open", "Result": "Failure"},
    ]
    return "\n".join(json.dumps(l) for l in logs)


@pytest.fixture
def scheduler_event():
    return {
        "source": "scheduler",
        "s3_access_point_arn": "arn:aws:s3:ap-northeast-1:123:accesspoint/fsxn-audit",
        "prefix": "audit/svm-prod-01/",
    }


@pytest.fixture
def s3_event():
    return {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "my-bucket"},
                    "object": {"key": "audit/svm-prod-01/2026/01/15/audit.json"},
                }
            }
        ]
    }
