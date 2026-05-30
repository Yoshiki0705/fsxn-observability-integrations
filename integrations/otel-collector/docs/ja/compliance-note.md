# コンプライアンス証跡ノート: OTel Collector

## Collector は配信レイヤー（証跡の権威ではない）

> **重要な区別**: OTel Collector は**配信およびルーティングレイヤー**であり、コンプライアンス証跡の権威ある情報源ではない。S3 に保存された生の監査ログ（EVTX/XML）が唯一の真実の情報源である。

```
┌─────────────────────────────────────────────────────────────────┐
│  Evidence Authority (Source of Truth)                             │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  S3 Bucket: Raw EVTX/XML audit logs                     │    │
│  │  - Immutable (versioning + Object Lock)                  │    │
│  │  - Complete (no filtering applied)                       │    │
│  │  - Timestamped by FSx for ONTAP                             │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Distribution Layer (OTel Collector)                              │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  - Normalized OTLP logs (search/alerting copies)         │    │
│  │  - May be filtered, sampled, or redacted                 │    │
│  │  - NOT suitable as sole compliance evidence              │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## コンプライアンスのための生 EVTX/XML 保持

### 保持要件

| 規制 | 最低保持期間 | フォーマット | 備考 |
|------|-------------|------------|------|
| SOX (J-SOX) | 7 年 | オリジナル形式 | 財務システムアクセスログ |
| PCI DSS | 1 年（3 ヶ月オンライン） | オリジナル形式 | カード会員データアクセス |
| GDPR | 目的に必要な期間 | オリジナル形式 | 消去権が適用 |
| HIPAA | 6 年 | オリジナル形式 | PHI アクセスログ |
| 社内ポリシー | 組織ごと | オリジナル形式 | 通常 3-7 年 |

### S3 保持設定

```yaml
# CloudFormation: Audit log bucket with compliance retention
AuditLogBucket:
  Type: AWS::S3::Bucket
  Properties:
    BucketName: !Sub fsxn-audit-logs-${AWS::AccountId}
    VersioningConfiguration:
      Status: Enabled
    ObjectLockEnabled: true
    ObjectLockConfiguration:
      ObjectLockEnabled: Enabled
      Rule:
        DefaultRetention:
          Mode: COMPLIANCE
          Years: 7
    LifecycleConfiguration:
      Rules:
        - Id: TransitionToGlacier
          Status: Enabled
          Transitions:
            - StorageClass: GLACIER
              TransitionInDays: 90
        - Id: TransitionToDeepArchive
          Status: Enabled
          Transitions:
            - StorageClass: DEEP_ARCHIVE
              TransitionInDays: 365
```

## 正規化 OTLP ログは検索/アラート用コピー

Collector は以下の目的で正規化されたコピーを Observability バックエンドに配信:

| 目的 | バックエンド | 保持期間 | 完全性 |
|------|------------|---------|--------|
| リアルタイムアラート | Grafana / Datadog | 30 日 | フィルタリングされる可能性あり |
| セキュリティ調査 | SIEM | 1 年 | セキュリティイベントのみ |
| 運用検索 | Honeycomb | 60 日 | サンプリングされる可能性あり |
| トレンド分析 | 任意 | 90 日 | 集約される可能性あり |

**これらのコピーはコンプライアンス証跡ではない。** 運用ツールである。

## 重複/欠落イベントの処理

### 潜在的原因

| 問題 | 原因 | 検出方法 | 緩和策 |
|------|------|---------|--------|
| 重複イベント | タイムアウト時の Lambda リトライ | event_id 重複排除 | 冪等処理 |
| 欠落イベント | Collector 障害 | イベント数比較 | DLQ + 再処理 |
| 遅延イベント | バックプレッシャー / キュー満杯 | タイムスタンプドリフト監視 | キューサイズアラート |
| 順序逆転イベント | 並列処理 | シーケンス番号ギャップ | バックエンドで受容 |

### イベント数照合

```bash
# Compare S3 source count vs backend received count
# Source: Count objects in S3 for date range
aws s3api list-objects-v2 \
  --bucket <audit-bucket> \
  --prefix "audit/svm-prod/2026/01/" \
  --query "Contents[].Key" | jq length

# Backend: Query event count for same date range
# (vendor-specific query)
```

### 照合ポリシー

- **日次**: 自動カウント比較（S3 オブジェクト vs バックエンドイベント）
- **週次**: 1% を超える不一致の手動レビュー
- **月次**: コンプライアンスチーム向け完全照合レポート
- **オンデマンド**: Collector 障害または設定変更後

## バックエンド別保持ポリシー

| バックエンド | 保持期間 | データ範囲 | 削除ポリシー |
|------------|---------|-----------|-------------|
| S3 (生データ) | 7 年 | 全イベント、オリジナル形式 | Object Lock COMPLIANCE モード |
| Security SIEM | 1 年 | セキュリティイベントのみ | 自動期限切れ |
| Grafana Cloud | 30 日 | 全イベント（正規化） | 自動期限切れ |
| Honeycomb | 60 日 | 全イベント（正規化） | 自動期限切れ |
| Datadog | 15 日（デフォルト） | 全イベント（正規化） | 自動期限切れ |

## ルーティング設定変更履歴

すべてのルーティング変更は監査目的で追跡する必要がある:

### 必要なドキュメント

- **誰が** ルーティングを変更したか（git author）
- **いつ** 変更が行われたか（git timestamp）
- **何を** 変更したか（diff）
- **なぜ** 変更したか（PR 説明）
- **承認** （PR レビュアー）

### 監査クエリ

```bash
# Full history of routing changes
git log --format="%H %ai %an %s" -- \
  'integrations/otel-collector/otel-collector-config*.yaml' \
  > routing-change-audit.log
```

## 証跡の連鎖（Chain of Custody）の考慮事項

### データフロードキュメント

```
1. FSx for ONTAP generates audit event
   → Timestamp: ONTAP system clock (NTP synced)
   → Format: EVTX or XML

2. Audit log written to S3 bucket
   → S3 object metadata: upload timestamp
   → Object Lock: immutable for retention period
   → Versioning: prevents overwrite

3. Lambda reads from S3 Access Point
   → CloudTrail: GetObject logged
   → Lambda: processing timestamp logged

4. Lambda sends OTLP to Collector
   → Network: TLS encrypted in transit
   → Collector: received timestamp in internal metrics

5. Collector exports to backends
   → Per-exporter: sent timestamp
   → Backend: ingestion timestamp
```

### 整合性検証

| レイヤー | 検証方法 | 頻度 |
|---------|---------|------|
| S3 ストレージ | Object Lock + バージョニング | 継続的 |
| S3 アクセス | CloudTrail 監査 | 継続的 |
| Lambda 処理 | CloudWatch Logs | 呼び出しごと |
| Collector 配信 | 内部メトリクス | 継続的 |
| バックエンド受信 | バックエンド監査ログ | イベントごと |

## アーカイブパス設計

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│ S3 (Standard)│────▶│ S3 (Glacier) │────▶│ S3 (Deep Archive)│
│  0-90 days   │     │  90-365 days │     │  365+ days       │
│  Online      │     │  5-12h restore│    │  12-48h restore  │
└──────────────┘     └──────────────┘     └──────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│  OTel Collector (copies for operational use)                   │
│  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────────────────┐ │
│  │ SIEM   │  │Grafana │  │Honeycomb│  │ Archive (S3 copy) │ │
│  │ 1 year │  │ 30 days│  │ 60 days│  │ 7 years (filtered)│ │
│  └────────┘  └────────┘  └────────┘  └────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### 主要原則

1. **生ログが権威** — バックエンドの保持期間に基づいて生の S3 ログを削除しない
2. **Collector コピーは運用用** — フィルタリング、サンプリング、期限切れは許容
3. **ソースでの不変性** — Object Lock が改ざんを防止
4. **復元能力** — Glacier/Deep Archive データは SLA 内で取得可能
5. **関心の分離** — コンプライアンスチームが S3 保持を所有; プラットフォームチームが Collector ルーティングを所有
