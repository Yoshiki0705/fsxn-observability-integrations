# PoC チェックリスト: OTel Collector 統合

## 5 フェーズ PoC 構造

```
Phase 1          Phase 2              Phase 3             Phase 4        Phase 5
Direct Send  →  Introduce Collector  →  Parallel Delivery  →  Compare  →  Cut Over
(baseline)      (shadow mode)           (dual write)         (validate)    (production)
```

## 前提条件チェックリスト

PoC 開始前に、すべての前提条件を確認すること:

- [ ] FSx ONTAP 監査ログが有効化され、S3 にログが出力されている
- [ ] S3 Access Point が設定済みで Lambda からアクセス可能
- [ ] 少なくとも 1 つのバックエンドアカウントがプロビジョニング済み（Grafana/Honeycomb/Datadog）
- [ ] ローカル Collector テスト用の Docker 環境が利用可能
- [ ] Lambda + ECS/Fargate デプロイ権限を持つ AWS 認証情報
- [ ] ネットワークパス確認済み: Lambda → Collector エンドポイント（ポート 4318）
- [ ] バックエンド認証情報の Secrets Manager シークレットが作成済み
- [ ] ベースラインイベント量を測定済み（events/day）
- [ ] ステークホルダーと成功基準を合意済み

## Phase 1: Direct Send（ベースライン）

**目標**: 既存の Direct Send Lambda でベースラインメトリクスを確立する。

### 成功基準

- [ ] Lambda がプライマリバックエンドにログを正常配信
- [ ] ベースラインレイテンシを測定（Lambda 呼び出し → バックエンド到着）
- [ ] ベースラインエラー率を記録（< 0.1% 目標）
- [ ] 1 日あたりのイベント数を文書化
- [ ] バックエンドに必要な属性がすべて存在

### アクション

```bash
# Measure baseline delivery latency
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=fsxn-<vendor>-log-shipper \
  --start-time $(date -u -v-1d +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Average p99
```

## Phase 2: Collector 導入（シャドウモード）

**目標**: 本番トラフィックに影響を与えずに OTel Collector をデプロイする。

### 成功基準

- [ ] Collector ヘルスチェックが通過（`curl http://<collector>:13133/`）
- [ ] Collector がポート 4318 で OTLP ペイロードを受信
- [ ] Collector が少なくとも 1 つのバックエンドにエクスポート成功
- [ ] 既存の Direct Send Lambda に影響なし

### アクション

```bash
# Deploy Collector (ECS Fargate)
aws cloudformation deploy \
  --template-file template-collector.yaml \
  --stack-name fsxn-otel-collector-poc \
  --capabilities CAPABILITY_IAM \
  --region ap-northeast-1

# Verify health
curl -f http://<collector-endpoint>:13133/

# Send test payload
bash scripts/generate-otlp-payload.sh --output /tmp/test.json
curl -X POST http://<collector-endpoint>:4318/v1/logs \
  -H "Content-Type: application/json" \
  -d @/tmp/test.json
```

## Phase 3: 並行配信（デュアルライト）

**目標**: Direct Send と Collector パスを同時に実行する。

### 成功基準

- [ ] 両パスが同一イベントをそれぞれのバックエンドに配信
- [ ] 単一パス内で重複イベントなし
- [ ] Collector パスのレイテンシが Direct Send ベースラインの 2 倍以内
- [ ] 24 時間の観測期間でデータロスゼロ
- [ ] Collector エクスポーターエラーカウント = 0

### アクション

```bash
# Deploy OTel Lambda alongside existing Lambda
aws cloudformation deploy \
  --template-file integrations/otel-collector/template.yaml \
  --stack-name fsxn-otel-integration-poc \
  --parameter-overrides \
    OtlpEndpoint=http://<collector-endpoint>:4318 \
    S3BucketName=<audit-bucket> \
  --capabilities CAPABILITY_IAM

# Configure EventBridge to trigger both Lambdas
# (existing rule continues, new rule added for OTel Lambda)
```

## Phase 4: 比較（検証）

**目標**: Direct Send と Collector パス間のデータパリティを確認する。

### データパリティチェック方法

```bash
# 1. Query event count from direct-send backend (e.g., Datadog)
#    Filter: service:fsxn-audit, last 24h → count

# 2. Query event count from Collector backend (e.g., Grafana)
#    Filter: {job="fsxn-audit"}, last 24h → count

# 3. Compare counts (tolerance: ±1%)
```

### 成功基準

- [ ] パス間のイベント数差異 < 1%
- [ ] Collector 配信ログに必要な属性がすべて存在
- [ ] タイムスタンプ精度が 1 秒以内
- [ ] 属性マッピングエラーなし
- [ ] Collector パスの p99 レイテンシが許容範囲内（< 10s エンドツーエンド）

### 比較チェックリスト

| メトリクス | Direct Send | Collector パス | 合格? |
|-----------|-------------|----------------|-------|
| Events/day | ___ | ___ | ±1% |
| p50 レイテンシ | ___ ms | ___ ms | < 2x |
| p99 レイテンシ | ___ ms | ___ ms | < 3x |
| エラー率 | ___ % | ___ % | < 0.1% |
| 属性完全性 | ___ / ___ | ___ / ___ | 100% |

## Phase 5: カットオーバー（本番）

**目標**: 本番トラフィックを Collector パスに切り替える。

### 成功基準

- [ ] すべての本番トラフィックが Collector 経由
- [ ] Direct Send Lambda が無効化（削除ではない）
- [ ] 48 時間以上の安定配信をモニタリングで確認
- [ ] ロールバックがテスト済みで文書化済み
- [ ] 旧 Lambda は削除前に 14 日間保持

### アクション

```bash
# 1. Disable direct-send EventBridge rule
aws events disable-rule \
  --name fsxn-<vendor>-s3-trigger \
  --region ap-northeast-1

# 2. Monitor Collector path for 48 hours
# 3. If stable, proceed to cleanup
# 4. If issues, execute rollback
```

## ロールバック手順

### 即時ロールバック（< 5 分）

```bash
# 1. Re-enable direct-send rule
aws events enable-rule \
  --name fsxn-<vendor>-s3-trigger \
  --region ap-northeast-1

# 2. Disable OTel Lambda rule
aws events disable-rule \
  --name fsxn-otel-s3-trigger \
  --region ap-northeast-1

# 3. Verify direct-send Lambda is processing
aws logs tail /aws/lambda/fsxn-<vendor>-log-shipper --since 2m
```

### 完全ロールバック

```bash
# 1. Re-enable direct-send (as above)
# 2. Delete OTel stack (optional, can keep for retry)
aws cloudformation delete-stack \
  --stack-name fsxn-otel-integration-poc

# 3. Document failure reason for post-mortem
```

## Go/No-Go 基準

| 基準 | 閾値 | 測定値 | Go? |
|------|------|--------|-----|
| データパリティ（イベント数） | ±1% | ___ | ☐ |
| エンドツーエンドレイテンシ（p99） | < 10s | ___ | ☐ |
| エラー率 | < 0.1% | ___ | ☐ |
| Collector 稼働率（7 日間） | > 99.9% | ___ | ☐ |
| 属性完全性 | 100% | ___ | ☐ |
| ロールバックテスト済み | Yes | ___ | ☐ |
| ステークホルダー承認 | Yes | ___ | ☐ |
| コスト差分が許容範囲 | < 20% 増加 | ___ | ☐ |

**判断**: すべての基準が "Go" であることが本番カットオーバーの条件。1 つでも "No-Go" がある場合は、再試行前に是正が必要。
