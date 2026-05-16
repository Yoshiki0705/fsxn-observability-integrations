# FSxN Observability Integrations

🌐 [日本語](docs/ja/getting-started.md) | [English](docs/en/getting-started.md)

---

## Overview / 概要

Amazon FSx for NetApp ONTAP の監査ログ・メトリクスを、**S3 Access Points** 経由で各 Observability ベンダーへ**サーバーレス**に配信するパターン集です。

Serverless observability integrations for Amazon FSx for NetApp ONTAP via S3 Access Points.

## Architecture Pattern / アーキテクチャパターン

```
FSx ONTAP → 監査ログ有効化 → S3 Access Point へ出力
S3 AP → EventBridge / S3 Event Notification → Lambda
Lambda → ベンダー固有 API エンドポイントへ配信

代替: S3 AP → Kinesis Data Firehose → ベンダー直接配信
```

## Supported Integrations / 対応ベンダー

| Vendor | Status | Description |
|--------|--------|-------------|
| [Datadog](integrations/datadog/) | ✅ Ready | Logs API v2 via Lambda |
| [New Relic](integrations/new-relic/) | ✅ Ready | Log API v1 via Lambda |
| [Splunk (Serverless)](integrations/splunk-serverless/) | ✅ Ready | HEC via Lambda (replaces EC2 pattern) |
| [OTel Collector](integrations/otel-collector/) | ✅ Ready | Vendor-neutral OTLP/HTTP |
| [Grafana Cloud](integrations/grafana/) | ✅ Ready | Loki Push API via Lambda |
| [Elastic](integrations/elastic/) | ✅ Ready | Elasticsearch Bulk API |
| [Dynatrace](integrations/dynatrace/) | ✅ Ready | Log Ingest API v2 |
| [Sumo Logic](integrations/sumo-logic/) | ✅ Ready | HTTP Source |
| [Honeycomb](integrations/honeycomb/) | ✅ Ready | Events Batch API |

## Background / 背景

既存の Splunk 統合ブログ ([AWS Blog](https://aws.amazon.com/jp/blogs/news/auditing-user-and-administrative-actions-on-amazon-fsx-for-netapp-ontap-using-splunk/)) は EC2 ベース（syslog-ng + Universal Forwarder）のアプローチです。

本プロジェクトでは、**完全サーバーレス**の代替パターンを提供します。

## Quick Start / クイックスタート

```bash
# 1. リポジトリクローン
git clone https://github.com/your-org/fsxn-observability-integrations.git
cd fsxn-observability-integrations

# 2. 依存関係インストール
npm install

# 3. 前提リソースのデプロイ（S3バケット + Access Point + EventBridge通知）
aws cloudformation deploy \
  --template-file shared/templates/prerequisites.yaml \
  --stack-name fsxn-observability-prerequisites \
  --parameter-overrides \
    AuditLogBucketName=my-fsxn-audit-logs \
    AccessPointName=fsxn-audit-ap \
  --capabilities CAPABILITY_IAM

# 4. FSx ONTAP 監査ログ有効化（ドライラン）
bash shared/scripts/ontap-audit-setup.sh \
  --endpoint <management-ip> --svm <svm-name> --dry-run

# 5. ベンダー統合のデプロイ（例: Datadog）
aws cloudformation deploy \
  --template-file integrations/datadog/template.yaml \
  --stack-name fsxn-datadog-integration \
  --parameter-overrides \
    S3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap \
    DatadogApiKeySecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:datadog-api-key \
    DatadogSite=datadoghq.com \
    S3BucketName=my-fsxn-audit-logs \
  --capabilities CAPABILITY_IAM
```

> 📝 詳細な手順は [前提条件ガイド (日本語)](docs/ja/prerequisites.md) / [Prerequisites Guide (English)](docs/en/prerequisites.md) を参照してください。

## Documentation / ドキュメント

- [前提条件・デプロイガイド (日本語)](docs/ja/prerequisites.md)
- [Prerequisites & Deployment Guide (English)](docs/en/prerequisites.md)
- [S3 AP 仕様・制約・トラブルシューティング (日本語)](docs/ja/s3ap-fsxn-specification.md)
- [S3 AP Specification & Troubleshooting (English)](docs/en/s3ap-fsxn-specification.md)
- [アーキテクチャ (日本語)](docs/ja/architecture.md)
- [Architecture (English)](docs/en/architecture.md)
- [イベントソースガイド (日本語)](docs/ja/event-sources.md)
- [Event Sources Guide (English)](docs/en/event-sources.md)
- [ベンダー比較 (日本語)](docs/ja/vendor-comparison.md)
- [Vendor Comparison (English)](docs/en/vendor-comparison.md)
- [デモシナリオ (日本語)](docs/ja/demo-scenarios.md)
- [Demo Scenarios (English)](docs/en/demo-scenarios.md)

## Tech Stack / 技術スタック

- **Infrastructure**: CloudFormation (YAML) + CDK (TypeScript)
- **Lambda**: Python 3.12 (ログ処理) + TypeScript (API連携)
- **Test**: Jest + pytest
- **CI/CD**: GitHub Actions
- **Docs**: Markdown (日英バイリンガル)

## License

MIT
