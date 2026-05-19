# 設定ガバナンスガイド: OTel Collector

## 設定ファイルオーナーシップ

| ファイル | オーナー | 承認要件 |
|---------|----------|----------|
| `otel-collector-config.yaml` | プラットフォーム / SRE チーム | PR レビュー + CI 検証 |
| `otel-collector-config-<env>.yaml` | プラットフォーム / SRE チーム | PR レビュー + CI 検証 |
| `.env` / `.env.<backend>` | セキュリティチーム | Secrets Manager ローテーション |
| `template-collector.yaml` (CFn) | インフラチーム | アーキテクチャレビュー |

## CI 検証

### CI パイプラインでの設定検証

```yaml
# .github/workflows/validate-otel-config.yaml
name: Validate OTel Collector Config
on:
  pull_request:
    paths:
      - 'integrations/otel-collector/otel-collector-config*.yaml'

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Pull OTel Collector image
        run: docker pull otel/opentelemetry-collector-contrib:0.152.0

      - name: Validate config syntax
        run: |
          docker run --rm \
            -v $(pwd)/integrations/otel-collector:/config \
            otel/opentelemetry-collector-contrib:0.152.0 \
            validate --config /config/otel-collector-config.yaml

      - name: Validate all config variants
        run: |
          for config in integrations/otel-collector/otel-collector-config*.yaml; do
            echo "Validating: $config"
            docker run --rm \
              -v $(pwd)/integrations/otel-collector:/config \
              otel/opentelemetry-collector-contrib:0.152.0 \
              validate --config /config/$(basename $config)
          done
```

### ローカル検証

```bash
# Validate before committing
docker run --rm \
  -v $(pwd):/config \
  otel/opentelemetry-collector-contrib:0.152.0 \
  validate --config /config/otel-collector-config.yaml
```

## 環境分離

### ディレクトリ構造

```
integrations/otel-collector/
├── otel-collector-config.yaml           # Default (dev/local)
├── otel-collector-config-staging.yaml   # Staging
├── otel-collector-config-prod.yaml      # Production
├── otel-collector-config-datadog.yaml   # Datadog backend
├── otel-collector-config-triple.yaml    # Triple backend
└── .env.example                         # Template (no secrets)
```

### 環境別の差異

| 設定 | Dev | Staging | Production |
|------|-----|---------|------------|
| Batch timeout | 1s | 5s | 5s |
| Batch size | 100 | 500 | 1000 |
| Log level | debug | info | info |
| Retry max | 1 | 3 | 5 |
| Health check | enabled | enabled | enabled |
| Internal metrics | enabled | enabled | enabled |
| Exporters | 1 (local) | 1-2 | All configured |

## シークレット管理ポリシー

### ルール

1. **シークレットをバージョン管理にコミットしない**
2. **すべてのバックエンド認証情報に Secrets Manager を使用**
3. **環境変数で参照**: `${env:SECRET_NAME}`
4. **最低 90 日ごとにローテーション**
5. **環境ごとにシークレットを分離**（dev/staging/prod）
6. **CloudTrail でアクセスを監査**

### シークレット命名規約

```
fsxn/otel/<environment>/<backend>/<credential-type>
```

例:
- `fsxn/otel/prod/grafana/basic-auth`
- `fsxn/otel/prod/honeycomb/api-key`
- `fsxn/otel/prod/datadog/api-key`

## 段階的ロールアウト / カナリア Collector

### カナリアデプロイ戦略

```
┌─────────────┐     ┌──────────────────┐
│   Lambda    │────▶│ Canary Collector  │──▶ Backend (5% traffic)
│  (all)      │     │ (new config)      │
│             │────▶│ Stable Collector  │──▶ Backend (95% traffic)
└─────────────┘     │ (current config)  │
                    └──────────────────┘
```

### ECS での実装

```yaml
# Deploy canary task with new config
CanaryService:
  Type: AWS::ECS::Service
  Properties:
    ServiceName: otel-collector-canary
    DesiredCount: 1
    TaskDefinition: !Ref CanaryTaskDefinition

# Stable service continues with current config
StableService:
  Type: AWS::ECS::Service
  Properties:
    ServiceName: otel-collector-stable
    DesiredCount: 2
    TaskDefinition: !Ref StableTaskDefinition
```

### カナリア検証ステップ

1. 新しい設定でカナリアをデプロイ（1 タスク）
2. トラフィックの 5-10% をカナリアにルーティング（加重ターゲットグループまたは DNS）
3. 30 分間モニタリング:
   - エクスポーターエラーカウント = 0
   - レイテンシがベースライン内
   - ドロップされたログなし
4. 正常な場合: カナリア設定を安定版に昇格
5. 異常な場合: カナリアを終了、ロールバック

## ロールバックプロセス

### 設定ロールバック

```bash
# 1. Identify last known good config
git log --oneline integrations/otel-collector/otel-collector-config-prod.yaml

# 2. Revert to previous version
git checkout <commit-hash> -- integrations/otel-collector/otel-collector-config-prod.yaml

# 3. Validate reverted config
docker run --rm \
  -v $(pwd)/integrations/otel-collector:/config \
  otel/opentelemetry-collector-contrib:0.152.0 \
  validate --config /config/otel-collector-config-prod.yaml

# 4. Deploy reverted config
aws ecs update-service \
  --cluster fsxn-otel \
  --service otel-collector \
  --force-new-deployment
```

### 自動ロールバックトリガー

```yaml
# CloudWatch Alarm → SNS → Lambda (auto-rollback)
ExporterErrorAlarm:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: otel-collector-exporter-errors
    MetricName: otelcol_exporter_send_failed_log_records
    Namespace: OTelCollector
    Statistic: Sum
    Period: 300
    EvaluationPeriods: 2
    Threshold: 100
    ComparisonOperator: GreaterThanThreshold
    AlarmActions:
      - !Ref RollbackSNSTopic
```

## 変更承認チェックリスト

Collector 設定変更をマージする前に:

- [ ] `otelcol validate --config` で設定を検証済み
- [ ] ハードコードされたシークレットなし（API キー、トークンを grep）
- [ ] 環境変数が Secrets Manager を参照
- [ ] バッチ設定がターゲット環境に適切
- [ ] エクスポーターエンドポイントがターゲット環境に正しい
- [ ] PR 説明にロールバック計画を記載
- [ ] カナリアデプロイを計画（本番変更の場合）
- [ ] 新しいエクスポーター追加時はモニタリングダッシュボードを更新
- [ ] 認証情報変更が関わる場合はセキュリティチームに通知
- [ ] プラットフォームチームから少なくとも 1 名のレビュアーが承認

## ルーティング変更の監査可能性

### Git 履歴を監査証跡として

```bash
# View routing change history
git log --all --oneline -- 'integrations/otel-collector/otel-collector-config*.yaml' \
  | grep -i "route\|export\|pipeline\|backend"
```

### 変更ドキュメントテンプレート

ルーティングを変更する各 PR には以下を含めること:

```markdown
## Routing Change Summary
- **What changed**: Added/removed/modified exporter for <backend>
- **Why**: <business justification>
- **Impact**: Logs now route to <new destination>
- **Rollback**: Revert commit <hash> and force-redeploy
- **Tested in**: staging / canary
```

## バックエンド別ルーティングポリシー

| バックエンド | データ種別 | 保持期間 | SLA | 備考 |
|-------------|-----------|----------|-----|------|
| Security SIEM | 削除、権限変更、アクセス失敗 | 1 年 | 99.9% | コンプライアンス要件 |
| Grafana Cloud | 全イベント（検索/アラート） | 30 日 | 99.5% | 運用可視性 |
| Honeycomb | 全イベント（探索） | 60 日 | 99.5% | 深い分析 |
| Archive (S3) | 全イベント（生データ） | 7 年 | 99.99% | コンプライアンス/法的保持 |
| 安価ストレージ | 読み取りイベント（大量） | 7 日 | 99% | コスト最適化 |

### ルーティング判断ツリー

```
Event arrives at Collector
  │
  ├── Is it a security event? (delete/permission/failed access)
  │     └── YES → Security SIEM + Grafana + Archive
  │
  ├── Is it a read event? (high volume)
  │     └── YES → Cheap storage only (or sampled to Grafana)
  │
  └── All other events
        └── Grafana + Honeycomb + Archive
```
