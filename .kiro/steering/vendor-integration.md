# 新ベンダー追加チェックリストとテンプレート

## ⚠️ Datadog E2E 検証からの重要教訓（全ベンダー共通）

以下は Datadog 統合の E2E 検証で発見された、全ベンダー統合に適用すべき重要事項:

1. **トリガー**: EventBridge Scheduler（ポーリング + チェックポイント）を使用。S3 Event Notifications は FSx ONTAP S3 AP で非対応
2. **バッチ失敗**: 例外を `raise` して checkpoint 進行を防止する（握りつぶし厳禁）
3. **DLQ**: Lambda `DeadLetterConfig` で設定。SQS ソースキュー DLQ ではない（`start-message-move-task` 不可）
4. **リトライ**: 指数バックオフ + ジッター（thundering herd 防止）
5. **配信保証**: at-least-once（exactly-once ではない）
6. **AuditLogPrefix**: デプロイ前に `list-objects-v2` で実際のキープレフィックスを確認
7. **監査ログ形式**: EVTX または XML（JSON ではない）
8. **ローテーション**: 検証時は時間ベース（5分間隔）を設定。サイズベースのみだと検証が進まない
9. **SACL/NFSv4 ACL**: 設定されていないとイベントが生成されない
10. **ARP 正式名称**: Autonomous Ransomware Protection（Anti-Ransomware ではない）

詳細: `.kiro/steering/datadog-lessons-learned.md` 参照

---

## 新ベンダー追加チェックリスト

### 事前調査
- [ ] ベンダー API ドキュメント確認
- [ ] 認証方式の確認（API Key, Token, Basic Auth）
- [ ] エンドポイント URL（リージョン別）
- [ ] バッチサイズ制限
- [ ] レート制限
- [ ] Firehose 対応有無
- [ ] タイムスタンプ制限の確認（Datadog: 18時間、各ベンダー要確認）
- [ ] gzip 圧縮対応の確認（リージョン/サイト固有の問題に注意）

### 実装
- [ ] ディレクトリ作成 (`integrations/<vendor>/`)
- [ ] CloudFormation テンプレート (`template.yaml`)
- [ ] Lambda 関数 (`lambda/handler.py`)
- [ ] IAM ロール（最小権限、S3 AP ARN に `/object/*` サフィックス必須）
- [ ] Secrets Manager 統合
- [ ] CloudWatch Alarms（Errors, Throttles, DLQ メッセージ数）
- [ ] Dead Letter Queue（Lambda DeadLetterConfig で設定）
- [ ] バッチ失敗時の例外 raise パターン実装
- [ ] 指数バックオフ + ジッターによるリトライ実装

### ONTAP 設定確認
- [ ] 時間ベースローテーション設定（検証用: 5分間隔）
- [ ] SACL/NFSv4 ACL が対象ファイルに設定済み
- [ ] `list-objects-v2` で AuditLogPrefix を確認
- [ ] EMS Webhook エンドポイント設定（EMS パス検証時）
- [ ] FPolicy External Engine 設定（FPolicy パス検証時）

### ドキュメント
- [ ] README.md（ベンダーディレクトリ）
- [ ] セットアップガイド（日本語: `docs/ja/setup-guide.md`）
- [ ] セットアップガイド（英語: `docs/en/setup-guide.md`）
- [ ] ベンダー側設定手順
- [ ] アラート/モニター設定のクエリ構文を記録

### テスト
- [ ] ユニットテスト (`tests/`)
- [ ] サンプルイベントデータ
- [ ] API モック
- [ ] E2E 検証: ログ到着確認（5分以内）
- [ ] E2E 検証: タイムスタンプのインデックス確認
- [ ] E2E 検証: EMS ARP イベント到着確認
- [ ] E2E 検証: FPolicy ファイル操作イベント到着確認

### 統合
- [ ] プロジェクト README.md のベンダー表更新
- [ ] ベンダー比較ドキュメント更新
- [ ] CI/CD ワークフロー追加

## Lambda 関数テンプレート

```python
"""FSxN audit log shipper for <Vendor Name>.

Reads audit logs from S3 Access Point, parses them,
and ships to <Vendor> <API Name>.

Key patterns (from Datadog E2E lessons):
- Batch failure: raise exception to prevent checkpoint advancement
- DLQ: Lambda async DLQ (not SQS source queue DLQ)
- Retry: exponential backoff WITH jitter
- Delivery: at-least-once (not exactly-once)
"""

import json
import logging
import os
import random
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
MAX_BATCH_SIZE = 5 * 1024 * 1024  # 5MB — adjust per vendor limit
MAX_RETRIES = 3

# Clients (initialized once per execution context — intentional caching)
secrets_client = boto3.client("secretsmanager")
s3_client = boto3.client("s3")
http = urllib3.PoolManager()

# API key cache (per execution context, not per invocation)
_api_key_cache: str | None = None


def get_api_key() -> str:
    """Retrieve API key from Secrets Manager (cached per execution context)."""
    global _api_key_cache
    if _api_key_cache is None:
        response = secrets_client.get_secret_value(SecretId=SECRET_ARN)
        _api_key_cache = response["SecretString"]
    return _api_key_cache


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler for log shipping.

    CRITICAL: On batch failure, raise exception to prevent checkpoint
    advancement. Lambda async retry → DLQ flow handles failures.
    """
    api_key = get_api_key()

    try:
        for record in event.get("Records", []):
            bucket = record["s3"]["bucket"]["name"]
            key = record["s3"]["object"]["key"]

            # Read from S3 Access Point (use AP ARN as Bucket parameter)
            response = s3_client.get_object(Bucket=S3_ACCESS_POINT_ARN, Key=key)
            data = response["Body"].read()

            # Parse logs (EVTX or XML format, NOT JSON)
            logs = parse_logs(data)

            # Ship to vendor
            ship_logs(logs, api_key)

    except Exception as e:
        # MUST raise to prevent checkpoint advancement
        # Lambda async DLQ will capture failed events after retries
        logger.error(f"Batch processing failed: {e}")
        raise

    return {"statusCode": 200, "body": "OK"}


def parse_logs(data: bytes) -> list[dict]:
    """Parse FSx ONTAP audit logs (EVTX or XML format)."""
    # Use shared/lambda-layers/log-parser/ for implementation
    raise NotImplementedError


def ship_logs(logs: list[dict], api_key: str) -> None:
    """Ship logs to vendor API with exponential backoff + jitter."""
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
                # Exponential backoff + jitter (prevents thundering herd)
                delay = (2 ** attempt) + random.uniform(0, 1)
                time.sleep(delay)
                continue
            raise Exception(f"API error: {response.status}")
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise
            delay = (2 ** attempt) + random.uniform(0, 1)
            time.sleep(delay)
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
  S3BucketName:           # 必須（EventBridge Scheduler 用）
  LogLevel:               # オプション (default: INFO)

Resources:
  LambdaFunction:         # メイン Lambda
    Type: AWS::Lambda::Function
    Properties:
      # CRITICAL: Lambda async DLQ (NOT SQS source queue DLQ)
      DeadLetterConfig:
        TargetArn: !GetAtt DeadLetterQueue.Arn
  LambdaExecutionRole:    # IAM ロール（S3 AP ARN + /object/* サフィックス必須）
  EventBridgeScheduler:   # トリガー（EventBridge Scheduler、NOT S3 Event Notifications）
  CloudWatchAlarms:       # 監視（Errors, Throttles, DLQ メッセージ数）
  DeadLetterQueue:        # DLQ（SQS、メッセージ保持 14 日）

Outputs:
  LambdaFunctionArn:
  CloudWatchAlarmArn:
  DeadLetterQueueArn:
  DeadLetterQueueUrl:
```

### DLQ 設定の注意点（Datadog E2E 教訓）

- Lambda `DeadLetterConfig` で DLQ を指定する（Lambda 非同期呼び出し用）
- SQS をイベントソースとして使用していない場合、SQS ソースキューの DLQ は無関係
- `start-message-move-task` は Lambda async DLQ では動作しない
- DLQ メッセージの再処理は手動で Lambda を再呼び出しする

### EventBridge Scheduler の注意点

- FSx ONTAP S3 AP は S3 Event Notifications 非対応
- EventBridge Scheduler で定期的に Lambda を起動（例: 5分間隔）
- Lambda 内でチェックポイント（DynamoDB or S3 マーカー）を管理
- 新規ファイルのみを処理する
