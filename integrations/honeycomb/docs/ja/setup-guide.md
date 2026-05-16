# Honeycomb セットアップガイド

🌐 [English](../en/setup-guide.md)

## 概要

FSx for ONTAP 監査ログを Honeycomb Events API に配信するセットアップ手順です。

## 前提条件

- Honeycomb アカウント
- [前提リソース](../../../docs/ja/prerequisites.md)デプロイ済み

## Step 1: Honeycomb API Key の準備

1. Honeycomb → **Team Settings** → **API Keys**
2. **Create API Key** → Permissions: `Send Events`
3. Dataset: `fsxn-audit`（自動作成される）

```bash
aws secretsmanager create-secret \
  --name "honeycomb/fsxn-api-key" \
  --secret-string '{"api_key":"YOUR_HONEYCOMB_API_KEY"}' \
  --region ap-northeast-1
```

## Step 2: CloudFormation デプロイ

```bash
aws cloudformation deploy \
  --template-file integrations/honeycomb/template.yaml \
  --stack-name fsxn-honeycomb-integration \
  --parameter-overrides \
    S3AccessPointArn=$AP_ARN \
    HoneycombApiKeySecretArn=arn:aws:secretsmanager:... \
    HoneycombDataset=fsxn-audit \
    S3BucketName=$BUCKET_NAME \
  --capabilities CAPABILITY_IAM
```

## Step 3: Honeycomb で確認

1. Dataset: `fsxn-audit`
2. Query: `GROUP BY operation, VISUALIZE COUNT`
3. フィルタ: `result = Failure`

## Honeycomb の強み

- 高カーディナリティデータの探索に最適
- BubbleUp で異常パターンを自動検出
- SLO 設定でファイルアクセス成功率を監視可能
