# OpenTelemetry Collector セットアップガイド

🌐 [English](../en/setup-guide.md)

## 概要

ベンダー中立の OTLP/HTTP プロトコルで FSx ONTAP 監査ログを任意のバックエンドに配信します。

## 前提条件

- OTLP 対応バックエンド（Grafana, Honeycomb, Datadog, Jaeger 等）
- [前提リソース](../../../docs/ja/prerequisites.md)デプロイ済み

## Step 1: OTLP エンドポイントの準備

### Grafana Cloud の場合
```
Endpoint: https://otlp-gateway-prod-ap-southeast-0.grafana.net/otlp
Headers: Authorization=Basic <base64(instance_id:api_key)>
```

### Honeycomb の場合
```
Endpoint: https://api.honeycomb.io
Headers: x-honeycomb-team=<api-key>,x-honeycomb-dataset=fsxn-audit
```

### セルフホスト Collector の場合
```
Endpoint: http://<collector-host>:4318
```

## Step 2: CloudFormation デプロイ

```bash
aws cloudformation deploy \
  --template-file integrations/otel-collector/template.yaml \
  --stack-name fsxn-otel-integration \
  --parameter-overrides \
    S3AccessPointArn=$AP_ARN \
    OtlpEndpoint=https://otlp-gateway.grafana.net/otlp \
    OtlpHeaders="Authorization=Basic xxx" \
    S3BucketName=$BUCKET_NAME \
    OtelServiceName=fsxn-ontap-audit \
  --capabilities CAPABILITY_IAM
```

## Step 3: 動作確認

テストイベントを送信し、バックエンドでログ到着を確認。

## セルフホスト Collector 設定例

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 5s

exporters:
  loki:
    endpoint: http://loki:3100/loki/api/v1/push
  otlphttp/honeycomb:
    endpoint: https://api.honeycomb.io
    headers:
      x-honeycomb-team: ${HONEYCOMB_KEY}

service:
  pipelines:
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [loki, otlphttp/honeycomb]
```

## メリット

- ベンダーロックイン回避: バックエンド切り替え時にコード変更不要
- マルチ配信: 1つの Lambda から複数バックエンドに同時配信可能
- 標準フォーマット: CNCF 標準の OpenTelemetry Log Data Model
