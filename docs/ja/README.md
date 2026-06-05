# FSx for ONTAP Observability Integrations

🌐 **日本語**（このページ） | [English](../en/README.md)

> 本リポジトリはコミュニティベースのリファレンス実装であり、AWS 公式サービス機能や準拠性を保証するものではありません。設定、コスト、コンプライアンス要件は各自の環境で検証してください。

---

## 概要

Amazon FSx for NetApp ONTAP の監査ログ・EMS イベント・FPolicy ファイル操作を、**FSx for ONTAP S3 Access Points** 経由で 9 つの Observability ベンダーへ **EC2 不要**で配信するパターン集です。

## パス選択ガイド

| 目的 | 推奨パス | 理由 |
|------|---------|------|
| 初回検証 | 監査ポーラーのみ | 読み取り→配信→チェックポイント→DLQ の最速検証 |
| GUI ベース管理 | NetApp Console + System Manager | CLI 不要。監査、クォータ、FSA 全て GUI で操作可能 |
| 単一 Observability バックエンド | ベンダー直接統合 | 構成要素が少なくシンプル |
| Grafana Cloud クイックスタート | OTLP Gateway 直接 | Loki へのネイティブ OTLP パス |
| マルチバックエンド / リダクション / ルーティング | OTel Collector or Grafana Alloy | パイプラインの横断的関心事を Lambda から分離 |
| 高信頼性 | SQS + DynamoDB ledger + Collector/Alloy | バックプレッシャー、リプレイ、バッチ処理、永続状態 |
| パートナー PoC | Partner Solution Brief + PoC チェックリスト | スコープ、成果物、責任分界の明確化 |

## 最初の 30 分

1. 上記「パス選択ガイド」でターゲット統合を特定
2. サンプルペイロードでユニットテスト実行: `python -m pytest integrations/datadog/tests/ -v`
3. [PoC 成功基準](../en/poc-success-criteria.md) を確認
4. サンドボックスアカウントで監査ポーラーのみデプロイ（下記クイックスタート参照）
5. 確認: 1 件のログレコード到着、チェックポイント前進、DLQ 空

## アーキテクチャパターン

```
FSx for ONTAP → 監査ログ有効化 → audit volume に出力
audit volume → FSx for ONTAP S3 Access Point で S3 API アクセス
EventBridge Scheduler → Lambda → ベンダー固有 API エンドポイントへ配信

EMS: ONTAP → Webhook → API Gateway → Lambda → ベンダー API
FPolicy: ONTAP → TCP:9898 → ECS Fargate → SQS → Lambda → ベンダー API
```

### トリガーモデルに関する注意

FSx for ONTAP S3 Access Points は **S3 Event Notifications および EventBridge オブジェクトレベルイベントをサポートしていません**。本プロジェクトでは:

- **EventBridge Scheduler ポーリング**: 定期的に Lambda を起動し、SSM Parameter Store にチェックポイントを保存して処理済みファイルを追跡
- **CloudTrail データイベント**: ニアリアルタイムトリガーの代替手段として文書化
- **通常の S3 バケット + S3 Event Notifications**: テストデータのバリデーション用途

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
| [CrowdStrike Falcon LogScale](../../integrations/crowdstrike/) | 🧪 実装準備完了 | HEC via Lambda (Splunk HEC 互換) |
| [NetApp Console / System Manager](../../integrations/netapp-console/) | ✅ 検証済み | GUI 管理 + FSA (File System Analytics) |

ステータス:
- ✅ **E2E 検証済み** — 実際の FSx for ONTAP 監査ログでデプロイ・検証完了

## 背景

既存の Splunk 統合ブログ ([AWS Blog](https://aws.amazon.com/jp/blogs/news/auditing-user-and-administrative-actions-on-amazon-fsx-for-netapp-ontap-using-splunk/)) は EC2 ベース（syslog-ng + Universal Forwarder）のアプローチです。

本プロジェクトでは、**EC2 不要**の代替パターンを提供します（Lambda + ECS Fargate を使用）。

## ビジネス価値

**Before → After**:
- 🔴 EC2 2台の常時運用（パッチ適用、エージェント更新、月額~$66） → 🟢 ゼロ運用のサーバーレスパイプライン（月額~$6、従量課金）
- 🔴 監査ログが FSx ボリューム内に閉じている → 🟢 既存 SIEM/Observability で即座に検索・アラート可能
- 🔴 ランサムウェア検知から対応開始まで数時間 → 🟢 EMS/FPolicy 経由で30秒以内にアラート発報

**定量的成果**:
- EC2 コレクター運用の削減（パッチ適用、エージェント管理不要）
- Observability ベンダー間で監査ログ配送を標準化
- ファイルアクセス行動の可視性向上
- ONTAP ネイティブテレメトリを活用した迅速なセキュリティ対応

## パートナーポジショニング

本プロジェクトは、EC2 ベースの FSx for ONTAP 監査ログコレクターを EC2 不要のベンダーニュートラルな Observability パイプラインへモダナイズするパートナーを支援します。

一般的な顧客シナリオ:
- EC2 上の Splunk Universal Forwarder の置き換え
- エンタープライズファイル共有の監査可視性モダナイゼーション
- FSx for ONTAP と既存 SIEM / Observability プラットフォームの統合
- ONTAP テレメトリを活用したランサムウェア検知ワークフローの準備

## サンプルデータで試す

FSx for ONTAP 監査ログがまだない場合、`examples/` のサンプルペイロードでパース・フォーマット・配信を検証できます:

```bash
bash scripts/generate-splunk-hec-payload.sh --count 5
bash scripts/generate-otlp-payload.sh --count 5
```

[`examples/`](../../examples/) にプリビルトの監査・EMS・FPolicy イベントペイロードがあります。

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

## 本番準備レベル

### Level 0: ローカルバリデーション
- サンプルペイロードのパースとユニットテスト
- OTLP / HEC ペイロードスナップショットテスト

### Level 1: クイックスタート
- SSM チェックポイント付き単一監査ポーラー
- EventBridge Scheduler + DLQ
- ベンダー直接配信

### Level 2: 運用 PoC
- ダッシュボードとアラート設定済み
- リプレイ Runbook 文書化済み
- コスト見積もり作成済み
- Webhook セキュリティ有効化

### Level 3: 本番ベースライン
- DynamoDB オブジェクトレジャー
- SQS バッファリング
- ポイズンピル処理
- パイプライン SLO 監視
- セキュリティレビュー完了

### Level 4: エンタープライズパイプライン
- OTel Collector or Grafana Alloy
- リダクション・ルーティングルール
- マルチバックエンドエクスポート
- コンプライアンスエビデンスパック

## テアダウン

```bash
aws cloudformation delete-stack --stack-name fsxn-datadog-integration --region ap-northeast-1
aws cloudformation delete-stack --stack-name fsxn-observability-prerequisites --region ap-northeast-1
# ONTAP 監査ログは有効なまま残ります — 必要に応じて個別に無効化:
# vserver audit disable -vserver <svm-name>
```

> **注意**: スタックを削除しても、ONTAP 監査ログや FSx ボリューム上の既存データには影響しません。

## GUI 管理（NetApp Console / System Manager）

ONTAP System Manager は NetApp Console 経由でブラウザからアクセスでき、CLI 不要で以下の操作が可能です:

- 監査ログ設定・管理
- Qtree クォータ（容量制限）の設定
- File System Analytics (FSA) — ファイルアクセス傾向の可視化
- Activity Tracking — リアルタイムファイル操作監視
- ボリューム・共有フォルダの管理

> **アクセス方法**: [NetApp Console](https://console.netapp.com/) → Systems → SERVICES → "Open" (System Manager)
>
> **コスト**: NetApp Console Link (Lambda) 約 $0.008/月。System Manager 自体は無料。

📖 [管理・監視 Decision Tree](decision-tree-management-monitoring.md)

📖 [System Manager GUI ガイド](system-manager-gui-guide.md)

📖 [NetApp Console Integration](../../integrations/netapp-console/)

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
- [管理・監視 Decision Tree](decision-tree-management-monitoring.md)
- [System Manager GUI ガイド](system-manager-gui-guide.md)

### 運用・本番
- [パイプライン SLO 定義](../en/pipeline-slo.md)
- [運用ガイド](operational-guide.md)
- [DLQ リプレイ Runbook](../en/runbooks/dlq-replay.md)
- [Lambda エラー Runbook](../en/runbooks/lambda-errors.md)
- [チェックポイント停滞 Runbook](../en/runbooks/checkpoint-stale.md)
- [S3 AP スループットベンチマーク](../en/s3ap-throughput-benchmark.md)
- [コスト検証テンプレート](../en/cost-validation.md)

> 📝 上記の `../en/` リンクは英語版ドキュメントです。技術的な内容のため英語のまま提供しています。

### セキュリティ・コンプライアンス
- [データ分類ガイド](../en/data-classification.md)
- [保持期間要件マトリクス](../en/retention-policy-matrix.md)
- [コンプライアンスエビデンスパック](../en/compliance-evidence-pack.md)
- [セキュリティレビューチェックリスト](security-review-checklist.md)
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
- [Partner Solution Brief](partner-solution-brief.md)
- [PoC 提案テンプレート](../en/poc-proposal-template.md)
- [PoC 成功基準](poc-success-criteria.md)
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
