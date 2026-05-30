# FSx for ONTAP Observability Integrations

🌐 **日本語**（このページ） | [English](../en/README.md)

---

## 概要

Amazon FSx for NetApp ONTAP の監査ログ・メトリクスを、**FSx for ONTAP S3 Access Points** 経由で各 Observability ベンダーへ **EC2 不要**で配信するパターン集です。

## アーキテクチャパターン

```
FSx for ONTAP → 監査ログ有効化 → audit volume に出力
audit volume → FSx for ONTAP S3 Access Point で S3 API アクセス
EventBridge Scheduler → Lambda → ベンダー固有 API エンドポイントへ配信

EMS: ONTAP → Webhook → API Gateway → Lambda → ベンダー API
FPolicy: ONTAP → TCP:9898 → ECS Fargate → SQS → Lambda → ベンダー API
```

## 対応ベンダー

| ベンダー | ステータス | 説明 |
|--------|--------|-------------|
| [Datadog](../../integrations/datadog/) | ✅ E2E 検証済み | Logs API v2 via Lambda |
| [New Relic](../../integrations/new-relic/) | ✅ E2E 検証済み | Log API v1 via Lambda |
| [Splunk (Serverless)](../../integrations/splunk-serverless/) | ✅ E2E 検証済み | HEC via Lambda (EC2 パターン置き換え) |
| [OTel Collector](../../integrations/otel-collector/) | ✅ E2E 検証済み | ベンダーニュートラル OTLP/HTTP (Datadog + Grafana + Honeycomb) |
| [Grafana Cloud](../../integrations/grafana/) | ✅ E2E 検証済み | OTLP Gateway via Lambda (Loki Push API フォールバック) |
| [Elastic](../../integrations/elastic/) | ✅ E2E 検証済み | Elasticsearch Bulk API |
| [Dynatrace](../../integrations/dynatrace/) | ✅ E2E 検証済み | Log Ingest API v2 |
| [Sumo Logic](../../integrations/sumo-logic/) | ✅ E2E 検証済み | HTTP Source |
| [Honeycomb](../../integrations/honeycomb/) | ✅ E2E 検証済み | Events Batch API |

ステータス:
- ✅ **E2E 検証済み** — 実際の FSx for ONTAP 監査ログでデプロイ・検証完了

## 背景

既存の Splunk 統合ブログ ([AWS Blog](https://aws.amazon.com/jp/blogs/news/auditing-user-and-administrative-actions-on-amazon-fsx-for-netapp-ontap-using-splunk/)) は EC2 ベース（syslog-ng + Universal Forwarder）のアプローチです。

本プロジェクトでは、**EC2 不要**の代替パターンを提供します（Lambda + ECS Fargate を使用）。

## ビジネス価値

- EC2 コレクター運用の削減（パッチ適用、エージェント管理不要）
- Observability ベンダー間で監査ログ配送を標準化
- ファイルアクセス行動の可視性向上
- ONTAP ネイティブテレメトリを活用した迅速なセキュリティ対応

## パートナーポジショニング

本プロジェクトは、EC2 ベースの FSx for ONTAP 監査ログコレクターを EC2 不要のベンダーニュートラルな Observability パイプラインへモダナイズするパートナーを支援します。

一般的な顧客シナリオ:
- EC2 上の Splunk Universal Forwarder の置き換え
- エンタープライズファイル共有の監査可視性モダナイゼーション（部門ファイルサーバー、SAP/Oracle/SQL Server 隣接共有などのアプリケーションインターフェースディレクトリ、VDI/EUC ホームディレクトリ、エンジニアリング・設計リポジトリ）
- FSx for ONTAP と既存 SIEM / Observability プラットフォームの統合
- ONTAP テレメトリを活用したランサムウェア検知ワークフローの準備

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

# 4. FSx for ONTAP 監査ログ有効化（ドライラン）
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

## クイックバリデーション

ベンダー統合スタックのデプロイ後:

```bash
# 1. Scheduler が Lambda を起動していることを確認
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

## テアダウン

```bash
# ベンダー統合スタックの削除
aws cloudformation delete-stack \
  --stack-name fsxn-datadog-integration \
  --region ap-northeast-1

# 前提条件スタックの削除（他のベンダースタックが依存していない場合）
aws cloudformation delete-stack \
  --stack-name fsxn-observability-prerequisites \
  --region ap-northeast-1

# ONTAP 監査ログは有効なまま残ります — 必要に応じて個別に無効化:
# vserver audit disable -vserver <svm-name>
```

> **注意**: スタックを削除しても、ONTAP 監査ログや FSx ボリューム上の既存データには影響しません。

## ドキュメント

### はじめに
- [前提条件・デプロイガイド](prerequisites.md)
- [最小テストパス](quick-start-minimum.md)
- [ONTAP 監査設定ガイド](ontap-audit-setup.md)

### アーキテクチャ・設計
- [アーキテクチャ](architecture.md)
- [イベントソースガイド](event-sources.md)
- [S3 AP 仕様・制約・トラブルシューティング](s3ap-fsxn-specification.md)
- [正規化イベントスキーマ](normalized-event-schema.md)
- [配信保証パターン](delivery-guarantees.md)

### 運用・本番
- [パイプライン SLO 定義](../en/pipeline-slo.md)
- [運用ガイド](operational-guide.md)
- [DLQ リプレイ Runbook](../en/runbooks/dlq-replay.md)
- [Lambda エラー Runbook](../en/runbooks/lambda-errors.md)
- [チェックポイント停滞 Runbook](../en/runbooks/checkpoint-stale.md)
- [S3 AP スループットベンチマーク](../en/s3ap-throughput-benchmark.md)
- [コスト検証テンプレート](../en/cost-validation.md)

### セキュリティ・コンプライアンス
- [データ分類ガイド](../en/data-classification.md)
- [保持期間要件マトリクス](../en/retention-policy-matrix.md)
- [コンプライアンスエビデンスパック](../en/compliance-evidence-pack.md)
- [セキュリティレビューチェックリスト](../en/security-review-checklist.md)
- [Webhook セキュリティガイド](../en/webhook-security.md)
- [データレジデンシーマトリクス](../en/data-residency.md)
- [ガバナンス・コンプライアンス](governance-and-compliance.md)

### エンタープライズ・スケール
- [マルチアカウントデプロイ (StackSets)](../en/multi-account-deployment.md)
- [クロスリージョンレプリケーション (DR)](../en/cross-region-replication.md)
- [OTel Collector PII リダクション Cookbook](../../integrations/otel-collector/docs/en/pii-redaction-cookbook.md)

### パートナー・ワークショップ
- [ベンダー比較](vendor-comparison.md)
- [パートナー FAQ](../en/partner-faq.md)
- [Partner Solution Brief](../en/partner-solution-brief.md)
- [PoC 提案テンプレート](../en/poc-proposal-template.md)
- [PoC 成功基準](../en/poc-success-criteria.md)
- [Workshop ハンズオンガイド（半日版）](../en/workshop-hands-on-half-day.md)
- [Workshop アジェンダ](../en/workshop-agenda.md)
- [デモシナリオ](demo-scenarios.md)
- [検知ユースケース](detection-use-cases.md)

## 技術スタック

- **Infrastructure**: CloudFormation (YAML) + CDK (TypeScript)
- **Lambda**: Python 3.12 (ログ処理) + TypeScript (API連携)
- **Test**: Jest + pytest
- **CI/CD**: GitHub Actions
- **Docs**: Markdown (日英バイリンガル)

## 関連プロジェクト

| リポジトリ | 説明 |
|-----------|------|
| [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns) | FPolicy イベント駆動パイプライン、キャパシティガードレール等 17 業界ユースケース |
| [fsxn-lakehouse-integrations](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations) | S3 Access Points 経由の Data Lake / Lakehouse プラットフォーム統合 |
| [FSx-for-ONTAP-Agentic-Access-Aware-RAG](https://github.com/Yoshiki0705/FSx-for-ONTAP-Agentic-Access-Aware-RAG) | Amazon Bedrock を使ったアクセス制御対応 Agentic RAG（CDK） |
| [fsx-ontap-lifecycle-management](https://github.com/Yoshiki0705/fsx-ontap-lifecycle-management) | S3 Glacier Deep Archive 連携の 3 階層ライフサイクル管理 |

## License

MIT
