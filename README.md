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
| [New Relic](integrations/new-relic/) | 🚧 Planned | Log API via Lambda |
| [Grafana Cloud](integrations/grafana/) | 🚧 Planned | Loki API via Lambda |
| [Splunk (Serverless)](integrations/splunk-serverless/) | 🚧 Planned | HEC via Lambda/Firehose |
| [Elastic](integrations/elastic/) | 🚧 Planned | Elasticsearch Ingest API |
| [Dynatrace](integrations/dynatrace/) | 🚧 Planned | Log Ingest API |
| [Sumo Logic](integrations/sumo-logic/) | 🚧 Planned | HTTP Source |
| [Honeycomb](integrations/honeycomb/) | 🚧 Planned | Events API |
| [OTel Collector](integrations/otel-collector/) | 🚧 Planned | Vendor-neutral OTLP |

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

# 3. ベンダー別ディレクトリへ移動（例: Datadog）
cd integrations/datadog

# 4. デプロイ
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-datadog-integration \
  --parameter-overrides \
    S3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit \
    DatadogApiKeySecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:datadog-api-key \
  --capabilities CAPABILITY_IAM
```

## Documentation / ドキュメント

- [アーキテクチャ (日本語)](docs/ja/architecture.md)
- [Architecture (English)](docs/en/architecture.md)
- [ベンダー比較 (日本語)](docs/ja/vendor-comparison.md)
- [Vendor Comparison (English)](docs/en/vendor-comparison.md)

## Tech Stack / 技術スタック

- **Infrastructure**: CloudFormation (YAML) + CDK (TypeScript)
- **Lambda**: Python 3.12 (ログ処理) + TypeScript (API連携)
- **Test**: Jest + pytest
- **CI/CD**: GitHub Actions
- **Docs**: Markdown (日英バイリンガル)

## License

MIT
