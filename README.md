# FSx for ONTAP Observability Integrations

🌐 [日本語](docs/ja/getting-started.md) | [English](docs/en/getting-started.md)

---

## Overview / 概要

Amazon FSx for NetApp ONTAP の監査ログ・メトリクスを、**FSx for ONTAP S3 Access Points** 経由で各 Observability ベンダーへ **EC2 不要**で配信するパターン集です。

EC2-free observability integrations for Amazon FSx for NetApp ONTAP via FSx for ONTAP S3 Access Points.

## Architecture Pattern / アーキテクチャパターン

```
FSx ONTAP → 監査ログ有効化 → audit volume に出力
audit volume → FSx for ONTAP S3 Access Point で S3 API アクセス
EventBridge Scheduler → Lambda → ベンダー固有 API エンドポイントへ配信

EMS: ONTAP → Webhook → API Gateway → Lambda → ベンダー API
FPolicy: ONTAP → TCP:9898 → ECS Fargate → SQS → Lambda → ベンダー API
```

## Supported Integrations / 対応ベンダー

| Vendor | Status | Description |
|--------|--------|-------------|
| [Datadog](integrations/datadog/) | ✅ E2E verified | Logs API v2 via Lambda |
| [New Relic](integrations/new-relic/) | 🧪 Implementation ready | Log API v1 via Lambda |
| [Splunk (Serverless)](integrations/splunk-serverless/) | 🧪 Implementation ready | HEC via Lambda (replaces EC2 pattern) |
| [OTel Collector](integrations/otel-collector/) | 🧪 Implementation ready | Vendor-neutral OTLP/HTTP |
| [Grafana Cloud](integrations/grafana/) | 🧪 Implementation ready | Loki Push API via Lambda |
| [Elastic](integrations/elastic/) | 🧪 Implementation ready | Elasticsearch Bulk API |
| [Dynatrace](integrations/dynatrace/) | 🧪 Implementation ready | Log Ingest API v2 |
| [Sumo Logic](integrations/sumo-logic/) | 🧪 Implementation ready | HTTP Source |
| [Honeycomb](integrations/honeycomb/) | 🧪 Implementation ready | Events Batch API |

Status:
- ✅ **E2E verified** — Deployed and validated with real FSx for ONTAP audit logs
- 🧪 **Implementation ready** — Code and CloudFormation available; E2E validation pending

## Background / 背景

既存の Splunk 統合ブログ ([AWS Blog](https://aws.amazon.com/jp/blogs/news/auditing-user-and-administrative-actions-on-amazon-fsx-for-netapp-ontap-using-splunk/)) は EC2 ベース（syslog-ng + Universal Forwarder）のアプローチです。

本プロジェクトでは、**EC2 不要**の代替パターンを提供します（Lambda + ECS Fargate を使用）。

## Business Outcomes / ビジネス価値

- EC2 コレクター運用の削減（パッチ適用、エージェント管理不要）
- Observability ベンダー間で監査ログ配送を標準化
- ファイルアクセス行動の可視性向上
- ONTAP ネイティブテレメトリを活用した迅速なセキュリティ対応

## Partner Positioning / パートナー向け

This project helps partners modernize EC2-based FSx for ONTAP audit log collectors into an EC2-free, vendor-neutral observability pipeline.

Common customer scenarios:
- Replacing Splunk Universal Forwarder on EC2
- Modernizing audit visibility for enterprise file shares (departmental file servers, application interface directories such as SAP/Oracle/SQL Server adjacent shares, VDI/EUC home directories, engineering and design repositories)
- Integrating FSx for ONTAP with existing SIEM / observability platforms
- Preparing for ransomware detection workflows using ONTAP telemetry

## Quick Validation / 動作確認手順

After deploying a vendor integration stack:

```bash
# 1. Confirm Scheduler is invoking Lambda
aws logs filter-log-events \
  --log-group-name /aws/lambda/fsxn-datadog-integration-shipper \
  --start-time $(python3 -c "import time; print(int((time.time()-300)*1000))") \
  --region ap-northeast-1

# 2. Confirm DLQ is empty (no failed events)
aws sqs get-queue-attributes \
  --queue-url <dlq-url> \
  --attribute-names All \
  --query 'Attributes.ApproximateNumberOfMessages'

# 3. Search in your observability platform
#    Datadog: source:fsxn
#    Splunk:  index=fsxn_audit
#    Grafana: {source="fsxn"}
```

## Teardown / スタック削除

```bash
# Remove vendor integration stack
aws cloudformation delete-stack \
  --stack-name fsxn-datadog-integration \
  --region ap-northeast-1

# Remove prerequisites stack (if no other vendor stacks depend on it)
aws cloudformation delete-stack \
  --stack-name fsxn-observability-prerequisites \
  --region ap-northeast-1

# ONTAP audit logging remains active — disable separately if needed:
# vserver audit disable -vserver <svm-name>
```

> **Note**: Deleting the stack does not affect ONTAP audit logging or existing data on the FSx volume. Audit logs continue to be written to the audit volume.

## Quick Start / クイックスタート

```bash
# 1. リポジトリクローン
git clone https://github.com/your-org/fsxn-observability-integrations.git
cd fsxn-observability-integrations

# 2. 依存関係インストール
npm install

# 3. 前提リソースのデプロイ（EventBridge Scheduler + チェックポイント）
aws cloudformation deploy \
  --template-file shared/templates/prerequisites.yaml \
  --stack-name fsxn-observability-prerequisites \
  --parameter-overrides \
    FsxS3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap \
  --capabilities CAPABILITY_IAM

# 4. FSx ONTAP 監査ログ有効化（ドライラン）
bash shared/scripts/ontap-audit-setup.sh \
  --endpoint <management-ip> --svm <svm-name> --dry-run

# 5. ベンダー統合のデプロイ（例: Datadog）
aws cloudformation deploy \
  --template-file integrations/datadog/template.yaml \
  --stack-name fsxn-datadog-integration \
  --parameter-overrides \
    FsxS3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap \
    DatadogApiKeySecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:datadog-api-key \
    DatadogSite=datadoghq.com \
  --capabilities CAPABILITY_NAMED_IAM
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
- [運用ガイド (日本語)](docs/ja/operational-guide.md)
- [Operational Guide (English)](docs/en/operational-guide.md)
- [ONTAP 監査設定ガイド (日本語)](docs/ja/ontap-audit-setup.md)
- [ONTAP Audit Setup Guide (English)](docs/en/ontap-audit-setup.md)
- [最小テストパス (日本語)](docs/ja/quick-start-minimum.md)
- [Minimum Test Path (English)](docs/en/quick-start-minimum.md)
- [検知ユースケース (日本語)](docs/ja/detection-use-cases.md)
- [Detection Use Cases (English)](docs/en/detection-use-cases.md)
- [正規化イベントスキーマ (日本語)](docs/ja/normalized-event-schema.md)
- [Normalized Event Schema (English)](docs/en/normalized-event-schema.md)

## Tech Stack / 技術スタック

- **Infrastructure**: CloudFormation (YAML) + CDK (TypeScript)
- **Lambda**: Python 3.12 (ログ処理) + TypeScript (API連携)
- **Test**: Jest + pytest
- **CI/CD**: GitHub Actions
- **Docs**: Markdown (日英バイリンガル)

## License

MIT
