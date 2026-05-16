# Grafana Cloud セットアップガイド

🌐 [English](../en/setup-guide.md)

## 概要

FSx for ONTAP 監査ログを Grafana Cloud Loki に配信するセットアップ手順です。

## 前提条件

- Grafana Cloud アカウント（Free tier 可: 50GB/月）
- [前提リソース](../../../docs/ja/prerequisites.md)デプロイ済み

## Step 1: Grafana Cloud 認証情報の準備

1. Grafana Cloud → **My Account** → **Loki** → **Details**
2. Instance ID と URL をメモ
3. **Generate API Key** → Role: `MetricsPublisher`

```bash
aws secretsmanager create-secret \
  --name "grafana/fsxn-credentials" \
  --secret-string '{"instance_id":"123456","api_key":"glc_xxx..."}' \
  --region ap-northeast-1
```

## Step 2: CloudFormation デプロイ

```bash
aws cloudformation deploy \
  --template-file integrations/grafana/template.yaml \
  --stack-name fsxn-grafana-integration \
  --parameter-overrides \
    S3AccessPointArn=$AP_ARN \
    GrafanaCredentialsSecretArn=arn:aws:secretsmanager:...:secret:grafana/fsxn-credentials-XXXXX \
    LokiEndpoint=https://logs-prod-us-central1.grafana.net \
    S3BucketName=$BUCKET_NAME \
  --capabilities CAPABILITY_IAM
```

## Step 3: Grafana で確認

### Explore → Loki

```logql
{job="fsxn-audit"} | json
{job="fsxn-audit", svm="svm-prod-01"} | json | Result="Failure"
{job="fsxn-audit"} | json | line_format "{{.UserName}} {{.Operation}} {{.ObjectName}}"
```

### ダッシュボード作成

- パネル1: ログ量推移 `rate({job="fsxn-audit"}[5m])`
- パネル2: 操作別内訳 `sum by (Operation) (count_over_time({job="fsxn-audit"} | json [1h]))`
- パネル3: 失敗アクセス `{job="fsxn-audit"} | json | Result="Failure"`

## トラブルシューティング

- **HTTP 401**: Instance ID / API Key を確認
- **Out of order entries**: タイムスタンプが降順になっていないか確認（Loki は昇順必須）
- **Rate limit**: Grafana Cloud Free tier は 4MB/分の制限あり
