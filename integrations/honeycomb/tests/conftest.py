import json
import os

import pytest

# Set environment variables BEFORE handler import
os.environ.setdefault("API_KEY_SECRET_ARN", "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:hc-key")
os.environ.setdefault("S3_ACCESS_POINT_ARN", "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit")
os.environ.setdefault("HONEYCOMB_DATASET", "fsxn-audit")
os.environ.setdefault("HONEYCOMB_API_URL", "https://api.honeycomb.io")
os.environ.setdefault("LOG_LEVEL", "DEBUG")


@pytest.fixture(autouse=True)
def env_vars(monkeypatch):
    monkeypatch.setenv("API_KEY_SECRET_ARN", "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:hc-key")
    monkeypatch.setenv("S3_ACCESS_POINT_ARN", "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit")
    monkeypatch.setenv("HONEYCOMB_DATASET", "fsxn-audit")
    monkeypatch.setenv("HONEYCOMB_API_URL", "https://api.honeycomb.io")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")


@pytest.fixture
def sample_logs():
    logs = [
        {"timestamp": "2026-01-15T12:00:01Z", "EventID": "4663", "SVMName": "svm-01",
         "UserName": "admin@corp.local", "ClientIP": "10.0.1.50", "Operation": "ReadData",
         "ObjectName": "/vol/data/file.txt", "Result": "Success"},
    ]
    return "\n".join(json.dumps(l) for l in logs)
