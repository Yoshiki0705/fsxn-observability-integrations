# New Relic セットアップガイド

🌐 [English](../en/setup-guide.md)

## 概要

FSx for ONTAP 監査ログを New Relic Logs に配信するサーバーレス統合のセットアップ手順です。

## 前提条件

- AWS アカウント（FSx ONTAP 稼働中）
- New Relic アカウント（Logs 機能有効）
- [前提リソース](../../../docs/ja/prerequisites.md)デプロイ済み

## Step 1: New Relic License Key の準備

1. New Relic → **API Keys** → **Create a key**
2. Key type: `INGEST - LICENSE`
3. 生成された License Key をコピー

```bash
aws secretsmanager create-secret \
  --name "new-relic/fsxn-license-key" \
  --secret-string '{"license_key":"YOUR_LICENSE_KEY"}' \
  --region ap-northeast-1
```

## Step 2: CloudFormation デプロイ

```bash
aws cloudformation deploy \
  --template-file integrations/new-relic/template.yaml \
  --stack-name fsxn-new-relic-integration \
  --parameter-overrides \
    S3AccessPointArn=$AP_ARN \
    NewRelicLicenseKeySecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:new-relic/fsxn-license-key-XXXXX \
    NewRelicRegion=US \
    S3BucketName=$BUCKET_NAME \
  --capabilities CAPABILITY_IAM
```

## Step 3: New Relic 側の設定

### Parsing Rule

1. **Logs** → **Parsing** → **Create parsing rule**
2. NRQL: `SELECT * FROM Log WHERE source='fsxn-ontap'`
3. Grok pattern でフィールド抽出

### Alert Condition

```sql
SELECT count(*) FROM Log
WHERE source = 'fsxn-ontap' AND attributes.result = 'Failure'
FACET attributes.user
```

## Step 4: 動作確認

```bash
# テストファイルをアップロード
aws s3 cp integrations/datadog/tests/test_data/sample_audit_logs.json \
  s3://$BUCKET_NAME/audit/svm-prod-01/test.json
```

New Relic Logs UI → `source:fsxn-ontap` で検索。

## トラブルシューティング

- **HTTP 403**: License Key が正しいか確認
- **HTTP 429**: レート制限。Lambda 同時実行数を制限
- **ログ未到着**: CloudWatch Logs で Lambda エラーを確認
