# Sumo Logic セットアップガイド

🌐 [English](../en/setup-guide.md)

## 概要

FSx for ONTAP 監査ログを Sumo Logic HTTP Source に配信するセットアップ手順です。

## 前提条件

- Sumo Logic アカウント（Free tier: 500MB/日）
- [前提リソース](../../../docs/ja/prerequisites.md)デプロイ済み

## Step 1: HTTP Source の作成

1. Sumo Logic → **Manage Data** → **Collection** → **Add Source**
2. Source type: **HTTP Logs & Metrics**
3. Source Category: `aws/fsxn/audit`
4. URL をコピー

```bash
aws secretsmanager create-secret \
  --name "sumo-logic/fsxn-http-source" \
  --secret-string '{"url":"https://endpoint1.collection.sumologic.com/receiver/v1/http/TOKEN"}' \
  --region ap-northeast-1
```

## Step 2: CloudFormation デプロイ

```bash
aws cloudformation deploy \
  --template-file integrations/sumo-logic/template.yaml \
  --stack-name fsxn-sumo-logic-integration \
  --parameter-overrides \
    S3AccessPointArn=$AP_ARN \
    SumoLogicHttpSourceSecretArn=arn:aws:secretsmanager:... \
    S3BucketName=$BUCKET_NAME \
  --capabilities CAPABILITY_IAM
```

## Step 3: Sumo Logic で確認

```
_sourceCategory=aws/fsxn/audit
| json auto
| where Operation = "ReadData"
| count by UserName
```

## トラブルシューティング

- **HTTP 401**: HTTP Source URL が正しいか確認
- **1MB 超過**: Lambda が自動分割しているか確認
