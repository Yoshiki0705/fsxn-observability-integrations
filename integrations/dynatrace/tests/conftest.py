import json, pytest

@pytest.fixture(autouse=True)
def env_vars(monkeypatch):
    monkeypatch.setenv("DYNATRACE_ENV_URL", "https://abc12345.live.dynatrace.com")
    monkeypatch.setenv("API_KEY_SECRET_ARN", "arn:aws:secretsmanager:ap-northeast-1:123:secret:dt")
    monkeypatch.setenv("S3_ACCESS_POINT_ARN", "arn:aws:s3:ap-northeast-1:123:accesspoint/fsxn-audit")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
