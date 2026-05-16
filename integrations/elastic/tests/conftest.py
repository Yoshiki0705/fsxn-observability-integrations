import json, pytest

@pytest.fixture(autouse=True)
def env_vars(monkeypatch):
    monkeypatch.setenv("ELASTIC_ENDPOINT", "https://my-cluster.es.amazonaws.com")
    monkeypatch.setenv("API_KEY_SECRET_ARN", "arn:aws:secretsmanager:ap-northeast-1:123:secret:elastic")
    monkeypatch.setenv("S3_ACCESS_POINT_ARN", "arn:aws:s3:ap-northeast-1:123:accesspoint/fsxn-audit")
    monkeypatch.setenv("INDEX_PREFIX", "fsxn-audit")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

@pytest.fixture
def sample_logs():
    logs = [
        {"timestamp": "2026-01-15T12:00:01Z", "EventID": "4663", "SVMName": "svm-01",
         "UserName": "admin", "Operation": "ReadData", "Result": "Success"},
    ]
    return "\n".join(json.dumps(l) for l in logs)
