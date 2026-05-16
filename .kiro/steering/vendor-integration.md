# 新ベンダー追加チェックリストとテンプレート

## 新ベンダー追加チェックリスト

### 事前調査
- [ ] ベンダー API ドキュメント確認
- [ ] 認証方式の確認（API Key, Token, Basic Auth）
- [ ] エンドポイント URL（リージョン別）
- [ ] バッチサイズ制限
- [ ] レート制限
- [ ] Firehose 対応有無

### 実装
- [ ] ディレクトリ作成 (`integrations/<vendor>/`)
- [ ] CloudFormation テンプレート (`template.yaml`)
- [ ] Lambda 関数 (`lambda/handler.py`)
- [ ] IAM ロール（最小権限）
- [ ] Secrets Manager 統合
- [ ] CloudWatch Alarms
- [ ] Dead Letter Queue

### ドキュメント
- [ ] README.md（ベンダーディレクトリ）
- [ ] セットアップガイド（日本語: `docs/ja/setup-guide.md`）
- [ ] セットアップガイド（英語: `docs/en/setup-guide.md`）
- [ ] ベンダー側設定手順

### テスト
- [ ] ユニットテスト (`tests/`)
- [ ] サンプルイベントデータ
- [ ] API モック

### 統合
- [ ] プロジェクト README.md のベンダー表更新
- [ ] ベンダー比較ドキュメント更新
- [ ] CI/CD ワークフロー追加

## Lambda 関数テンプレート

```python
"""FSxN audit log shipper for <Vendor Name>.

Reads audit logs from S3 Access Point, parses them,
and ships to <Vendor> <API Name>.
"""

import json
import logging
import os
import time
from typing import Any

import boto3
import urllib3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Configuration
VENDOR_API_ENDPOINT = os.environ["VENDOR_API_ENDPOINT"]
SECRET_ARN = os.environ["API_KEY_SECRET_ARN"]
S3_ACCESS_POINT_ARN = os.environ["S3_ACCESS_POINT_ARN"]
MAX_BATCH_SIZE = 5 * 1024 * 1024  # 5MB
MAX_RETRIES = 3

# Clients
secrets_client = boto3.client("secretsmanager")
s3_client = boto3.client("s3")
http = urllib3.PoolManager()


def get_api_key() -> str:
    """Retrieve API key from Secrets Manager."""
    response = secrets_client.get_secret_value(SecretId=SECRET_ARN)
    return response["SecretString"]


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler for log shipping."""
    api_key = get_api_key()

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        # Read from S3 Access Point
        response = s3_client.get_object(Bucket=S3_ACCESS_POINT_ARN, Key=key)
        data = response["Body"].read()

        # Parse logs
        # TODO: Use shared log-parser layer
        logs = parse_logs(data)

        # Ship to vendor
        ship_logs(logs, api_key)

    return {"statusCode": 200, "body": "OK"}


def parse_logs(data: bytes) -> list[dict]:
    """Parse FSx ONTAP audit logs."""
    # Implementation depends on log format
    raise NotImplementedError


def ship_logs(logs: list[dict], api_key: str) -> None:
    """Ship logs to vendor API with retry."""
    for attempt in range(MAX_RETRIES):
        try:
            response = http.request(
                "POST",
                VENDOR_API_ENDPOINT,
                body=json.dumps(logs).encode(),
                headers={
                    "Content-Type": "application/json",
                    # Vendor-specific auth header
                },
            )
            if response.status < 300:
                return
            if response.status == 429 or response.status >= 500:
                time.sleep(2 ** attempt)
                continue
            raise Exception(f"API error: {response.status}")
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(2 ** attempt)
```

## CloudFormation テンプレート構造

各ベンダーの `template.yaml` は以下の構造に従う:

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: FSxN <Vendor> Integration

Parameters:
  S3AccessPointArn:       # 必須
  ApiKeySecretArn:        # 必須
  VendorEndpoint:         # ベンダー固有
  LogLevel:               # オプション (default: INFO)

Resources:
  LambdaFunction:         # メイン Lambda
  LambdaExecutionRole:    # IAM ロール
  EventBridgeRule:        # トリガー
  CloudWatchAlarm:        # 監視
  DeadLetterQueue:        # DLQ

Outputs:
  LambdaFunctionArn:
  CloudWatchAlarmArn:
```
