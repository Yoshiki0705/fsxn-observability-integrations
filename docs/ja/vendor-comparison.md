# ベンダー比較

## 対応ベンダー一覧

| ベンダー | 配信方式 | 認証方式 | バッチサイズ上限 | Firehose対応 |
|---------|---------|---------|---------------|-------------|
| Datadog | Logs API v2 | API Key (Header) | 5MB/リクエスト | ✅ |
| New Relic | Log API | License Key (Header) | 1MB/リクエスト | ✅ |
| Grafana Cloud | OTLP Gateway | Basic Auth | 制限なし (推奨4MB) | ❌ |
| Splunk | HEC | HEC Token (Header) | 制限なし | ✅ (組み込み) |
| Elastic | Bulk API | API Key / Basic Auth | 制限なし (推奨10MB) | ❌ |
| Dynatrace | Log Ingest API | API Token (Header) | 1MB/リクエスト | ✅ |
| Sumo Logic | HTTP Source | URL内蔵 | 1MB/リクエスト | ❌ |
| Honeycomb | Events API | API Key (Header) | 5MB/リクエスト | ❌ |
| OTel Collector | OTLP/HTTP | 設定依存 | 設定依存 | ❌ |

## コスト比較

**Observability プラットフォーム側の取り込みコスト**推定値（AWS インフラコスト ~$5-50/月は別途）:

| ベンダー | 無料枠 | 1 GB/月 | 10 GB/月 | 100 GB/月 | 課金モデル |
|---------|--------|---------|----------|-----------|-----------|
| New Relic | 100 GB/月 | $0 | $0 | $0 | 無料枠超過分 $0.35/GB |
| Grafana Cloud | 50 GB/月 | $0 | $0 | ~$40 | 無料枠超過分 $0.50/GB |
| Sumo Logic | 500 MB/日 (~15 GB/月) | $0 | $0 | ~$300 | 日次取り込み量ベース |
| Honeycomb | 2000万イベント/月 | $0 | $0 | ~$100 | イベント数ベース |
| Datadog | なし（トライアルのみ） | ~$10 | ~$100 | ~$1,000 | $0.10/GB 取り込み + 保持 |
| Splunk | なし（ライセンスベース） | ライセンス依存 | ライセンス依存 | ライセンス依存 | 日次インデックス量ライセンス |
| Dynatrace | なし（DDUベース） | ~1 DDU/日 | ~10 DDU/日 | ~100 DDU/日 | Davis Data Units |
| Elastic Cloud | 14日間トライアル | ~$30 (最小構成) | ~$95 | ~$300+ | ストレージ + コンピュート |
| OTel Collector | N/A (セルフホスト) | $0 (インフラのみ) | $0 (インフラのみ) | $0 (インフラのみ) | バックエンドコストのみ |

> **注意**: 価格は概算であり、リージョン、契約形態、コミットメントにより変動します。最新の価格は各ベンダーの料金ページで確認してください。AWS インフラコスト（Lambda, EventBridge, S3, Secrets Manager）は通常 $5-50/月です。

### AWS インフラコスト推定

| コンポーネント | 1 GB/月 | 10 GB/月 | 100 GB/月 |
|--------------|---------|----------|-----------|
| Lambda (256MB, 5分間隔) | ~$1 | ~$5 | ~$30 |
| EventBridge Scheduler | ~$0.01 | ~$0.01 | ~$0.01 |
| Secrets Manager | ~$0.40 | ~$0.40 | ~$0.40 |
| CloudWatch Logs | ~$0.50 | ~$2 | ~$10 |
| SQS (DLQ) | ~$0 | ~$0 | ~$0 |
| **合計 AWS** | **~$2** | **~$8** | **~$41** |

## 選定ガイド

### コスト重視
- **New Relic**: 最も寛大な無料枠（100 GB/月）
- **Grafana Cloud**: 良好な無料枠（50 GB/月）+ OSS エコシステム
- **Sumo Logic**: 無料枠あり（500 MB/日）
- **Elastic**: セルフホスト可能（取り込みコストなし）

### 既存環境との統合
- **Datadog**: 既に Datadog を APM/インフラ監視で使用している場合
- **Splunk**: 既存 Splunk 環境がある場合（EC2 UF からのサーバーレス移行）
- **Dynatrace**: AI 駆動の根本原因分析と APM 相関が必要な場合

### ベンダーロックイン回避
- **OTel Collector**: ベンダー中立、コード変更なしでバックエンド切り替え可能
- **Grafana Cloud**: OSS ベースのスタック（Loki, Grafana）
- **Honeycomb**: OTel Collector 経由で強力

### エンタープライズ / コンプライアンス
- **Splunk**: 確立された SIEM、コンプライアンスレポート
- **CrowdStrike Falcon LogScale**: 次世代 SIEM、Falcon XDR エコシステムと統合
- **Elastic**: セルフホストによるデータ主権確保
- **Datadog**: SOC 2, HIPAA, FedRAMP オプション

## アーキテクチャパターン比較

### パターン A: Lambda 直接配信
```
S3 AP → EventBridge → Lambda → Vendor API
```
- ✅ シンプル、低コスト（少量ログ向け）
- ❌ 大量ログ時にスロットリングリスク
- ❌ バックエンドごとにベンダー固有コードが必要

### パターン B: Firehose 経由
```
S3 AP → Lambda (変換) → Firehose → Vendor API
```
- ✅ 自動バッファリング、高スループット
- ✅ 組み込みリトライとバックプレッシャー
- ❌ Firehose 対応ベンダーのみ（Datadog, Splunk, New Relic, Dynatrace）
- ❌ 追加の Firehose コスト

### パターン C: OTel Collector 経由
```
S3 AP → Lambda (OTLP) → OTel Collector → 複数バックエンド
```
- ✅ ベンダー中立な Lambda コード（バックエンド間で変更不要）
- ✅ 単一パイプラインから複数バックエンドへのファンアウト
- ✅ Collector 設定でルーティング、フィルタリング、リダクション
- ❌ Collector インフラが必要（ECS Fargate 推奨）
- ❌ 運用の複雑さが増加
