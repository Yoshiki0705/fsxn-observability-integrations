# FSx for ONTAP Observability Integrations

🌐 [日本語](docs/ja/README.md) | [English](docs/en/README.md)

> This is a community reference implementation and not an official AWS service feature or compliance attestation. Validate all configurations, costs, and compliance requirements in your own environment.
>
> 本リポジトリはコミュニティベースのリファレンス実装であり、AWS 公式サービス機能や準拠性を保証するものではありません。設定、コスト、コンプライアンス要件は各自の環境で検証してください。

---

## Overview / 概要

Amazon FSx for NetApp ONTAP の監査ログ・メトリクスを、**FSx for ONTAP S3 Access Points** 経由で各 Observability ベンダーへ **EC2 不要**で配信するパターン集です。

EC2-free observability integrations for Amazon FSx for NetApp ONTAP via FSx for ONTAP S3 Access Points.

## Choose Your Path / パス選択ガイド

| Goal | Recommended Path | Why |
|---|---|---|
| First validation | Audit poller only | Fastest way to prove read path, delivery, checkpoint, and DLQ |
| Single observability backend | Direct vendor integration | Fewer moving parts |
| Grafana Cloud quickstart | Direct OTLP Gateway | Native OTLP path to Loki |
| Multi-backend / redaction / routing | OTel Collector or Grafana Alloy | Move cross-cutting pipeline concerns out of Lambda |
| Higher reliability | SQS + DynamoDB ledger + Collector/Alloy | Backpressure, replay, batching, durable state |
| Partner PoC | Partner Solution Brief + PoC Checklist | Clear scope, deliverables, and responsibility boundaries |

## Recommended First 30 Minutes / 最初の30分

1. Read "Choose Your Path" above to identify your target integration
2. Run unit tests with sample payloads: `python -m pytest integrations/datadog/tests/ -v`
3. Review the [PoC Success Criteria](docs/en/poc-success-criteria.md) for your target integration
4. Deploy audit-only path in a sandbox account (see Quick Start below)
5. Confirm: one log record arrives, checkpoint advances, DLQ remains empty

## Architecture Pattern / アーキテクチャパターン

```
FSx ONTAP → 監査ログ有効化 → audit volume に出力
audit volume → FSx for ONTAP S3 Access Point で S3 API アクセス
EventBridge Scheduler → Lambda → ベンダー固有 API エンドポイントへ配信

EMS: ONTAP → Webhook → API Gateway → Lambda → ベンダー API
FPolicy: ONTAP → TCP:9898 → ECS Fargate → SQS → Lambda → ベンダー API
```

### Trigger Model Note / トリガーモデルに関する注意

FSx for ONTAP S3 Access Points は **S3 Event Notifications および EventBridge オブジェクトレベルイベントをサポートしていません**。そのため、本プロジェクトでは以下のアプローチを採用しています:

- **EventBridge Scheduler によるポーリング**: 定期的に Lambda を起動し、SSM Parameter Store にチェックポイントを保存して処理済みファイルを追跡
- **CloudTrail データイベント**: ニアリアルタイムのトリガーが必要な場合の代替手段として文書化されています（S3 AP へのアクセスを CloudTrail で記録し、EventBridge ルールでフィルタリング）
- **通常の S3 バケット + S3 Event Notifications**: テストデータのバリデーション用途では、通常の S3 バケットに対して S3 Event Notifications を使用可能

> FSx for ONTAP S3 Access Points do NOT support S3 Event Notifications or EventBridge object-level events. This project uses EventBridge Scheduler polling with SSM Parameter Store checkpointing. CloudTrail data events are a documented alternative for near-real-time triggering. Regular S3 bucket test data may use S3 Event Notifications for validation.

## Supported Integrations / 対応ベンダー

| Vendor | Status | Description |
|--------|--------|-------------|
| [Datadog](integrations/datadog/) | ✅ E2E verified | Logs API v2 via Lambda |
| [New Relic](integrations/new-relic/) | ✅ E2E verified | Log API v1 via Lambda |
| [Splunk (Serverless)](integrations/splunk-serverless/) | ✅ E2E verified | HEC via Lambda (replaces EC2 pattern) |
| [OTel Collector](integrations/otel-collector/) | ✅ E2E verified | Vendor-neutral OTLP/HTTP (Datadog + Grafana + Honeycomb) |
| [Grafana Cloud](integrations/grafana/) | ✅ E2E verified | OTLP Gateway via Lambda (Loki Push API fallback) |
| [Elastic](integrations/elastic/) | ✅ E2E verified | Elasticsearch Bulk API |
| [Dynatrace](integrations/dynatrace/) | ✅ E2E verified | Log Ingest API v2 |
| [Sumo Logic](integrations/sumo-logic/) | ✅ E2E verified | HTTP Source |
| [Honeycomb](integrations/honeycomb/) | ✅ E2E verified | Events Batch API |

Status:
- ✅ **E2E verified** — Deployed and validated with real FSx for ONTAP audit logs
- 🧪 **Implementation ready** — Code and CloudFormation available; E2E validation pending

## Background / 背景

既存の Splunk 統合ブログ ([AWS Blog](https://aws.amazon.com/jp/blogs/news/auditing-user-and-administrative-actions-on-amazon-fsx-for-netapp-ontap-using-splunk/)) は EC2 ベース（syslog-ng + Universal Forwarder）のアプローチです。

本プロジェクトでは、**EC2 不要**の代替パターンを提供します（Lambda + ECS Fargate を使用）。

## Business Outcomes / ビジネス価値

**Before → After**:
- 🔴 EC2 2台の常時運用（パッチ適用、エージェント更新、月額~$66） → 🟢 ゼロ運用のサーバーレスパイプライン（月額~$6、従量課金）
- 🔴 監査ログが FSx ボリューム内に閉じている → 🟢 既存 SIEM/Observability で即座に検索・アラート可能
- 🔴 ランサムウェア検知から対応開始まで数時間 → 🟢 EMS/FPolicy 経由で30秒以内にアラート発報

**Measurable outcomes**:
- EC2 コレクター運用の削減（パッチ適用、エージェント管理不要）
- Observability ベンダー間で監査ログ配送を標準化
- ファイルアクセス行動の可視性向上
- ONTAP ネイティブテレメトリを活用した迅速なセキュリティ対応

## Partner Positioning / パートナー向け

本プロジェクトは、EC2 ベースの FSx for ONTAP 監査ログコレクターを、EC2 不要かつベンダーニュートラルな Observability パイプラインへモダナイズするためのパターンを提供します。

想定されるお客様シナリオ:
- EC2 上の Splunk Universal Forwarder の置き換え
- エンタープライズファイル共有の監査可視性モダナイゼーション（部門ファイルサーバー、SAP/Oracle/SQL Server 連携ディレクトリ、VDI/EUC ホームディレクトリ、設計・開発リポジトリ）
- FSx for ONTAP と既存 SIEM / Observability プラットフォームの統合
- ONTAP テレメトリを活用したランサムウェア検知ワークフローの準備

## Try with Sample Data / サンプルデータで試す

If you do not have FSx for ONTAP audit logs yet, use the sample payloads under `examples/` to validate parsing, formatting, and backend delivery:

```bash
# Generate Splunk HEC test payload
bash scripts/generate-splunk-hec-payload.sh --count 5

# Generate OTLP test payload
bash scripts/generate-otlp-payload.sh --count 5
```

See [`examples/`](examples/) for pre-built sample audit, EMS, and FPolicy event payloads.

## Quick Start / クイックスタート

```bash
# 1. リポジトリクローン
git clone https://github.com/Yoshiki0705/fsxn-observability-integrations.git
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

## Quick Validation / 動作確認手順

ベンダー統合スタックのデプロイ後、以下のコマンドで動作確認できます:

```bash
# 1. Scheduler が Lambda を呼び出していることを確認
aws logs filter-log-events \
  --log-group-name /aws/lambda/fsxn-datadog-integration-shipper \
  --start-time $(python3 -c "import time; print(int((time.time()-300)*1000))") \
  --region ap-northeast-1

# 2. DLQ が空であることを確認（失敗イベントなし）
aws sqs get-queue-attributes \
  --queue-url <dlq-url> \
  --attribute-names All \
  --query 'Attributes.ApproximateNumberOfMessages'

# 3. Observability プラットフォームで検索
#    Datadog: source:fsxn
#    Splunk:  index=fsxn_audit
#    Grafana: {source="fsxn"}
```

## Production Readiness Levels / 本番準備レベル

### Level 0: Local Validation
- Sample payload parsing and unit tests
- OTLP / HEC payload snapshot tests

### Level 1: Quickstart
- Single audit poller with SSM checkpoint
- EventBridge Scheduler + DLQ
- Direct vendor delivery

### Level 2: Operational PoC
- Dashboard and alerts configured
- Replay runbook documented
- Cost estimate produced
- Webhook security enabled

### Level 3: Production Baseline
- DynamoDB object ledger
- SQS buffering
- Poison-pill handling
- Pipeline SLO monitoring
- Security review completed

### Level 4: Enterprise Pipeline
- OTel Collector or Grafana Alloy
- Redaction and routing rules
- Multi-backend export
- Compliance evidence pack

## Teardown / スタック削除

```bash
# ベンダー統合スタックの削除
aws cloudformation delete-stack \
  --stack-name fsxn-datadog-integration \
  --region ap-northeast-1

# 前提条件スタックの削除（他のベンダースタックが依存していない場合のみ）
aws cloudformation delete-stack \
  --stack-name fsxn-observability-prerequisites \
  --region ap-northeast-1

# ONTAP 監査ログは引き続き有効 — 必要に応じて別途無効化:
# vserver audit disable -vserver <svm-name>
```

> **注意**: スタックを削除しても、ONTAP の監査ログ設定や FSx ボリューム上の既存データには影響しません。監査ログは引き続き audit volume に書き込まれます。

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
- [配信保証パターン (日本語)](docs/ja/delivery-guarantees.md)
- [Delivery Guarantee Patterns (English)](docs/en/delivery-guarantees.md)
- [Webhook セキュリティガイド (English)](docs/en/webhook-security.md)
- [ガバナンス・コンプライアンス (日本語)](docs/ja/governance-and-compliance.md)
- [Governance & Compliance (English)](docs/en/governance-and-compliance.md)
- [セキュリティレビューチェックリスト (日本語)](docs/ja/security-review-checklist.md)
- [Security Review Checklist (English)](docs/en/security-review-checklist.md)
- [PoC 成功基準 (日本語)](docs/ja/poc-success-criteria.md)
- [PoC Success Criteria (English)](docs/en/poc-success-criteria.md)
- [Pipeline SLO Definitions (English)](docs/en/pipeline-slo.md)
- [Data Classification Guide (English)](docs/en/data-classification.md)
- [DLQ Replay Runbook (English)](docs/en/runbooks/dlq-replay.md)
- [Partner Solution Brief (English)](docs/en/partner-solution-brief.md)
- [Retention Policy Matrix (English)](docs/en/retention-policy-matrix.md)
- [Partner FAQ (English)](docs/en/partner-faq.md)
- [Workshop Hands-On Guide — Half Day (English)](docs/en/workshop-hands-on-half-day.md)
- [DLQ Replay Runbook (English)](docs/en/runbooks/dlq-replay.md)
- [Lambda Errors Runbook (English)](docs/en/runbooks/lambda-errors.md)
- [Checkpoint Staleness Runbook (English)](docs/en/runbooks/checkpoint-stale.md)
- [PoC Proposal Template (English)](docs/en/poc-proposal-template.md)
- [Workshop Agenda (English)](docs/en/workshop-agenda.md)
- [Data Residency Matrix (English)](docs/en/data-residency.md)
- [Multi-Account Deployment (English)](docs/en/multi-account-deployment.md)
- [Cross-Region Replication (English)](docs/en/cross-region-replication.md)
- [Compliance Evidence Pack (English)](docs/en/compliance-evidence-pack.md)
- [Security Best Practices (English)](docs/en/security-best-practices.md)

## Tech Stack / 技術スタック

- **Infrastructure**: CloudFormation (YAML) + CDK (TypeScript)
- **Lambda**: Python 3.12 (ログ処理) + TypeScript (API連携)
- **Test**: Jest + pytest
- **CI/CD**: GitHub Actions
- **Docs**: Markdown (日英バイリンガル)

## License

MIT

## Roadmap

See [ROADMAP.md](ROADMAP.md) for planned features, Phase 2-4 milestones, and blog series plan.
