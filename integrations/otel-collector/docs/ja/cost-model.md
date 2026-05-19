# コストモデル: OTel Collector 統合

## コスト計算式

```
Monthly Cost = event_volume × destination_count × retention_policy
             + infrastructure_cost (Lambda + Collector + Network)
```

## コストドライバー

| ドライバー | コンポーネント | スケーリング要因 |
|-----------|---------------|-----------------|
| Lambda 実行 | 呼び出し回数 + 実行時間 | イベント量 |
| Collector コンピュート | ECS Fargate (vCPU + メモリ) | スループット |
| NAT Gateway | 時間課金 + GB 処理量 | エグレス量 |
| VPC Endpoints | 時間課金 + GB 処理量 | API コール量 |
| CloudWatch Logs | 取り込み + ストレージ | ログ詳細度 |
| バックエンド取り込み | GB あたり取り込み | イベント量 × 宛先数 |
| バックエンド保持 | GB あたり保存/日 | 保持期間 |
| データ転送 | クロス AZ + インターネットエグレス | イベント量 |

## サンプルイベントサイズ推定

| イベント種別 | 平均サイズ (JSON) | 平均サイズ (OTLP) | 備考 |
|-------------|-----------------|------------------|------|
| S3 Audit (単一) | ~1.5 KB | ~1.2 KB | ファイル操作イベント |
| EMS イベント | ~2.0 KB | ~1.6 KB | システムイベント |
| FPolicy イベント | ~1.0 KB | ~0.8 KB | ファイルアクセス通知 |
| バッチ (100 イベント) | ~150 KB | ~80 KB | OTLP バッチングがより効率的 |

## イベント量/日の例

| ボリューム層 | Events/Day | GB/Day (OTLP) | ユースケース |
|-------------|-----------|----------------|-------------|
| **Low** | 10,000 | ~0.01 GB | 開発/テスト環境、単一 SVM |
| **Medium** | 500,000 | ~0.5 GB | 本番、中程度のファイルアクティビティ |
| **High** | 5,000,000 | ~5 GB | 高アクティビティ本番、複数 SVM |
| **Very High** | 50,000,000 | ~50 GB | エンタープライズ、高負荷 NAS ワークロード |

## バックエンド取り込み GB/日 推定

```
ingest_gb_per_day = events_per_day × avg_event_size_bytes / (1024³)
                  × destination_count
```

| ボリューム | 1 バックエンド | 2 バックエンド | 3 バックエンド |
|-----------|--------------|--------------|--------------|
| Low (10K/day) | 0.01 GB | 0.02 GB | 0.03 GB |
| Medium (500K/day) | 0.5 GB | 1.0 GB | 1.5 GB |
| High (5M/day) | 5 GB | 10 GB | 15 GB |
| Very High (50M/day) | 50 GB | 100 GB | 150 GB |

## NAT Gateway vs VPC Endpoint コストトレードオフ

### NAT Gateway

| コンポーネント | コスト (ap-northeast-1) | 備考 |
|--------------|----------------------|------|
| 時間課金 | $0.062/hour (~$45/month) | NAT Gateway あたり |
| データ処理 | $0.062/GB | NAT 経由の全トラフィック |

### VPC Endpoint (Interface)

| コンポーネント | コスト (ap-northeast-1) | 備考 |
|--------------|----------------------|------|
| 時間課金 | $0.014/hour (~$10/month) | エンドポイントあたり AZ あたり |
| データ処理 | $0.01/GB | エンドポイント経由のトラフィック |

### 判断マトリクス

| シナリオ | 推奨 | 理由 |
|---------|------|------|
| < 100 GB/月 エグレス | NAT Gateway | シンプル、単一コンポーネント |
| > 100 GB/月 エグレス | VPC Endpoint | GB あたりコストが低い |
| 複数 AWS サービス | VPC Endpoints | サービスごとの分離 |
| バックエンドが AWS サービス | VPC Endpoint | インターネットエグレス不要 |
| バックエンドが外部 SaaS | NAT Gateway | インターネット到達が必要 |

## CloudWatch Logs 保持期間の影響

| 保持期間 | ストレージコスト/GB/月 | 30 日コスト (1 GB/日取り込み) |
|---------|----------------------|-------------------------------|
| 1 日 | $0.033 | $1.00 |
| 7 日 | $0.033 | $7.00 |
| 14 日 | $0.033 | $14.00 |
| 30 日 | $0.033 | $30.00 |
| 90 日 | $0.033 | $90.00 |
| 無期限 | $0.033 | 無限に増加 |

**推奨**: Lambda ログ保持期間を 14-30 日に設定。Collector ログ保持期間を 7-14 日に設定。

## ノイジーオペレーションフィルタリングによる節約

### フィルタリング前（全イベントを全バックエンドへ）

```
5M events/day × 3 backends × $0.50/GB ingest = $7.50/day = $225/month
```

### フィルタリング後（種別ごとにルーティング）

| イベント種別 | ボリューム | 宛先 | コスト |
|-------------|-----------|------|--------|
| セキュリティ (delete/perm) | 50K/day | SIEM + Grafana + Archive | $0.15/day |
| 読み取りイベント | 4M/day | Archive のみ (安価) | $0.40/day |
| その他の操作 | 950K/day | Grafana + Honeycomb | $1.90/day |

```
Total after filtering: $2.45/day = $73.50/month (67% savings)
```

## 大量読み取りイベント戦略

読み取りイベント（GetObject, ReadDir, ListDir）は通常、総イベント量の 60-80% を占めるが、セキュリティ価値は低い。

### オプション

| 戦略 | コスト影響 | データロス | ユースケース |
|------|-----------|-----------|-------------|
| 完全ドロップ | -80% ボリューム | あり | コンプライアンス不要環境 |
| サンプリング (1:100) | -79% ボリューム | 部分的 | トレンド分析で十分 |
| 安価ストレージへルーティング | -60% コスト | なし | コンプライアンスで保持必要 |
| 短い保持期間 (7d) | -50% コスト | 7 日後 | 運用トラブルシューティングのみ |

### 読み取りイベントルーティングの Collector 設定

```yaml
# Route read events to cheap storage, security events to SIEM
connectors:
  routing:
    default_pipelines: [logs/general]
    table:
      - statement: route() where attributes["fsxn.operation"] == "READ"
        pipelines: [logs/cheap]
      - statement: route() where attributes["fsxn.operation"] == "DELETE"
        pipelines: [logs/security]

service:
  pipelines:
    logs/input:
      receivers: [otlp]
      processors: [batch]
      exporters: [routing]
    logs/general:
      receivers: [routing]
      exporters: [otlp_http/grafana, otlp_http/honeycomb]
    logs/cheap:
      receivers: [routing]
      exporters: [otlp_http/archive]
    logs/security:
      receivers: [routing]
      exporters: [otlp_http/siem, otlp_http/grafana, otlp_http/archive]
```

## 月額コスト見積もりサマリー

### Low Volume (10K events/day, 1 バックエンド)

| コンポーネント | 月額コスト |
|--------------|-----------|
| Lambda (256MB, 500ms avg) | ~$0.50 |
| ECS Fargate (0.25 vCPU, 512MB) | ~$9.00 |
| NAT Gateway (hourly) | ~$45.00 |
| NAT Gateway (data, 0.3 GB) | ~$0.02 |
| CloudWatch Logs (14d retention) | ~$0.50 |
| Backend ingest (Grafana, 0.3 GB) | ~$1.50 |
| **合計** | **~$56.52** |

### Medium Volume (500K events/day, 2 バックエンド)

| コンポーネント | 月額コスト |
|--------------|-----------|
| Lambda (512MB, 800ms avg) | ~$15.00 |
| ECS Fargate (0.5 vCPU, 1GB) | ~$18.00 |
| NAT Gateway (hourly) | ~$45.00 |
| NAT Gateway (data, 30 GB) | ~$1.86 |
| CloudWatch Logs (14d retention) | ~$7.00 |
| Backend ingest (2×, 30 GB) | ~$150.00 |
| **合計** | **~$236.86** |

### High Volume (5M events/day, 3 バックエンド, フィルタリングあり)

| コンポーネント | 月額コスト |
|--------------|-----------|
| Lambda (1024MB, 1s avg) | ~$75.00 |
| ECS Fargate (1 vCPU, 2GB, 2 tasks) | ~$72.00 |
| NAT Gateway (hourly) | ~$45.00 |
| NAT Gateway (data, 150 GB) | ~$9.30 |
| CloudWatch Logs (7d retention) | ~$5.00 |
| Backend ingest (filtered, 73.5 GB) | ~$367.50 |
| **合計** | **~$573.80** |

> **注意**: バックエンド取り込みコストはベンダーにより大きく異なる。正確な見積もりはベンダーの料金ページを確認すること。上記の $5/GB は例示。
