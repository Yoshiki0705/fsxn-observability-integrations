# はじめに

## 前提条件

- AWS アカウント
- AWS CLI v2 設定済み
- Amazon FSx for NetApp ONTAP ファイルシステム（監査ログ有効化済み）
- Node.js 18+ (開発用)
- Python 3.12+ (Lambda 関数用)

## セットアップ手順

### 1. FSx for ONTAP 監査ログの有効化

FSx for ONTAP コンソールまたは CLI で監査ログを有効化し、S3 バケットへの出力を設定します。

```bash
# ONTAP CLI で監査ログ有効化
vserver audit create -vserver <svm-name> \
  -destination /vol/audit_logs \
  -format evtx \
  -rotate-size 100MB
```

### 2. S3 Access Point の作成

```bash
aws s3control create-access-point \
  --account-id 123456789012 \
  --name fsxn-audit-ap \
  --bucket fsxn-audit-logs-bucket \
  --vpc-configuration VpcId=vpc-xxxxxxxx
```

### 3. ベンダー統合のデプロイ

各ベンダーのディレクトリに移動し、CloudFormation テンプレートをデプロイします。

```bash
# 例: Datadog 統合
cd integrations/datadog
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-datadog-integration \
  --parameter-overrides \
    S3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap \
    DatadogApiKeySecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:datadog-api-key \
  --capabilities CAPABILITY_IAM
```

### 4. 動作確認

FSx for ONTAP でファイル操作を行い、ベンダー側でログが受信されることを確認します。

## 次のステップ

- [アーキテクチャ詳細](architecture.md)
- [ベンダー比較](vendor-comparison.md)
- [Datadog セットアップガイド](../../integrations/datadog/docs/ja/setup-guide.md)
