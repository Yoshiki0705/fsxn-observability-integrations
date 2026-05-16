# Dynatrace セットアップガイド

🌐 [English](../en/setup-guide.md)

## 概要

FSx for ONTAP 監査ログを Dynatrace Log Ingest API v2 に配信するセットアップ手順です。

## 前提条件

- Dynatrace 環境（SaaS / Managed）
- [前提リソース](../../../docs/ja/prerequisites.md)デプロイ済み

## Step 1: Dynatrace API Token の作成

1. Dynatrace → **Settings** → **Integration** → **Dynatrace API**
2. **Generate token** → Scopes: `logs.ingest`
3. トークンをコピー

```bash
aws secretsmanager create-secret \
  --name "dynatrace/fsxn-api-token" \
  --secret-string '{"api_token":"dt0c01.xxx..."}' \
  --region ap-northeast-1
```

## Step 2: CloudFormation デプロイ

```bash
aws cloudformation deploy \
  --template-file integrations/dynatrace/template.yaml \
  --stack-name fsxn-dynatrace-integration \
  --parameter-overrides \
    S3AccessPointArn=$AP_ARN \
    DynatraceApiTokenSecretArn=arn:aws:secretsmanager:... \
    DynatraceEnvUrl=https://abc12345.live.dynatrace.com \
    S3BucketName=$BUCKET_NAME \
  --capabilities CAPABILITY_IAM
```

## Step 3: Dynatrace で確認

1. **Observe & Explore** → **Logs**
2. フィルタ: `log.source="fsxn-ontap"`
3. DQL:
```dql
fetch logs
| filter log.source == "fsxn-ontap"
| sort timestamp desc
| limit 20
```

## トラブルシューティング

- **HTTP 401**: API Token の `logs.ingest` スコープを確認
- **1MB 超過**: バッチサイズが自動分割されているか Lambda ログで確認
