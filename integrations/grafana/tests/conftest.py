"""Pytest fixtures for Grafana integration tests."""
import json
import pytest


@pytest.fixture(autouse=True)
def env_vars(monkeypatch):
    monkeypatch.setenv("LOKI_ENDPOINT", "https://logs-prod.grafana.net")
    monkeypatch.setenv("LOKI_TENANT_ID", "")
    monkeypatch.setenv("API_KEY_SECRET_ARN", "arn:aws:secretsmanager:ap-northeast-1:123:secret:grafana")
    monkeypatch.setenv("S3_ACCESS_POINT_ARN", "arn:aws:s3:ap-northeast-1:123:accesspoint/fsxn-audit")
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
