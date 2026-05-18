# セットアップガイド

## 前提条件

- AWS アカウント
- New Relic アカウント（無料枠 100GB/月）

## デプロイ手順

### Step 1: New Relic License Key の準備

New Relic コンソールから License Key を取得します。

```bash
aws secretsmanager create-secret \
  --name fsxn-new-relic-license-key \
  --secret-string YOUR_LICENSE_KEY \
  --region ap-northeast-1
```

### Step 2: CloudFormation デプロイ

| パラメータ | 説明 | デフォルト値 |
|-----------|------|-------------|
| `S3AccessPointArn` | S3 AP の ARN | - |
| `NewRelicLicenseKeySecretArn` | License Key の Secret ARN | - |
| `NewRelicRegion` | New Relic リージョン | `US` |

```bash
aws cloudformation deploy \
  --template-file integrations/new-relic/template.yaml \
  --stack-name fsxn-new-relic-integration \
  --capabilities CAPABILITY_IAM
```

## 動作確認

テストイベントを送信して動作を確認します。

```json
{
  "Records": [
    {
      "s3": {
        "bucket": {"name": "fsxn-audit-logs"},
        "object": {"key": "audit/svm-prod/2026/01/15/audit.json"}
      }
    }
  ]
}
```

## NRQL クエリ例

```sql
SELECT count(*) FROM Log WHERE source='fsxn-ontap' SINCE 1 hour ago
```
