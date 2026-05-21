# FSx for ONTAP Observability Integrations

🌐 **日本語**（このページ） | [English](../en/README.md)

---

## 概要

Amazon FSx for NetApp ONTAP の監査ログ・メトリクスを、**FSx for ONTAP S3 Access Points** 経由で各 Observability ベンダーへ **EC2 不要**で配信するパターン集です。

## アーキテクチャパターン

```
FSx ONTAP → 監査ログ有効化 → audit volume に出力
audit volume → FSx for ONTAP S3 Access Point で S3 API アクセス
EventBridge Scheduler → Lambda → ベンダー固有 API エンドポイントへ配信

EMS: ONTAP → Webhook → API Gateway → Lambda → ベンダー API
FPolicy: ONTAP → TCP:9898 → ECS Fargate → SQS → Lambda → ベンダー API
```

## 対応ベンダー

| ベンダー | ステータス | 説明 |
|--------|--------|-------------|
| [Datadog](../../integrations/datadog/) | ✅ E2E 検証済み | Logs API v2 via Lambda |
| [New Relic](../../integrations/new-relic/) | 🧪 実装済み | Log API v1 via Lambda |
| [Splunk (Serverless)](../../integrations/splunk-serverless/) | 🧪 実装済み | HEC via Lambda (EC2 パターン置き換え) |
| [OTel Collector](../../integrations/otel-collector/) | 🧪 実装済み | ベンダーニュートラル OTLP/HTTP |
| [Grafana Cloud](../../integrations/grafana/) | 🧪 実装済み | Loki Push API via Lambda |
| [Elastic](../../integrations/elastic/) | 🧪 実装済み | Elasticsearch Bulk API |
| [Dynatrace](../../integrations/dynatrace/) | 🧪 実装済み | Log Ingest API v2 |
| [Sumo Logic](../../integrations/sumo-logic/) | 🧪 実装済み | HTTP Source |
| [Honeycomb](../../integrations/honeycomb/) | 🧪 実装済み | Events Batch API |

ステータス:
- ✅ **E2E 検証済み** — 実際の FSx for ONTAP 監査ログでデプロイ・検証完了
- 🧪 **実装済み** — コードと CloudFormation あり。E2E 検証は未実施

## 背景

既存の Splunk 統合ブログ ([AWS Blog](https://aws.amazon.com/jp/blogs/news/auditing-user-and-administrative-actions-on-amazon-fsx-for-netapp-ontap-using-splunk/)) は EC2 ベース（syslog-ng + Universal Forwarder）のアプローチです。

本プロジェクトでは、**EC2 不要**の代替パターンを提供します（Lambda + ECS Fargate を使用）。

## ビジネス価値

- EC2 コレクター運用の削減（パッチ適用、エージェント管理不要）
- Observability ベンダー間で監査ログ配送を標準化
- ファイルアクセス行動の可視性向上
- ONTAP ネイティブテレメトリを活用した迅速なセキュリティ対応

## クイックスタート

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

> 📝 詳細な手順は [前提条件ガイド](prerequisites.md) を参照してください。

## ドキュメント

- [前提条件・デプロイガイド](prerequisites.md)
- [S3 AP 仕様・制約・トラブルシューティング](s3ap-fsxn-specification.md)
- [アーキテクチャ](architecture.md)
- [イベントソースガイド](event-sources.md)
- [ベンダー比較](vendor-comparison.md)
- [デモシナリオ](demo-scenarios.md)
- [運用ガイド](operational-guide.md)
- [ONTAP 監査設定ガイド](ontap-audit-setup.md)
- [最小テストパス](quick-start-minimum.md)
- [検知ユースケース](detection-use-cases.md)
- [正規化イベントスキーマ](normalized-event-schema.md)
- [配信保証パターン](delivery-guarantees.md)
- [Webhook セキュリティガイド](../en/webhook-security.md)

## 技術スタック

- **Infrastructure**: CloudFormation (YAML) + CDK (TypeScript)
- **Lambda**: Python 3.12 (ログ処理) + TypeScript (API連携)
- **Test**: Jest + pytest
- **CI/CD**: GitHub Actions
- **Docs**: Markdown (日英バイリンガル)

## License

MIT
