# OTel Collector 統合セットアップガイド

FSx for ONTAP 監査ログを OpenTelemetry Collector 経由で Grafana Cloud（Loki）と Honeycomb に同時配信するためのセットアップ手順です。

## 前提条件

- Docker および Docker Compose がインストール済み
- AWS CLI v2 が設定済み（`aws configure`）
- FSx for ONTAP S3 Access Point が作成済み
- Grafana Cloud アカウント（Loki エンドポイント、User ID、API Token）
- Honeycomb アカウント（API Key）
- Python 3.12（Lambda 開発用）

## OTel Collector Docker セットアップ

OTel Collector をローカルで起動し、OTLP/HTTP でログを受信します。

### Docker Compose 設定

```yaml
services:
  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    ports:
      - "4318:4318"   # OTLP HTTP
      - "13133:13133" # Health check
    volumes:
      - ./otel-collector-config.yaml:/etc/otelcol-contrib/config.yaml
    environment:
      - GRAFANA_LOKI_ENDPOINT=${GRAFANA_LOKI_ENDPOINT}
      - GRAFANA_LOKI_USER=${GRAFANA_LOKI_USER}
      - GRAFANA_LOKI_TOKEN=${GRAFANA_LOKI_TOKEN}
      - HONEYCOMB_API_KEY=${HONEYCOMB_API_KEY}
      - HONEYCOMB_DATASET=${HONEYCOMB_DATASET:-fsxn-audit}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:13133/"]
      interval: 5s
      timeout: 3s
      retries: 5
      start_period: 10s
    restart: unless-stopped
```

### 環境変数の設定

`.env.example` をコピーして `.env` を作成し、認証情報を設定します：

```bash
cp .env.example .env
# Edit .env with your actual credentials
```

### 起動

```bash
cd integrations/otel-collector
docker compose up -d
```

ヘルスチェックの確認：

```bash
curl -f http://localhost:13133/
```

## Collector YAML 設定

OTel Collector の設定ファイルは、OTLP レシーバー、バッチプロセッサー、および Loki + Honeycomb エクスポーターを定義します。

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 5s
    send_batch_size: 1000

exporters:
  loki:
    endpoint: ${env:GRAFANA_LOKI_ENDPOINT}
    default_labels_enabled:
      exporter: false
      job: true
    headers:
      Authorization: "Basic ${env:GRAFANA_LOKI_USER}:${env:GRAFANA_LOKI_TOKEN}"

  otlphttp/honeycomb:
    endpoint: https://api.honeycomb.io
    headers:
      x-honeycomb-team: ${env:HONEYCOMB_API_KEY}
      x-honeycomb-dataset: ${env:HONEYCOMB_DATASET}

extensions:
  health_check:
    endpoint: 0.0.0.0:13133

service:
  extensions: [health_check]
  pipelines:
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [loki, otlphttp/honeycomb]
```

この設定により、Lambda から送信された OTLP ログが自動的に Grafana Cloud と Honeycomb の両方に配信されます。

## CloudFormation デプロイ

Lambda 関数と関連リソースを AWS にデプロイします。

### パラメータ

| パラメータ | 説明 | 例 |
|-----------|------|-----|
| `S3AccessPointArn` | FSx ONTAP S3 AP の ARN | `arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit` |
| `OtlpEndpoint` | OTel Collector エンドポイント | `http://collector:4318` |
| `ApiKeySecretArn` | 認証トークンの Secret ARN（任意） | `arn:aws:secretsmanager:...` |
| `ServiceName` | OTLP service.name 属性 | `fsxn-audit` |
| `S3BucketName` | 監査ログバケット名 | `fsxn-audit-logs-bucket` |

### デプロイコマンド

```bash
aws cloudformation deploy \
  --template-file integrations/otel-collector/template.yaml \
  --stack-name fsxn-otel-integration \
  --parameter-overrides \
    S3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit \
    OtlpEndpoint=http://your-collector:4318 \
    S3BucketName=fsxn-audit-logs-bucket \
    ServiceName=fsxn-audit \
  --capabilities CAPABILITY_IAM \
  --region ap-northeast-1
```

## テストイベント実行

Lambda 関数にテストイベントを送信して動作を確認します。

```bash
aws lambda invoke \
  --function-name fsxn-otel-integration-shipper \
  --payload file://integrations/otel-collector/tests/test_data/sample_s3_event.json \
  --cli-binary-format raw-in-base64-out \
  /tmp/otel-response.json

cat /tmp/otel-response.json
```

期待されるレスポンス：

```json
{"statusCode": 200, "body": {"total_logs": 6, "total_shipped": 6, "errors": []}}
```

## 検証手順

### 1. Lambda 実行ログの確認

CloudWatch Logs で OTLP 配信成功を確認します：

```bash
aws logs tail /aws/lambda/fsxn-otel-integration-shipper --since 5m
```

期待される出力：`OTLP payload sent successfully` のログエントリが表示されること。

![CloudWatch OTLP 配信成功](../../../../docs/screenshots/01-cloudwatch-otlp-success.png)

### 2. Grafana Cloud でのログ到着確認

Grafana Cloud Explore で以下のクエリを実行します：

- データソース: Loki
- クエリ: `{job="fsxn-audit"}`

5分以内に FSx ONTAP 監査ログが表示されることを確認します。`event.type`、`user.name`、`fsxn.operation` 属性が含まれていることを確認してください。

![Grafana Cloud ログ到着](../../../../docs/screenshots/02-grafana-logs-arrival.png)

### 3. Honeycomb でのログ到着確認

Honeycomb の `fsxn-audit` データセットでクエリを実行します：

- データセット: `fsxn-audit`
- 時間範囲: 過去5分

5分以内に FSx ONTAP 監査ログが表示されることを確認します。

### 4. マルチバックエンド一貫性確認

Grafana Cloud と Honeycomb の両方で同一のイベント（同じタイムスタンプ、同じファイルパス）が確認できることを検証します。

## Datadog バックエンド設定

Grafana Cloud + Honeycomb の代わりに **Datadog** をバックエンドとして使用する場合の設定です。Lambda コードの変更は不要で、OTel Collector の設定ファイルを切り替えるだけで配信先を変更できます。

### Datadog 用 Collector 設定

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 5s
    send_batch_size: 1000

exporters:
  datadog:
    api:
      key: ${env:DD_API_KEY}
      site: ${env:DD_SITE}

extensions:
  health_check:
    endpoint: 0.0.0.0:13133

service:
  extensions: [health_check]
  pipelines:
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [datadog]
```

### Docker Compose（Datadog 版）の起動

```bash
# 1. Configure credentials
cp .env.datadog.example .env.datadog
# Edit .env.datadog with your DD_API_KEY and DD_SITE
# DD_SITE examples:
#   datadoghq.com (US1), datadoghq.eu (EU),
#   ap1.datadoghq.com (AP1/Japan), us3.datadoghq.com (US3)

# 2. Start OTel Collector with Datadog config
# Option A: docker compose (if available)
docker compose -f docker-compose-datadog.yaml --env-file .env.datadog up -d

# Option B: docker run (fallback for Colima or environments without compose plugin)
docker run -d --name otel-collector-datadog \
  -p 4318:4318 -p 13133:13133 \
  -v $(pwd)/otel-collector-config-datadog.yaml:/etc/otelcol-contrib/config.yaml \
  --env-file .env.datadog \
  otel/opentelemetry-collector-contrib:0.152.0

# 3. Verify health check
curl -f http://localhost:13133/
```

> **注意**: macOS で Colima を使用している場合、`docker compose` (v2 プラグイン) が利用できないことがあります。その場合は方法 B の `docker run` を使用してください。

### Datadog での検証手順

1. Datadog Logs UI にログインします
2. 検索フィルタに `source:fsxn-audit` または `service:fsxn-ontap`（FPolicy の場合）を入力します
3. FSx ONTAP ログが到着していることを確認します（5分以内）
4. 構造化属性が含まれることを確認します：
   - **S3 監査ログ**: `event.type`、`user.name`、`fsxn.operation`、`client.address`、`fsxn.result`、`fsxn.path`
   - **FPolicy**: `client_ip`、`file_path`、`operation_type`、`volume_name`、`event_id`、`timestamp`、`file_size`、`svm`/`vserver`

> **確認済み**: FPolicy → OTel Collector → Datadog パスは 2026-05-18 に検証完了。
> Service: `fsxn-ontap`、Source: `fsxn-fpolicy` として Datadog に表示されます。

### ローカルテストスクリプト

自動化されたローカルテストを実行するには：

```bash
bash scripts/test-local-datadog.sh
```

このスクリプトは以下を自動実行します：
- OTel Collector の起動（Datadog 設定）
- ヘルスチェック確認
- サンプル OTLP ペイロードの送信
- Collector ログの確認
- クリーンアップ
