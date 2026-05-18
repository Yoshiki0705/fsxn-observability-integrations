# マイグレーションガイド: ベンダー直接送信 → OTel Collector パス

## 概要

既存のベンダー直接送信（Datadog/New Relic/Splunk 等）から OTel Collector パスへの移行手順です。ゼロダウンタイムで移行できます。

## 前提条件

- 既存のベンダー直接送信 Lambda が稼働中
- OTel Collector の設定ファイルが準備済み
- 新旧両方のバックエンドの認証情報が利用可能

## 移行ステップ

### Step 1: OTel Collector のデプロイ

既存環境に影響を与えずに OTel Collector をデプロイします。

```bash
# Docker (ローカル/開発)
docker run -d --name otel-collector \
  -p 4318:4318 -p 13133:13133 \
  -v $(pwd)/otel-collector-config.yaml:/etc/otelcol-contrib/config.yaml \
  --env-file .env \
  otel/opentelemetry-collector-contrib:0.152.0

# ヘルスチェック確認
curl -f http://localhost:13133/
```

ECS Fargate の場合:

```bash
aws cloudformation deploy \
  --template-file template-collector.yaml \
  --stack-name fsxn-otel-collector \
  --capabilities CAPABILITY_IAM \
  --region ap-northeast-1
```

### Step 2: OTel Collector の設定（既存バックエンド + 新バックエンド）

移行期間中は、既存バックエンドと新バックエンドの両方にログを配信します。

```yaml
# otel-collector-config-migration.yaml
exporters:
  # 既存バックエンド（例: Datadog）
  datadog:
    api:
      key: ${env:DD_API_KEY}
      site: ${env:DD_SITE}

  # 新バックエンド（例: Grafana Cloud）
  otlphttp/grafana:
    endpoint: ${env:GRAFANA_OTLP_ENDPOINT}
    headers:
      Authorization: "Basic ${env:GRAFANA_BASIC_AUTH}"

service:
  pipelines:
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [datadog, otlphttp/grafana]  # 両方に配信
```

### Step 3: Lambda エンドポイントの更新

既存の Lambda を OTel Collector エンドポイントに向けます。

**重要**: OTel Collector 用の Lambda（`handler.py`）は OTLP 形式で送信するため、既存のベンダー固有 Lambda とは別物です。新しい Lambda をデプロイします。

```bash
# 新しい OTel Lambda をデプロイ
aws cloudformation deploy \
  --template-file integrations/otel-collector/template.yaml \
  --stack-name fsxn-otel-integration \
  --parameter-overrides \
    S3AccessPointArn=<your-s3-ap-arn> \
    OtlpEndpoint=http://<collector-endpoint>:4318 \
    S3BucketName=<your-bucket> \
  --capabilities CAPABILITY_IAM \
  --region ap-northeast-1
```

### Step 4: 並行稼働と検証

新旧両方の Lambda を並行稼働させ、データの一貫性を確認します。

```bash
# 新 Lambda のテストイベント送信
aws lambda invoke \
  --function-name fsxn-otel-integration-shipper \
  --payload file://tests/test_data/sample_s3_event.json \
  --cli-binary-format raw-in-base64-out \
  /tmp/otel-response.json

# レスポンス確認
cat /tmp/otel-response.json
# 期待: {"statusCode": 200, "body": {"total_logs": N, "total_shipped": N, "errors": []}}
```

検証チェックリスト:
- [ ] 新バックエンドにログが到着している
- [ ] 構造化属性が正しくマッピングされている
- [ ] 既存バックエンドにも引き続きログが到着している
- [ ] レイテンシが許容範囲内

### Step 5: EventBridge ルールの切り替え

検証完了後、EventBridge ルールのターゲットを新 Lambda に切り替えます。

```bash
# 既存ルールのターゲットを確認
aws events list-targets-by-rule \
  --rule fsxn-<old-vendor>-s3-trigger \
  --region ap-northeast-1

# 新 Lambda をターゲットに追加（または既存ルールを更新）
aws events put-targets \
  --rule fsxn-otel-s3-trigger \
  --targets "Id=OtelShipper,Arn=<new-lambda-arn>"
```

### Step 6: 旧 Lambda の無効化

新パスが安定稼働していることを確認後、旧 Lambda を無効化します。

```bash
# 旧 EventBridge ルールを無効化（削除ではなく無効化）
aws events disable-rule \
  --name fsxn-<old-vendor>-s3-trigger \
  --region ap-northeast-1
```

> **注意**: すぐに削除せず、1-2週間は無効化状態で保持してください。問題発生時にすぐにロールバックできます。

### Step 7: OTel Collector から旧バックエンドのエクスポーターを削除

移行完了後、Collector 設定から旧バックエンドを削除します。

```yaml
# 旧バックエンドを削除
exporters:
  # datadog:  ← 削除
  #   api:
  #     key: ${env:DD_API_KEY}
  #     site: ${env:DD_SITE}

  otlphttp/grafana:
    endpoint: ${env:GRAFANA_OTLP_ENDPOINT}
    headers:
      Authorization: "Basic ${env:GRAFANA_BASIC_AUTH}"

service:
  pipelines:
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlphttp/grafana]  # 新バックエンドのみ
```

```bash
# Collector を再起動して設定を反映
docker restart otel-collector
```

## ロールバック手順

問題が発生した場合のロールバック手順です。

### 即時ロールバック（Step 5-6 の段階）

```bash
# 1. 旧 EventBridge ルールを再有効化
aws events enable-rule \
  --name fsxn-<old-vendor>-s3-trigger \
  --region ap-northeast-1

# 2. 新 EventBridge ルールを無効化
aws events disable-rule \
  --name fsxn-otel-s3-trigger \
  --region ap-northeast-1
```

### 完全ロールバック

```bash
# 1. 旧 Lambda スタックが存在することを確認
aws cloudformation describe-stacks \
  --stack-name fsxn-<old-vendor>-integration \
  --region ap-northeast-1

# 2. 旧ルールを再有効化
aws events enable-rule \
  --name fsxn-<old-vendor>-s3-trigger \
  --region ap-northeast-1

# 3. 新スタックを削除（オプション）
aws cloudformation delete-stack \
  --stack-name fsxn-otel-integration \
  --region ap-northeast-1
```

## 移行タイムライン（推奨）

| 日 | アクション | リスク |
|----|---------|--------|
| Day 1 | Step 1-2: Collector デプロイ | なし（既存に影響なし） |
| Day 2-3 | Step 3-4: 新 Lambda デプロイ + 並行稼働 | 低（テストイベントのみ） |
| Day 4-5 | Step 5: EventBridge 切り替え | 中（本番トラフィック移行） |
| Day 5-14 | 監視期間 | 低（ロールバック可能） |
| Day 15 | Step 6: 旧 Lambda 無効化 | 低 |
| Day 30 | Step 7: 旧エクスポーター削除 + 旧スタック削除 | なし |

## 注意事項

- 移行中はログの重複が発生する可能性があります（新旧両方が同じイベントを処理）
- バックエンド側で重複排除が必要な場合は、`trace_id` や `event_id` でフィルタリングしてください
- Lambda コードは完全に異なるため、「コード変更」ではなく「新規デプロイ」として扱います
- 旧 Lambda のコードは参考として保持し、OTel Lambda が安定するまで削除しないでください
