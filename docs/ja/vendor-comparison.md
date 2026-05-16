# ベンダー比較

## 対応ベンダー一覧

| ベンダー | 配信方式 | 認証方式 | バッチサイズ上限 | Firehose対応 |
|---------|---------|---------|---------------|-------------|
| Datadog | Logs API v2 | API Key (Header) | 5MB/リクエスト | ✅ |
| New Relic | Log API | License Key (Header) | 1MB/リクエスト | ✅ |
| Grafana Cloud | Loki Push API | Basic Auth | 制限なし (推奨4MB) | ❌ |
| Splunk | HEC | HEC Token (Header) | 制限なし | ✅ (組み込み) |
| Elastic | Bulk API | API Key / Basic Auth | 制限なし (推奨10MB) | ❌ |
| Dynatrace | Log Ingest API | API Token (Header) | 1MB/リクエスト | ✅ |
| Sumo Logic | HTTP Source | URL内蔵 | 1MB/リクエスト | ❌ |
| Honeycomb | Events API | API Key (Header) | 5MB/リクエスト | ❌ |
| OTel Collector | OTLP/HTTP | 設定依存 | 設定依存 | ❌ |

## 選定ガイド

### コスト重視
- **Sumo Logic**: 無料枠あり（500MB/日）
- **Grafana Cloud**: 無料枠あり（50GB/月）
- **Elastic**: セルフホスト可能

### 既存環境との統合
- **Datadog**: 既に Datadog を使用している場合
- **Splunk**: 既存 Splunk 環境がある場合（サーバーレス移行）
- **Dynatrace**: APM と統合したい場合

### ベンダーロックイン回避
- **OTel Collector**: ベンダー中立、将来の切り替えが容易
- **Grafana Cloud**: OSS ベースのスタック

## アーキテクチャパターン比較

### パターン A: Lambda 直接配信
```
S3 AP → EventBridge → Lambda → Vendor API
```
- ✅ シンプル、低コスト（少量ログ向け）
- ❌ 大量ログ時にスロットリングリスク

### パターン B: Firehose 経由
```
S3 AP → Lambda (変換) → Firehose → Vendor API
```
- ✅ 自動バッファリング、高スループット
- ❌ Firehose 対応ベンダーのみ、追加コスト
