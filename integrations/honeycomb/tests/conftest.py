import pytest

@pytest.fixture(autouse=True)
def env_vars(monkeypatch):
    monkeypatch.setenv("API_KEY_SECRET_ARN", "arn:aws:secretsmanager:ap-northeast-1:123:secret:honeycomb")
    monkeypatch.setenv("S3_ACCESS_POINT_ARN", "arn:aws:s3:ap-northeast-1:123:accesspoint/fsxn-audit")
    monkeypatch.setenv("HONEYCOMB_DATASET", "fsxn-audit")
    monkeypatch.setenv("HONEYCOMB_API_URL", "https://api.honeycomb.io")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
