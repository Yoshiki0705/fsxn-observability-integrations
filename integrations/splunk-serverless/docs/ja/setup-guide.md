# Splunk Serverless セットアップガイド

🌐 [English](../en/setup-guide.md)

## 概要

FSx for ONTAP 監査ログを Splunk HEC (HTTP Event Collector) 経由でサーバーレスに配信する統合のセットアップ手順です。

> **既存パターンとの違い**: [AWS ブログ](https://aws.amazon.com/jp/blogs/news/auditing-user-and-administrative-actions-on-amazon-fsx-for-netapp-ontap-using-splunk/)の EC2 ベース（syslog-ng + Universal Forwarder）を完全サーバーレスに置き換えます。

## 前提条件

- Splunk Enterprise / Splunk Cloud（HEC 有効化済み）
- [前提リソース](../../../docs/ja/prerequisites.md)デプロイ済み

## Step 1: Splunk HEC トークンの作成

1. Splunk Web → **Settings** → **Data Inputs** → **HTTP Event Collector**
2. **New Token** → Name: `fsxn-audit-log-shipper`
3. Source type: `fsxn:ontap:audit`、Index: `fsxn_audit`
4. トークンをコピー

```bash
aws secretsmanager create-secret \
  --name "splunk/fsxn-hec-token" \
  --secret-string '{"hec_token":"YOUR_HEC_TOKEN"}' \
  --region ap-northeast-1
```

## Step 2: Splunk Index の作成

```
# Splunk CLI
splunk add index fsxn_audit -maxDataSize auto_high_volume
```

## Step 3: CloudFormation デプロイ

```bash
aws cloudformation deploy \
  --template-file integrations/splunk-serverless/template.yaml \
  --stack-name fsxn-splunk-integration \
  --parameter-overrides \
    S3AccessPointArn=$AP_ARN \
    SplunkHecTokenSecretArn=arn:aws:secretsmanager:...:secret:splunk/fsxn-hec-token-XXXXX \
    SplunkHecEndpoint=https://splunk.example.com:8088 \
    S3BucketName=$BUCKET_NAME \
    SplunkIndex=fsxn_audit \
  --capabilities CAPABILITY_IAM
```

## Step 4: 動作確認

Splunk Search:
```spl
index=fsxn_audit sourcetype=fsxn:ontap:audit | head 10
```

## EC2 ベースとの比較

| 項目 | EC2 ベース (既存) | サーバーレス (本プロジェクト) |
|------|-----------------|--------------------------|
| インフラ | EC2 × 2台 (syslog-ng + UF) | Lambda + EventBridge |
| 月額コスト | ~$150+ (EC2 + EBS) | ~$5 (従量課金) |
| スケーリング | 手動 | 自動 |
| パッチ管理 | 必要 | 不要 |
| 可用性 | 手動 HA 構成 | AWS マネージド |
| レイテンシ | ~10秒 | ~30秒 |

## ネットワーク考慮事項

- Splunk が VPC 内: Lambda を同じ VPC に配置 + NAT Gateway
- Splunk Cloud: HEC エンドポイントがパブリックアクセス可能であること確認
- 自己署名証明書: `VerifySSL=false` パラメータを設定
