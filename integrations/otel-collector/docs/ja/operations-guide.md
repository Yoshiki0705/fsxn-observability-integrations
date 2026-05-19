# OTel Collector 運用ガイド

## 最小限の Collector ヘルスチェック

本番 Collector デプロイメントでは、最低限以下のシグナルを監視する必要がある:

| チェック | 方法 | 正常状態 | アラート条件 |
|---------|------|---------|-------------|
| Collector プロセスヘルス | `health_check` エクステンション :13133 | HTTP 200 | Non-200 またはタイムアウト |
| OTLP レシーバー可用性 | HTTP GET `http://<collector>:4318` | 接続受付 | 接続拒否 |
| エクスポーターエラー数 | 内部メトリクス `otelcol_exporter_send_failed_log_records` | 0 | 5 分間 > 0 |
| エクスポーターキュー長 | 内部メトリクス `otelcol_exporter_queue_size` | < 80% 容量 | > 80% 容量 |
| バッチ送信レイテンシ | 内部メトリクス `otelcol_exporter_send_latency` | < 5s p99 | > 10s p99 |
| バックエンド固有レスポンスエラー | 内部メトリクス `otelcol_exporter_send_failed_*` エクスポーターごと | 0 | 持続的に > 0 |
| 最終成功エクスポートタイムスタンプ | `otelcol_exporter_sent_log_records` レートから導出 | レート > 0 | 5 分間レート = 0 |

### ヘルスチェック設定

```yaml
extensions:
  health_check:
    endpoint: 0.0.0.0:13133
    path: /
    check_collector_pipeline:
      enabled: true
      exporter_failure_threshold: 5

service:
  extensions: [health_check]
  telemetry:
    metrics:
      address: 0.0.0.0:8888
      level: detailed
```

### モニタリングスクリプト

```bash
#!/bin/bash
# Minimum health check script for cron or monitoring agent

COLLECTOR_HOST="${COLLECTOR_HOST:-localhost}"

# 1. Process health
if ! curl -sf "http://${COLLECTOR_HOST}:13133/" > /dev/null 2>&1; then
  echo "CRITICAL: Collector health check failed"
  exit 2
fi

# 2. OTLP receiver availability
if ! curl -sf -o /dev/null -w "%{http_code}" \
  "http://${COLLECTOR_HOST}:4318/v1/logs" 2>/dev/null | grep -q "405\|200"; then
  echo "WARNING: OTLP receiver not responding"
  exit 1
fi

# 3. Check internal metrics for exporter errors
FAILED=$(curl -sf "http://${COLLECTOR_HOST}:8888/metrics" 2>/dev/null \
  | grep 'otelcol_exporter_send_failed_log_records' \
  | awk '{sum += $2} END {print sum+0}')

if [ "${FAILED}" -gt 0 ]; then
  echo "WARNING: Exporter has ${FAILED} failed sends"
  exit 1
fi

echo "OK: Collector healthy"
exit 0
```

### ヘルスチェック用 CloudWatch Alarm

```yaml
CollectorHealthAlarm:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: otel-collector-unhealthy
    MetricName: HealthCheckStatus
    Namespace: ECS/ContainerInsights
    Statistic: Minimum
    Period: 60
    EvaluationPeriods: 3
    Threshold: 1
    ComparisonOperator: LessThanThreshold
    AlarmActions:
      - !Ref AlertSNSTopic
```

---

## ヘルスチェックとモニタリング

### ヘルスチェックエンドポイント

OTel Collector は Port 13133 でヘルスチェックエンドポイントを公開します。

```bash
# 基本ヘルスチェック
curl -f http://localhost:13133/

# レスポンス例
{"status":"Server available","upSince":"2026-05-18T14:02:03Z","uptime":"2h30m15s"}
```

### Collector 内部メトリクス

OTel Collector は Prometheus 形式の内部メトリクスを公開できます。

```yaml
# otel-collector-config.yaml に追加
service:
  telemetry:
    metrics:
      address: 0.0.0.0:8888
      level: detailed
```

主要メトリクス：

| メトリクス | 説明 | アラート閾値 |
|-----------|------|------------|
| `otelcol_exporter_sent_log_records` | 送信成功ログ数 | — |
| `otelcol_exporter_send_failed_log_records` | 送信失敗ログ数 | > 0 |
| `otelcol_receiver_accepted_log_records` | 受信ログ数 | — |
| `otelcol_receiver_refused_log_records` | 拒否ログ数 | > 0 |
| `otelcol_processor_batch_batch_send_size` | バッチサイズ | — |

### CloudWatch アラーム

CloudFormation テンプレートには以下のアラームが含まれています：

- **ErrorAlarm**: Lambda エラー率が閾値超過（5分間で5回以上）
- **ThrottleAlarm**: Lambda スロットリング検出
- **DLQAlarm**: Dead Letter Queue にメッセージ到着

## スケーリング考慮事項

### Lambda 同時実行数

| ログ量 | 推奨同時実行数 | メモリ |
|--------|--------------|--------|
| < 100 イベント/分 | デフォルト (1000) | 256 MB |
| 100-1000 イベント/分 | デフォルト (1000) | 512 MB |
| > 1000 イベント/分 | Reserved Concurrency 設定 | 1024 MB |

### OTel Collector スケーリング

Docker（ローカル/開発）:
- 単一インスタンスで十分
- CPU: 0.5 vCPU、メモリ: 512 MB

ECS Fargate（本番）:
- Auto Scaling: CPU 70% で水平スケール
- 最小: 1 タスク、最大: 4 タスク
- CPU: 0.5-1 vCPU、メモリ: 1-2 GB

### バッチプロセッサーチューニング

```yaml
processors:
  batch:
    timeout: 5s          # 低レイテンシ: 1s、高スループット: 10s
    send_batch_size: 1000  # 低レイテンシ: 100、高スループット: 5000
    send_batch_max_size: 5000
```

### Processor Ordering

本番環境では、プロセッサーリストで `memory_limiter` を `batch` の**前**に配置する。これにより、追加データをバッファリングする前にメモリ圧力を検出できる:

```yaml
processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
    spike_limit_mib: 128
  batch:
    timeout: 5s
    send_batch_size: 1000

service:
  pipelines:
    logs:
      processors: [memory_limiter, batch]  # memory_limiter FIRST
```

`memory_limiter` プロセッサーは Collector のメモリ使用量を監視し、ソフトリミットを超えた場合に新しいデータの受信を拒否してガベージコレクションをトリガーする。これにより OOM kill を防止する。

### Exporter Resilience: sending_queue and retry_on_failure

本番環境では、各エクスポーターにリトライとキュー設定を構成する:

```yaml
exporters:
  otlp_http/grafana:
    endpoint: ${env:GRAFANA_OTLP_ENDPOINT}
    headers:
      Authorization: "Basic ${env:GRAFANA_BASIC_AUTH}"
    sending_queue:
      enabled: true
      num_consumers: 10
      queue_size: 5000
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 300s
```

**主要な動作**:
- **In-memory queue** — 短時間のバックエンド障害を吸収（秒〜分単位）
- **Queue full** → 新しいデータはドロップされる（`otelcol_exporter_enqueue_failed_log_records` を監視）
- **Retry timeout exceeded**（`max_elapsed_time`）→ キュー内の最古データがドロップされる
- **Persistent storage**（ファイルベースキュー）— Collector 再起動に耐える。本番では storage エクステンション経由で構成:

```yaml
extensions:
  file_storage:
    directory: /var/lib/otelcol/queue

exporters:
  otlp_http/grafana:
    sending_queue:
      storage: file_storage
```

## 障害モードとリカバリ

### 障害パターン一覧

| 障害 | 影響 | 自動リカバリ | 手動対応 |
|------|------|------------|---------|
| OTel Collector ダウン | ログ配信停止 | Docker restart policy | コンテナ再起動 |
| バックエンド一時障害 | 該当バックエンドのみ停止 | Collector リトライ | — |
| バックエンド長期障害 | ログ損失の可能性 | DLQ へフォールバック | バックエンド復旧後に再送 |
| Lambda タイムアウト | 該当バッチのみ失敗 | EventBridge リトライ | DLQ 確認 |
| S3 AP アクセス失敗 | ログ読み取り不可 | Lambda リトライ | IAM/ネットワーク確認 |

### リカバリ手順

#### OTel Collector 再起動

```bash
# Docker
docker restart otel-collector

# ECS Fargate
aws ecs update-service --cluster fsxn-otel --service otel-collector --force-new-deployment
```

#### DLQ メッセージの再処理

```bash
# DLQ メッセージ数の確認
aws sqs get-queue-attributes \
  --queue-url <dlq-url> \
  --attribute-names ApproximateNumberOfMessages

# メッセージの再処理（Lambda を手動呼び出し）
aws sqs receive-message --queue-url <dlq-url> --max-number-of-messages 10
```

#### バックエンド障害時のフォールバック

1. Collector ログで送信失敗を確認
2. 障害バックエンドのエクスポーターを一時無効化
3. バックエンド復旧後にエクスポーターを再有効化
4. 障害期間中のログは DLQ から再送

## ログローテーションとリテンション

### CloudWatch Logs

| ロググループ | リテンション | 説明 |
|-------------|-----------|------|
| `/aws/lambda/fsxn-otel-integration-shipper` | 30 日 | Lambda 実行ログ |
| `/ecs/otel-collector` | 14 日 | Collector コンテナログ |

### Collector ログレベル

```yaml
service:
  telemetry:
    logs:
      level: info        # 本番: info、デバッグ: debug
      output_paths: ["stdout"]
```

### 監査ログ（S3）

| 設定 | 値 | 説明 |
|------|-----|------|
| ライフサイクルルール | 90 日後に Glacier | コスト最適化 |
| バージョニング | 有効 | 誤削除防止 |
| レプリケーション | オプション | DR 要件に応じて |

## 定期メンテナンス

### 週次

- [ ] CloudWatch アラーム状態の確認
- [ ] DLQ メッセージ数の確認（0 であること）
- [ ] Collector ヘルスチェックの確認

### 月次

- [ ] OTel Collector イメージの更新確認
- [ ] Lambda ランタイムの更新確認
- [ ] コスト分析（Lambda 実行時間、データ転送量）
- [ ] バックエンドのログ到着率の確認

### 四半期

- [ ] セキュリティパッチの適用
- [ ] IAM ポリシーの最小権限レビュー
- [ ] Secrets Manager のキーローテーション
- [ ] DR テスト（バックエンド切り替え）
