# 運用ランブック

## 4 レイヤーヘルスモデル

すべての運用シナリオはこのレイヤーモデルで診断する:

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1: Producer (Lambda)                                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Generates OTLP logs from ONTAP telemetry sources        │    │
│  │  Monitor: CloudWatch Lambda metrics                      │    │
│  └─────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2: Collector Process                                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Receives, processes, and routes OTLP logs               │    │
│  │  Monitor: health_check + internal metrics                │    │
│  └─────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────┤
│  Layer 3: Exporter                                               │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Delivers logs to each backend                           │    │
│  │  Monitor: otelcol_exporter_* metrics                     │    │
│  └─────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────┤
│  Layer 4: Backend                                                │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Ingests, indexes, and serves queries                    │    │
│  │  Monitor: Backend-specific dashboards                    │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

| レイヤー | 監視対象 | 主要メトリクス |
|---------|---------|--------------|
| Producer (Lambda) | エラー、実行時間、リトライ回数 | CloudWatch Lambda メトリクス |
| Collector プロセス | OTLP レシーバー、メモリ、CPU | health_check + 内部メトリクス |
| Exporter | エラー数、リトライ数、キュー長 | otelcol_exporter_* メトリクス |
| Backend | 最終成功取り込み、イベント数、レイテンシ | バックエンド固有ダッシュボード |

---

## ランブック 1: Collector 利用不可

### 症状
- Lambda が OTLP 送信時に接続拒否またはタイムアウトを受信
- ヘルスチェックエンドポイント（`http://<collector>:13133/`）が non-200 またはタイムアウト
- すべてのバックエンドに新しいログが表示されない

### 検出
- CloudWatch Alarm: `otel-collector-unhealthy`
- Lambda エラーログ: `ConnectionRefusedError` または `TimeoutError`
- ECS タスクステータス: STOPPED または PENDING

### 影響
- **すべてのバックエンド**が新しいログの受信を停止
- Lambda リトライ枯渇 → イベントが DLQ に送信
- データギャップ期間 = 復旧までの時間

### 解決手順

```bash
# 1. Check ECS task status
aws ecs describe-services \
  --cluster fsxn-otel \
  --services otel-collector \
  --query "services[0].{desired:desiredCount,running:runningCount,events:events[:3]}"

# 2. Check task stopped reason
aws ecs list-tasks --cluster fsxn-otel --service-name otel-collector --desired-status STOPPED
aws ecs describe-tasks --cluster fsxn-otel --tasks <task-arn> \
  --query "tasks[0].{reason:stoppedReason,exitCode:containers[0].exitCode}"

# 3. Force new deployment
aws ecs update-service \
  --cluster fsxn-otel \
  --service otel-collector \
  --force-new-deployment

# 4. Verify recovery
watch -n 5 'curl -sf http://<collector>:13133/ && echo OK || echo FAIL'

# 5. Reprocess DLQ after recovery
aws sqs get-queue-attributes \
  --queue-url <dlq-url> \
  --attribute-names ApproximateNumberOfMessages
```

### 予防策
- 指数バックオフ付き ECS 再起動ポリシー
- 高可用性のためのマルチ AZ デプロイ
- 再起動に耐える永続キュー（file_storage エクステンション）

---

## ランブック 2: バックエンドエクスポーター障害（単一バックエンド）

### 症状
- 1 つのバックエンドがログ受信を停止; 他は正常に継続
- Collector 内部メトリクスが特定バックエンドのエクスポーターエラーを表示
- Lambda エラーなし（Collector は正常）

### 検出
- メトリクス: `otelcol_exporter_send_failed_log_records{exporter="otlp_http/<backend>"}` > 0
- メトリクス: `otelcol_exporter_queue_size{exporter="otlp_http/<backend>"}` 増加中
- バックエンド固有ダッシュボードにギャップ表示

### 影響
- **単一バックエンド**のみ影響; 他のバックエンドは影響なし
- キューが短時間の障害を吸収（分単位）
- 長期障害 → キュー満杯 → そのバックエンドのみデータドロップ

### 解決手順

```bash
# 1. Identify failing exporter
curl -sf http://<collector>:8888/metrics | \
  grep 'otelcol_exporter_send_failed_log_records'

# 2. Check exporter queue status
curl -sf http://<collector>:8888/metrics | \
  grep 'otelcol_exporter_queue_size'

# 3. Check backend status (vendor-specific)
# Datadog: https://status.datadoghq.com/
# Grafana: https://status.grafana.com/
# Honeycomb: https://status.honeycomb.io/

# 4. If backend is down, wait for recovery (queue handles short outages)
# If backend is up but rejecting, check credentials:
aws secretsmanager get-secret-value \
  --secret-id fsxn-otel-<backend>-api-key \
  --query "VersionIdsToStages"

# 5. If credentials expired, rotate and restart
aws ecs update-service \
  --cluster fsxn-otel \
  --service otel-collector \
  --force-new-deployment
```

### 予防策
- エクスポーターごとの `sending_queue` に十分な `queue_size` を設定
- 適切な `max_elapsed_time` で `retry_on_failure` を設定
- バックエンドステータスページの監視
- 認証情報ローテーションアラート（有効期限 30 日前）

---

## ランブック 3: キュー増大 / バックプレッシャー

### 症状
- エクスポーターキューサイズが着実に増加
- Collector メモリ使用量が上昇
- `memory_limiter` がトリガーされる可能性（レシーバーがデータ受信を拒否開始）

### 検出
- メトリクス: `otelcol_exporter_queue_size` > 設定 `queue_size` の 80%
- メトリクス: `otelcol_processor_refused_log_records` > 0（memory_limiter アクティブ）
- CloudWatch: ECS タスクメモリ使用率 > 80%

### 影響
- キュー満杯時: そのエクスポーターの新しいイベントがドロップ
- memory_limiter トリガー時: Lambda が 503 を受信 → リトライ → DLQ
- 複数エクスポーターが同時にキューイングするとカスケード効果の可能性

### 解決手順

```bash
# 1. Identify which exporter(s) are queuing
curl -sf http://<collector>:8888/metrics | \
  grep 'otelcol_exporter_queue_size'

# 2. Check if backend is slow or down
curl -sf http://<collector>:8888/metrics | \
  grep 'otelcol_exporter_send_latency'

# 3. If backend is slow: temporarily increase batch timeout
# Edit config and redeploy (or use config reload if supported)

# 4. If sustained: scale Collector horizontally
aws ecs update-service \
  --cluster fsxn-otel \
  --service otel-collector \
  --desired-count 2

# 5. If critical: temporarily disable non-essential exporters
# Remove the slow exporter from pipeline, redeploy
# Reprocess missed data from DLQ after recovery
```

### 予防策
- 想定バースト期間 × イベントレートに基づいて `queue_size` を設定
- 適切なリミットで `memory_limiter` を設定
- CPU/メモリ閾値に基づくオートスケーリング
- クリティカルなエクスポーターには永続キュー（`file_storage`）

---

## ランブック 4: Lambda が Collector に到達不可

### 症状
- Lambda ログに Collector エンドポイントへの接続タイムアウトが表示
- Lambda 実行時間が最大値（タイムアウト）
- DLQ にイベントが蓄積

### 検出
- CloudWatch: Lambda Duration = タイムアウト値
- CloudWatch: Lambda Errors 増加
- Lambda ログ: `ConnectTimeoutError: Connect timeout on endpoint URL`

### 影響
- テレメトリがどのバックエンドにも配信されない
- DLQ にイベントが蓄積（修正後に再処理可能）
- 監査ログ処理が遅延

### 解決手順

```bash
# 1. Verify Collector is running and healthy
curl -sf http://<collector>:13133/ && echo "Collector OK" || echo "Collector DOWN"

# 2. Check security group rules
aws ec2 describe-security-groups \
  --group-ids <collector-sg-id> \
  --query "SecurityGroups[0].IpPermissions[?ToPort==\`4318\`]"

# 3. Check VPC connectivity (if Lambda is in VPC)
# Ensure Lambda subnet can route to Collector subnet
aws ec2 describe-route-tables \
  --filters "Name=association.subnet-id,Values=<lambda-subnet-id>"

# 4. Check Collector endpoint configuration in Lambda env vars
aws lambda get-function-configuration \
  --function-name fsxn-otel-integration-shipper \
  --query "Environment.Variables.OTEL_COLLECTOR_ENDPOINT"

# 5. If DNS issue: verify service discovery or endpoint resolution
# If network issue: check NACLs, route tables, NAT Gateway

# 6. After fix: reprocess DLQ
aws lambda invoke \
  --function-name fsxn-otel-dlq-reprocessor \
  --payload '{"source": "manual"}' \
  /dev/null
```

### 予防策
- 可能な限り Lambda と Collector を同じ VPC/サブネットに配置
- Lambda タイムアウト前にヘルスチェックアラームがトリガー
- Lambda コールドスタート時のエンドポイント接続テスト（早期失敗）
- ネットワークデバッグ用に VPC Flow Logs を有効化

---

## ランブック 5: 単一バックエンドのみデータ欠損

### 症状
- 1 つのバックエンドが同じ時間範囲で他より少ないイベントを表示
- Collector メトリクスにエクスポーターエラーなし
- 他のバックエンドには完全なデータあり

### 検出
- クロスバックエンドイベント数比較（日次照合）
- バックエンド固有クエリが期待より少ない結果を返す
- Collector メトリクスに対応するエクスポーターエラーなし

### 影響
- 単一バックエンドのデータが不完全
- そのバックエンドのアラートやダッシュボードに影響する可能性
- 影響を受けたバックエンドが監査に使用されている場合、コンプライアンスリスク

### 解決手順

```bash
# 1. Check if filtering is applied per-exporter
grep -A 10 'processors:' otel-collector-config.yaml

# 2. Check backend-specific timestamp rejection
# Grafana/Loki: events older than reject_old_samples_max_age are silently dropped
# Datadog: events older than 18 hours are rejected

# 3. Check for backend-side rate limiting
# Look for HTTP 429 responses in Collector debug logs
docker logs otel-collector 2>&1 | grep -i "429\|rate.limit\|too.many"

# 4. Check backend ingestion pipeline
# Verify index/dataset exists and is accepting data
# Check backend-side processing rules (exclusion filters, sampling)

# 5. If timestamp issue: adjust Lambda to use current time as fallback
# If rate limit: reduce batch size or add jitter

# 6. Backfill missing data from S3 source
# Re-invoke Lambda for the affected time range
```

### 予防策
- 各バックエンドのタイムスタンプ受付ウィンドウを理解
- バックエンド側の取り込みメトリクスを監視
- 全バックエンドにわたる日次自動照合
- 取り込み時刻ではなく ONTAP タイムスタンプを主要イベント時刻として使用

---

## ランブック 6: 設定ロールバックが必要

### 症状
- 最近の設定変更が予期しない動作を引き起こした
- デプロイ後にイベントが正しくルーティングされない
- 設定更新後にエクスポーターエラーが開始

### 検出
- 相関: 最後のデプロイ後に問題が開始
- Git ログに最近の設定変更あり
- Collector ログに設定検証エラー

### 影響
- 変更内容に依存: ルーティングエラー、データ欠損、または完全障害
- 期間 = 検出時間 + ロールバック時間

### 解決手順

```bash
# 1. Identify the problematic commit
git log --oneline -5 -- \
  'integrations/otel-collector/otel-collector-config*.yaml'

# 2. Revert to last known good config
git revert <problematic-commit>
# OR
git checkout <last-good-commit> -- \
  'integrations/otel-collector/otel-collector-config.yaml'

# 3. Validate the reverted config
docker run --rm \
  -v $(pwd)/integrations/otel-collector/otel-collector-config.yaml:/etc/otelcol/config.yaml \
  otel/opentelemetry-collector-contrib:0.152.0 \
  validate --config /etc/otelcol/config.yaml

# 4. Deploy the rollback
git commit -m "fix: rollback Collector config to last known good state"
git push origin main
# CI/CD deploys automatically, or:
aws ecs update-service \
  --cluster fsxn-otel \
  --service otel-collector \
  --force-new-deployment

# 5. Verify recovery
curl -sf http://<collector>:13133/ && echo "Healthy"
curl -sf http://<collector>:8888/metrics | \
  grep 'otelcol_exporter_send_failed_log_records'

# 6. Reprocess any DLQ messages from the incident window
```

### 予防策
- デプロイ前の CI 設定検証（`validate` コマンド）
- 段階的ロールアウト（カナリア → フル）
- 設定変更に PR レビュー + 承認を必須化
- ヘルスチェック失敗時の自動ロールバック（ECS デプロイメントサーキットブレーカー）

---

## ランブック 7: 緊急 Direct-Send バイパス

### 症状
- Collector がダウンし、迅速に復旧できない
- クリティカルなテレメトリ（監査ログ、セキュリティイベント）の流れを継続する必要がある
- DLQ が満杯に近づき、リテンション制限に達しそう

### 検出
- Collector が 30 分以上利用不可
- DLQ メッセージ数が許容閾値を超えて増加
- ビジネスクリティカルな監視が盲目状態

### 影響
- マルチバックエンドファンアウトの一時的喪失
- 単一バックエンドがデータを受信（優先度で選択）
- Collector 復旧まで設定の乖離

### 解決手順

```bash
# 1. Identify the highest-priority backend
# Typically: SIEM for security events, primary observability for audit

# 2. Update Lambda environment to bypass Collector
aws lambda update-function-configuration \
  --function-name fsxn-otel-integration-shipper \
  --environment "Variables={
    DELIVERY_MODE=direct,
    DIRECT_SEND_ENDPOINT=https://<backend-endpoint>,
    DIRECT_SEND_API_KEY_SECRET_ARN=arn:aws:secretsmanager:<region>:123456789012:secret:fsxn-<backend>-api-key
  }"

# 3. Verify direct send is working
aws logs tail /aws/lambda/fsxn-otel-integration-shipper --since 5m \
  | grep -i "direct.send\|success\|error"

# 4. Process DLQ backlog
aws lambda invoke \
  --function-name fsxn-otel-dlq-reprocessor \
  --payload '{"mode": "direct", "target": "<backend>"}' \
  /dev/null

# 5. After Collector recovery: revert to normal mode
aws lambda update-function-configuration \
  --function-name fsxn-otel-integration-shipper \
  --environment "Variables={
    DELIVERY_MODE=collector,
    OTEL_COLLECTOR_ENDPOINT=http://<collector>:4318
  }"

# 6. Reconcile: identify events that only went to one backend
# Backfill other backends from S3 source if needed
```

### 予防策
- Lambda が環境変数切り替えでデュアルモード（collector + direct）をサポート
- Secrets Manager に事前設定された direct-send 認証情報
- 四半期ごとのランブックリハーサル
- Collector HA デプロイ（マルチ AZ、オートスケーリング）

---

## クイックリファレンス: 診断フロー

```
Issue detected
     │
     ▼
┌─────────────────────────────────┐
│ Is Collector health check OK?   │
└──────────┬──────────────────────┘
           │
     ┌─────┴─────┐
     │           │
    YES          NO → Runbook 1 (Collector Unavailable)
     │
     ▼
┌─────────────────────────────────┐
│ Are all exporters sending OK?   │
└──────────┬──────────────────────┘
           │
     ┌─────┴─────┐
     │           │
    YES          NO → Runbook 2 (Backend Failing)
     │                  or Runbook 3 (Queue Growing)
     ▼
┌─────────────────────────────────┐
│ Is Lambda sending to Collector? │
└──────────┬──────────────────────┘
           │
     ┌─────┴─────┐
     │           │
    YES          NO → Runbook 4 (Lambda Cannot Reach)
     │
     ▼
┌─────────────────────────────────┐
│ Is data present in all backends?│
└──────────┬──────────────────────┘
           │
     ┌─────┴─────┐
     │           │
    YES          NO → Runbook 5 (Missing in One Backend)
     │
     ▼
  System healthy ✅
```
